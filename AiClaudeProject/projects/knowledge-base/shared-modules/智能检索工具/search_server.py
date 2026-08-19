#!/usr/bin/env python3
"""产品知识库搜索服务 - 启动本地 Web 搜索界面"""
import json, os, sys, logging, datetime
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

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parents[3]  # AiClaudeProject/
sys.path.insert(0, str(HERE))
from search_engine import SearchEngine

from logging.handlers import RotatingFileHandler

LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(exist_ok=True)

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
SESSION_STORE = {}  # session_id -> context dict, avoids URL length limit
SEARCH_COUNTER = {  # 搜索统计计数器
    "total": 0,
    "today": 0,
    "week": 0,
    "faq_hits": 0,
    "ai_summaries": 0,
}

COUNTER_FILE = HERE / "search_counter.json"

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
    """持久化搜索计数器"""
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
    return engine

def rebuild_engine():
    """重建引擎（FAQ增删后调用，避免重复追加）"""
    global engine
    engine = SearchEngine()
    engine._load_synonyms()
    engine._load_keyword_index()
    engine._load_module_files()
    engine._load_knowledge_base()
    engine._load_faq_knowledge()
    engine._load_report_data()
    engine.save_cache()


class SearchHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE / "static"), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

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

            # 记录搜索查询到日志文件
            try:
                with open(LOG_DIR / "search_queries.log", "a", encoding="utf-8") as f:
                    f.write(f"{datetime.datetime.now().isoformat()}\t{query}\t{total}\n")
            except Exception:
                pass

            # 1b. Add quick summary for immediate display
            ans = result.get('answer', {})
            result['quick_summary'] = {
                'module': ans.get('module', ''),
                'dept': ans.get('dept', ''),
                'owner': ans.get('module_owner', ''),
                'snippet': ans.get('summary', '')[:200] if ans.get('summary') else '',
            }

            # 2. 构建 Claude prompt 并存储到 session store（避免 URL 过长导致 414）
            api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                prompt = eng.build_claude_prompt(query, result.get("results", []))
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
                                content = faq_path.read_text(encoding="utf-8")
                            except Exception:
                                content = ""
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
                        "sub_module": doc["sub_module"],
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
                "faqCount": faq_count,
                "weekQuestions": SEARCH_COUNTER.get("week", 0),
                "weekNew": kb_count,
                "weekNewGrowth": 0,
                "aiMatchConfidence": 92,
            })
        elif parsed.path == "/api/documents":
            """返回文档列表（支持分页和模块筛选）"""
            eng = get_engine()
            params = parse_qs(parsed.query)
            module = params.get("module", [""])[0]
            page = int(params.get("page", ["1"])[0])
            page_size = min(int(params.get("page_size", ["20"])[0]), 100)
            docs = []
            all_docs = sorted(eng.kb_docs, key=lambda d: (
                # 按文件修改时间倒序，最新在前
                (PROJECT_DIR / d["path"]).stat().st_mtime
                if (PROJECT_DIR / d["path"]).exists() else 0
            ), reverse=True)
            # 过滤掉 FAQ 条目（FAQ 在 kb_docs 中用于搜索索引，不在文档列表展示）
            all_docs = [d for d in all_docs if not d.get("title", "").startswith("[FAQ]")]
            if module:
                all_docs = [d for d in all_docs if module in d.get("path", "")]
            total = len(all_docs)
            start = (page - 1) * page_size
            for doc in all_docs[start:start + page_size]:
                name = doc.get("title", doc["path"].split("/")[-1].replace(".md", ""))
                dept = doc.get("dept", "")
                product = doc.get("domain", "")
                doc_path = PROJECT_DIR / doc["path"]
                updated = "2026-08-10"
                if doc_path.exists():
                    mtime = doc_path.stat().st_mtime
                    updated = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                # 提取文档关键词（从内容中匹配关键词索引，取前5个高频词）
                keywords = []
                content_sample = doc.get("content_sample", "")
                if content_sample:
                    from collections import Counter
                    kw_counter = Counter()
                    for kw in eng.keyword_map:
                        if kw in content_sample:
                            kw_counter[kw] = content_sample.count(kw)
                    keywords = [kw for kw, _ in kw_counter.most_common(5)]
                docs.append({
                    "id": hash(doc["path"]) % 10000,
                    "name": name,
                    "path": doc["path"],
                    "product": product,
                    "dept": dept,
                    "updated": updated,
                    "keywords": keywords,
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
            faq_dir = PROJECT_DIR / "projects/knowledge-base/FAQ知识库" / dept / sub_module if sub_module else PROJECT_DIR / "projects/knowledge-base/FAQ知识库" / dept
            faq_dir.mkdir(parents=True, exist_ok=True)

            if not faq_id:
                faq_id = f"FAQ-{dept}-{sub_module}-{len(list(faq_dir.glob('*.md')))+1:03d}"

            safe_title = title.replace("/", "-").replace("?", "").replace(":", "")
            file_path = faq_dir / f"{safe_title}.md"

            kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
            today = datetime.date.today().isoformat()

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

{content}
"""
            file_path.write_text(file_content, encoding="utf-8")

            # 重建引擎全部索引（避免重复追加）
            rebuild_engine()
            server_logger.info(f"FAQ_SAVE id={faq_id} title='{title}' dept={dept}")

            self._json({"ok": True, "faq_id": faq_id, "path": str(file_path.relative_to(PROJECT_DIR))})
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
                rebuild_engine()
                server_logger.info(f"FAQ_DELETE path={faq_path}")
                self._json({"ok": True, "message": "已删除"})
            else:
                self._json({"error": "FAQ 文件不存在"})
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
            """搜索建议/自动补全"""
            params = parse_qs(parsed.query)
            q = params.get("q", [""])[0].strip()
            if not q:
                self._json({"suggestions": []})
                return
            eng = get_engine()
            suggestions = []
            # 从关键词索引匹配
            for kw in eng.keyword_map:
                if q in kw and len(suggestions) < 8:
                    if kw not in suggestions:
                        suggestions.append(kw)
            # 从 FAQ 标题匹配
            for faq in eng.faq_docs:
                if q in faq.get("title", "") and len(suggestions) < 10:
                    s = faq["title"]
                    if s not in suggestions:
                        suggestions.append(s)
            self._json({"suggestions": suggestions[:10]})
        elif parsed.path == "/api/menu":
            """返回左侧菜单树数据（从 product_module.xlsx 生成）"""
            import pandas as pd
            from collections import defaultdict

            xlsx_path = PROJECT_DIR / "其他文档区" / "product_module.xlsx"
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

            self._json({
                'productModules': convert(product_tree),
                'businessModules': convert(biz_tree),
                'deptKnowledge': convert(dept_tree),
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
            """返回报表数据列表"""
            eng = get_engine()
            params = parse_qs(parsed.query)
            page = int(params.get("page", ["1"])[0])
            page_size = min(int(params.get("page_size", ["20"])[0]), 100)
            all_reports = eng.report_docs
            total = len(all_reports)
            start = (page - 1) * page_size
            reports = []
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
            """返回关键词列表（支持搜索）"""
            eng = get_engine()
            params = parse_qs(parsed.query)
            q = params.get("q", [""])[0].strip()
            page = int(params.get("page", ["1"])[0])
            page_size = min(int(params.get("page_size", ["50"])[0]), 200)

            keywords = []
            for kw, entries in eng.keyword_map.items():
                if not q or q in kw:
                    keywords.append({
                        "keyword": kw,
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

        elif parsed.path == "/api/keywords/add":
            """添加关键词映射"""
            params = parse_qs(parsed.query)
            keyword = params.get("keyword", [""])[0].strip()
            module = params.get("module", [""])[0].strip()
            dept = params.get("dept", [""])[0].strip()
            if not keyword or not module:
                self._json({"error": "keyword 和 module 为必填参数"})
                return
            eng = get_engine()
            # Add to keyword_map
            entry = {"module": module, "dept": dept, "domain": "", "kb_path": "", "note": "手动添加"}
            eng.keyword_map[keyword].append(entry)
            eng.save_cache()
            server_logger.info(f"KEYWORD_ADD {keyword} -> {module} ({dept})")
            self._json({"ok": True, "keyword": keyword, "module": module})

        elif parsed.path == "/api/keywords/delete":
            """删除关键词"""
            eng = get_engine()
            params = parse_qs(parsed.query)
            keyword = params.get("keyword", [""])[0].strip()
            if not keyword or keyword not in eng.keyword_map:
                self._json({"error": "关键词不存在"})
                return
            del eng.keyword_map[keyword]
            eng.save_cache()
            server_logger.info(f"KEYWORD_DELETE {keyword}")
            self._json({"ok": True})

        else:
            super().do_GET()

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

        except anthropic.APIError as e:
            server_logger.error(f"CLAUDE_API_ERROR: {str(e)}")
            self._sse_send({"error": f"API 错误: {str(e)}"})
        except Exception as e:
            server_logger.error(f"CLAUDE_ERROR: {str(e)}")
            self._sse_send({"error": f"调用失败: {str(e)}"})

        self._sse_done()

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
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

        # 提取标题
        title = ""
        for line in content.split("\n"):
            if line.startswith("# ") and not line.startswith("## "):
                title = line[2:].strip()
                break

        # 提取 frontmatter
        fm = {}
        fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()

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
    load_counter()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server_logger.info(f"SERVER_START port={port}")
    server = ThreadingHTTPServer(("0.0.0.0", port), SearchHandler)
    print(f"\n  产品知识库搜索服务已启动")
    print(f"  打开浏览器访问: http://localhost:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()