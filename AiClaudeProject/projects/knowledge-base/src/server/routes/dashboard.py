"""Dashboard 路由：总览/统计/趋势/最近更新/菜单树/部门树/报表/日志/热词/重建

数据源约定（修复后）：
  - 趋势/热词 ← search_logs 表（/api/search 写入）
  - 日志 ← runtime/logs/kb_server.log（FastAPI 自身日志）
  - 报表 ← reports 表（is_deleted=FALSE）
"""
from collections import defaultdict
from datetime import datetime, timedelta, date

from fastapi import APIRouter, BackgroundTasks, Depends, Query

import main
from auth import verify_token
from config import settings
from repository import DBRepository

router = APIRouter(tags=["仪表盘"])


@router.get("/dashboard")
async def dashboard(user: str = Depends(verify_token)):
    """知识总览仪表盘"""
    if main.search_engine is None:
        return {"error": "搜索引擎未就绪"}

    faq_count = len(main.search_engine.faq_docs)
    kb_count = len([d for d in main.search_engine.kb_docs
                    if not d.get('path', '').startswith('data/faq/')])
    report_count = len(main.search_engine.report_docs) if hasattr(main.search_engine, 'report_docs') else 0

    # 近 7 天搜索次数（search_logs 表）
    week_questions = 0
    try:
        repo = DBRepository()
        since = (date.today() - timedelta(days=7)).isoformat()
        row = repo._execute_one(
            "SELECT COUNT(*) AS c FROM search_logs WHERE created_at >= :since", {"since": since})
        week_questions = row["c"] if row else 0
    except Exception:
        pass

    return {
        "totalDocs": kb_count + faq_count + report_count,
        "faqCount": faq_count,
        "totalKbDocs": kb_count,
        "totalReports": report_count,
        "weekQuestions": week_questions,
        "weekNew": kb_count,
        "weekNewGrowth": 0,
        "aiMatchConfidence": 92,
    }


@router.get("/stats")
async def stats(user: str = Depends(verify_token)):
    """系统统计"""
    if main.search_engine is None:
        return {"error": "搜索引擎未就绪"}

    today_questions = 0
    counters = {}
    try:
        repo = DBRepository()
        row = repo._execute_one(
            "SELECT COUNT(*) AS c FROM search_logs WHERE created_at >= :since",
            {"since": date.today().isoformat()})
        today_questions = row["c"] if row else 0
        counters = repo.get_all_counters()
    except Exception:
        pass

    def counter(key):
        v = counters.get(key, 0)
        return int(v) if v is not None else 0

    useful = counter("feedback_useful")
    not_useful = counter("feedback_not_useful")
    satisfaction = round(useful / (useful + not_useful) * 100) if (useful + not_useful) > 0 else None

    return {
        "totalDocs": len([d for d in main.search_engine.kb_docs
                          if not d.get('path', '').startswith('data/faq/')]),
        "faqCount": len(main.search_engine.faq_docs),
        "modules": len(main.search_engine.module_map),
        "keywords": len(main.search_engine.keyword_map),
        "today_questions": today_questions,
        "faq_hits": counter("faq_hits"),
        "ai_summaries": counter("ai_summaries"),
        "satisfaction": satisfaction,  # 有用反馈占比（%），无反馈为 null
    }


@router.get("/trends")
async def trends(days: int = 7, user: str = Depends(verify_token)):
    """搜索趋势（search_logs 表按日聚合）"""
    daily = {}
    try:
        repo = DBRepository()
        since = (date.today() - timedelta(days=days - 1)).isoformat()
        rows = repo._execute(
            "SELECT CAST(created_at AS DATE) AS d, COUNT(*) AS c FROM search_logs "
            "WHERE created_at >= :since GROUP BY CAST(created_at AS DATE)",
            {"since": since})
        for r in rows:
            key = str(r["d"])[:10]
            daily[key] = r["c"]
    except Exception:
        pass
    today = date.today()
    return {
        "trends": [
            {"date": (today - timedelta(days=i)).isoformat(),
             "count": daily.get((today - timedelta(days=i)).isoformat(), 0)}
            for i in range(days - 1, -1, -1)
        ]
    }


@router.get("/recent")
async def recent(user: str = Depends(verify_token)):
    """最近更新（排除 [FAQ] 条目，与 documents/dashboard 口径一致）"""
    if main.search_engine is None:
        return {"recent": []}

    docs = []
    for doc in main.search_engine.kb_docs:
        p = doc.get("path", "")
        if p.startswith("data/faq/"):
            continue
        full = settings.PROJECT_DIR / p
        try:
            mtime = datetime.fromtimestamp(full.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if full.exists() \
                else datetime.now().strftime("%Y-%m-%d %H:%M")
        except Exception:
            mtime = datetime.now().strftime("%Y-%m-%d %H:%M")
        docs.append({
            "title": doc.get("title", ""),
            "path": p,
            "dept": doc.get("dept", ""),
            "updated": mtime,
        })
    docs.sort(key=lambda x: x["updated"], reverse=True)
    return {"recent": docs[:6]}


@router.get("/menu")
async def menu(user: str = Depends(verify_token)):
    """左侧菜单树（统一从数据库 modules 表读取）"""
    repo = DBRepository()

    rows = repo._execute("""
        SELECT m.name as module_name, m.description, m.dev_owner, m.module_owner,
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

    all_depts = repo._execute("SELECT id, name, parent_id, level FROM departments")
    dept_map = {d["id"]: d for d in all_depts}

    # 产品模块树: 产品线 → 产品 → 模块
    product_tree = defaultdict(lambda: defaultdict(list))
    for r in rows:
        line = r["product_line_name"] or "未分类"
        prod = r["product_name"] or "未分类"
        mod = r["module_name"]
        if mod:
            product_tree[line][prod].append({
                "name": mod,
                "desc": r["description"] or "",
                "owner": r["module_owner"] or "",
                "dev_owner": r["dev_owner"] or "",
            })

    # 业务模块树: 领域 → 产品线 → 产品 → 模块
    biz_tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        domain = r["business_domain"] or "未分类"
        line = r["product_line_name"] or "未分类"
        prod = r["product_name"] or "未分类"
        mod = r["module_name"]
        if mod:
            biz_tree[domain][line][prod].append(mod)

    # 部门知识树: 一级部门 → 二级部门 → 三级部门 → 模块
    dept_tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        dept_id = r["dept_id"]
        if not dept_id:
            continue
        chain = []
        current_id = dept_id
        while current_id and current_id in dept_map:
            chain.append(dept_map[current_id])
            current_id = dept_map[current_id].get("parent_id")

        if len(chain) >= 3:
            d1, d2, d3 = chain[2]["name"], chain[1]["name"], chain[0]["name"]
        elif len(chain) == 2:
            d1, d2, d3 = chain[1]["name"], chain[0]["name"], chain[0]["name"]
        else:
            d1 = d2 = d3 = chain[0]["name"] if chain else "未分类"

        mod = r["module_name"]
        if mod:
            dept_tree[d1][d2][d3].append(mod)

    def convert(d):
        if isinstance(d, defaultdict):
            return {k: convert(v) for k, v in d.items()}
        return d

    # kb_dept: 从搜索引擎 kb_docs 路径解析
    kb_dept = defaultdict(lambda: defaultdict(list))
    if main.search_engine:
        for doc in main.search_engine.kb_docs:
            parts = doc.get("path", "").split("/")
            if "knowledge" in parts:
                idx = parts.index("knowledge")
                if len(parts) > idx + 2:
                    kb_dept[parts[idx + 1]][parts[idx + 2]].append(doc.get("title", ""))

    return {
        "productModules": convert(product_tree),
        "businessModules": convert(biz_tree),
        "deptKnowledge": convert(dept_tree),
        "kbDept": convert(kb_dept),
    }


@router.get("/departments/tree")
async def departments_tree(user: str = Depends(verify_token)):
    """部门树（嵌套结构，含 doc_count）"""
    repo = DBRepository()
    rows = repo._execute(
        "SELECT id, name, parent_id, level, code, dir_name FROM departments ORDER BY level, name"
    )
    try:
        doc_counts = repo.get_all_department_doc_counts()  # {department_id: count}
    except Exception:
        doc_counts = {}

    dept_map = {}
    for r in rows:
        dept_map[r["id"]] = {
            "id": r["id"], "name": r["name"],
            "parent_id": r["parent_id"], "level": r["level"],
            "code": r["code"] or "", "dir_name": r["dir_name"] or "",
            "doc_count": doc_counts.get(r["id"], 0), "children": [],
        }

    tree = []
    for r in rows:
        node = dept_map[r["id"]]
        parent_id = r["parent_id"]
        if parent_id and parent_id in dept_map:
            dept_map[parent_id]["children"].append(node)
        else:
            tree.append(node)

    return {"tree": tree, "total_docs": sum(doc_counts.values())}


@router.get("/departments/options")
async def departments_options(user: str = Depends(verify_token)):
    """部门选项（含层级与父级名称）"""
    repo = DBRepository()
    rows = repo._execute(
        "SELECT id, name, parent_id, level, code, dir_name FROM departments ORDER BY level, name"
    )
    name_map = {r["id"]: r["name"] for r in rows}
    options = []
    for r in rows:
        parent_name = name_map.get(r["parent_id"], "") if r["parent_id"] else ""
        options.append({
            "name": r["name"],
            "dir_name": r["dir_name"] or "",
            "code": r["code"] or "",
            "id": r["id"],
            "level": r["level"],
            "parent_name": parent_name,
            "label": f"{parent_name} > {r['name']}" if parent_name else r["name"],
        })
    return {"options": options}


@router.get("/rebuild")
async def rebuild_index(background_tasks: BackgroundTasks, user: str = Depends(verify_token)):
    """重建索引（后台异步执行，不阻塞请求）"""
    def _rebuild():
        try:
            if main.search_engine is not None:
                import shutil
                cache_dir = settings.RUNTIME_DIR / "cache"
                for f in cache_dir.glob("*"):
                    if f.is_file():
                        f.unlink()
                # 先完整构建新引擎，再原子替换，避免加载期间请求打到半成品引擎
                new_engine = type(main.search_engine)()
                new_engine.load_all()
                main.search_engine = new_engine
        except Exception:
            pass

    background_tasks.add_task(_rebuild)
    return {"ok": True, "message": "索引重建已启动（后台执行）"}


@router.get("/reports")
async def reports(
    page: int = Query(1),
    page_size: int = Query(20, le=100),
    category: str = Query(""),
    user: str = Depends(verify_token),
):
    """报表列表（reports 表，支持分类与分页）"""
    import json as _json
    repo = DBRepository()
    query = ("SELECT id, title, week, year, category, dept_summary, path, created_at "
             "FROM reports WHERE is_deleted = FALSE")
    params = []
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY year DESC NULLS LAST, week DESC"
    try:
        rows = repo._execute(query, params)
        all_reports = []
        for row in rows:
            ds = row["dept_summary"]
            all_reports.append({
                "id": row["id"],
                "title": row["title"],
                "week": row["week"],
                "year": row["year"],
                "category": row["category"],
                "summary": (_json.dumps(ds, ensure_ascii=False)[:200] if ds else ""),
                "path": row["path"],
                "created_at": str(row["created_at"]) if row["created_at"] else "",
            })
        total = len(all_reports)
        start = (page - 1) * page_size
        return {"reports": all_reports[start:start + page_size], "total": total,
                "page": page, "page_size": page_size,
                "categories": ["周报", "月报", "年度报表"]}
    except Exception:
        # 文件回退
        if main.search_engine is None:
            return {"reports": [], "total": 0}
        docs = [{"title": d.get("title", ""), "path": d.get("path", "")}
                for d in main.search_engine.report_docs]
        return {"reports": docs, "total": len(docs), "categories": ["周报", "月报", "年度报表"]}


@router.get("/logs")
async def logs(lines: int = Query(100, le=1000), user: str = Depends(verify_token)):
    """服务日志（FastAPI 自身日志 kb_server.log）"""
    log_file = settings.RUNTIME_DIR / "logs" / "kb_server.log"
    if not log_file.exists():
        return {"logs": [], "total": 0}
    all_lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    return {"logs": [l.strip() for l in all_lines[-lines:]], "total": len(all_lines)}


@router.get("/hotwords")
async def hotwords(days: int = 7, limit: int = 20, user: str = Depends(verify_token)):
    """搜索热词（search_logs 表最近 N 天 GROUP BY）"""
    repo = DBRepository()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        rows = repo._execute(
            "SELECT query, COUNT(*) as cnt FROM search_logs "
            "WHERE created_at >= :since AND query IS NOT NULL AND query != '' "
            "GROUP BY query ORDER BY cnt DESC LIMIT :limit",
            {"since": since, "limit": limit}
        )
        return {"hotwords": [{"word": r["query"], "count": r["cnt"]} for r in rows]}
    except Exception:
        return {"hotwords": []}
