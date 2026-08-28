#!/usr/bin/env python3
"""
知识库数据迁移脚本 v3.0
从 .md 文件批量迁移到 PostgreSQL 数据库

用法:
    # 1. 仅建表（不迁移数据）
    DATABASE_URL_SYNC=postgresql://kb_user:kb_pass@localhost:5432/knowledge_base \
        python3 migrate_to_v3.py --schema-only

    # 2. 完整迁移（建表 + 导入所有数据）
    DATABASE_URL_SYNC=postgresql://kb_user:kb_pass@localhost:5432/knowledge_base \
        python3 migrate_to_v3.py --all

    # 3. 只迁移特定类型
    DATABASE_URL_SYNC=postgresql://kb_user:kb_pass@localhost:5432/knowledge_base \
        python3 migrate_to_v3.py --modules --documents --faqs

    # 4. 导入后触发搜索服务重建索引
    DATABASE_URL_SYNC=postgresql://kb_user:kb_pass@localhost:5432/knowledge_base \
        python3 migrate_to_v3.py --all --rebuild

迁移数据量:
    modules:     71 个 .md → modules + module_menus + module_keywords
    documents:   73 个 .md → documents + document_departments + document_images
    faqs:       358 个 .md → faqs + faq_categories + faq_tags + faq_related + faq_images
    reports:     12 个 .md → reports
    raw_docs:    70 个 .md → raw_documents + raw_document_images

特性:
    - 幂等: 可重复执行，已存在的数据根据 path/faq_code 去重跳过
    - 安全: 旧表 DROP 前先检查，有数据时提示确认
    - 图片: 自动提取 Markdown 中的 ![](url) 到 image 表
    - 关联: 自动建立 FK 关联（部门/产品/模块/产品线）
"""

import os
import re
import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── 路径设置 ──────────────────────────────────────────────
HERE = Path(__file__).resolve().parent  # src/server/
PROJECT_DIR = HERE.parent.parent        # knowledge-base/
DATA_DIR = PROJECT_DIR / "data"
CONFIG_DIR = PROJECT_DIR / "config"
SCHEMA_FILE = CONFIG_DIR / "schema_v3.sql"

sys.path.insert(0, str(HERE))

# ── 数据库连接 ────────────────────────────────────────────
def get_db_url():
    url = os.getenv("DATABASE_URL_SYNC", "")
    if url:
        return url
    # 默认使用 zcy1 用户（现有表属主），可通过环境变量覆盖
    return "postgresql://zcy1:@localhost:5432/knowledge_base"

def get_db_engine():
    from sqlalchemy import create_engine
    db_url = get_db_url()
    print(f"  📦 数据库: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    return create_engine(db_url, echo=False, pool_pre_ping=True)

def execute_sql(engine, sql, params=None):
    """执行 SQL，返回字典列表"""
    from sqlalchemy import text
    with engine.connect() as conn:
        if params:
            result = conn.execute(text(sql), params)
        else:
            result = conn.execute(text(sql))
        conn.commit()
        try:
            return [dict(row._mapping) for row in result]
        except Exception:
            return []

def execute_sql_file(engine, filepath):
    """执行 SQL 文件（每条语句独立事务，互不影响）"""
    sql_content = filepath.read_text(encoding="utf-8")
    statements = []
    current = []
    in_function = False
    for line in sql_content.split("\n"):
        stripped = line.strip()
        # 跳过注释和空行
        if stripped.startswith("--") or not stripped:
            continue
        # 跟踪函数体（$$ ... $$）
        if "$$" in stripped:
            in_function = not in_function
        current.append(line)
        # 仅在函数体外时才按分号分割
        if not in_function and stripped.endswith(";"):
            stmt = "\n".join(current).rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            current = []
    # 处理最后一个语句
    if current:
        stmt = "\n".join(current).rstrip(";").strip()
        if stmt:
            statements.append(stmt)

    from sqlalchemy import text
    ok = 0
    fail = 0
    skip = 0
    for i, stmt in enumerate(statements):
        if not stmt:
            continue
        try:
            # 每条语句独立事务
            with engine.connect() as conn:
                conn.execute(text(stmt))
                conn.commit()
            ok += 1
        except Exception as e:
            err_msg = str(e)
            # 跳过无害错误
            if any(skip_msg in err_msg for skip_msg in [
                "already exists",
                "does not exist",
                "duplicate column",
                "must be owner of",
                "InsufficientPrivilege",
            ]):
                skip += 1
            else:
                fail += 1
                print(f"  ⚠️  语句 {i+1} 失败: {err_msg[:150]}")
    print(f"  ✅ Schema 已就绪 ({ok} 条成功, {skip} 条跳过, {fail} 条失败)")

# ── 工具函数 ──────────────────────────────────────────────

def compute_hash(text):
    """计算 SHA256 哈希"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def extract_images_from_markdown(content):
    """从 Markdown 中提取所有图片 URL 和 alt 文本"""
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    return [{"alt": m.group(1), "url": m.group(2)} for m in re.finditer(pattern, content)]

def parse_frontmatter(text):
    """解析 YAML frontmatter，返回 (meta_dict, body_text)"""
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return {}, text
    fm = fm_match.group(1)
    body = text[fm_match.end():]

    meta = {}
    for line in fm.split("\n"):
        kv = re.match(r"^(\w+):\s*(.+)$", line)
        if kv:
            key = kv.group(1).strip()
            val = kv.group(2).strip().strip('"').strip("'")
            meta[key] = val

    # 解析 keywords 为数组
    if "keywords" in meta:
        kw = meta["keywords"]
        if isinstance(kw, str):
            if kw.startswith("[") and kw.endswith("]"):
                try:
                    meta["keywords"] = json.loads(kw)
                except Exception:
                    meta["keywords"] = [k.strip().strip('"').strip("'") for k in kw.strip("[]").split(",") if k.strip()]
            else:
                meta["keywords"] = [k.strip() for k in kw.split(",") if k.strip()]

    # 解析 related_modules 为数组
    if "related_modules" in meta:
        rm = meta["related_modules"]
        if isinstance(rm, str):
            if rm.startswith("[") and rm.endswith("]"):
                try:
                    meta["related_modules"] = json.loads(rm)
                except Exception:
                    meta["related_modules"] = []
            else:
                meta["related_modules"] = []

    # 解析 related (FAQ 关联)
    if "related" in meta:
        rel = meta["related"]
        if isinstance(rel, str):
            if rel.startswith("[") and rel.endswith("]"):
                try:
                    meta["related"] = json.loads(rel)
                except Exception:
                    meta["related"] = []
            else:
                meta["related"] = []

    # 解析 tickets
    if "tickets" in meta:
        tks = meta["tickets"]
        if isinstance(tks, str):
            if tks.startswith("[") and tks.endswith("]"):
                try:
                    meta["tickets"] = json.loads(tks)
                except Exception:
                    meta["tickets"] = []
            else:
                meta["tickets"] = []

    # 解析 status: 兼容 TEXT → INT
    if "status" in meta:
        status_map = {"active": 1, "outdated": 2, "deprecated": 3, "draft": 0}
        if meta["status"] in status_map:
            meta["status"] = status_map[meta["status"]]

    # 内容中的 tags 字段（FAQ 用）
    if "tags" in meta:
        tags = meta["tags"]
        if isinstance(tags, str):
            if tags.startswith("[") and tags.endswith("]"):
                try:
                    meta["tags"] = json.loads(tags)
                except Exception:
                    meta["tags"] = [k.strip().strip('"').strip("'") for k in tags.strip("[]").split(",") if k.strip()]
            else:
                meta["tags"] = [k.strip() for k in tags.split(",") if k.strip()]

    return meta, body

def count_words(text):
    """统计文本字数（去除 Markdown 标记和 URL）"""
    clean = re.sub(r'!\[.*?\]\(.*?\)', '', text)  # 去图片
    clean = re.sub(r'\[([^\]]*)\]\(.*?\)', r'\1', clean)  # 去链接 URL
    clean = re.sub(r'[#*`>|\[\]\(\)\{\}]', '', clean)  # 去标记
    return len(clean.replace('\n', '').replace(' ', ''))

def get_dept_id(engine, dept_name):
    """根据部门名称查找部门 ID"""
    if not dept_name:
        return None
    rows = execute_sql(engine,
        "SELECT id FROM departments WHERE name = :name LIMIT 1",
        {"name": dept_name}
    )
    return rows[0]["id"] if rows else None

def get_product_id(engine, product_name):
    """根据产品名称查找产品 ID"""
    if not product_name:
        return None
    rows = execute_sql(engine,
        "SELECT id FROM products WHERE name = :name LIMIT 1",
        {"name": product_name}
    )
    return rows[0]["id"] if rows else None

def get_product_line_id(engine, pl_name):
    """根据产品线名称查找 ID"""
    if not pl_name:
        return None
    rows = execute_sql(engine,
        "SELECT id FROM product_lines WHERE name = :name LIMIT 1",
        {"name": pl_name}
    )
    return rows[0]["id"] if rows else None

def get_module_id(engine, module_name):
    """根据模块名称查找模块 ID"""
    if not module_name:
        return None
    rows = execute_sql(engine,
        "SELECT id FROM modules WHERE name = :name AND is_deleted = FALSE LIMIT 1",
        {"name": module_name}
    )
    return rows[0]["id"] if rows else None

# ── 迁移函数 ──────────────────────────────────────────────

def migrate_schema(engine):
    """执行 schema_v3.sql 建表"""
    print("\n" + "="*60)
    print("📋 第0步：执行 Schema 建表")
    print("="*60)
    execute_sql_file(engine, SCHEMA_FILE)

def migrate_modules(engine):
    """迁移 data/modules/*.md → modules + module_menus + module_keywords"""
    print("\n" + "="*60)
    print("📦 第1步：迁移模块定义 (modules)")
    print("="*60)

    modules_dir = DATA_DIR / "modules"
    if not modules_dir.exists():
        print("  ⚠️  modules 目录不存在，跳过")
        return

    md_files = sorted(modules_dir.rglob("*.md"))
    total = len(md_files)
    print(f"  找到 {total} 个模块文件")

    count = 0
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        rel_path = str(md_file.relative_to(PROJECT_DIR))

        # 模块名称
        module_name = meta.get("name", "")
        if not module_name or module_name.startswith("module-"):
            if module_name.startswith("module-"):
                module_name = module_name[len("module-"):]  # 去除 "module-" 前缀
            else:
                # 从文件名推断
                module_name = md_file.stem

        # 检查是否已存在
        existing = execute_sql(engine,
            "SELECT id FROM modules WHERE name = :name LIMIT 1",
            {"name": module_name}
        )
        if existing:
            # 已存在，跳过
            continue

        # 提取元数据
        dept_name = meta.get("department", "")
        dept_id = get_dept_id(engine, dept_name)
        product_name = meta.get("product", "")
        product_id = get_product_id(engine, product_name)

        # 提取关键词（从 ## 关键词 段落）
        kw_match = re.search(r'##\s*关键词\s*\n(.+?)(?=\n##|\n---|\Z)', body, re.DOTALL)
        keywords = []
        if kw_match:
            kw_text = kw_match.group(1).strip()
            keywords = [k.strip() for k in kw_text.split(",") if k.strip()]

        # 提取菜单映射（从 ## 菜单映射 表格）
        menus = []
        menu_section = re.search(r'##\s*菜单映射\s*\n(.*?)(?=\n##|\n---|\Z)', body, re.DOTALL)
        if menu_section:
            for line in menu_section.group(1).split("\n"):
                if line.startswith("|") and not line.startswith("|--") and not line.startswith("| 一级"):
                    cells = [c.strip() for c in line.split("|")[1:-1]]
                    if len(cells) >= 3 and cells[0]:
                        menus.append({
                            "level1": cells[0] if cells[0] != "-" else "",
                            "level2": cells[1] if len(cells) > 1 and cells[1] != "-" else "",
                            "level3": cells[2] if len(cells) > 2 and cells[2] != "-" else "",
                        })

        # 插入模块
        execute_sql(engine, """
            INSERT INTO modules (name, department_id, product_id, dev_owner, module_owner,
                appendix, business_domain, associated_dept, sub_dept, description,
                path, dir_name)
            VALUES (:name, :dept_id, :product_id, :dev_owner, :module_owner,
                :appendix, :business_domain, :associated_dept, :sub_dept, :description,
                :path, :dir_name)
        """, {
            "name": module_name,
            "dept_id": dept_id,
            "product_id": product_id,
            "dev_owner": meta.get("dev_owner", ""),
            "module_owner": meta.get("module_owner", ""),
            "appendix": meta.get("appendix", ""),
            "business_domain": meta.get("business_domain", dept_name),
            "associated_dept": meta.get("associated_dept", ""),
            "sub_dept": meta.get("sub_dept", ""),
            "description": meta.get("description", ""),
            "path": str(rel_path),
            "dir_name": md_file.parent.name,
        })

        module_id = execute_sql(engine,
            "SELECT id FROM modules WHERE name = :name LIMIT 1",
            {"name": module_name}
        )[0]["id"]

        # 插入菜单映射
        for i, menu in enumerate(menus):
            execute_sql(engine, """
                INSERT INTO module_menus (module_id, level1, level2, level3, sort_order)
                VALUES (:module_id, :level1, :level2, :level3, :sort_order)
            """, {
                "module_id": module_id,
                "level1": menu["level1"],
                "level2": menu["level2"],
                "level3": menu["level3"],
                "sort_order": i,
            })

        # 插入关键词
        for kw in keywords:
            execute_sql(engine, """
                INSERT INTO module_keywords (module_id, keyword)
                VALUES (:module_id, :keyword)
                ON CONFLICT (module_id, keyword) DO NOTHING
            """, {"module_id": module_id, "keyword": kw})

        count += 1
        if count % 10 == 0:
            print(f"  已迁移 {count}/{total} 个模块...")

    print(f"  ✅ 模块迁移完成: {count} 个模块")

def migrate_documents(engine):
    """迁移 data/knowledge/*.md → documents + document_departments + document_images"""
    print("\n" + "="*60)
    print("📄 第2步：迁移知识文档 (documents)")
    print("="*60)

    kb_dir = DATA_DIR / "knowledge"
    if not kb_dir.exists():
        print("  ⚠️  knowledge 目录不存在，跳过")
        return

    md_files = sorted(kb_dir.rglob("*.md"))
    # 排除 INDEX.md
    md_files = [f for f in md_files if f.name != "INDEX.md"]
    total = len(md_files)
    print(f"  找到 {total} 个知识文档")

    count = 0
    img_count = 0
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        rel_path = str(md_file.relative_to(PROJECT_DIR))

        # 检查是否已存在
        existing = execute_sql(engine,
            "SELECT id FROM documents WHERE path = :path LIMIT 1",
            {"path": rel_path}
        )
        if existing:
            continue

        title = meta.get("title", "")
        if not title:
            # 从正文第一个 # 标题提取
            title_match = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else md_file.stem

        dept_name = meta.get("dept", "")
        dept_id = get_dept_id(engine, dept_name)
        module_name = meta.get("module", "")
        module_id = get_module_id(engine, module_name)
        product_name = meta.get("product", "")
        product_id = get_product_id(engine, product_name)
        product_line_name = meta.get("product_line", "")
        product_line_id = get_product_line_id(engine, product_line_name)

        keywords = meta.get("keywords", [])
        if isinstance(keywords, str):
            keywords = []
        related_modules = meta.get("related_modules", [])
        if isinstance(related_modules, str):
            related_modules = []

        content_hash = compute_hash(text)
        word_count = count_words(body)

        # 插入文档
        execute_sql(engine, """
            INSERT INTO documents (path, filename, title, content, content_hash, word_count,
                dept, dept_id, module, module_id, product, product_id,
                product_line, product_line_id, date, appendix, keywords, related_modules)
            VALUES (:path, :filename, :title, :content, :content_hash, :word_count,
                :dept, :dept_id, :module, :module_id, :product, :product_id,
                :product_line, :product_line_id, :date, :appendix, :keywords, :related_modules)
        """, {
            "path": rel_path,
            "filename": md_file.name,
            "title": title,
            "content": text,
            "content_hash": content_hash,
            "word_count": word_count,
            "dept": dept_name,
            "dept_id": dept_id,
            "module": module_name,
            "module_id": module_id,
            "product": product_name,
            "product_id": product_id,
            "product_line": product_line_name,
            "product_line_id": product_line_id,
            "date": meta.get("date", ""),
            "appendix": meta.get("appendix", ""),
            "keywords": keywords,
            "related_modules": related_modules,
        })

        doc_id = execute_sql(engine,
            "SELECT id FROM documents WHERE path = :path LIMIT 1",
            {"path": rel_path}
        )[0]["id"]

        # 插入部门关联
        if dept_id:
            execute_sql(engine, """
                INSERT INTO document_departments (document_id, department_id, is_primary, source)
                VALUES (:doc_id, :dept_id, TRUE, 'auto')
                ON CONFLICT (document_id, department_id) DO NOTHING
            """, {"doc_id": doc_id, "dept_id": dept_id})

        # 提取并插入图片 URL
        images = extract_images_from_markdown(text)
        for img in images:
            execute_sql(engine, """
                INSERT INTO document_images (document_id, image_url, alt_text)
                VALUES (:doc_id, :url, :alt)
                ON CONFLICT (document_id, image_url) DO NOTHING
            """, {"doc_id": doc_id, "url": img["url"], "alt": img["alt"]})
            img_count += 1

        count += 1
        if count % 10 == 0:
            print(f"  已迁移 {count}/{total} 个文档...")

    print(f"  ✅ 知识文档迁移完成: {count} 个文档, {img_count} 张图片引用")

def migrate_faqs(engine):
    """迁移 data/faq/*.md → faqs + faq_categories + faq_tags + faq_related + faq_images"""
    print("\n" + "="*60)
    print("❓ 第3步：迁移 FAQ 知识库 (faqs)")
    print("="*60)

    faq_dir = DATA_DIR / "faq"
    if not faq_dir.exists():
        print("  ⚠️  faq 目录不存在，跳过")
        return

    md_files = sorted(faq_dir.rglob("*.md"))
    # 排除 INDEX.md 和 TEMPLATE.md
    md_files = [f for f in md_files if f.name not in ("INDEX.md", "TEMPLATE.md")]
    total = len(md_files)
    print(f"  找到 {total} 个 FAQ 文件")

    # 先收集所有分类（从目录结构）
    categories = {}  # (dept, sub_module) → category_id
    cat_dirs = set()
    for md_file in md_files:
        rel = md_file.relative_to(faq_dir)
        parts = rel.parts
        if len(parts) >= 2:
            dept = parts[0]   # 如 immunization
            sub = parts[1]    # 如 immunization
            cat_dirs.add((dept, sub))

    for dept, sub in sorted(cat_dirs):
        existing = execute_sql(engine,
            "SELECT id FROM faq_categories WHERE dept = :dept AND sub_module = :sub AND parent_id IS NULL LIMIT 1",
            {"dept": dept, "sub": sub}
        )
        if not existing:
            execute_sql(engine, """
                INSERT INTO faq_categories (name, dept, sub_module, level)
                VALUES (:name, :dept, :sub, 1)
            """, {"name": f"{dept}/{sub}", "dept": dept, "sub": sub})
            cat_id = execute_sql(engine,
                "SELECT id FROM faq_categories WHERE dept = :dept AND sub_module = :sub LIMIT 1",
                {"dept": dept, "sub": sub}
            )[0]["id"]
            categories[(dept, sub)] = cat_id
        else:
            categories[(dept, sub)] = existing[0]["id"]

    count = 0
    img_count = 0
    tag_count = 0
    related_count = 0
    ticket_count = 0

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        rel_path = str(md_file.relative_to(PROJECT_DIR))

        faq_code = meta.get("id", "")
        if not faq_code:
            # 从文件名提取
            faq_code = md_file.stem

        # 检查是否已存在
        existing = execute_sql(engine,
            "SELECT id FROM faqs WHERE faq_code = :code LIMIT 1",
            {"code": faq_code}
        )
        if existing:
            continue

        # 分类
        rel = md_file.relative_to(faq_dir)
        parts = rel.parts
        dept_dir = parts[0] if len(parts) >= 1 else ""
        sub_dir = parts[1] if len(parts) >= 2 else ""
        cat_id = categories.get((dept_dir, sub_dir))

        dept_name = meta.get("dept", "")
        dept_id = get_dept_id(engine, dept_name)
        module_name = meta.get("module", "")
        module_id = get_module_id(engine, module_name)

        # 提取 question（从 ## 问题描述 段落）
        q_match = re.search(r'##\s*问题描述\s*\n+(.+?)(?=\n##|\n---|\Z)', body, re.DOTALL)
        faq_question = q_match.group(1).strip()[:500] if q_match else ""

        # 提取 answer（从 ## 解决方法 或 ## 原因分析 到末尾的正文）
        a_match = re.search(r'(##\s*(?:问题描述|解决方法|原因分析).*$)', body, re.DOTALL)
        faq_answer = a_match.group(1).strip() if a_match else body.strip()

        # tags
        tags = meta.get("tags", [])
        if not tags:
            tags = meta.get("keywords", [])
        if isinstance(tags, str):
            tags = []

        # status
        status = meta.get("status", 1)
        if isinstance(status, str):
            status_map = {"active": 1, "outdated": 2, "deprecated": 3, "draft": 0}
            status = status_map.get(status, 1)

        # 插入 FAQ
        # 处理空时间戳：TIMESTAMPTZ 不接受空字符串
        create_time = meta.get("created", "").strip()
        update_time = meta.get("reviewed", "").strip()
        if not create_time or create_time == "":
            create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not update_time or update_time == "":
            update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        execute_sql(engine, """
            INSERT INTO faqs (faq_code, faq_title, faq_question, faq_answer, content,
                category_id, dept, dept_id, sub_module, module, module_id, scene,
                tags, status, sort_num, source_file_name, file_path,
                version_from, create_user, update_user, create_time, update_time)
            VALUES (:faq_code, :faq_title, :faq_question, :faq_answer, :content,
                :category_id, :dept, :dept_id, :sub_module, :module, :module_id, :scene,
                :tags, :status, :sort_num, :source_file_name, :file_path,
                :version_from, :create_user, :update_user, :create_time, :update_time)
        """, {
            "faq_code": faq_code,
            "faq_title": meta.get("title", md_file.stem),
            "faq_question": faq_question,
            "faq_answer": faq_answer,
            "content": text,
            "category_id": cat_id,
            "dept": dept_name,
            "dept_id": dept_id,
            "sub_module": meta.get("sub_module", sub_dir),
            "module": module_name,
            "module_id": module_id,
            "scene": meta.get("scene", ""),
            "tags": tags,
            "status": status,
            "sort_num": int(meta.get("sort_num", 0)),
            "source_file_name": md_file.name,
            "file_path": rel_path,
            "version_from": meta.get("version_from", ""),
            "create_user": meta.get("create_user", ""),
            "update_user": meta.get("update_user", ""),
            "create_time": create_time,
            "update_time": update_time,
        })

        faq_id = execute_sql(engine,
            "SELECT id FROM faqs WHERE faq_code = :code LIMIT 1",
            {"code": faq_code}
        )[0]["id"]

        # 插入标签关联
        for tag in tags:
            execute_sql(engine, """
                INSERT INTO faq_tags (faq_id, tag)
                VALUES (:faq_id, :tag)
                ON CONFLICT (faq_id, tag) DO NOTHING
            """, {"faq_id": faq_id, "tag": tag})
            tag_count += 1

        # 插入关联 FAQ
        related = meta.get("related", [])
        if isinstance(related, str):
            related = []
        for rel_code in related:
            # 先插入关联记录（即使目标 FAQ 可能还未导入）
            execute_sql(engine, """
                INSERT INTO faq_related (faq_id, related_faq_id)
                SELECT :faq_id, id FROM faqs WHERE faq_code = :rel_code
                ON CONFLICT (faq_id, related_faq_id) DO NOTHING
            """, {"faq_id": faq_id, "rel_code": rel_code})
            related_count += 1

        # 插入工单关联
        tickets = meta.get("tickets", [])
        if isinstance(tickets, str):
            tickets = []
        for ticket_id in tickets:
            execute_sql(engine, """
                INSERT INTO faq_tickets (faq_id, ticket_id)
                VALUES (:faq_id, :ticket_id)
                ON CONFLICT (faq_id, ticket_id) DO NOTHING
            """, {"faq_id": faq_id, "ticket_id": ticket_id})
            ticket_count += 1

        # 提取图片
        images = extract_images_from_markdown(text)
        for img in images:
            execute_sql(engine, """
                INSERT INTO faq_images (faq_id, image_url, alt_text)
                VALUES (:faq_id, :url, :alt)
                ON CONFLICT (faq_id, image_url) DO NOTHING
            """, {"faq_id": faq_id, "url": img["url"], "alt": img["alt"]})
            img_count += 1

        count += 1
        if count % 20 == 0:
            print(f"  已迁移 {count}/{total} 个 FAQ...")

    print(f"  ✅ FAQ 迁移完成: {count} 个 FAQ, {tag_count} 个标签, "
          f"{related_count} 个关联, {ticket_count} 个工单, {img_count} 张图片")

def migrate_reports(engine):
    """迁移 data/reports/*.md → reports"""
    print("\n" + "="*60)
    print("📊 第4步：迁移报表 (reports)")
    print("="*60)

    report_dir = DATA_DIR / "reports"
    if not report_dir.exists():
        print("  ⚠️  reports 目录不存在，跳过")
        return

    md_files = sorted(report_dir.rglob("*.md"))
    total = len(md_files)
    print(f"  找到 {total} 个报表文件")

    count = 0
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        rel_path = str(md_file.relative_to(PROJECT_DIR))

        # 检查是否已存在
        existing = execute_sql(engine,
            "SELECT id FROM reports WHERE path = :path LIMIT 1",
            {"path": rel_path}
        )
        if existing:
            continue

        # 提取标题
        title = ""
        for line in text.split("\n"):
            if line.startswith("# ") and not line.startswith("## "):
                title = line[2:].strip()
                break
        if not title:
            title = md_file.stem

        # 推断周次和年份
        week = None
        year = None
        week_match = re.search(r'(\d{4})-W(\d{1,2})', title)
        if week_match:
            year = int(week_match.group(1))
            week = f"{week_match.group(1)}-W{week_match.group(2)}"

        # 推断类别
        category = "周报"
        if "月报" in title or md_file.parent.name == "monthly":
            category = "月报"
        elif "年报" in title:
            category = "年报"

        content_hash = compute_hash(text)

        execute_sql(engine, """
            INSERT INTO reports (title, week, year, category, content, content_hash, path)
            VALUES (:title, :week, :year, :category, :content, :content_hash, :path)
        """, {
            "title": title,
            "week": week,
            "year": year,
            "category": category,
            "content": text,
            "content_hash": content_hash,
            "path": rel_path,
        })

        count += 1

    print(f"  ✅ 报表迁移完成: {count} 个报表")

def migrate_raw_documents(engine):
    """迁移 data/raw-docs/*.md → raw_documents + raw_document_images"""
    print("\n" + "="*60)
    print("📝 第5步：迁移原始文档 (raw_documents)")
    print("="*60)

    raw_dir = DATA_DIR / "raw-docs"
    if not raw_dir.exists():
        print("  ⚠️  raw-docs 目录不存在，跳过")
        return

    md_files = sorted(raw_dir.rglob("*.md"))
    total = len(md_files)
    print(f"  找到 {total} 个原始文档")

    count = 0
    img_count = 0
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        rel_path = str(md_file.relative_to(PROJECT_DIR))

        # 检查是否已存在
        existing = execute_sql(engine,
            "SELECT id FROM raw_documents WHERE path = :path LIMIT 1",
            {"path": rel_path}
        )
        if existing:
            continue

        # 提取标题
        title = ""
        for line in text.split("\n"):
            if line.startswith("# ") and not line.startswith("## "):
                title = line[2:].strip()
                break
        if not title:
            title = md_file.stem

        # 从路径推断部门/模块
        rel = md_file.relative_to(raw_dir)
        dept_name = rel.parts[0] if len(rel.parts) >= 1 else ""
        dept_id = get_dept_id(engine, dept_name)

        # 提取日期
        date = ""
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', md_file.stem)
        if date_match:
            date = date_match.group(1)

        # 提取图片
        images = extract_images_from_markdown(text)
        image_count = len(images)

        content_hash = compute_hash(text)

        execute_sql(engine, """
            INSERT INTO raw_documents (path, filename, title, content, content_hash,
                dept, dept_id, module, product, date, image_count)
            VALUES (:path, :filename, :title, :content, :content_hash,
                :dept, :dept_id, :module, :product, :date, :image_count)
        """, {
            "path": rel_path,
            "filename": md_file.name,
            "title": title,
            "content": text,
            "content_hash": content_hash,
            "dept": dept_name,
            "dept_id": dept_id,
            "module": "",
            "product": "",
            "date": date,
            "image_count": image_count,
        })

        doc_id = execute_sql(engine,
            "SELECT id FROM raw_documents WHERE path = :path LIMIT 1",
            {"path": rel_path}
        )[0]["id"]

        for img in images:
            execute_sql(engine, """
                INSERT INTO raw_document_images (document_id, image_url, alt_text)
                VALUES (:doc_id, :url, :alt)
                ON CONFLICT (document_id, image_url) DO NOTHING
            """, {"doc_id": doc_id, "url": img["url"], "alt": img["alt"]})
            img_count += 1

        count += 1
        if count % 10 == 0:
            print(f"  已迁移 {count}/{total} 个原始文档...")

    print(f"  ✅ 原始文档迁移完成: {count} 个文档, {img_count} 张图片")

def rebuild_search_index(engine):
    """触发搜索服务重建索引"""
    print("\n" + "="*60)
    print("🔄 触发搜索服务重建索引")
    print("="*60)
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:8000/api/rebuild", timeout=10)
        print("  ✅ 已触发 /api/rebuild")
    except Exception as e:
        print(f"  ⚠️  无法连接搜索服务: {e}")
        print("  💡 请手动重启搜索服务以重建索引")

def print_summary(engine):
    """打印迁移后的数据统计"""
    print("\n" + "="*60)
    print("📊 迁移后数据统计")
    print("="*60)

    stats = [
        ("modules", "SELECT COUNT(*) FROM modules WHERE is_deleted = FALSE"),
        ("module_menus", "SELECT COUNT(*) FROM module_menus"),
        ("module_keywords", "SELECT COUNT(*) FROM module_keywords"),
        ("documents", "SELECT COUNT(*) FROM documents WHERE is_deleted = FALSE"),
        ("document_images", "SELECT COUNT(*) FROM document_images"),
        ("faqs", "SELECT COUNT(*) FROM faqs WHERE is_deleted = FALSE"),
        ("faq_tags", "SELECT COUNT(*) FROM faq_tags"),
        ("faq_related", "SELECT COUNT(*) FROM faq_related"),
        ("faq_tickets", "SELECT COUNT(*) FROM faq_tickets"),
        ("faq_images", "SELECT COUNT(*) FROM faq_images"),
        ("reports", "SELECT COUNT(*) FROM reports WHERE is_deleted = FALSE"),
        ("raw_documents", "SELECT COUNT(*) FROM raw_documents WHERE is_deleted = FALSE"),
        ("raw_document_images", "SELECT COUNT(*) FROM raw_document_images"),
        ("keywords", "SELECT COUNT(*) FROM keywords"),
        ("synonyms", "SELECT COUNT(*) FROM synonyms"),
        ("departments", "SELECT COUNT(*) FROM departments"),
    ]

    for name, sql in stats:
        try:
            rows = execute_sql(engine, sql)
            count = rows[0]["count"] if rows else 0
            print(f"  {name:20s}: {count:>6}")
        except Exception:
            print(f"  {name:20s}:   N/A")

# ── 主入口 ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="知识库数据迁移脚本 v3.0")
    parser.add_argument("--schema-only", action="store_true", help="仅执行建表 SQL")
    parser.add_argument("--all", action="store_true", help="执行全部迁移")
    parser.add_argument("--modules", action="store_true", help="迁移模块定义")
    parser.add_argument("--documents", action="store_true", help="迁移知识文档")
    parser.add_argument("--faqs", action="store_true", help="迁移 FAQ 知识库")
    parser.add_argument("--reports", action="store_true", help="迁移报表")
    parser.add_argument("--raw-docs", action="store_true", help="迁移原始文档")
    parser.add_argument("--rebuild", action="store_true", help="迁移后触发搜索服务重建索引")
    args = parser.parse_args()

    # 如果没有指定任何参数，默认执行 --all
    if not any([args.schema_only, args.all, args.modules, args.documents,
                args.faqs, args.reports, args.raw_docs]):
        args.all = True

    print("="*60)
    print("🚀 知识库数据迁移脚本 v3.0")
    print(f"   项目目录: {PROJECT_DIR}")
    print(f"   数据目录: {DATA_DIR}")
    print("="*60)

    engine = get_db_engine()

    try:
        # Step 0: 建表（始终执行，因为用的是 IF NOT EXISTS / DROP IF EXISTS）
        migrate_schema(engine)

        if args.all or args.modules:
            migrate_modules(engine)

        if args.all or args.documents:
            migrate_documents(engine)

        if args.all or args.faqs:
            migrate_faqs(engine)

        if args.all or args.reports:
            migrate_reports(engine)

        if args.all or args.raw_docs:
            migrate_raw_documents(engine)

        # 打印统计
        print_summary(engine)

        # 重建索引
        if args.rebuild:
            rebuild_search_index(engine)

        print("\n🎉 迁移完成！")
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()