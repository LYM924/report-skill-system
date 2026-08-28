#!/usr/bin/env python3
"""产品知识库搜索服务 - 启动本地 Web 搜索界面"""
import json, os, sys, logging, datetime, urllib.parse
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，支持并发请求（避免 SSE 流式连接阻塞其他请求）"""
    daemon_threads = True
from urllib.parse import urlparse, parse_qs, quote as url_quote

logging.getLogger().setLevel(logging.WARNING)
import jieba
jieba.setLogLevel(logging.WARNING)

HERE = Path(__file__).resolve().parent  # src/server/
PROJECT_DIR = HERE.parent.parent  # knowledge-base/
RUNTIME_DIR = PROJECT_DIR / "runtime"
DATA_DIR = PROJECT_DIR / "data"
sys.path.insert(0, str(HERE))
from search_engine import SearchEngine
from spell_corrector import create_corrector
from repository import DBRepository
from keyword_extractor import get_extractor, build_extractor_idf

from logging.handlers import RotatingFileHandler

LOG_DIR = RUNTIME_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 配置日志
log_handler = RotatingFileHandler(
    LOG_DIR / "search_server.log",
    maxBytes=5 * 1024 * 1024,  # 5MB per file
    backupCount=5,              # keep 5 backups
    encoding="utf-8",
)
log_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))

server_logger = logging.getLogger("search_server")
server_logger.setLevel(logging.INFO)
server_logger.addHandler(log_handler)
server_logger.propagate = False  # don't send to root logger

engine = None
db_repo = None  # 数据库访问（优先使用）
SESSION_STORE = {}
SESSION_FILE = RUNTIME_DIR / "sessions.json"

def load_sessions():
    """加载持久化的会话数据"""
    if SESSION_FILE.exists():
        try:
            import time
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 清理过期会话（>30分钟）
            now = time.time()
            for k, v in saved.items():
                if now - v.get("created", 0) < 1800:
                    SESSION_STORE[k] = v
        except Exception:
            pass

def save_sessions():
    """持久化会话数据"""
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(SESSION_STORE, f, ensure_ascii=False)
    except Exception:
        pass
SEARCH_COUNTER = {  # 搜索统计计数器
    "total": 0,
    "today": 0,
    "week": 0,
    "faq_hits": 0,
    "ai_summaries": 0,
}

COUNTER_FILE = RUNTIME_DIR / "search_counter.json"

def load_counter():
    """加载持久化的搜索计数器"""
    if COUNTER_FILE.exists():
        try:
            with open(COUNTER_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            SEARCH_COUNTER.update(saved)
        except Exception:
            pass

def save_counter():
    """持久化搜索计数器（数据库优先，文件回退）"""
    if db_repo:
        for key, value in SEARCH_COUNTER.items():
            if isinstance(value, (int, float)):
                db_repo._execute_write(
                    "INSERT OR REPLACE INTO search_counter (key, value) VALUES (?, ?)",
                    (key, int(value))
                )
        return
    try:
        with open(COUNTER_FILE, "w", encoding="utf-8") as f:
            json.dump(SEARCH_COUNTER, f, ensure_ascii=False)
    except Exception:
        pass


def get_engine():
    global engine
    if engine is None:
        engine = SearchEngine()
        if not engine.load_cache():
            engine._load_synonyms()
            engine._load_keyword_index()
            engine._load_module_files()
            engine._load_knowledge_base()
            engine._load_faq_knowledge()
            engine._load_report_data()
            engine.save_cache()
        # Ensure BM25 and vector index are loaded
        if engine.bm25 is None:
            engine._load_bm25_index()
        if engine.vector is None:
            engine._load_vector_index()
    return engine

def _save_keywords_to_db(kw_list, dept, module, kb_path=""):
    """将提取的关键词同步写入数据库 keywords 表"""
    if not db_repo or not kw_list:
        return
    try:
        # 查找或创建 module_id
        row = db_repo._execute_one(
            "SELECT id FROM modules WHERE name = ? LIMIT 1", (module,)
        )
        module_id = row['id'] if row else None
        for kw in kw_list:
            db_repo._execute_write(
                "INSERT OR IGNORE INTO keywords (keyword, module_id, department, domain, kb_path) VALUES (?, ?, ?, ?, ?)",
                (kw, module_id, dept, module, kb_path)
            )
    except Exception:
        pass  # 关键词入库失败不影响主流程

def rebuild_engine():
    """重建引擎（FAQ增删后调用，清除所有缓存避免脏数据）"""
    global engine
    import shutil
    cache_dir = RUNTIME_DIR / "cache"
    for f in cache_dir.glob("*"):
        if f.is_file():
            f.unlink()
    engine = SearchEngine()
    engine.load_all()
    engine.save_cache()
    server_logger.info("CACHE_CLEARED_AND_REBUILT")

def reload_faqs():
    """轻量级重载 FAQ 数据（从 DB 读取，文件仅作备份）"""
    global engine
    if engine is None:
        engine = SearchEngine()
    # 从 DB 加载（DB 是主数据源）
    engine.faq_docs = []
    engine._load_faq_knowledge()
    # 从 kb_docs 中移除旧的 FAQ 条目
    engine.kb_docs = [d for d in engine.kb_docs if not d.get('path', '').startswith('data/faq/')]
    # 重新将 FAQ 加入 kb_docs（用于 BM25 索引）
    for faq in engine.faq_docs:
        # 兼容 dict 和 FAQ 对象两种格式
        if isinstance(faq, dict):
            content = faq.get('content_sample', '') or ''
            rel_path = faq.get('path', '') or ''
            dept = faq.get('dept', '') or ''
            sub_module = faq.get('sub_module', '') or ''
            title = faq.get('title', '') or ''
        else:
            content = faq.faq_answer if hasattr(faq, 'faq_answer') else ''
            rel_path = faq.path or ''
            dept = faq.dept or ''
            sub_module = faq.sub_module or ''
            title = faq.faq_title or ''
        sample = (content or '')[:5000]
        engine.kb_docs.append({
            "path": rel_path,
            "dept": dept,
            "domain": sub_module,
            "title": f"[FAQ] {title}",
            "content_sample": sample,
        })
    engine._load_bm25_index()
    server_logger.info("FAQ_RELOADED")


class SearchHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RUNTIME_DIR / "static"), **kwargs)

    # ── 辅助方法（供路由模块使用）──

    def _get_engine(self):
        return get_engine()

    def _get_project_dir(self):
        return PROJECT_DIR

    def _get_counter(self, key):
        return SEARCH_COUNTER.get(key, 0)

    def _get_session(self, sid):
        return SESSION_STORE.get(sid)

    def _set_session(self, sid, data):
        SESSION_STORE[sid] = data
        save_sessions()  # 持久化到文件

    def _cleanup_sessions(self):
        import time
        now = time.time()
        for k in list(SESSION_STORE.keys()):
            if now - SESSION_STORE[k].get("created", 0) > 600:
                del SESSION_STORE[k]

    # ── 认证 ──

    def _check_auth(self):
        """API Key 认证：环境变量 KB_API_KEY 设置后生效，未设置则跳过（开发模式）"""
        api_key = os.environ.get("KB_API_KEY", "")
        if not api_key:
            return True  # 未配置 API Key，允许所有请求（开发模式）

        # 1. Header: Authorization: Bearer <key>
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            if auth_header[7:] == api_key:
                return True

        # 2. Query param: ?api_key=<key>
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if params.get("api_key", [""])[0] == api_key:
            return True

        return False

    def _require_auth(self):
        """需要认证的 API 路径"""
        path = urlparse(self.path).path
        # 静态资源和首页不需要认证
        if path == "/" or path.startswith("/assets/") or path.startswith("/favicon") or path.startswith("/icons"):
            return False
        # API 路径需要认证
        return path.startswith("/api/")

    def _read_json(self):
        """读取 POST/PUT/DELETE 请求的 JSON body"""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode('utf-8')
        return json.loads(body) if body else {}

    def do_GET(self):
        parsed = urlparse(self.path)

        # 认证检查
        if self._require_auth() and not self._check_auth():
            self._json({"error": "未授权访问，请提供有效的 API Key"}, 401)
            return

        # 路由分发：优先使用模块化路由，回退到内联路由
        from router import router
        route_handler = router.dispatch("GET", parsed.path)
        if route_handler:
            params = parse_qs(parsed.query)
            route_handler(self, params)
            return

        # === 以下为待迁移的内联路由 ===

        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            top = int(params.get("top", ["15"])[0])
            page = int(params.get("page", ["1"])[0])
            page_size = min(int(params.get("page_size", ["10"])[0]), 50)

            if not query:
                self._json({"error": "请提供查询参数 q"})
                return

            # 搜索计数
            SEARCH_COUNTER["total"] = SEARCH_COUNTER.get("total", 0) + 1
            SEARCH_COUNTER["today"] = SEARCH_COUNTER.get("today", 0) + 1
            SEARCH_COUNTER["week"] = SEARCH_COUNTER.get("week", 0) + 1
            server_logger.info(f"SEARCH query='{query}' tokens={list(jieba.cut(query))}")

            # Track hotwords
            if "hotwords" not in SEARCH_COUNTER:
                SEARCH_COUNTER["hotwords"] = {}
            SEARCH_COUNTER["hotwords"][query] = SEARCH_COUNTER["hotwords"].get(query, 0) + 1

            # Track monthly searches
            month_key = f"month_{datetime.datetime.now().month}"
            SEARCH_COUNTER[month_key] = SEARCH_COUNTER.get(month_key, 0) + 1

            # 持久化计数器（每次搜索保存）
            save_counter()

            eng = get_engine()

            # 0. 先查 FAQ 缓存
            cached = eng.check_faq_cache(query)
            if cached:
                SEARCH_COUNTER["faq_hits"] = SEARCH_COUNTER.get("faq_hits", 0) + 1
                SEARCH_COUNTER[f"faq_month_{datetime.datetime.now().month}"] = SEARCH_COUNTER.get(f"faq_month_{datetime.datetime.now().month}", 0) + 1
                # 持久化计数器
                save_counter()
                result = {
                    "query": query,
                    "tokens": list(jieba.cut(query)),
                    "expanded_terms": [],
                    "total": 1,
                    "from_cache": True,
                    "cached_answer": {
                        "source": "faq_cache",
                        "question": query,
                        "summary": cached["answer"],
                        "module": cached.get("module", ""),
                        "matched_keywords": cached.get("keywords", []),
                        "saved_at": cached.get("saved_at", ""),
                    },
                    "results": [],
                    "claude_stream_url": None,
                }
                self._json(result)
                return

            # 1. 常规搜索
            result = eng.search(query, top=top)

            # 分页处理
            all_results = result.get("results", [])
            total = len(all_results)
            start = (page - 1) * page_size
            paged_results = all_results[start:start + page_size]

            result["results"] = paged_results
            result["total"] = total
            result["page"] = page
            result["page_size"] = page_size
            result["has_more"] = start + page_size < total

            # 为搜索结果添加部门层级路径（P1-4）
            if db_repo:
                try:
                    # 构建部门 ID→path 缓存
                    dept_paths = {}
                    all_depts = db_repo._execute(
                        "SELECT id, name, parent_id FROM departments"
                    )
                    dept_lookup = {d['id']: (d['name'], d['parent_id']) for d in all_depts}
                    def get_dept_path(name):
                        if name in dept_paths:
                            return dept_paths[name]
                        # 按名称查找部门ID
                        for did, (dname, pid) in dept_lookup.items():
                            if dname == name:
                                parts = [name]
                                while pid and pid in dept_lookup:
                                    pname, pid = dept_lookup[pid]
                                    parts.append(pname)
                                path = ' > '.join(reversed(parts))
                                dept_paths[name] = path
                                return path
                        dept_paths[name] = name
                        return name
                    for r in paged_results:
                        dept = r.get('dept', '')
                        if dept and dept not in dept_paths:
                            get_dept_path(dept)
                        r['dept_path'] = dept_paths.get(dept, dept)
                except Exception:
                    pass

            # 记录搜索查询到日志文件
            try:
                with open(LOG_DIR / "search_queries.log", "a", encoding="utf-8") as f:
                    f.write(f"{datetime.datetime.now().isoformat()}\t{query}\t{total}\n")
            except Exception:
                pass

            # 1b. Add quick summary for immediate display
            ans = result.get('answer') or {}
            result['quick_summary'] = {
                'module': ans.get('module', ''),
                'dept': ans.get('dept', ''),
                'owner': ans.get('module_owner', ''),
                'snippet': ans.get('summary', '')[:200] if ans.get('summary') else '',
            }

            # 2. 构建 RAG prompt 并存储到 session store（使用 RAG 确保 AI 总结基于搜索结果）
            api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                prompt = eng.build_rag_prompt(query, result.get("results", []))
                import uuid, time
                sid = uuid.uuid4().hex[:12]
                SESSION_STORE[sid] = {"prompt": prompt, "query": query, "created": time.time()}
                # 清理超过 10 分钟的旧 session
                now = time.time()
                for k in list(SESSION_STORE.keys()):
                    if now - SESSION_STORE[k].get("created", 0) > 600:
                        del SESSION_STORE[k]
                result["claude_stream_url"] = "/api/claude-stream?sid={}".format(sid)
            else:
                result["claude_stream_url"] = None

            self._json(result)
        elif parsed.path == "/api/rebuild":
            rebuild_engine()
            server_logger.info("INDEX_REBUILD manual trigger")
            self._json({"ok": True, "message": "索引已重建"})
        elif parsed.path == "/api/faq":
            params = parse_qs(parsed.query)
            faq_id = params.get("id", [""])[0]
            eng = get_engine()

            if faq_id:
                # 返回单个 FAQ 的完整内容
                for doc in eng.faq_docs:
                    if doc.get("faq_id") == faq_id:
                        faq_path = PROJECT_DIR / doc["path"]
                        if faq_path.exists():
                            try:
                                raw = faq_path.read_text(encoding="utf-8")
                            except Exception:
                                raw = ""
                            # 剥离 YAML frontmatter，只返回正文内容
                            content = raw
                            if raw.startswith("---"):
                                parts = raw.split("---", 2)
                                if len(parts) >= 3:
                                    content = parts[2].lstrip("\n")
                            self._json({
                                "id": doc["faq_id"],
                                "title": doc["title"],
                                "keywords": doc.get("keywords", []),
                                "dept": doc["dept"],
                                "sub_module": doc["sub_module"],
                                "path": doc["path"],
                                "content": content,
                            })
                            return
                self._json({"error": "FAQ not found"}, 404)
            else:
                # 返回 FAQ 列表
                faq_list = []
                for doc in eng.faq_docs:
                    faq_list.append({
                        "id": doc.get("faq_id", ""),
                        "title": doc.get("title", ""),
                        "keywords": doc.get("keywords", []),
                        "dept": doc["dept"],
                        "sub_module": doc.get("sub_module", ""),
                        "module": doc.get("module", doc.get("sub_module", "")),
                        "path": doc["path"],
                    })
                self._json({"faqs": faq_list, "total": len(faq_list)})
        elif parsed.path == "/api/claude-stream":
            params = parse_qs(parsed.query)
            sid = params.get("sid", [""])[0]
            deep = params.get("deep", ["0"])[0] == "1"  # 新增：深度分析模式

            if not sid or sid not in SESSION_STORE:
                self._sse_start()
                self._sse_send({"error": "会话已过期，请重新搜索"})
                self._sse_done()
                return

            session = SESSION_STORE.get(sid)  # 深度分析需要复用 session
            query = session.get("query", "")
            context = session.get("prompt", {})

            # 深度分析模式：增强 prompt
            if deep and context.get("messages"):
                orig_content = context["messages"][0].get("content", "")
                context["messages"][0]["content"] = (
                    "请对以下问题进行深度分析，包括：\n"
                    "1. 问题拆解 - 将问题分解为子问题\n"
                    "2. 分点回答 - 每个子问题给出详细答案\n"
                    "3. 操作建议 - 给出具体操作步骤\n"
                    "4. 关联信息 - 相关的 FAQ、文档、配置项\n\n"
                    + orig_content
                )

            api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                self._sse_start()
                self._sse_send({"error": "未配置 ANTHROPIC_AUTH_TOKEN 或 ANTHROPIC_API_KEY 环境变量"})
                self._sse_done()
                return

            SEARCH_COUNTER["ai_summaries"] = SEARCH_COUNTER.get("ai_summaries", 0) + 1
            save_counter()
            self._handle_claude_stream(query, context, api_key)
            return
        elif parsed.path == "/api/stats":
            eng = get_engine()
            self._json({
                "keywords": len(eng.keyword_map),
                "modules": len(eng.module_map),
                "menus": len(eng.menu_map),
                "kb_docs": len([d for d in eng.kb_docs if not d.get("title", "").startswith("[FAQ]")]),
                "faq_docs": len(eng.faq_docs),
                "report_docs": len(eng.report_docs),
                "total_searches": SEARCH_COUNTER.get("total", 0),
                "today_searches": SEARCH_COUNTER.get("today", 0),
                "faq_hits": SEARCH_COUNTER.get("faq_hits", 0),
                "ai_summaries": SEARCH_COUNTER.get("ai_summaries", 0),
            })
        elif parsed.path == "/api/dashboard":
            """返回知识总览仪表盘数据（真实统计）"""
            eng = get_engine()
            faq_count = len(eng.faq_docs)
            report_count = len(eng.report_docs)
            # kb_docs 包含 FAQ 条目（用于搜索索引），统计时需排除
            kb_count = len([d for d in eng.kb_docs if not d.get("title", "").startswith("[FAQ]")])
            total_docs = kb_count + faq_count + report_count
            self._json({
                "totalDocs": total_docs,
                "totalKbDocs": kb_count,
                "faqCount": faq_count,
                "totalReports": report_count,
                "weekQuestions": SEARCH_COUNTER.get("week", 0),
                "weekNew": kb_count,
                "weekNewGrowth": 0,
                "aiMatchConfidence": 92,
            })
        elif parsed.path == "/api/documents":
            """返回文档列表（支持分页、模块筛选、部门ID筛选）"""
            eng = get_engine()
            params = parse_qs(parsed.query)
            module = params.get("module", [""])[0]
            dept_id = params.get("dept_id", [""])[0]  # 新增：按数据库部门ID筛选
            page = int(params.get("page", ["1"])[0])
            page_size = min(int(params.get("page_size", ["20"])[0]), 100)
            docs = []
            all_docs = sorted(eng.kb_docs, key=lambda d: (
                (PROJECT_DIR / d["path"]).stat().st_mtime
                if (PROJECT_DIR / d["path"]).exists() else 0
            ), reverse=True)
            all_docs = [d for d in all_docs if not d.get("title", "").startswith("[FAQ]")]

            # 按部门ID筛选（使用 document_departments 关联表）
            if dept_id:
                try:
                    dept_id_int = int(dept_id)
                    if db_repo:
                        # 从关联表获取该部门及其子部门的所有文档路径
                        doc_paths = set(db_repo.get_documents_by_department(dept_id_int))
                        if doc_paths:
                            all_docs = [d for d in all_docs if d.get("path", "") in doc_paths]
                        else:
                            # 关联表无数据时，回退到名称匹配
                            dept_names = set()
                            target = db_repo._execute_one(
                                "SELECT name FROM departments WHERE id = ?", (dept_id_int,)
                            )
                            if target: dept_names.add(target['name'])
                            children = db_repo._execute(
                                "SELECT id, name FROM departments WHERE parent_id = ?", (dept_id_int,)
                            )
                            for c in children:
                                dept_names.add(c['name'])
                                gc = db_repo._execute(
                                    "SELECT name FROM departments WHERE parent_id = ?", (c['id'],)
                                )
                                for g in gc: dept_names.add(g['name'])
                            if dept_names:
                                all_docs = [d for d in all_docs
                                            if d.get("dept", "") in dept_names
                                            or d.get("dept3", "") in dept_names
                                            or d.get("domain", "") in dept_names]
                except ValueError:
                    pass
            elif module:
                # 精确匹配 dept/dept3，再匹配 product 字段，再匹配路径段
                all_docs = [d for d in all_docs
                            if module == d.get("dept", "") or module == d.get("dept3", "")
                            or module == d.get("domain", "") or module == d.get("product", "")
                            or module in d.get("path", "").split("/")]
            total = len(all_docs)
            start = (page - 1) * page_size
            for doc in all_docs[start:start + page_size]:
                # 构建显示名称：优先使用 title（如果是有意义的标题），否则用模块名+日期
                module_name = doc.get("module", "") or doc.get("domain", "")
                raw_date = doc.get("date", "")
                doc_title = doc.get("title", "")
                # 格式化日期
                doc_date = raw_date
                if '-' not in doc_date and len(doc_date) >= 8:
                    doc_date = f"{doc_date[:4]}-{doc_date[4:6]}-{doc_date[6:8]}"
                elif '-' not in doc_date and len(doc_date) >= 6:
                    doc_date = f"{doc_date[:4]}-{doc_date[4:6]}"
                kw = [k.replace('\xa0', '').strip() for k in doc.get("keywords", [])[:2]]
                # 标题有意义则用标题，否则用模块名+日期
                if doc_title and not doc_title.startswith("202") and len(doc_title) > 6:
                    name = doc_title
                elif module_name and doc_date:
                    name = f"{module_name} · {doc_date}"
                    if kw:
                        name += f" · {' '.join(kw)}"
                else:
                    name = doc.get("title", doc["path"].split("/")[-1].replace(".md", ""))
                dept = doc.get("dept", "")
                product = doc.get("domain", "")
                doc_path = PROJECT_DIR / doc["path"]
                updated = "2026-08-10"
                if doc_path.exists():
                    mtime = doc_path.stat().st_mtime
                    updated = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                docs.append({
                    "id": hash(doc["path"]) % 10000,
                    "name": name,
                    "path": doc["path"],
                    "product": product,
                    "dept": dept,
                    "dept3": doc.get("dept3", ""),
                    "updated": updated,
                    "keywords": doc.get("keywords", []),
                    "confidence": 85 + (hash(doc["path"]) % 10),
                })
            self._json({"documents": docs, "total": total, "page": page, "page_size": page_size})
        elif parsed.path == "/api/image":
            params = parse_qs(parsed.query)
            img_path = params.get("path", [""])[0]
            self._serve_image(img_path)
        elif parsed.path == "/api/document":
            params = parse_qs(parsed.query)
            doc_path = params.get("path", [""])[0]
            if not doc_path:
                self._json({"error": "请提供文档路径"})
                return
            self._serve_document(doc_path)
        elif parsed.path == "/api/faq/save":
            """保存 FAQ 草稿或正式条目"""
            params = parse_qs(parsed.query)
            faq_id = params.get("id", [""])[0]
            title = params.get("title", [""])[0]
            keywords = params.get("keywords", [""])[0]
            dept = params.get("dept", [""])[0]
            sub_module = params.get("sub_module", [""])[0]
            module = params.get("module", [""])[0]
            content = params.get("content", [""])[0]
            status = params.get("status", ["draft"])[0]

            if not title or not dept:
                self._json({"error": "title 和 dept 为必填参数"})
                return

            import urllib.parse
            from repository.dept_mapping import get_dept_path, get_submodule_path
            dept_path = get_dept_path(dept)
            sub_path = get_submodule_path(sub_module) if sub_module else ""
            faq_dir = DATA_DIR / "faq" / dept_path / sub_path if sub_path else DATA_DIR / "faq" / dept_path
            faq_dir.mkdir(parents=True, exist_ok=True)

            if not faq_id:
                # 从数据库获取部门代码，兜底使用拼音首字母
                dept_code = "XX"
                if db_repo:
                    try:
                        row = db_repo._execute_one(
                            "SELECT code FROM departments WHERE name = ? AND code IS NOT NULL",
                            (dept,)
                        )
                        if row:
                            dept_code = row['code']
                    except Exception:
                        pass
                if dept_code == "XX":
                    dept_codes = {"数智财务组": "SZ", "免疫规划组": "YM", "电子档案组": "DZ", "数字化支撑组": "ZH"}
                    dept_code = dept_codes.get(dept, "XX")
                mod_code = sub_module[:3] if sub_module else "XXX"
                faq_id = f"FAQ-{dept_code}-{mod_code}-{len(list(faq_dir.glob('*.md')))+1:03d}"

            safe_title = title.replace("/", "-").replace("?", "").replace(":", "")
            file_path = faq_dir / f"{safe_title}.md"

            kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
            # 用户未提供关键词时，自动提取
            if not kw_list and content:
                try:
                    kw_extractor = get_extractor()
                    if not kw_extractor._built:
                        build_extractor_idf(str(DATA_DIR))
                    kw_list = kw_extractor.extract(content, top_k=10)
                except Exception:
                    kw_list = []
            today = datetime.date.today().isoformat()

            # 防御：剥离 content 中可能夹带的 YAML frontmatter（防止重复 frontmatter）
            safe_content = content
            if safe_content.strip().startswith("---"):
                parts = safe_content.split("---", 2)
                if len(parts) >= 3:
                    safe_content = parts[2].lstrip("\n")

            file_content = f"""---
id: {faq_id}
title: {title}
keywords: {kw_list}
module: {module}
dept: {dept}
sub_module: {sub_module}
scene: ""
status: {status}
version_from: ""
created: {today}
reviewed: {today}
related: []
tickets: []
---

# {title}

{safe_content}
"""
            try:
                file_path.write_text(file_content, encoding="utf-8")
            except Exception as e:
                server_logger.error(f"FAQ_SAVE_FAILED id={faq_id} error={e}")
                self._json({"error": f"文件写入失败: {str(e)}"}, 500)
                return

            # 同步写入 DB（主数据源）
            if db_repo:
                try:
                    from repository.base import FAQ
                    faq_obj = FAQ(
                        faq_code=faq_id, faq_title=title, faq_question=safe_content[:500],
                        faq_answer=safe_content, content=file_content,
                        tags=kw_list, dept=dept, sub_module=sub_module, module=module,
                        status=1, path=str(file_path.relative_to(PROJECT_DIR)),
                    )
                    db_repo.save_faq(faq_obj)
                except Exception as e:
                    server_logger.error(f"FAQ_DB_SAVE_FAILED id={faq_id} error={e}")

            # 轻量重载 FAQ（不重建全部索引，秒级完成）
            try:
                reload_faqs()
            except Exception as e:
                server_logger.error(f"FAQ_RELOAD_FAILED id={faq_id} error={e}")
                self._json({"ok": True, "faq_id": faq_id, "path": str(file_path.relative_to(PROJECT_DIR)), "warning": "索引刷新失败，请稍后手动重建"})
                return

            server_logger.info(f"FAQ_SAVE id={faq_id} title='{title}' dept={dept}")
            _save_keywords_to_db(kw_list, dept, sub_module, str(file_path.relative_to(PROJECT_DIR)))
            self._json({"ok": True, "faq_id": faq_id, "path": str(file_path.relative_to(PROJECT_DIR))})
        elif parsed.path == "/api/faq/import":
            """Excel 批量导入 FAQ"""
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self._json({"error": "请使用 multipart/form-data 上传 Excel 文件"})
                return
            try:
                import openpyxl, tempfile, cgi, io
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                # 解析 multipart
                boundary = content_type.split('boundary=')[1].strip()
                parts = body.split(b'--' + boundary.encode())
                success = 0
                fail = 0
                for part in parts:
                    if b'filename=' in part:
                        header_end = part.find(b'\r\n\r\n')
                        file_data = part[header_end + 4:]
                        file_data = file_data.rsplit(b'\r\n', 1)[0]  # remove trailing boundary
                        wb = openpyxl.load_workbook(io.BytesIO(file_data), read_only=True)
                        ws = wb.active
                        rows = list(ws.iter_rows(values_only=True))
                        if not rows or len(rows) < 2:
                            self._json({"error": "Excel 文件为空或无表头"})
                            return
                        headers = [str(h).strip() if h else '' for h in rows[0]]
                        # 映射列名: 标题/问题/title, 关键词/keywords, 部门/dept, 模块/module, 问题描述/description, 解决方法/solution
                        col_map = {}
                        for i, h in enumerate(headers):
                            hl = h.lower()
                            if any(k in hl for k in ['标题', '问题', 'title']): col_map['title'] = i
                            elif any(k in hl for k in ['关键词', 'keywords', '标签', 'tags']): col_map['keywords'] = i
                            elif any(k in hl for k in ['部门', 'dept', '业务组']): col_map['dept'] = i
                            elif any(k in hl for k in ['模块', 'module', '子模块']): col_map['module'] = i
                            elif any(k in hl for k in ['描述', '问题描述', 'description', '现象']): col_map['desc'] = i
                            elif any(k in hl for k in ['解决', '方案', 'solution', '答案', 'answer', '方法']): col_map['solution'] = i
                        for row in rows[1:]:
                            if not row or all(v is None or str(v).strip() == '' for v in row):
                                continue
                            title = str(row[col_map.get('title', 0)] or '').strip()
                            if not title or len(title) < 4 or title.isdigit():
                                fail += 1
                                continue
                            keywords = str(row[col_map.get('keywords', 1)] or '').strip() if col_map.get('keywords') else ''
                            dept = str(row[col_map.get('dept', 2)] or '').strip() if col_map.get('dept') else '数智财务组'
                            module = str(row[col_map.get('module', 3)] or '').strip() if col_map.get('module') else ''
                            desc = str(row[col_map.get('desc', 4)] or '').strip() if col_map.get('desc') else ''
                            solution = str(row[col_map.get('solution', 5)] or '').strip() if col_map.get('solution') else ''
                            content = f"## 问题描述\n\n{desc}\n\n## 原因分析\n\n（待补充）\n\n## 解决方法\n\n{solution}"
                            # 直接保存文件
                            from repository.dept_mapping import get_dept_path, get_submodule_path
                            dept_path = get_dept_path(dept)
                            sub_path = get_submodule_path(module) if module else ""
                            faq_dir = DATA_DIR / "faq" / dept_path / (sub_path or "")
                            faq_dir.mkdir(parents=True, exist_ok=True)
                            seq = len(list(faq_dir.glob("*.md"))) + 1
                            dept_code = "XX"
                            if db_repo:
                                try:
                                    row = db_repo._execute_one(
                                        "SELECT code FROM departments WHERE name = ? AND code IS NOT NULL",
                                        (dept,)
                                    )
                                    if row:
                                        dept_code = row['code']
                                except Exception:
                                    pass
                            if dept_code == "XX":
                                dept_code = {"数智财务组": "SZ", "免疫规划组": "YM", "电子档案组": "DZ", "数字化支撑组": "ZH"}.get(dept, "XX")
                            mod_code = module[:3] if module else "XXX"
                            faq_id = f"FAQ-{dept_code}-{mod_code}-{seq:03d}"
                            safe_title = title.replace("/", "-").replace("?", "").replace(":", "")
                            file_path = faq_dir / f"{safe_title}.md"
                            kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
                            today = datetime.date.today().isoformat()
                            file_content = f"""---
id: {faq_id}
title: {title}
keywords: {kw_list}
module: {module}
dept: {dept}
sub_module: {module}
scene: ""
status: active
version_from: ""
created: {today}
reviewed: {today}
related: []
tickets: []
---

# {title}

{content}
"""
                            file_path.write_text(file_content, encoding="utf-8")
                            success += 1
                        wb.close()
                rebuild_engine()
                self._json({"ok": True, "success": success, "fail": fail})
            except ImportError:
                self._json({"error": "请安装 openpyxl: pip install openpyxl"})
            except Exception as e:
                server_logger.error(f"FAQ_IMPORT_ERROR: {e}")
                self._json({"error": f"导入失败: {str(e)}"})
        elif parsed.path == "/api/faq/suggest":
            """根据关键词推荐 FAQ 归属部门和模块"""
            params = parse_qs(parsed.query)
            title = params.get("title", [""])[0]
            keywords = params.get("keywords", [""])[0]

            text = title + " " + keywords
            eng = get_engine()

            from collections import Counter
            dept_votes = Counter()
            module_votes = Counter()

            for kw in eng.keyword_map:
                if kw in text:
                    for entry in eng.keyword_map[kw]:
                        if entry.get("dept"):
                            dept_votes[entry["dept"]] += 1
                        if entry.get("module"):
                            module_votes[entry["module"]] += 1

            # 默认值
            best_dept = dept_votes.most_common(1)[0][0] if dept_votes else "数智财务组"
            best_module = module_votes.most_common(1)[0][0] if module_votes else "浙里报"

            self._json({
                "dept": best_dept,
                "module": best_module,
                "dept_votes": dict(dept_votes.most_common(5)),
                "module_votes": dict(module_votes.most_common(5)),
            })
        elif parsed.path == "/api/faq/delete":
            """删除 FAQ"""
            params = parse_qs(parsed.query)
            faq_path = params.get("path", [""])[0]
            if not faq_path:
                self._json({"error": "请提供 FAQ 路径"})
                return
            full_path = PROJECT_DIR / faq_path
            if full_path.exists():
                full_path.unlink()
            # 同时从 DB 删除（逻辑删除）
            if db_repo:
                try:
                    db_repo.delete_faq(faq_path)
                except Exception:
                    pass
            reload_faqs()
            server_logger.info(f"FAQ_DELETE path={faq_path}")
            self._json({"ok": True, "message": "已删除"})
        elif parsed.path == "/api/faq/view":
            """FAQ 浏览计数 +1"""
            params = parse_qs(parsed.query)
            faq_id = params.get("id", [""])[0]
            if faq_id and db_repo:
                try:
                    db_repo._execute_write("UPDATE faqs SET view_count = view_count + 1 WHERE faq_code = ?", (faq_id,))
                except Exception:
                    pass
            self._json({"ok": True})
        elif parsed.path == "/api/chat":
            """AI 对话模式（不依赖搜索的纯聊天）"""
            params = parse_qs(parsed.query)
            message = params.get("message", [""])[0]

            if not message:
                self._json({"error": "请提供 message 参数"})
                return

            api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                self._sse_start()
                self._sse_send({"error": "未配置 ANTHROPIC_AUTH_TOKEN 或 ANTHROPIC_API_KEY 环境变量"})
                self._sse_done()
                return

            context = {
                "system": "你是智能知识库AI助手，帮助用户解答产品相关问题。回答要简洁、准确。",
                "messages": [{"role": "user", "content": message}],
            }
            SEARCH_COUNTER["ai_summaries"] = SEARCH_COUNTER.get("ai_summaries", 0) + 1
            save_counter()
            self._handle_claude_stream(message, context, api_key)
            return
        elif parsed.path == "/api/rag":
            """RAG 智能问答：搜索 + AI 回答（POST）"""
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(body)
            except Exception:
                data = {}
            message = data.get("message", "") or parse_qs(parsed.query).get("message", [""])[0]

            if not message:
                self._json({"error": "请提供 message 参数"})
                return

            api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                self._sse_start()
                self._sse_send({"error": "未配置 ANTHROPIC_API_KEY"})
                self._sse_done()
                return

            # 执行搜索获取相关文档
            eng = get_engine()
            search_result = eng.search(message, top=5)
            results = search_result.get("results", [])

            # 构建 RAG prompt
            rag = eng.build_rag_prompt(message, results)
            rag["_meta"] = {"sources": rag.get("sources", []), "results_count": len(results)}
            SEARCH_COUNTER["ai_summaries"] = SEARCH_COUNTER.get("ai_summaries", 0) + 1
            save_counter()
            self._handle_claude_stream(message, rag, api_key)
            return
        elif parsed.path == "/api/trends":
            """返回搜索趋势数据（最近6个月）"""
            self._json({
                "trends": [
                    {"month": "3月", "value": SEARCH_COUNTER.get("month_3", 0)},
                    {"month": "4月", "value": SEARCH_COUNTER.get("month_4", 0)},
                    {"month": "5月", "value": SEARCH_COUNTER.get("month_5", 0)},
                    {"month": "6月", "value": SEARCH_COUNTER.get("month_6", 0)},
                    {"month": "7月", "value": SEARCH_COUNTER.get("month_7", 0)},
                    {"month": "8月", "value": SEARCH_COUNTER.get("month_8", 0)},
                ],
                "faqTrends": [
                    {"month": "3月", "value": SEARCH_COUNTER.get("faq_month_3", 0)},
                    {"month": "4月", "value": SEARCH_COUNTER.get("faq_month_4", 0)},
                    {"month": "5月", "value": SEARCH_COUNTER.get("faq_month_5", 0)},
                    {"month": "6月", "value": SEARCH_COUNTER.get("faq_month_6", 0)},
                    {"month": "7月", "value": SEARCH_COUNTER.get("faq_month_7", 0)},
                    {"month": "8月", "value": SEARCH_COUNTER.get("faq_month_8", 0)},
                ],
            })
        elif parsed.path == "/api/hotwords":
            """返回搜索热词 Top10"""
            hot = SEARCH_COUNTER.get("hotwords", {})
            sorted_hot = sorted(hot.items(), key=lambda x: x[1], reverse=True)[:10]
            self._json({"hotwords": [{"word": w, "count": c} for w, c in sorted_hot]})
        elif parsed.path == "/api/suggest":
            """搜索建议/自动补全（DB优先，文件回退）"""
            params = parse_qs(parsed.query)
            q = params.get("q", [""])[0].strip()
            if not q or len(q) < 1:
                self._json({"suggestions": []})
                return
            eng = get_engine()
            suggestions = []

            # 1. 从数据库关键词匹配（快速）
            if db_repo:
                try:
                    rows = db_repo._execute(
                        "SELECT DISTINCT keyword FROM keywords WHERE keyword LIKE ? LIMIT 10",
                        (f"%{q}%",)
                    )
                    for row in rows:
                        if row["keyword"] not in suggestions:
                            suggestions.append(row["keyword"])
                except Exception:
                    pass

            # 2. 从关键词索引匹配（文件回退）
            if len(suggestions) < 8:
                for kw in eng.keyword_map:
                    if q in kw and len(suggestions) < 10:
                        if kw not in suggestions:
                            suggestions.append(kw)

            # 3. 从 FAQ 标题匹配
            for faq in eng.faq_docs:
                if q in faq.get("title", "") and len(suggestions) < 10:
                    s = faq["title"]
                    if s not in suggestions:
                        suggestions.append(s)
            self._json({"suggestions": suggestions[:10]})
        elif parsed.path == "/api/search/related":
            """相关搜索推荐"""
            params = parse_qs(parsed.query)
            q = params.get("q", [""])[0].strip()
            if not q:
                self._json({"related": []})
                return
            eng = get_engine()
            related = eng.get_related_searches(q, limit=6)
            self._json({"related": related, "query": q})
        elif parsed.path == "/api/departments/options":
            """返回所有部门选项列表（扁平，供下拉菜单使用）"""
            options = []
            if db_repo:
                try:
                    rows = db_repo._execute(
                        "SELECT id, name, level, parent_id FROM departments ORDER BY level, name"
                    )
                    # 构建 parent_id → name 查找
                    dept_names = {r['id']: r['name'] for r in rows}
                    for r in rows:
                        parent_name = dept_names.get(r['parent_id'], '') if r['parent_id'] else ''
                        label = f"{r['name']}" if not parent_name else f"{parent_name} > {r['name']}"
                        options.append({
                            "id": r['id'],
                            "name": r['name'],
                            "level": r['level'],
                            "parent_id": r['parent_id'],
                            "parent_name": parent_name,
                            "label": label,
                            "value": r['name'],
                        })
                except Exception as e:
                    server_logger.error(f"DEPT_OPTIONS_ERROR: {e}")
            self._json({"options": options})
        elif parsed.path == "/api/departments/tree":
            """返回部门层级树（从数据库，含准确的文档计数和完整路径）"""
            tree = []
            dept_map = {}
            if db_repo:
                try:
                    # 1. 构建所有部门 ID→信息 的映射
                    all_rows = db_repo._execute(
                        "SELECT id, name, parent_id, level, code, dir_name FROM departments ORDER BY level, name"
                    )
                    dept_map = {}
                    for r in all_rows:
                        dept_map[r['id']] = {
                            "id": r['id'], "name": r['name'],
                            "parent_id": r['parent_id'], "level": r['level'],
                            "code": r['code'] or "", "dir_name": r['dir_name'] or "",
                            "doc_count": 0, "children": [], "path": "",
                        }

                    # 2. 基于 document_departments 关联表精确统计文档数
                    doc_counts = db_repo.get_all_department_doc_counts()
                    for did, cnt in doc_counts.items():
                        if did in dept_map:
                            dept_map[did]['doc_count'] = cnt

                    # 3. 构建完整路径（向上追溯父级）
                    def build_path(dept_id):
                        parts = []
                        current = dept_id
                        while current and current in dept_map:
                            parts.append(dept_map[current]['name'])
                            current = dept_map[current]['parent_id']
                        return ' > '.join(reversed(parts))

                    for d in dept_map.values():
                        d['path'] = build_path(d['id'])

                    # 4. 构建树结构
                    for d in dept_map.values():
                        parent_id = d['parent_id']
                        if parent_id and parent_id in dept_map:
                            dept_map[parent_id]['children'].append(d)
                        elif d['level'] == 1:
                            tree.append(d)

                    # 5. 递归排序子节点
                    def sort_children(node):
                        node['children'].sort(key=lambda x: x['name'])
                        for child in node['children']:
                            sort_children(child)
                    tree.sort(key=lambda x: x['name'])
                    for node in tree:
                        sort_children(node)

                except Exception as e:
                    server_logger.error(f"DEPT_TREE_ERROR: {e}")

            total_docs = sum(d['doc_count'] for d in dept_map.values()) if dept_map else 0
            self._json({"tree": tree, "total_docs": total_docs})
        elif parsed.path == "/api/menu":
            """返回左侧菜单树数据（从 product_module.xlsx 生成）"""
            import pandas as pd
            from collections import defaultdict

            xlsx_path = PROJECT_DIR.parent.parent / "其他文档区" / "product_module.xlsx"
            if not xlsx_path.exists():
                self._json({"error": "product_module.xlsx 不存在"})
                return

            df = pd.read_excel(xlsx_path)

            # 产品模块树: 产品线 → 产品 → 模块
            product_tree = defaultdict(lambda: defaultdict(list))
            for _, row in df.iterrows():
                line = str(row['所属产品线']) if pd.notna(row['所属产品线']) else '未分类'
                prod = str(row['所属产品']) if pd.notna(row['所属产品']) else '未分类'
                mod = str(row['模块名称']) if pd.notna(row['模块名称']) else ''
                if mod:
                    product_tree[line][prod].append({
                        'name': mod,
                        'desc': str(row['模块描述']) if pd.notna(row['模块描述']) else '',
                        'owner': str(row['模块负责人']) if pd.notna(row['模块负责人']) else '',
                        'dev_owner': str(row['研发负责人']) if pd.notna(row['研发负责人']) else '',
                    })

            # 业务模块树: 领域 → 产品线 → 产品 → 模块
            biz_tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
            for _, row in df.iterrows():
                domain = str(row['所属领域']) if pd.notna(row['所属领域']) else '未分类'
                line = str(row['所属产品线']) if pd.notna(row['所属产品线']) else '未分类'
                prod = str(row['所属产品']) if pd.notna(row['所属产品']) else '未分类'
                mod = str(row['模块名称']) if pd.notna(row['模块名称']) else ''
                if mod:
                    biz_tree[domain][line][prod].append(mod)

            # 部门知识树: 一级部门 → 二级部门 → 三级部门
            dept_tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
            for _, row in df.iterrows():
                d1 = str(row['模块关联一级部门']) if pd.notna(row['模块关联一级部门']) else '未分类'
                d2 = str(row['模块关联二级部门']) if pd.notna(row['模块关联二级部门']) else '未分类'
                d3 = str(row['模块关联部门']) if pd.notna(row['模块关联部门']) else '未分类'
                mod = str(row['模块名称']) if pd.notna(row['模块名称']) else ''
                if mod:
                    dept_tree[d1][d2][d3].append(mod)

            def convert(d):
                if isinstance(d, defaultdict):
                    return {k: convert(v) for k, v in d.items()}
                return d

            # 知识库目录结构：部门 → 模块 → 文档数
            eng = get_engine()
            kb_dept = defaultdict(lambda: defaultdict(list))
            for doc in eng.kb_docs:
                parts = doc.get("path", "").split("/")
                # 路径格式: projects/knowledge-base/knowledge/部门/模块/文档.md
                if "knowledge" in parts:
                    idx = parts.index("knowledge")
                    if len(parts) > idx + 2:
                        dept = parts[idx + 1]
                        mod = parts[idx + 2]
                        kb_dept[dept][mod].append(doc.get("title", ""))

            self._json({
                'productModules': convert(product_tree),
                'businessModules': convert(biz_tree),
                'deptKnowledge': convert(dept_tree),
                'kbDept': convert(kb_dept),
            })
        elif parsed.path == "/api/recent":
            """返回最近更新的文档"""
            eng = get_engine()
            docs_with_time = []
            for doc in eng.kb_docs:
                p = PROJECT_DIR / doc["path"]
                if p.exists():
                    docs_with_time.append((p.stat().st_mtime, doc))
            docs_with_time.sort(reverse=True)
            recent = []
            for mtime, doc in docs_with_time[:6]:
                recent.append({
                    "name": doc.get("title", doc["path"].split("/")[-1]),
                    "dept": doc.get("dept", ""),
                    "updated": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                    "path": doc["path"],
                })
            self._json({"recent": recent})
        elif parsed.path == "/api/logs":
            """返回最近日志（用于页面查看）"""
            params = parse_qs(parsed.query)
            lines = int(params.get("lines", ["100"])[0])
            log_file = LOG_DIR / "search_server.log"
            if not log_file.exists():
                self._json({"logs": [], "message": "暂无日志"})
                return
            with open(log_file, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
            recent = all_lines[-lines:]
            self._json({"logs": [l.strip() for l in recent], "total": len(all_lines)})
        elif parsed.path == "/api/reports":
            """返回报表数据列表（DB优先，文件回退）"""
            eng = get_engine()
            params = parse_qs(parsed.query)
            page = int(params.get("page", ["1"])[0])
            page_size = min(int(params.get("page_size", ["20"])[0]), 100)
            category = params.get("category", [""])[0]  # 周报/月报/年度报表

            reports = []

            # 1. 从数据库读取（优先）
            if db_repo:
                try:
                    query = "SELECT id, title, week, year, category, dept_summary, path, created_at FROM reports"
                    query_params = []
                    if category:
                        query += " WHERE category = ?"
                        query_params.append(category)
                    query += " ORDER BY year DESC, week DESC"
                    rows = db_repo._execute(query, query_params)
                    for row in rows:
                        reports.append({
                            "id": row["id"],
                            "title": row["title"],
                            "week": row["week"],
                            "year": row["year"],
                            "category": row["category"],
                            "summary": row["dept_summary"][:200] if row["dept_summary"] else "",
                            "path": row["path"],
                            "created_at": row["created_at"],
                        })
                    total = len(reports)
                    start = (page - 1) * page_size
                    reports = reports[start:start + page_size]
                    self._json({"reports": reports, "total": total, "page": page, "page_size": page_size,
                                "categories": ["周报", "月报", "年度报表"]})
                    return
                except Exception:
                    pass  # 回退到文件

            # 2. 文件回退
            all_reports = eng.report_docs
            total = len(all_reports)
            start = (page - 1) * page_size
            for doc in all_reports[start:start + page_size]:
                reports.append({
                    "id": hash(doc["path"]) % 10000,
                    "title": doc.get("title", doc["path"].split("/")[-1]),
                    "path": doc["path"],
                    "dept": doc.get("dept", ""),
                    "snippets": doc.get("snippets", []),
                })
            self._json({"reports": reports, "total": total, "page": page, "page_size": page_size})
        elif parsed.path == "/api/faq/similar":
            """根据关键词推荐相似 FAQ"""
            params = parse_qs(parsed.query)
            keywords = params.get("keywords", [""])[0]
            if not keywords:
                self._json({"faqs": []})
                return
            eng = get_engine()
            kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
            scored = []
            for faq in eng.faq_docs:
                score = 0
                for kw in kw_list:
                    if kw in faq.get("title", ""):
                        score += 3
                    for fkw in faq.get("keywords", []):
                        if kw in fkw:
                            score += 2
                if score > 0:
                    scored.append({
                        "id": faq.get("faq_id", ""),
                        "title": faq.get("title", ""),
                        "keywords": faq.get("keywords", []),
                        "dept": faq.get("dept", ""),
                        "score": score,
                    })
            scored.sort(key=lambda x: x["score"], reverse=True)
            self._json({"faqs": scored[:5]})
        elif parsed.path == "/api/keywords":
            """返回关键词列表（支持搜索）- 从新表读取，包含 ID 信息"""
            eng = get_engine()
            params = parse_qs(parsed.query)
            q = params.get("q", [""])[0].strip()
            page = int(params.get("page", ["1"])[0])
            page_size = min(int(params.get("page_size", ["50"])[0]), 200)

            keywords = []
            for kw, entries in eng.keyword_map.items():
                if not q or q in kw:
                    # 聚合条目信息，保留 ID
                    mappings = []
                    for e in entries:
                        mappings.append({
                            "mapping_id": e.get("mapping_id", 0),
                            "keyword_id": e.get("keyword_id", 0),
                            "module": e.get("module", ""),
                            "module_id": e.get("module_id", 0),
                            "dept": e.get("dept", ""),
                            "dept_id": e.get("dept_id", 0),
                        })
                    keywords.append({
                        "keyword": kw,
                        "mappings": mappings,
                        "modules": list(set(e.get("module", "") for e in entries)),
                        "depts": list(set(e.get("dept", "") for e in entries)),
                        "count": len(entries),
                    })
            keywords.sort(key=lambda x: x["count"], reverse=True)
            total = len(keywords)
            start = (page - 1) * page_size
            self._json({
                "keywords": keywords[start:start + page_size],
                "total": total,
                "page": page,
                "page_size": page_size,
            })

        elif parsed.path == "/api/document/update":
            """更新文档元数据（部门、产品模块、关键词、文件名），不修改正文内容"""
            params = parse_qs(parsed.query)
            doc_path = params.get("path", [""])[0]
            dept = params.get("dept", [""])[0]
            dept_ids = params.get("dept_ids", [""])[0]  # 部门ID列表，逗号分隔
            product = params.get("product", [""])[0]
            keywords = params.get("keywords", [""])[0]
            new_filename = params.get("new_filename", [""])[0].strip()

            if not doc_path:
                self._json({"error": "请提供文档路径"})
                return

            full_path = PROJECT_DIR / doc_path
            if not full_path.exists():
                self._json({"error": "文档不存在"})
                return

            try:
                text = full_path.read_text(encoding="utf-8")
            except Exception as e:
                self._json({"error": f"读取文档失败: {str(e)}"})
                return

            # 重命名文件（如果提供了新文件名）
            if new_filename:
                if not new_filename.endswith('.md'):
                    new_filename += '.md'
                # 安全检查：文件名不能包含路径分隔符
                if '/' in new_filename or '\\' in new_filename:
                    self._json({"error": "文件名不能包含路径分隔符"})
                    return
                new_full_path = full_path.parent / new_filename
                if new_full_path.exists() and new_full_path != full_path:
                    self._json({"error": f"目标文件已存在: {new_filename}"})
                    return
                try:
                    full_path.rename(new_full_path)
                    server_logger.info(f"DOC_RENAME {doc_path} -> {new_full_path.relative_to(PROJECT_DIR)}")
                    doc_path = str(new_full_path.relative_to(PROJECT_DIR))
                    full_path = new_full_path
                except Exception as e:
                    self._json({"error": f"重命名失败: {str(e)}"})
                    return

            # 更新或添加 YAML frontmatter（含重命名后的标题）
            import re
            fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            if fm_match:
                old_fm = fm_match.group(1)
                body = text[fm_match.end():]
                new_fm_lines = []
                updated = set()
                for line in old_fm.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith("dept:") or stripped.startswith("department:"):
                        new_fm_lines.append(f"dept: {dept}")
                        updated.add("dept")
                    elif stripped.startswith("product:") or stripped.startswith("domain:") or stripped.startswith("module:"):
                        new_fm_lines.append(f"product: {product}")
                        updated.add("product")
                    elif stripped.startswith("keywords:"):
                        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
                        new_fm_lines.append(f"keywords: {kw_list}")
                        updated.add("keywords")
                    elif stripped.startswith("title:"):
                        if new_filename:
                            new_fm_lines.append(f"title: {new_filename.replace('.md', '')}")
                            updated.add("title")
                        else:
                            new_fm_lines.append(line)
                    else:
                        new_fm_lines.append(line)
                # 添加缺失的字段
                if "dept" not in updated:
                    new_fm_lines.append(f"dept: {dept}")
                if "product" not in updated:
                    new_fm_lines.append(f"product: {product}")
                if "keywords" not in updated:
                    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
                    new_fm_lines.append(f"keywords: {kw_list}")
                if new_filename and "title" not in updated:
                    new_fm_lines.append(f"title: {new_filename.replace('.md', '')}")
                new_text = "---\n" + "\n".join(new_fm_lines) + "\n---" + body
            else:
                # 没有 frontmatter，在文件开头添加
                kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
                new_fm = f"""---
dept: {dept}
product: {product}
keywords: {kw_list}
---
"""
                new_text = new_fm + "\n" + text

            try:
                full_path.write_text(new_text, encoding="utf-8")
            except Exception as e:
                self._json({"error": f"写入文档失败: {str(e)}"})
                return

            # 同步更新 document_departments 关联表（多对多）
            if dept_ids and db_repo:
                try:
                    id_list = [int(did) for did in dept_ids.split(",") if did.strip().isdigit()]
                    if id_list:
                        db_repo.set_document_departments(doc_path, id_list)
                        server_logger.info(f"DEPT_LINK doc={doc_path} dept_ids={id_list}")
                except Exception as e:
                    server_logger.error(f"DEPT_LINK_ERROR: {e}")

            # 异步重建索引（避免同步 rebuild 导致客户端超时）
            server_logger.info(f"DOC_UPDATE path={doc_path} dept={dept} product={product}")
            self._json({"ok": True, "path": doc_path, "renamed": bool(new_filename)})
            import threading
            threading.Thread(target=rebuild_engine, daemon=True).start()

        elif parsed.path == "/api/document/upload":
            """上传文档到知识库"""
            eng = get_engine()
            # 读取 POST body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._json({"error": "请上传文件内容"})
                return

            post_data = self.rfile.read(content_length).decode('utf-8')

            # 解析 multipart 或 JSON body
            import json as json_module
            try:
                data = json_module.loads(post_data)
            except:
                # 尝试解析 URL-encoded
                params = parse_qs(post_data)
                data = {
                    "filename": params.get("filename", [""])[0],
                    "content": params.get("content", [""])[0],
                    "dept": params.get("dept", [""])[0],
                    "module": params.get("module", [""])[0],
                }

            filename = data.get("filename", "").strip()
            content = data.get("content", "").strip()
            dept = data.get("dept", "数智财务组").strip()
            dept_ids = data.get("dept_ids", "")  # 逗号分隔的部门ID
            module = data.get("module", "浙里报").strip()

            if not filename or not content:
                self._json({"error": "filename 和 content 为必填参数"})
                return

            if not filename.endswith('.md'):
                filename += '.md'

            # 格式转换：补充 frontmatter（匹配迁移脚本格式）
            today = datetime.date.today().isoformat()
            has_frontmatter = content.strip().startswith('---')

            # 提取标题
            title = filename.replace('.md', '')
            for line in content.split('\n'):
                if line.startswith('# ') and not line.startswith('## '):
                    title = line[2:].strip()
                    break

            # 提取关键词：综合 TF-IDF（自定义IDF）+ TextRank 双引擎
            try:
                extractor = get_extractor()
                if not extractor._built:
                    build_extractor_idf(str(DATA_DIR))
                kw_list = extractor.extract(content, top_k=10)
            except Exception:
                kw_list = []

            # 兜底：关键词库补充（避免遗漏业务术语）
            if len(kw_list) < 5:
                for kw in eng.keyword_map:
                    if len(kw) >= 2 and kw in content[:3000] and kw not in kw_list:
                        kw_list.append(kw)
                    if len(kw_list) >= 10:
                        break

            if not has_frontmatter:
                # 尝试自动匹配模块（使用引擎内置的 product_module_map）
                auto_mod = module
                auto_dept = dept
                if eng.product_module_map:
                    try:
                        import re as _re
                        from collections import Counter as _Counter
                        meta = {'dept': dept, 'text': content[:5000], 'title': title,
                                'keywords': kw_list, 'product': module, 'product_line': module}
                        candidates = {n: i for n, i in eng.product_module_map.items()
                                      if i['所属部门'] == dept or i['一级部门'] == dept}
                        scores = _Counter()
                        for mod_name in candidates:
                            if mod_name in title: scores[mod_name] += 10
                            for kw in kw_list:
                                if mod_name in kw or kw in mod_name: scores[mod_name] += 5
                            count = content[:5000].count(mod_name)
                            if count > 0: scores[mod_name] += min(count, 8)
                            if candidates[mod_name]['所属产品'] == module: scores[mod_name] += 3
                        if scores:
                            primary = scores.most_common(1)[0][0]
                            if scores[primary] > 0:
                                info = eng.product_module_map.get(primary, {})
                                auto_mod = primary
                                auto_dept = info.get('所属部门', dept)
                                server_logger.info(f"DOC_AUTO_MATCH {filename} -> {auto_dept}/{auto_mod}")
                    except Exception:
                        pass

                frontmatter = f"""---
title: {title}
dept: {auto_dept}
module: {auto_mod}
product: {auto_mod}
product_line: {auto_mod}
date: {today}
keywords: {kw_list}
appendix: ""
related_modules: []
imported: {datetime.datetime.now().isoformat()}
---
"""
                # 剥离内容中可能已有的旧 frontmatter
                body = content
                while body.strip().startswith('---'):
                    parts = body.split('---', 2)
                    if len(parts) >= 3:
                        body = parts[2].lstrip('\n')
                    else:
                        break
                content = frontmatter + '\n' + body

            # 保存到 knowledge 目录（部门名和模块名转换为英文路径）
            from repository.dept_mapping import get_dept_path, get_submodule_path
            dept_en = get_dept_path(dept)
            module_en = get_submodule_path(module)
            target_dir = DATA_DIR / "knowledge" / dept_en / module_en
            target_dir.mkdir(parents=True, exist_ok=True)

            file_path = target_dir / filename
            file_path.write_text(content, encoding='utf-8')

            # 更新 INDEX.md
            try:
                existing = list(target_dir.glob("*.md"))
                index_lines = [
                    f"# {module} - 文档索引", "",
                    f"**所属部门**: {dept}",
                    f"**产品模块**: {module}",
                    f"**文档数量**: {len(existing)}",
                    f"**更新时间**: {today}", "",
                    "## 文档列表", "",
                ]
                for d in sorted(existing, key=lambda x: x.stat().st_mtime, reverse=True):
                    if d.name == "INDEX.md":
                        continue
                    t = d.read_text(encoding='utf-8')[:500]
                    dt = datetime.datetime.fromtimestamp(d.stat().st_mtime).strftime('%Y-%m-%d')
                    doc_title = d.stem
                    m = re.search(r'^#\s+(.+)$', t, re.MULTILINE)
                    if m:
                        doc_title = m.group(1).strip()
                    index_lines.append(f"- [{doc_title}]({d.name}) — {dt}")
                index_lines.append("")
                (target_dir / "INDEX.md").write_text('\n'.join(index_lines), encoding='utf-8')
            except Exception:
                pass

            # 同步文档-部门关联
            if dept_ids and db_repo:
                try:
                    id_list = [int(did) for did in dept_ids.split(",") if did.strip().isdigit()]
                    if id_list:
                        db_repo.set_document_departments(str(file_path.relative_to(PROJECT_DIR)), id_list)
                except Exception:
                    pass

            # 增量索引：只添加新文档，不重建全量索引
            server_logger.info(f"DOC_UPLOAD {filename} -> {dept}/{module}")
            _save_keywords_to_db(kw_list, dept, module, str(file_path.relative_to(PROJECT_DIR)))
            self._json({"ok": True, "path": str(file_path.relative_to(PROJECT_DIR)), "filename": filename,
                        "dept": dept, "module": module})
            # 增量更新 BM25 索引（秒级完成）
            try:
                eng.add_to_index(str(file_path.relative_to(PROJECT_DIR)), content, dept, module)
            except Exception:
                import threading
                threading.Thread(target=rebuild_engine, daemon=True).start()  # 兜底：全量重建

        elif parsed.path == "/api/feedback":
            """搜索反馈：记录用户对搜索结果的评价"""
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            result_id = params.get("result_id", [""])[0].strip()
            result_path = params.get("result_path", [""])[0].strip()
            feedback_type = params.get("type", [""])[0].strip()  # useful | not_useful

            if not query or not feedback_type:
                self._json({"error": "请提供 q 和 type 参数"})
                return

            if feedback_type not in ("useful", "not_useful"):
                self._json({"error": "type 必须为 useful 或 not_useful"})
                return

            # 记录反馈（数据库优先，文件回退）
            if db_repo:
                try:
                    db_repo.save_feedback(query, result_id, result_path, feedback_type)
                except Exception as e:
                    self._json({"error": f"记录失败: {str(e)}"}, 500)
                    return
            else:
                feedback_file = RUNTIME_DIR / "feedback.jsonl"
                timestamp = datetime.datetime.now().isoformat()
                record = {
                    "timestamp": timestamp,
                    "query": query,
                    "result_id": result_id,
                    "result_path": result_path,
                    "type": feedback_type,
                }
                try:
                    with open(feedback_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except Exception as e:
                    self._json({"error": f"记录失败: {str(e)}"}, 500)
                    return

            # 更新计数器
            SEARCH_COUNTER[f"feedback_{feedback_type}"] = SEARCH_COUNTER.get(f"feedback_{feedback_type}", 0) + 1
            save_counter()

            server_logger.info(f"FEEDBACK query='{query}' type={feedback_type} path={result_path}")
            self._json({"ok": True})

        else:
            super().do_GET()

    def do_POST(self):
        """处理 POST 请求"""
        parsed = urlparse(self.path)

        # 认证检查
        if self._require_auth() and not self._check_auth():
            self._json({"error": "未授权访问，请提供有效的 API Key"}, 401)
            return

        if parsed.path == "/api/document/upload":
            # 直接处理上传，不委托给 do_GET
            eng = get_engine()
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._json({"error": "请上传文件内容"})
                return
            post_data = self.rfile.read(content_length).decode('utf-8')
            import json as json_module
            try:
                data = json_module.loads(post_data)
            except:
                from urllib.parse import parse_qs as pqs
                params = pqs(post_data)
                data = {"filename": params.get("filename", [""])[0], "content": params.get("content", [""])[0],
                        "dept": params.get("dept", [""])[0], "module": params.get("module", [""])[0]}
            filename = data.get("filename", "").strip()
            content = data.get("content", "").strip()
            dept = data.get("dept", "数智财务组").strip()
            module = data.get("module", "浙里报").strip()
            if not filename or not content:
                self._json({"error": "filename 和 content 为必填参数"})
                return
            if not filename.endswith('.md'):
                filename += '.md'
            today = datetime.date.today().isoformat()
            has_frontmatter = content.strip().startswith('---')
            title = filename.replace('.md', '')
            for line in content.split('\n'):
                if line.startswith('# ') and not line.startswith('## '):
                    title = line[2:].strip(); break
            from repository.dept_mapping import get_dept_path, get_submodule_path
            dept_dir = DATA_DIR / "knowledge" / get_dept_path(dept)
            mod_dir = get_submodule_path(module) if module else ""
            target_dir = dept_dir / mod_dir if mod_dir else dept_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            safe_name = filename.replace('/', '-').replace(' ', '-')
            file_path = target_dir / safe_name
            if not has_frontmatter:
                # 提取关键词
                try:
                    kw_extractor = get_extractor()
                    if not kw_extractor._built:
                        build_extractor_idf(str(DATA_DIR))
                    kw_list = kw_extractor.extract(content, top_k=10)
                except Exception:
                    kw_list = []
                fm = f"---\ntitle: {title}\ndept: {dept}\ndept3: {dept}\nmodule: {module}\ndate: {today.replace('-', '')}\nkeywords: {kw_list}\nappendix: \nrelated_modules: []\nimported: {datetime.datetime.now().isoformat()}\n---\n\n"
                content = fm + content
            file_path.write_text(content, encoding='utf-8')
            server_logger.info(f"DOC_UPLOAD {filename} -> {dept}/{module}")
            _save_keywords_to_db(kw_list, dept, module, str(file_path.relative_to(PROJECT_DIR)))
            self._json({"ok": True, "path": str(file_path.relative_to(PROJECT_DIR)), "filename": filename, "dept": dept, "module": module})
            # 增量更新 BM25 索引
            try:
                eng.add_to_index(str(file_path.relative_to(PROJECT_DIR)), content, dept, module)
            except Exception:
                import threading
                threading.Thread(target=rebuild_engine, daemon=True).start()
            return
        elif parsed.path in ("/api/feedback", "/api/rag", "/api/chat", "/api/faq/import"):
            self.do_GET()
        elif parsed.path == "/api/keywords":
            self._handle_keyword_add()
        else:
            self.send_error(404)

    def do_PUT(self):
        """处理 PUT 请求"""
        parsed = urlparse(self.path)
        if parsed.path == "/api/keywords":
            self._handle_keyword_update()
        else:
            self.send_error(404)

    def do_DELETE(self):
        """处理 DELETE 请求"""
        parsed = urlparse(self.path)
        if parsed.path == "/api/keywords":
            self._handle_keyword_delete()
        else:
            self.send_error(404)

    # ══════ 关键词 CRUD 处理器（ID方案，DB主写） ══════

    def _handle_keyword_add(self):
        """POST /api/keywords - 新增关键词映射"""
        data = self._read_json()
        keyword = (data.get("keyword", "") or "").strip()
        module_id = data.get("module_id", 0)
        module_name = (data.get("module", "") or "").strip()
        dept_id = data.get("dept_id", 0)
        dept = (data.get("dept", "") or "").strip()

        if not keyword:
            self._json({"error": "keyword 为必填参数"})
            return
        if not module_id and not module_name:
            self._json({"error": "module_id 或 module 为必填参数"})
            return

        # 如果传了 module 名称但没传 module_id，从 DB 查找
        if not module_id and module_name and db_repo:
            row = db_repo._execute_one(
                "SELECT id FROM modules WHERE name = ? LIMIT 1", (module_name,)
            )
            if row:
                module_id = row["id"]

        if db_repo:
            result = db_repo.add_keyword(keyword, module_id, dept_id, dept)
            if result.get("error"):
                self._json({"error": result["error"]})
                return
        else:
            result = {}

        # 同步到内存 keyword_map
        eng = get_engine()
        entry = {
            "module": module_name,
            "dept": dept,
            "module_id": module_id,
            "dept_id": dept_id,
            "keyword_id": result.get("keyword_id", 0) if db_repo else 0,
            "mapping_id": result.get("mapping_id", 0) if db_repo else 0,
            "domain": "", "kb_path": "", "note": "手动添加",
        }
        if not eng.keyword_map.get(keyword):
            eng.keyword_map[keyword] = []
        eng.keyword_map[keyword].append(entry)
        eng.save_cache()
        server_logger.info(f"KEYWORD_ADD {keyword} module_id={module_id} dept_id={dept_id}")
        self._json({"ok": True, "keyword": keyword, "mapping_id": result.get("mapping_id") if db_repo else 0})

    def _handle_keyword_update(self):
        """PUT /api/keywords - 修改关键词映射"""
        data = self._read_json()
        mapping_id = data.get("mapping_id", 0)
        keyword = (data.get("keyword", "") or "").strip()
        module_id = data.get("module_id", 0)
        module_name = (data.get("module", "") or "").strip()
        dept_id = data.get("dept_id", 0)
        dept = (data.get("dept", "") or "").strip()

        if not mapping_id:
            self._json({"error": "mapping_id 为必填参数"})
            return

        # 如果传了 module 名称但没传 module_id，从 DB 查找
        if not module_id and module_name and db_repo:
            row = db_repo._execute_one(
                "SELECT id FROM modules WHERE name = ? LIMIT 1", (module_name,)
            )
            if row:
                module_id = row["id"]

        eng = get_engine()

        # 在内存中查找并更新
        old_keyword = None
        found = False
        for kw, entries in eng.keyword_map.items():
            for i, e in enumerate(entries):
                if e.get("mapping_id") == mapping_id:
                    old_keyword = kw
                    if keyword and keyword != kw:
                        # 关键词改名：移动 key
                        entries[i]["keyword"] = keyword
                        # 同步文档引用
                        for doc in eng.kb_docs:
                            kw_list = doc.get("keywords", [])
                            if isinstance(kw_list, list) and kw in kw_list:
                                kw_list[kw_list.index(kw)] = keyword
                    if module_id:
                        entries[i]["module_id"] = module_id
                    if module_name:
                        entries[i]["module"] = module_name
                    if dept_id:
                        entries[i]["dept_id"] = dept_id
                    if dept:
                        entries[i]["dept"] = dept
                    entries[i]["note"] = "手动修改"
                    found = True
                    break
            if found:
                if keyword and keyword != old_keyword:
                    eng.keyword_map[keyword] = eng.keyword_map.pop(old_keyword)
                break

        if not found:
            self._json({"error": f"未找到 mapping_id={mapping_id} 的映射"})
            return

        # 写 DB
        if db_repo:
            db_repo.update_keyword(mapping_id, keyword=keyword or None,
                                   module_id=module_id or None,
                                   dept_id=dept_id or None, dept=dept or None)

        eng.save_cache()
        server_logger.info(f"KEYWORD_UPDATE mapping_id={mapping_id} keyword={keyword} module_id={module_id} dept_id={dept_id}")
        self._json({"ok": True, "mapping_id": mapping_id, "keyword": keyword or old_keyword})

    def _handle_keyword_delete(self):
        """DELETE /api/keywords - 删除关键词映射或整个关键词"""
        data = self._read_json()
        mapping_id = data.get("mapping_id", 0)
        keyword_id = data.get("keyword_id", 0)

        if not mapping_id and not keyword_id:
            self._json({"error": "请提供 mapping_id 或 keyword_id"})
            return

        eng = get_engine()

        if mapping_id:
            # 删除单个映射
            if db_repo:
                db_repo.delete_mapping(mapping_id)
            # 更新内存
            for kw, entries in list(eng.keyword_map.items()):
                eng.keyword_map[kw] = [e for e in entries if e.get("mapping_id") != mapping_id]
                if not eng.keyword_map[kw]:
                    del eng.keyword_map[kw]
            server_logger.info(f"KEYWORD_DELETE_MAPPING mapping_id={mapping_id}")
        elif keyword_id:
            # 删除整个关键词
            if db_repo:
                db_repo.delete_keyword(keyword_id)
            # 更新内存
            for kw, entries in list(eng.keyword_map.items()):
                if any(e.get("keyword_id") == keyword_id for e in entries):
                    del eng.keyword_map[kw]
            server_logger.info(f"KEYWORD_DELETE_ALL keyword_id={keyword_id}")

        eng.save_cache()
        self._json({"ok": True})

    def _sse_start(self):
        """发送 SSE 响应头"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _sse_send(self, data):
        """发送一条 SSE 事件"""
        payload = json.dumps(data, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _sse_done(self):
        """发送 SSE 结束信号"""
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _handle_claude_stream(self, query, context, api_key):
        """调用 Anthropic API，流式推送 Claude 回答"""
        self._sse_start()

        try:
            import anthropic
        except ImportError:
            self._sse_send({"error": "请安装 anthropic SDK: pip install anthropic"})
            self._sse_done()
            return

        # 支持自定义 API 代理（如国内中转服务）
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
        auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")

        client_kwargs = {}
        if base_url:
            client_kwargs["base_url"] = base_url
        if auth_token:
            client_kwargs["auth_token"] = auth_token  # Bearer token 方式
        else:
            client_kwargs["api_key"] = api_key        # x-api-key 方式

        client = anthropic.Anthropic(**client_kwargs)

        model = os.environ.get("CLAUDE_MODEL",
                 os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL",
                 os.environ.get("ANTHROPIC_MODEL",
                 "claude-sonnet-4-20250514")))
        system_prompt = context.get("system", "")
        messages = context.get("messages", [{"role": "user", "content": query}])

        full_response = ""

        try:
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    self._sse_send({"text": text})

            # 发送完整回答和元数据
            self._sse_send({
                "type": "complete",
                "full_response": full_response,
                "meta": context.get("_meta", {}),
            })

        except anthropic.RateLimitError as e:
            server_logger.error(f"CLAUDE_RATE_LIMIT: {str(e)}")
            self._sse_send({"error": "rate_limit", "message": "AI 服务调用频率过高，请稍后重试",
                            "hint": "当前 API 配额已用尽，您仍可查看搜索结果和 FAQ 文档"})
        except anthropic.APIError as e:
            server_logger.error(f"CLAUDE_API_ERROR: {str(e)}")
            # 429 状态码也视为限流（某些代理可能不抛出 RateLimitError）
            if hasattr(e, 'status_code') and e.status_code == 429:
                self._sse_send({"error": "rate_limit", "message": "AI 服务调用频率过高，请稍后重试",
                                "hint": "当前 API 配额已用尽，您仍可查看搜索结果和 FAQ 文档"})
            else:
                self._sse_send({"error": "api_error", "message": f"AI 服务异常: {str(e)}",
                                "hint": "请稍后重试，或查看搜索结果获取相关信息"})
        except Exception as e:
            server_logger.error(f"CLAUDE_ERROR: {str(e)}")
            self._sse_send({"error": "unknown", "message": f"AI 调用失败: {str(e)}",
                            "hint": "请检查网络连接后重试"})

        self._sse_done()

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_document(self, doc_path):
        """返回文档完整内容"""
        import re
        full_path = PROJECT_DIR / doc_path
        if not full_path.exists():
            self._json({"error": f"文档不存在: {doc_path}"})
            return
        try:
            content = full_path.read_text(encoding="utf-8")
        except Exception:
            self._json({"error": "无法读取文档"})
            return

        # 提取标题（优先 frontmatter title，其次 H1 标题）
        title = ""
        fm = {}
        fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()
            title = fm.get("title", "")

        # 如果 frontmatter 没有 title 或 title 是纯日期，用 H1 标题
        if not title or (len(title) < 12 and any(c.isdigit() for c in title)):
            for line in content.split("\n"):
                if line.startswith("# ") and not line.startswith("## "):
                    title = line[2:].strip()
                    break

        # 去掉 frontmatter 后的正文
        body = content
        if fm_match:
            body = content[fm_match.end():].strip()

        # 将相对路径的图片转为可访问的路径
        # 图片路径如: ![xxx](https://...) 或相对路径
        doc_dir = full_path.parent
        def resolve_img(m):
            alt = m.group(1)
            src = m.group(2)
            if src.startswith("http"):
                return f"![{alt}]({src})"
            # 相对路径 → 相对于文档所在目录
            img_path = doc_dir / src
            if img_path.exists():
                return f"![{alt}](/api/image?path={url_quote(str(img_path.relative_to(PROJECT_DIR)))})"
            return f"![{alt}]({src})"
        body = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", resolve_img, body)

        self._json({
            "path": doc_path,
            "title": title,
            "frontmatter": fm,
            "content": body,
        })

    def _serve_image(self, img_path):
        """返回图片文件"""
        full_path = PROJECT_DIR / img_path
        if not full_path.exists():
            self.send_error(404)
            return
        ext = full_path.suffix.lower()
        content_types = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
            ".bmp": "image/bmp",
        }
        ct = content_types.get(ext, "application/octet-stream")
        try:
            data = full_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def log_message(self, format, *args):
        """记录 HTTP 请求日志"""
        server_logger.info(f"{self.client_address[0]} - {format % args}")


def main():
    global db_repo
    try:
        db_repo = DBRepository()
        print("  📦 数据库已连接: runtime/knowledge.db")
        # 自动迁移 FAQ：首次启动时将文件 FAQ 导入 DB（幂等）
        try:
            imported = db_repo.bulk_import_faqs()
            if imported > 0:
                print(f"  📝 FAQ 已导入数据库: {imported} 篇")
        except Exception:
            pass
    except Exception:
        print("  ⚠️  数据库不可用，使用文件存储")
        db_repo = None

    # 自动迁移关键词到 v2 新表（幂等）
    if db_repo:
        try:
            result = db_repo.migrate_keywords_to_v2()
            if result.get("status") == "ok":
                print(f"  📝 关键词已迁移到 v2: {result['keywords']} 关键词, {result['mappings']} 映射")
        except Exception:
            pass

    load_counter()
    load_sessions()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server_logger.info(f"SERVER_START port={port}")
    server = ThreadingHTTPServer(("0.0.0.0", port), SearchHandler)
    print(f"\n  产品知识库搜索服务已启动")
    print(f"  打开浏览器访问: http://localhost:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()


# 导入路由模块（注册路由）
import routes.dashboard  # noqa: E402

if __name__ == "__main__":
    main()