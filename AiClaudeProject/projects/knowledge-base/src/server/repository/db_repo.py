"""
DBRepository - SQLite 数据库数据访问实现

从 SQLite 数据库读取结构化数据（模块、关键词、同义词、反馈、统计）。
文档内容（knowledge、FAQ、raw-docs）仍从文件系统读取。
"""

import json
import re
from sqlalchemy import create_engine, text
from dataclasses import asdict
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from .base import (
    Document, FAQ, ModuleInfo, Report, KnowledgeRepository
)
from .dept_mapping import get_dept_path, get_submodule_path

# 路径常量
HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent.parent.parent  # knowledge-base/
DATA_DIR = PROJECT_DIR / "data"
RUNTIME_DIR = PROJECT_DIR / "runtime"
DB_PATH = RUNTIME_DIR / "knowledge.db"

def _get_db_url():
    """获取数据库 URL

    优先使用 config.py 已加载的环境变量（Web 服务启动时 config.py 最先 import）。
    兜底：若 config.py 未被导入（如 CLI 直接运行 search_engine.py），自动加载 .env。
    """
    import os
    # 兜底：config.py 未加载时，确保 .env 中的 DATABASE_URL_SYNC 可用
    if not os.getenv("DATABASE_URL_SYNC") and not os.getenv("_KB_ENV_LOADED"):
        _ensure_env_loaded()
    pg_url = os.getenv("DATABASE_URL_SYNC", "")
    if pg_url and "postgresql" in pg_url:
        return pg_url
    return f"sqlite:///{DB_PATH}"


def _ensure_env_loaded():
    """兜底加载 .env（当 config.py 未被先导入时使用，如 CLI 直接运行 search_engine.py）"""
    import os
    env_file = PROJECT_DIR / ".env"
    if not env_file.exists():
        return
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and (key not in os.environ or val):
                os.environ[key] = val
    os.environ["_KB_ENV_LOADED"] = "1"  # 标记已加载，避免重复

# 状态映射: 旧 TEXT → 新 INT
STATUS_MAP = {"active": 1, "outdated": 2, "deprecated": 3, "draft": 0}
STATUS_REVERSE = {1: "active", 2: "outdated", 3: "deprecated", 0: "draft"}


class DBRepository(KnowledgeRepository):
    """数据库 + 文件系统混合数据访问"""

    def __init__(self, db_url=None):
        self.db_url = db_url or _get_db_url()
        self.engine = create_engine(
            self.db_url, echo=False,
            pool_size=5,           # 常驻连接数（1 worker 足够）
            max_overflow=3,        # 峰值最多 8 个连接
            pool_recycle=1800,     # 30 分钟回收（防 PG 8h 空闲断连）
            pool_pre_ping=True,    # 连接取用前检测存活
            pool_timeout=10,       # 等连接最多 10s
        )
        self._init_schema()

    def _init_schema(self):
        """初始化数据库表结构

        - PostgreSQL：Schema 由 config/migrations/ 管理（psql 应用），此处不做任何建表
        - SQLite（回退模式）：执行 config/schema.sql 建表
        """
        if "postgresql" in self.db_url:
            return
        schema_file = PROJECT_DIR / "config" / "schema.sql"
        if schema_file.exists():
            schema_sql = schema_file.read_text(encoding="utf-8")
            with self.engine.connect() as conn:
                for stmt in schema_sql.split(";"):
                    stmt = stmt.strip()
                    if stmt and not stmt.startswith("--"):
                        try:
                            conn.execute(text(stmt))
                        except Exception:
                            pass
                conn.commit()

    def _execute(self, sql, params=None):
        """执行查询并返回字典列表"""
        sql, params = self._convert_params(sql, params)
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params) if params else conn.execute(text(sql))
            return [dict(row._mapping) for row in result]

    def _execute_one(self, sql, params=None):
        """执行查询并返回单行字典"""
        sql, params = self._convert_params(sql, params)
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params) if params else conn.execute(text(sql))
            row = result.fetchone()
            return dict(row._mapping) if row else None

    def _execute_write(self, sql, params=None):
        """执行写操作并提交，自动转换 SQLite 语法到 PostgreSQL"""
        sql, params = self._convert_params(sql, params)
        sql = self._adapt_sql(sql)
        with self.engine.connect() as conn:
            conn.execute(text(sql), params) if params else conn.execute(text(sql))
            conn.commit()

    @staticmethod
    def _adapt_sql(sql):
        """将 SQLite 特有语法转为 PostgreSQL 兼容语法"""
        import re
        # INSERT OR REPLACE → INSERT ... ON CONFLICT ... DO UPDATE
        m = re.match(r"INSERT OR REPLACE INTO (\w+) \((.+?)\) VALUES \((.+?)\)", sql, re.IGNORECASE)
        if m:
            table, cols, vals = m.group(1), m.group(2), m.group(3)
            col_list = [c.strip() for c in cols.split(",")]
            # 用第一个非 id 列作为冲突检测列，通常需要 UNIQUE 约束
            # 对于 search_counter: key 是 UNIQUE
            conflict_col = col_list[0]  # 默认第一列
            if table == "search_counter":
                conflict_col = "key"
            elif "keywords" in table:
                conflict_col = "keyword"
            set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in col_list if c != conflict_col)
            return f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT ({conflict_col}) DO UPDATE SET {set_clause}"

        # INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
        m = re.match(r"INSERT OR IGNORE INTO (\w+) (.+)", sql, re.IGNORECASE)
        if m:
            table, rest = m.group(1), m.group(2)
            # 找到冲突列：对于 keywords_v2 是 keyword，对于 keywords 没有 UNIQUE 约束
            conflict_col = "keyword" if "keywords" in table else "id"
            return f"INSERT INTO {table} {rest} ON CONFLICT ({conflict_col}) DO NOTHING"

        return sql

    @staticmethod
    def _convert_params(sql, params):
        """将 ? 占位符转换为 SQLAlchemy 的 :param_N 命名参数。
        只替换不在引号内的 ?，避免误替换字符串字面量中的 ? 字符。
        """
        if not params:
            return sql, None
        if isinstance(params, dict):
            return sql, params
        if isinstance(params, (list, tuple)):
            named = {}
            # 使用正则替换不在引号内的 ? 占位符
            result_sql = []
            in_quote = False
            param_idx = 0
            i = 0
            while i < len(sql):
                ch = sql[i]
                if ch == "'" and (i == 0 or sql[i-1] != '\\'):
                    in_quote = not in_quote
                    result_sql.append(ch)
                elif ch == '?' and not in_quote and param_idx < len(params):
                    name = f"p{param_idx}"
                    result_sql.append(f":{name}")
                    named[name] = params[param_idx]
                    param_idx += 1
                else:
                    result_sql.append(ch)
                i += 1
            return ''.join(result_sql), named
        return sql, {"p0": params}

    # ══════ Modules ══════

    def get_all_modules(self) -> dict[str, ModuleInfo]:
        """从数据库读取所有模块（批量预加载菜单/关键词，消除 N+1）"""
        from collections import defaultdict as _dd

        # 1. 主查询
        rows = self._execute("""
            SELECT m.*, d.name as dept_name, p.name as product_name,
                   pl.name as product_line_name
            FROM modules m
            LEFT JOIN departments d ON m.department_id = d.id
            LEFT JOIN products p ON m.product_id = p.id
            LEFT JOIN product_lines pl ON p.product_line_id = pl.id
        """)

        # 2. 批量预加载菜单（1 条 SQL）
        menu_rows = self._execute("SELECT module_id, level1, level2, level3 FROM module_menus")
        menus_by_mod = _dd(list)
        for mr in menu_rows:
            for level in [mr["level1"], mr["level2"], mr["level3"]]:
                if level and level != "-":
                    menus_by_mod[mr["module_id"]].append(level)

        # 3. 批量预加载关键词（1 条 SQL）
        kw_rows = self._execute("""
            SELECT DISTINCT km.module_id, kw.keyword
            FROM keyword_mappings km
            JOIN keywords_v2 kw ON kw.id = km.keyword_id
            WHERE kw.is_deleted = FALSE AND km.is_deleted = FALSE
        """)
        kws_by_mod = _dd(list)
        for kr in kw_rows:
            kws_by_mod[kr["module_id"]].append(kr["keyword"])

        # 4. 组装
        modules = {}
        for row in rows:
            mid = row["id"]
            modules[row["name"]] = asdict(ModuleInfo(
                name=row["name"],
                path=row["path"] or "",
                dept=row["dept_name"] or "",
                domain=row["business_domain"] or "",
                product=row["product_name"] or "",
                keywords=kws_by_mod.get(mid, []),
                menus=menus_by_mod.get(mid, []),
            ))

        return modules

    # ══════ 名称 → ID 解析（部门限定优先） ══════

    def resolve_dept_id(self, dept: str):
        """按部门名称解析 departments.id（无匹配返回 None）"""
        if not dept:
            return None
        row = self._execute_one(
            "SELECT id FROM departments WHERE name = ? LIMIT 1", (dept.strip(),)
        )
        return row["id"] if row else None

    def resolve_module_id(self, module: str, dept_name: str = ""):
        """按模块名称解析 modules.id。

        提供部门名时优先「部门+名称」联合匹配，避免同名模块跨部门时
        LIMIT 1 取错记录；modules 表部门为旧组织架构，无部门匹配时
        回退名称唯一查找（保持历史行为）。
        """
        if not module:
            return None
        dept_id = self.resolve_dept_id(dept_name) if dept_name else None
        if dept_id:
            row = self._execute_one(
                "SELECT id FROM modules WHERE name = ? AND department_id = ? LIMIT 1",
                (module.strip(), dept_id)
            )
            if row:
                return row["id"]
        row = self._execute_one(
            "SELECT id FROM modules WHERE name = ? LIMIT 1", (module.strip(),)
        )
        return row["id"] if row else None

    # ══════ Keywords v2 (ID-based) ══════

    def get_all_keywords_v2(self) -> dict[str, list[dict]]:
        """从新表加载关键词索引，返回兼容 keyword_map 格式"""
        keyword_map = defaultdict(list)
        now = datetime.now().isoformat()
        rows = self._execute("""
            SELECT kw.id as keyword_id, kw.keyword,
                   km.id as mapping_id, km.module_id, km.department_id,
                   km.department, km.domain, km.kb_path, km.note,
                   m.name as module_name,
                   d.name as dept_name
            FROM keyword_mappings km
            JOIN keywords_v2 kw ON km.keyword_id = kw.id
            LEFT JOIN modules m ON km.module_id = m.id
            LEFT JOIN departments d ON km.department_id = d.id
            WHERE kw.is_deleted = FALSE AND km.is_deleted = FALSE
        """)
        for row in rows:
            keyword_map[row["keyword"]].append({
                "mapping_id": row["mapping_id"],
                "keyword_id": row["keyword_id"],
                "module": row["module_name"] or "",
                "module_id": row["module_id"] or 0,
                "dept": row["dept_name"] or row["department"] or "",
                "dept_id": row["department_id"] or 0,
                "domain": row["domain"] or "",
                "kb_path": row["kb_path"] or "",
                "note": row["note"] or "",
            })
        return dict(keyword_map)

    def add_keyword(self, keyword: str, module_id: int, dept_id: int, dept: str = "",
                    kb_path: str = "") -> dict:
        """新增关键词+映射，返回 {keyword_id, mapping_id}

        - 关键词实体已存在（含软删除）时复活并刷新时间
        - 存活映射存在时复活该映射而非新增重复行（部分唯一索引 uq_km_kw_mod_active）
        """
        now = datetime.now().isoformat()
        # 外键字段 0 → NULL，避免违反外键约束
        module_id = module_id or None
        dept_id = dept_id or None
        # 关键词已存在（含软删除）时复活并刷新时间
        self._execute_write(
            "INSERT INTO keywords_v2 (keyword, created_at, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (keyword) DO UPDATE SET is_deleted = FALSE, updated_at = ?",
            (keyword, now, now, now)
        )
        row = self._execute_one("SELECT id FROM keywords_v2 WHERE keyword = ?", (keyword,))
        keyword_id = row["id"] if row else None
        if not keyword_id:
            return {"error": "关键词写入失败"}
        # 映射：复活式 upsert（部分唯一索引仅约束存活行；module_id 为 NULL 时不冲突，允许共存）
        try:
            self._execute_write(
                "INSERT INTO keyword_mappings "
                "(keyword_id, module_id, department_id, department, kb_path, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (keyword_id, module_id) WHERE is_deleted = FALSE DO UPDATE SET "
                "is_deleted = FALSE, department_id = EXCLUDED.department_id, "
                "department = EXCLUDED.department, kb_path = EXCLUDED.kb_path, updated_at = ?",
                (keyword_id, module_id, dept_id, dept, kb_path, now, now, now)
            )
        except Exception as e:
            # 部分唯一索引不存在等兼容场景：退回普通 INSERT（重复行风险由迁移脚本治理）
            self._execute_write(
                "INSERT INTO keyword_mappings "
                "(keyword_id, module_id, department_id, department, kb_path, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (keyword_id, module_id, dept_id, dept, kb_path, now, now)
            )
        mapping_id = self._execute_one(
            "SELECT id FROM keyword_mappings WHERE keyword_id = ? AND module_id IS NOT DISTINCT FROM ? "
            "ORDER BY id DESC LIMIT 1",
            (keyword_id, module_id)
        )
        return {"keyword_id": keyword_id, "mapping_id": mapping_id["id"] if mapping_id else None}

    def update_keyword(self, mapping_id: int, keyword: str = None, module_id: int = None,
                       dept_id: int = None, dept: str = None) -> dict:
        """更新关键词映射（通过 mapping_id 定位，全量覆盖语义）

        - keyword 改名撞 UNIQUE 时返回 {"error": "关键词已存在"}
        - module_id/dept_id/dept 传 None 表示清空（0 也会转为 NULL）
        - 两步 UPDATE 在同一事务内执行（keywords_v2 + keyword_mappings 原子性）
        """
        now = datetime.now().isoformat()
        # 先获取当前记录
        current = self._execute_one(
            "SELECT keyword_id FROM keyword_mappings WHERE id = ? AND is_deleted = FALSE",
            (mapping_id,)
        )
        if not current:
            return {"error": "映射不存在或已删除"}
        keyword_id = current["keyword_id"]

        # 同一连接 + 同一事务执行两步 UPDATE（防止部分成功导致两表不一致）
        with self.engine.connect() as conn:
            try:
                # 第一步：如果 keyword 文本变了，更新 keywords_v2 表
                if keyword:
                    sql1, params1 = self._convert_params(
                        "UPDATE keywords_v2 SET keyword = ?, updated_at = ? WHERE id = ?",
                        (keyword, now, keyword_id)
                    )
                    sql1 = self._adapt_sql(sql1)
                    conn.execute(text(sql1), params1)

                # 第二步：更新映射记录
                sql2, params2 = self._convert_params(
                    "UPDATE keyword_mappings SET module_id = ?, department_id = ?, department = ?, updated_at = ? "
                    "WHERE id = ?",
                    (module_id or None, dept_id or None, dept or "", now, mapping_id)
                )
                sql2 = self._adapt_sql(sql2)
                conn.execute(text(sql2), params2)

                conn.commit()
            except Exception as e:
                conn.rollback()
                # 唯一约束冲突（新词已存在）
                err_msg = str(e).lower()
                if "unique" in err_msg or "duplicate" in err_msg or "冲突" in err_msg:
                    return {"error": "关键词已存在"}
                raise
        return {"ok": True}

    def delete_mapping(self, mapping_id: int) -> bool:
        """软删除一条关键词映射（不存在/已删返回 False）"""
        exists = self._execute_one(
            "SELECT id FROM keyword_mappings WHERE id = ? AND is_deleted = FALSE", (mapping_id,))
        if not exists:
            return False
        now = datetime.now().isoformat()
        self._execute_write(
            "UPDATE keyword_mappings SET is_deleted = TRUE, updated_at = ? WHERE id = ?",
            (now, mapping_id)
        )
        return True

    def delete_keyword(self, keyword_id: int) -> bool:
        """软删除关键词及其所有映射（不存在/已删返回 False）"""
        exists = self._execute_one(
            "SELECT id FROM keywords_v2 WHERE id = ? AND is_deleted = FALSE", (keyword_id,))
        if not exists:
            return False
        now = datetime.now().isoformat()
        self._execute_write(
            "UPDATE keywords_v2 SET is_deleted = TRUE, updated_at = ? WHERE id = ?",
            (now, keyword_id)
        )
        self._execute_write(
            "UPDATE keyword_mappings SET is_deleted = TRUE, updated_at = ? WHERE keyword_id = ?",
            (now, keyword_id)
        )
        return True

    # ══════ Synonyms ══════

    def get_synonyms(self) -> dict[str, list[str]]:
        """从数据库读取同义词"""
        synonyms = {}
        rows = self._execute("SELECT word, synonym FROM synonyms")
        for row in rows:
            if row["word"] not in synonyms:
                synonyms[row["word"]] = []
            synonyms[row["word"]].append(row["synonym"])
        return synonyms

    # ══════ Documents (仍从文件系统读取) ══════

    def get_all_documents(self) -> list[Document]:
        return self._read_docs_from_dir(DATA_DIR / "knowledge")

    def get_all_faqs(self) -> list[FAQ]:
        """从数据库读取 FAQ（优先），无数据则回退文件系统"""
        faqs = []
        # 1. 从数据库读取（优先，JOIN 获取中文显示名）
        try:
            rows = self._execute(
                "SELECT * FROM faqs WHERE is_deleted = FALSE ORDER BY dept, sub_module, sort_num"
            )
            if rows:
                for row in rows:
                    faq = self._row_to_faq(row)
                    faqs.append(faq)
                if faqs:
                    return faqs
        except Exception:
            pass

        # 2. 从文件系统读取（回退）
        faq_dir = DATA_DIR / "faq"
        if not faq_dir.exists():
            return faqs
        for md_file in sorted(faq_dir.rglob("*.md")):
            if md_file.name in ("INDEX.md", "TEMPLATE.md"):
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            faq = self._parse_faq(text, str(md_file.relative_to(PROJECT_DIR)))
            if faq:
                faqs.append(faq)
        return faqs

    def _row_to_faq(self, row) -> FAQ:
        """DB row → FAQ dataclass"""
        def parse_json(val, default=None):
            if default is None:
                default = []
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        return FAQ(
            faq_code=row["faq_code"] or "",
            faq_title=row["faq_title"] or "",
            faq_question=row["faq_question"] or "",
            faq_answer=row["faq_answer"] or "",
            content=row["content"] or "",
            path=row["file_path"] or "",
            tags=parse_json(row["tags"]),
            dept=row["dept"] or "",
            dept_id=row["dept_id"] or 0,
            sub_module=row["sub_module"] or "",
            module=row["module"] or "",
            module_id=row["module_id"] or 0,
            scene=row["scene"] or "",
            status=row["status"] or 0,
            category_id=row["category_id"] or 0,
            sort_num=row["sort_num"] or 0,
            view_count=row["view_count"] or 0,
            source_file_name=row["source_file_name"] or "",
            version_from=row["version_from"] or "",
            related=parse_json(row["related"]),
            tickets=parse_json(row["tickets"]),
            create_user=row["create_user"] or "",
            update_user=row["update_user"] or "",
            create_time=row["create_time"] or "",
            update_time=row["update_time"] or "",
            is_deleted=bool(row["is_deleted"]) if row.get("is_deleted") is not None else False,
        )

    def get_all_reports(self) -> list[Report]:
        """从数据库 + 文件系统读取报表"""
        reports = []
        # 1. 从数据库读取（优先）
        try:
            rows = self._execute(
                "SELECT id, title, content, path FROM reports ORDER BY year DESC, week DESC"
            )
            for row in rows:
                reports.append(Report(
                    path=row["path"] or "",
                    title=row["title"],
                    content=row["content"][:500] if row["content"] else "",
                ))
            if reports:
                return reports
        except Exception:
            pass

        # 2. 从文件系统读取（回退）
        report_dir = DATA_DIR / "reports"
        if not report_dir.exists():
            return reports
        for md_file in sorted(report_dir.rglob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            title = ""
            for line in text.split("\n"):
                if line.startswith("# ") and not line.startswith("## "):
                    title = line[2:].strip()
                    break
            reports.append(Report(
                path=str(md_file.relative_to(PROJECT_DIR)),
                title=title, content=text[:500]
            ))
        return reports

    def get_raw_docs(self) -> list[Document]:
        return self._read_docs_from_dir(DATA_DIR / "raw-docs")

    def _read_docs_from_dir(self, directory: Path) -> list[Document]:
        """从文件系统读取文档"""
        docs = []
        if not directory.exists():
            return docs
        for md_file in sorted(directory.rglob("*.md")):
            if md_file.name == "INDEX.md":
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            doc = self._parse_document(text, str(md_file.relative_to(PROJECT_DIR)))
            if doc:
                docs.append(doc)
        return docs

    def _parse_document(self, text: str, rel_path: str):
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not fm_match:
            return None
        fm = fm_match.group(1)
        body = text[fm_match.end():]

        def get_field(name, default=""):
            m = re.search(rf"^{name}:\s*(.+)$", fm, re.MULTILINE)
            return m.group(1).strip().strip('"').strip("'") if m else default

        tags = get_field("keywords", "[]")
        if tags.startswith("["):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = [k.strip().strip("'\"") for k in tags.strip("[]").split(",") if k.strip()]
        else:
            tags = [k.strip() for k in tags.split(",") if k.strip()]

        return Document(
            path=rel_path, title=get_field("title", ""), content=body[:500],
            dept=get_field("dept", ""), module=get_field("module", ""),
            product=get_field("product", ""), product_line=get_field("product_line", ""),
            date=get_field("date", ""),
            keywords=keywords if isinstance(keywords, list) else [],
            appendix=get_field("appendix", ""),
        )

    def _parse_faq(self, text: str, rel_path: str):
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not fm_match:
            return None
        fm = fm_match.group(1)
        body = text[fm_match.end():]

        def get_field(name, default=""):
            m = re.search(rf"^{name}:\s*(.+)$", fm, re.MULTILINE)
            return m.group(1).strip().strip('"').strip("'") if m else default

        tags = get_field("keywords", "[]")
        if tags.startswith("["):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = [k.strip().strip("'\"") for k in tags.strip("[]").split(",") if k.strip()]
        else:
            tags = [k.strip() for k in tags.split(",") if k.strip()]

        # 兼容旧 status 字段（TEXT → INT）
        old_status = get_field("status", "active")
        status_int = STATUS_MAP.get(old_status, 1)

        # 兼容旧 id 字段 → faq_code
        faq_code = get_field("id", "")

        # 兼容旧 title 字段 → faq_title
        faq_title = get_field("title", "")

        # 尝试从正文提取 question（## 问题描述 下第一段）
        q_match = re.search(r'##\s*问题描述\s*\n+(.+?)(?=\n##|\n---|\Z)', body, re.DOTALL)
        faq_question = q_match.group(1).strip()[:500] if q_match else ""

        return FAQ(
            faq_code=faq_code,
            faq_title=faq_title,
            faq_question=faq_question,
            faq_answer=body.strip(),
            content=text,
            path=rel_path,
            tags=tags if isinstance(tags, list) else [],
            dept=get_field("dept", ""),
            sub_module=get_field("sub_module", ""),
            module=get_field("module", ""),
            scene=get_field("scene", ""),
            status=status_int,
            source_file_name=rel_path.split("/")[-1] if rel_path else "",
            version_from=get_field("version_from", ""),
            related=[],
            tickets=[],
            create_time=get_field("created", ""),
            update_time=get_field("reviewed", ""),
        )

    # ══════ FAQ CRUD ══════

    def save_faq(self, faq: FAQ, write_file: bool = True) -> str:
        """保存 FAQ：数据库为主，文件同步为辅

        write_file=False：仅写数据库，文件由路由层负责（避免 title.md 与 faq_code.md 双文件）
        """
        # 1. 写入数据库（primary）
        tags_list = faq.tags if isinstance(faq.tags, list) else []
        related_json = json.dumps(faq.related, ensure_ascii=False) if faq.related else "[]"
        tickets_json = json.dumps(faq.tickets, ensure_ascii=False) if faq.tickets else "[]"
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self._execute_write("""
            INSERT INTO faqs
            (faq_code, faq_title, faq_question, faq_answer, content, category_id,
             dept, dept_id, sub_module, module, module_id, scene, tags, status, sort_num, view_count,
             source_file_name, file_path, version_from, related, tickets,
             create_user, update_user, create_time, update_time, is_deleted)
            VALUES (:faq_code, :faq_title, :faq_question, :faq_answer, :content, :category_id,
             :dept, :dept_id, :sub_module, :module, :module_id, :scene, :tags, :status, :sort_num, :view_count,
             :source_file_name, :file_path, :version_from, :related, :tickets,
             :create_user, :update_user, :create_time, :update_time, :is_deleted)
            ON CONFLICT (faq_code) DO UPDATE SET
                faq_title = EXCLUDED.faq_title,
                faq_question = EXCLUDED.faq_question,
                faq_answer = EXCLUDED.faq_answer,
                content = EXCLUDED.content,
                category_id = EXCLUDED.category_id,
                dept = EXCLUDED.dept,
                dept_id = EXCLUDED.dept_id,
                sub_module = EXCLUDED.sub_module,
                module = EXCLUDED.module,
                module_id = EXCLUDED.module_id,
                scene = EXCLUDED.scene,
                tags = EXCLUDED.tags,
                status = EXCLUDED.status,
                sort_num = EXCLUDED.sort_num,
                source_file_name = EXCLUDED.source_file_name,
                file_path = EXCLUDED.file_path,
                version_from = EXCLUDED.version_from,
                related = EXCLUDED.related,
                tickets = EXCLUDED.tickets,
                update_user = EXCLUDED.update_user,
                update_time = EXCLUDED.update_time,
                is_deleted = EXCLUDED.is_deleted
        """, {
            "faq_code": faq.faq_code,
            "faq_title": faq.faq_title,
            "faq_question": faq.faq_question,
            "faq_answer": faq.faq_answer,
            "content": faq.content,
            "category_id": faq.category_id or None,  # 0 → NULL，避免违反外键
            "dept": faq.dept,
            "dept_id": faq.dept_id or None,  # 0 → NULL，避免违反外键
            "sub_module": faq.sub_module,
            "module": faq.module,
            "module_id": faq.module_id or None,  # 0 → NULL，避免违反外键
            "scene": faq.scene,
            "tags": tags_list,
            "status": faq.status,
            "sort_num": faq.sort_num,
            "view_count": faq.view_count,
            "source_file_name": faq.source_file_name,
            "file_path": faq.path,
            "version_from": faq.version_from,
            "related": related_json,
            "tickets": tickets_json,
            "create_user": faq.create_user,
            "update_user": faq.update_user,
            "create_time": faq.create_time or now,
            "update_time": now,
            "is_deleted": bool(faq.is_deleted),  # PG BOOLEAN 类型
        })

        # 2. 同步写文件（backup）—— write_file=False 时由路由层负责文件写入
        if write_file:
            dept_dir = get_dept_path(faq.dept) or "fin-tech"
            sub_dir = get_submodule_path(faq.sub_module) or get_submodule_path(faq.module) or "other"
            target_dir = DATA_DIR / "faq" / dept_dir / sub_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{faq.faq_code}.md" if faq.faq_code else f"{faq.faq_title}.md"
            file_path = target_dir / filename
            content = f"""---
id: {faq.faq_code}
title: {faq.faq_title}
keywords: {json.dumps(faq.tags, ensure_ascii=False)}
module: {faq.module}
dept: {faq.dept}
sub_module: {faq.sub_module}
scene: "{faq.scene}"
status: {STATUS_REVERSE.get(faq.status, 'active')}
version_from: "{faq.version_from}"
created: {faq.create_time or ''}
reviewed: {faq.update_time or ''}
related: {json.dumps(faq.related, ensure_ascii=False) if faq.related else '[]'}
tickets: {json.dumps(faq.tickets, ensure_ascii=False) if faq.tickets else '[]'}
---

{faq.faq_answer}
"""
            file_path.write_text(content, encoding="utf-8")
            rel_path = str(file_path.relative_to(PROJECT_DIR))
            self._execute_write("UPDATE faqs SET file_path = ? WHERE faq_code = ?", (rel_path, faq.faq_code))
            return rel_path
        return faq.path

    def delete_faq(self, path: str) -> dict:
        """逻辑删除 FAQ：is_deleted = TRUE

        优先按 file_path 匹配，回退按 faq_code 匹配。
        返回 {"ok": True, "matched": int}，matched=0 表示未找到记录。
        """
        faq_code = path.split("/")[-1].replace(".md", "")
        for key, val in [("file_path", path), ("faq_code", faq_code)]:
            sql, params = self._convert_params(
                f"UPDATE faqs SET is_deleted = TRUE, update_time = :update_time WHERE {key} = :val AND is_deleted = FALSE",
                {"update_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "val": val})
            sql = self._adapt_sql(sql)
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params)
                conn.commit()
                if result.rowcount > 0:
                    return {"ok": True, "matched": result.rowcount}
        return {"ok": False, "matched": 0, "error": "FAQ 不存在"}

    def bulk_import_faqs(self, faq_dir=None) -> int:
        """批量导入 FAQ：从目录扫描 .md 文件导入数据库（幂等）"""
        if faq_dir is None:
            faq_dir = DATA_DIR / "faq"
        imported = 0
        for md_file in sorted(Path(faq_dir).rglob("*.md")):
            if md_file.name in ("INDEX.md", "TEMPLATE.md"):
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            faq = self._parse_faq(text, str(md_file.relative_to(PROJECT_DIR)))
            if not faq or not faq.faq_code:
                continue
            existing = self._execute_one("SELECT id FROM faqs WHERE faq_code = ?", (faq.faq_code,))
            if existing:
                continue
            self._execute_write("""
                INSERT INTO faqs (faq_code, faq_title, faq_question, faq_answer, content,
                dept, sub_module, module, scene, tags, status, source_file_name, file_path,
                version_from, create_time, update_time)
                VALUES (:faq_code, :faq_title, :faq_question, :faq_answer, :content,
                :dept, :sub_module, :module, :scene, :tags, :status, :source_file_name, :file_path,
                :version_from, :create_time, :update_time)
            """, {
                "faq_code": faq.faq_code,
                "faq_title": faq.faq_title,
                "faq_question": faq.faq_question,
                "faq_answer": faq.faq_answer,
                "content": faq.content,
                "dept": faq.dept,
                "sub_module": faq.sub_module,
                "module": faq.module,
                "scene": faq.scene,
                "tags": faq.tags if isinstance(faq.tags, list) else [],
                "status": faq.status,
                "source_file_name": faq.source_file_name,
                "file_path": faq.path,
                "version_from": faq.version_from,
                "create_time": faq.create_time,
                "update_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            })
            imported += 1
        return imported

    # ══════ Feedback (数据库) ══════

    def save_feedback(self, query: str, result_id: str, result_path: str, feedback_type: str) -> None:
        self._execute_write(
            "INSERT INTO feedback (query, result_id, result_path, type) VALUES (?, ?, ?, ?)",
            (query, result_id, result_path, feedback_type)
        )

        # 更新统计
        key = f"feedback_{feedback_type}"
        self._execute_write(
            "INSERT INTO search_counter (key, value) VALUES (?, 1) "
            "ON CONFLICT(key) DO UPDATE SET value = search_counter.value + 1",
            (key,)
        )

    # ══════ Search Counter (数据库) ══════

    def get_counter(self, key: str) -> int:
        row = self._execute_one(
            "SELECT value FROM search_counter WHERE key = :key", {"key": key}
        )
        return row["value"] if row else 0

    def increment_counter(self, key: str) -> None:
        self._execute_write(
            "INSERT INTO search_counter (key, value) VALUES (?, 1) "
            "ON CONFLICT(key) DO UPDATE SET value = search_counter.value + 1",
            (key,)
        )

    def get_all_counters(self) -> dict:
        rows = self._execute("SELECT key, value FROM search_counter")
        return {row["key"]: row["value"] for row in rows}

    # ══════ 语义查询方法（消灭 SearchEngine/路由层硬编码 SQL）══════

    def get_faq_tags(self) -> list[dict]:
        """获取所有 FAQ 的 tags 字段（用于 jieba 词典加载）"""
        return self._execute("SELECT DISTINCT tags FROM faqs WHERE is_deleted = FALSE")

    def get_all_documents_raw(self) -> list[dict]:
        """获取全量文档原始行（SearchEngine 索引构建用）"""
        return self._execute(
            "SELECT path, title, content, dept, module, product, date, "
            "keywords, dept as dept3 FROM documents WHERE is_deleted = FALSE"
        )

    def get_all_reports_raw(self) -> list[dict]:
        """获取全量报表原始行（SearchEngine 索引构建用）"""
        return self._execute("SELECT path, title, content FROM reports WHERE is_deleted = FALSE")

    def get_faq_latest_update(self) -> str:
        """获取 FAQ 表最新更新时间（缓存版本检测用）"""
        row = self._execute_one("SELECT MAX(update_time) as latest FROM faqs WHERE is_deleted = FALSE")
        return row["latest"] if row and row["latest"] else ""

    def get_cache_version(self) -> int:
        """获取缓存版本号（缓存一致性检测用）"""
        return self.get_counter("cache_version")

    def check_table_columns(self, table_name: str) -> list[str]:
        """查询表的列名列表（information_schema.columns），返回列名列表"""
        rows = self._execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (table_name,)
        )
        return [r["column_name"] for r in rows]

    def check_table_indexes(self, table_name: str, indexname: str = None) -> list[str]:
        """查询表的索引名列表（pg_indexes），可选按索引名精确过滤"""
        if indexname:
            rows = self._execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = ? AND indexname = ?",
                (table_name, indexname)
            )
        else:
            rows = self._execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = ?",
                (table_name,)
            )
        return [r["indexname"] for r in rows]

    def get_table_count(self, table_name: str):
        """查询表的行数，表不存在时返回 None"""
        row = self._execute_one(f"SELECT COUNT(*) AS c FROM {table_name}")
        return row["c"] if row else None

    def get_active_counts(self):
        """获取各表有效记录数（is_deleted=FALSE），返回 dict

        用于 Dashboard 统计，替代遍历内存计数。
        """
        doc_count = self._execute_one(
            "SELECT COUNT(*) AS c FROM documents WHERE is_deleted = FALSE"
        )
        faq_count = self._execute_one(
            "SELECT COUNT(*) AS c FROM faqs WHERE is_deleted = FALSE"
        )
        report_count = self._execute_one(
            "SELECT COUNT(*) AS c FROM reports WHERE is_deleted = FALSE"
        )
        keyword_count = self._execute_one(
            "SELECT COUNT(DISTINCT keyword) AS c FROM keywords_v2 WHERE is_deleted = FALSE"
        )
        return {
            "documents": doc_count["c"] if doc_count else 0,
            "faqs": faq_count["c"] if faq_count else 0,
            "reports": report_count["c"] if report_count else 0,
            "keywords": keyword_count["c"] if keyword_count else 0,
        }

    def get_recent_documents(self, limit: int = 6):
        """最近更新的文档（排除 FAQ，按 updated_at 倒序）

        用于 Dashboard /recent，替代遍历内存 kb_docs。
        """
        return self._execute(
            "SELECT path, title, dept, updated_at FROM documents "
            "WHERE is_deleted = FALSE AND path NOT LIKE 'data/faq/%%' "
            "ORDER BY updated_at DESC NULLS LAST LIMIT :limit",
            {"limit": limit}
        )

    def save_search_log(self, query: str, normalized_q: str, results_count: int,
                        has_answer: bool, search_time_ms: int,
                        user_agent: str = "", ip_hash: str = "") -> None:
        """写入搜索日志到 search_logs 表"""
        self._execute_write(
            "INSERT INTO search_logs (query, normalized_q, result_count, has_answer, "
            "search_time_ms, source, user_agent, ip_hash) "
            "VALUES (:q, :nq, :cnt, :ha, :ms, 'web', :ua, :ip)",
            {"q": query[:2000], "nq": normalized_q[:2000] if normalized_q else None,
             "cnt": results_count, "ha": has_answer, "ms": search_time_ms,
             "ua": user_agent, "ip": ip_hash},
        )

    def search_keywords_like(self, prefix: str, limit: int = 10) -> list[str]:
        """模糊搜索关键词（keywords_v2 LIKE 匹配，返回去重关键词列表）"""
        rows = self._execute(
            "SELECT DISTINCT keyword FROM keywords_v2 WHERE keyword LIKE ? AND is_deleted = FALSE LIMIT ?",
            (f"%{prefix}%", limit)
        )
        return [r["keyword"] for r in rows]

    def get_department_name(self, dept_id: int) -> str:
        """按部门 ID 查询部门名称，无匹配返回空字符串"""
        row = self._execute_one("SELECT name FROM departments WHERE id = ?", (dept_id,))
        return row["name"] if row else ""

    def get_module_name(self, module_id: int) -> str:
        """按模块 ID 查询模块名称，无匹配返回空字符串"""
        row = self._execute_one("SELECT name FROM modules WHERE id = ?", (module_id,))
        return row["name"] if row else ""

    def get_dept_code(self, dept_name: str) -> str:
        """按部门名称查询部门编码（code），无匹配返回 None"""
        row = self._execute_one(
            "SELECT code FROM departments WHERE name = ? AND code IS NOT NULL LIMIT 1",
            (dept_name,)
        )
        return row["code"] if row else None

    def increment_faq_views(self, faq_code: str) -> None:
        """FAQ 浏览计数 +1"""
        self._execute_write(
            "UPDATE faqs SET view_count = view_count + 1 WHERE faq_code = ?",
            (faq_code,)
        )

    def get_module_product_map(self) -> dict[str, dict]:
        """获取模块→产品信息映射（模块名→产品/产品线/部门/业务域）"""
        rows = self._execute("""
            SELECT m.name as module_name,
                   p.name as product_name, pl.name as product_line_name,
                   d.name as dept_name, m.business_domain
            FROM modules m
            LEFT JOIN products p ON m.product_id = p.id
            LEFT JOIN product_lines pl ON p.product_line_id = pl.id
            LEFT JOIN departments d ON m.department_id = d.id
        """)
        result = {}
        for r in rows:
            if r["module_name"]:
                result[r["module_name"]] = {
                    "product": r["product_name"] or "",
                    "product_line": r["product_line_name"] or "",
                    "dept": r["dept_name"] or "",
                    "domain": r["business_domain"] or "",
                }
        return result

    def save_document(self, doc: dict) -> None:
        """保存文档（INSERT ON CONFLICT UPDATE）

        doc 需包含键: path, filename, title, content, dept, dept_id, module,
        module_id, product, product_line, date, keywords
        """
        self._execute_write(
            "INSERT INTO documents "
            "(path, filename, title, content, dept, dept_id, module, module_id, product, product_line, date, keywords, imported_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now(), now()) "
            "ON CONFLICT (path) DO UPDATE SET "
            "filename = EXCLUDED.filename, title = EXCLUDED.title, content = EXCLUDED.content, "
            "dept = EXCLUDED.dept, dept_id = EXCLUDED.dept_id, module = EXCLUDED.module, "
            "module_id = EXCLUDED.module_id, product = EXCLUDED.product, product_line = EXCLUDED.product_line, "
            "date = EXCLUDED.date, keywords = EXCLUDED.keywords, updated_at = now()",
            (doc["path"], doc["filename"], doc["title"], doc["content"],
             doc["dept"], doc.get("dept_id"), doc["module"], doc.get("module_id"),
             doc["product"], doc["product_line"], doc["date"], doc["keywords"])
        )

    def document_exists(self, path: str) -> bool:
        """检查文档路径是否已存在"""
        row = self._execute_one("SELECT id FROM documents WHERE path = ?", (path,))
        return row is not None

    def get_document_by_path(self, path: str):
        """按 path 查文档行（文件缺失时回退用，返回 dict 或 None）

        只查 is_deleted=FALSE 的有效记录，返回 content/title/dept/module 等字段。
        """
        row = self._execute_one(
            "SELECT path, title, content, dept, module, product, product_line, keywords "
            "FROM documents WHERE path = :path AND is_deleted = FALSE",
            {"path": path}
        )
        return row

    def get_documents_page(self, dept_id: int = 0, module: str = ""):
        """文档列表（DB 直查，替代遍历内存 kb_docs）

        返回 dict 列表，每个含 path/title/dept/module/product/product_line/date/keywords。
        不含 content（列表不需要正文，节省传输和内存）。
        dept_id 过滤走 document_departments 关联表（含子部门递归）。
        """
        if dept_id:
            paths = self.get_documents_by_department(dept_id)
            if not paths:
                return []
            placeholders = ", ".join(f":p{i}" for i in range(len(paths)))
            params = {f"p{i}": p for i, p in enumerate(paths)}
            rows = self._execute(
                "SELECT path, title, dept, module, product, product_line, date, keywords "
                f"FROM documents WHERE path IN ({placeholders}) AND is_deleted = FALSE "
                "ORDER BY updated_at DESC NULLS LAST",
                params
            )
        else:
            rows = self._execute(
                "SELECT path, title, dept, module, product, product_line, date, keywords "
                "FROM documents WHERE is_deleted = FALSE "
                "ORDER BY updated_at DESC NULLS LAST"
            )
        return rows

    def get_faqs_page(self):
        """FAQ 列表（DB 直查，替代遍历内存 faq_docs）

        返回 dict 列表，每个含 faq_code/faq_title/dept/sub_module/module/tags/file_path。
        """
        return self._execute(
            "SELECT faq_code, faq_title, dept, sub_module, module, tags, file_path "
            "FROM faqs WHERE is_deleted = FALSE ORDER BY update_time DESC NULLS LAST"
        )

    def update_document_path(self, old_path: str, new_path: str) -> bool:
        """文档改名后同步更新 DB path（ON CONFLICT key）

        返回 True 表示更新成功，False 表示旧路径无记录。
        """
        row = self._execute_one(
            "SELECT id FROM documents WHERE path = :path AND is_deleted = FALSE",
            {"path": old_path}
        )
        if not row:
            return False
        self._execute_write(
            "UPDATE documents SET path = :new_path, updated_at = now() WHERE path = :old_path",
            (new_path, old_path)
        )
        return True

    def get_search_log_count_since(self, since: str = None) -> int:
        """获取指定日期以来的搜索日志数量（since=None 时统计全量）"""
        if since:
            row = self._execute_one(
                "SELECT COUNT(*) AS c FROM search_logs WHERE created_at >= :since",
                {"since": since}
            )
        else:
            row = self._execute_one("SELECT COUNT(*) AS c FROM search_logs")
        return row["c"] if row else 0

    def get_search_trends(self, days: int = 30) -> list[dict]:
        """获取搜索趋势（按日聚合，最近 N 天）"""
        from datetime import date, timedelta
        since = (date.today() - timedelta(days=days - 1)).isoformat()
        rows = self._execute(
            "SELECT CAST(created_at AS DATE) AS d, COUNT(*) AS c FROM search_logs "
            "WHERE created_at >= :since GROUP BY CAST(created_at AS DATE)",
            {"since": since}
        )
        return [{"date": str(r["d"])[:10], "count": r["c"]} for r in rows]

    def get_menu_modules(self) -> tuple[list[dict], list[dict]]:
        """获取菜单所需数据：模块行（含产品/产品线/部门 JOIN）+ 全量部门行"""
        module_rows = self._execute("""
            SELECT m.id as module_id, m.name as module_name, m.description, m.dev_owner, m.module_owner,
                   m.business_domain,
                   p.name as product_name,
                   pl.name as product_line_name,
                   d.name as dept_name, d.id as dept_id, d.parent_id, d.level
            FROM modules m
            LEFT JOIN products p ON m.product_id = p.id
            LEFT JOIN product_lines pl ON p.product_line_id = pl.id
            LEFT JOIN departments d ON m.department_id = d.id
            WHERE m.name IS NOT NULL AND m.is_deleted = FALSE
        """)
        dept_rows = self._execute("SELECT id, name, parent_id, level FROM departments")
        return module_rows, dept_rows

    def get_department_tree(self) -> list[dict]:
        """获取部门树原始行（按 level, name 排序）"""
        return self._execute(
            "SELECT id, name, parent_id, level, code, dir_name FROM departments ORDER BY level, name"
        )

    def get_reports_page(self, category: str = "") -> list[dict]:
        """获取报表列表（支持分类过滤）"""
        if category:
            return self._execute(
                "SELECT id, title, week, year, category, dept_summary, path, created_at "
                "FROM reports WHERE is_deleted = FALSE AND category = ? "
                "ORDER BY year DESC NULLS LAST, week DESC",
                (category,)
            )
        return self._execute(
            "SELECT id, title, week, year, category, dept_summary, path, created_at "
            "FROM reports WHERE is_deleted = FALSE "
            "ORDER BY year DESC NULLS LAST, week DESC"
        )

    def get_hot_keywords(self, days: int = 30, limit: int = 20) -> list[dict]:
        """获取搜索热词（最近 N 天 GROUP BY query）"""
        from datetime import datetime as _dt, timedelta
        since = (_dt.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = self._execute(
            "SELECT query, COUNT(*) as cnt FROM search_logs "
            "WHERE created_at >= :since AND query IS NOT NULL AND query != '' "
            "GROUP BY query ORDER BY cnt DESC LIMIT :limit",
            {"since": since, "limit": limit}
        )
        return [{"word": r["query"], "count": r["cnt"]} for r in rows]

    # ══════ 文档-部门关联（多对多）══════

    def set_document_departments(self, doc_path: str, dept_ids: list[int],
                                  primary_dept_id: int = None) -> int:
        """设置文档的关联部门（先删后插，支持多选）

        doc_path: 文档路径
        dept_ids: 部门ID列表
        primary_dept_id: 主部门ID（可选，默认取末级最具体的部门）
        """
        # 删除旧关联
        self._execute_write(
            "DELETE FROM document_departments WHERE document_path = ?", (doc_path,)
        )
        if not dept_ids:
            return 0

        if primary_dept_id is None:
            primary_dept_id = dept_ids[-1]  # 默认最末级为主部门

        now = __import__('datetime').datetime.now().isoformat()
        for did in dept_ids:
            self._execute_write(
                """INSERT INTO document_departments
                   (document_path, department_id, is_primary, source, updated_at)
                   VALUES (:path, :did, :primary, 'manual', :now)
                   ON CONFLICT (document_path, department_id) DO UPDATE SET
                   is_primary = EXCLUDED.is_primary,
                   updated_at = EXCLUDED.updated_at""",
                {"path": doc_path, "did": did,
                 "primary": True if did == primary_dept_id else False,
                 "now": now}
            )
        return len(dept_ids)

    def get_document_departments(self, doc_path: str) -> list[dict]:
        """获取文档的关联部门列表"""
        rows = self._execute(
            """SELECT dd.*, d.name as dept_name, d.parent_id, d.level
               FROM document_departments dd
               JOIN departments d ON dd.department_id = d.id
               WHERE dd.document_path = ?
               ORDER BY dd.is_primary DESC, d.level DESC""",
            (doc_path,)
        )
        return [dict(r) for r in rows]

    def get_department_document_count(self, dept_id: int, include_children: bool = True) -> int:
        """获取部门及其子部门的文档总数"""
        if include_children:
            # 递归获取所有子部门ID
            dept_ids = {dept_id}
            children = self._execute(
                "SELECT id FROM departments WHERE parent_id = :pid", {"pid": dept_id}
            )
            for c in children:
                dept_ids.add(c['id'])
                gc = self._execute(
                    "SELECT id FROM departments WHERE parent_id = :pid", {"pid": c['id']}
                )
                for g in gc:
                    dept_ids.add(g['id'])
            # 使用命名参数
            names = {f"d{i}": did for i, did in enumerate(dept_ids)}
            placeholders = ','.join(f":{n}" for n in names)
            row = self._execute(
                f"SELECT COUNT(DISTINCT document_path) as cnt FROM document_departments WHERE department_id IN ({placeholders})",
                names
            )
        else:
            row = self._execute(
                "SELECT COUNT(DISTINCT document_path) as cnt FROM document_departments WHERE department_id = :did",
                {"did": dept_id}
            )
        return row[0]['cnt'] if row else 0

    def get_all_department_doc_counts(self) -> dict[int, int]:
        """获取所有部门的文档计数（用于部门树）"""
        # 兼容 SQLite (document_path) 和 PostgreSQL v3 (document_id)
        rows = self._execute(
            """SELECT department_id, COUNT(*) as cnt
               FROM document_departments GROUP BY department_id"""
        )
        return {r['department_id']: r['cnt'] for r in rows}

    def get_documents_by_department(self, dept_id: int, include_children: bool = True) -> list[str]:
        """获取部门下所有文档路径"""
        if include_children:
            dept_ids = {dept_id}
            children = self._execute(
                "SELECT id FROM departments WHERE parent_id = ?", (dept_id,)
            )
            for c in children:
                dept_ids.add(c['id'])
                gc = self._execute(
                    "SELECT id FROM departments WHERE parent_id = ?", (c['id'],)
                )
                for g in gc:
                    dept_ids.add(g['id'])
            placeholders = ','.join('?' * len(dept_ids))
            rows = self._execute(
                f"SELECT DISTINCT document_path FROM document_departments WHERE department_id IN ({placeholders})",
                tuple(dept_ids)
            )
        else:
            rows = self._execute(
                "SELECT DISTINCT document_path FROM document_departments WHERE department_id = ?",
                (dept_id,)
            )
        return [r['document_path'] for r in rows]

    def migrate_document_departments_from_frontmatter(self) -> int:
        """从文档 frontmatter dept 字段迁移到关联表（一次性迁移）"""
        import sys
        sys.path.insert(0, str(PROJECT_DIR / "src" / "server"))
        from search_engine import SearchEngine
        engine = SearchEngine(use_db=True)
        if not engine.load_cache():
            engine.load_all()
        engine._load_bm25_index()
        engine._load_vector_index()

        # 构建部门名称→ID映射
        name_to_id = {}
        rows = self._execute("SELECT id, name FROM departments")
        for r in rows:
            name_to_id[r['name']] = r['id']

        migrated = 0
        for doc in engine.kb_docs:
            dept = doc.get('dept', '') or doc.get('dept3', '')
            if not dept:
                continue
            doc_path = doc.get('path', '')
            if not doc_path:
                continue

            # 检查是否已有关联
            existing = self._execute(
                "SELECT COUNT(*) as cnt FROM document_departments WHERE document_path = ?",
                (doc_path,)
            )
            if existing['cnt'] > 0:
                continue

            # 支持逗号分隔的多部门
            dept_names = [d.strip() for d in dept.split(',') if d.strip()]
            dept_ids = []
            for dn in dept_names:
                if dn in name_to_id:
                    dept_ids.append(name_to_id[dn])

            if dept_ids:
                self.set_document_departments(doc_path, dept_ids)
                migrated += 1

        return migrated

    # ══════ 单例工厂（全项目共享连接池）══════

_repo_instance = None

def get_repo() -> "DBRepository":
    """DBRepository 单例工厂——全项目共享一个 Engine + 连接池，避免每次请求新建连接"""
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = DBRepository()
    return _repo_instance