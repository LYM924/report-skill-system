"""Dashboard 路由：总览/统计/趋势/最近更新/菜单树/部门树/报表/日志/热词/重建

数据源约定（修复后）：
  - 趋势/热词 ← search_logs 表（/api/search 写入）
  - 日志 ← runtime/logs/kb_server.log（FastAPI 自身日志）
  - 报表 ← reports 表（is_deleted=FALSE）
"""
from collections import defaultdict
from datetime import datetime, timedelta, date

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse, Response

import main
from auth import verify_token, require_admin
from config import settings
from repository import get_repo
from service.audit import log_action

router = APIRouter(tags=["仪表盘"])


def _cached_response(data: dict, max_age: int = 10):
    """返回带 Cache-Control 头的 JSON 响应"""
    resp = JSONResponse(data)
    resp.headers["Cache-Control"] = f"private, max-age={max_age}"
    return resp


@router.get("/dashboard")
async def dashboard(user: str = Depends(verify_token)):
    """知识总览仪表盘（DB 直查 + Redis 短缓存，与列表数据一致）"""
    from service.cache import cache_get, cache_set, KEY_DASHBOARD
    # 先查缓存
    cached = cache_get(KEY_DASHBOARD)
    if cached:
        return cached

    try:
        repo = get_repo()
        counts = repo.get_active_counts()
        faq_count = counts["faqs"]
        kb_count = counts["documents"]
        report_count = counts["reports"]
    except Exception:
        faq_count = kb_count = report_count = 0

    # 近 7 天搜索次数（search_logs 表）
    week_questions = 0
    try:
        repo = get_repo()
        since = (date.today() - timedelta(days=7)).isoformat()
        week_questions = repo.get_search_log_count_since(since)
    except Exception:
        pass

    result = {
        "totalDocs": kb_count + faq_count + report_count,
        "faqCount": faq_count,
        "totalKbDocs": kb_count,
        "totalReports": report_count,
        "weekQuestions": week_questions,
        "weekNew": kb_count,
        "weekNewGrowth": 0,
        "aiMatchConfidence": 92,
    }
    # 写入缓存（TTL 30s）
    cache_set(KEY_DASHBOARD, result, ttl=30)
    return _cached_response(result, max_age=30)


@router.get("/stats")
async def stats(user: str = Depends(verify_token)):
    """系统统计（DB 直查 + Redis 短缓存，与列表数据一致）"""
    from service.cache import cache_get, cache_set, KEY_STATS
    cached = cache_get(KEY_STATS)
    if cached:
        return cached

    today_questions = 0
    counters = {}
    counts = {}
    try:
        repo = get_repo()
        today_questions = repo.get_search_log_count_since(date.today().isoformat())
        counters = repo.get_all_counters()
        counts = repo.get_active_counts()
    except Exception:
        pass

    def counter(key):
        v = counters.get(key, 0)
        return int(v) if v is not None else 0

    useful = counter("feedback_useful")
    not_useful = counter("feedback_not_useful")
    satisfaction = round(useful / (useful + not_useful) * 100) if (useful + not_useful) > 0 else None

    result = {
        "totalDocs": counts.get("documents", 0),
        "faqCount": counts.get("faqs", 0),
        "modules": 0,  # 模块数从 modules 表统计，不再从内存
        "keywords": counts.get("keywords", 0),
        "today_questions": today_questions,
        "faq_hits": counter("faq_hits"),
        "ai_summaries": counter("ai_summaries"),
        "satisfaction": satisfaction,  # 有用反馈占比（%），无反馈为 null
    }
    cache_set(KEY_STATS, result, ttl=30)
    return _cached_response(result, max_age=30)


@router.get("/trends")
async def trends(days: int = 7, user: str = Depends(verify_token)):
    """搜索趋势（search_logs 表按日聚合）"""
    daily = {}
    try:
        repo = get_repo()
        for item in repo.get_search_trends(days):
            daily[item["date"]] = item["count"]
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
    """最近更新（DB 直查 + Redis 短缓存，排除 FAQ，按 updated_at 倒序）"""
    from service.cache import cache_get, cache_set, KEY_RECENT
    cached = cache_get(KEY_RECENT)
    if cached:
        return cached

    docs = []
    try:
        repo = get_repo()
        rows = repo.get_recent_documents(limit=6)
        for row in rows:
            updated = ""
            if row.get("updated_at"):
                try:
                    updated = str(row["updated_at"])[:16].replace("T", " ")
                except Exception:
                    updated = str(row["updated_at"])
            docs.append({
                "title": row.get("title", ""),
                "path": row.get("path", ""),
                "dept": row.get("dept", ""),
                "updated": updated,
            })
    except Exception:
        pass
    result = {"recent": docs}
    cache_set(KEY_RECENT, result, ttl=10)
    return _cached_response(result, max_age=10)


@router.get("/menu")
async def menu(user: str = Depends(verify_token)):
    """左侧菜单树（统一从数据库 modules 表读取）"""
    repo = get_repo()

    rows, all_depts = repo.get_menu_modules()
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

    # kb_dept: 从 DB documents 表路径解析（替代遍历内存 kb_docs）
    kb_dept = defaultdict(lambda: defaultdict(list))
    try:
        repo = get_repo()
        doc_rows = repo.get_all_documents_raw()
        for doc in doc_rows:
            parts = doc.get("path", "").split("/")
            if "knowledge" in parts:
                idx = parts.index("knowledge")
                if len(parts) > idx + 2:
                    kb_dept[parts[idx + 1]][parts[idx + 2]].append(doc.get("title", ""))
    except Exception:
        pass

    return {
        "productModules": convert(product_tree),
        "businessModules": convert(biz_tree),
        "deptKnowledge": convert(dept_tree),
        "kbDept": convert(kb_dept),
        # 模块扁平选项（前端选择器携带 module_id + 关联字段，支持选择模块后联动填充部门/产品）
        "moduleOptions": [{
            "id": r["module_id"],
            "name": r["module_name"],
            "productId": r.get("product_id"),
            "product": r.get("product_name", ""),
            "productLine": r.get("product_line_name", ""),
            "deptId": r.get("dept_id"),
            "dept": r.get("dept_name", ""),
            "domain": r.get("business_domain", ""),
        } for r in rows if r["module_name"]],
    }


@router.get("/departments/tree")
async def departments_tree(user: str = Depends(verify_token)):
    """部门树（嵌套结构，含 doc_count）"""
    repo = get_repo()
    rows = repo.get_department_tree()
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
    repo = get_repo()
    rows = repo.get_department_tree()
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
async def rebuild_index(background_tasks: BackgroundTasks, user: str = Depends(require_admin)):
    """重建索引（后台异步执行，不阻塞请求）"""
    def _rebuild():
        try:
            if main.search_engine is not None:
                main.search_engine = main.search_engine.rebuild_all()
        except Exception:
            pass

    background_tasks.add_task(_rebuild)
    log_action(user, "system.rebuild")
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
    repo = get_repo()
    try:
        rows = repo.get_reports_page(category)
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
    repo = get_repo()
    try:
        return {"hotwords": repo.get_hot_keywords(days, limit)}
    except Exception:
        return {"hotwords": []}
