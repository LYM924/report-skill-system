"""Dashboard 路由"""
from fastapi import APIRouter, Depends
from auth import verify_token

router = APIRouter(tags=["仪表盘"])


@router.get("/dashboard")
async def dashboard(user: str = Depends(verify_token)):
    """知识总览仪表盘"""
    import main
    if main.search_engine is None:
        return {"error": "搜索引擎未就绪"}

    # FAQ 同时在 kb_docs 和 faq_docs 中，去重统计
    faq_count = len(main.search_engine.faq_docs)
    kb_count = len([d for d in main.search_engine.kb_docs
                    if not d.get('path', '').startswith('data/faq/')])
    report_count = len(main.search_engine.report_docs) if hasattr(main.search_engine, 'report_docs') else 0

    return {
        "totalDocs": kb_count + faq_count + report_count,
        "faqCount": faq_count,
        "totalKbDocs": kb_count,
        "totalReports": report_count,
        "weekQuestions": 0,
        "weekNew": kb_count,
        "weekNewGrowth": 0,
        "aiMatchConfidence": 92,
    }


@router.get("/stats")
async def stats(user: str = Depends(verify_token)):
    """系统统计"""
    import main
    if main.search_engine is None:
        return {"error": "搜索引擎未就绪"}

    return {
        "totalDocs": len([d for d in main.search_engine.kb_docs
                          if not d.get('path', '').startswith('data/faq/')]),
        "faqCount": len(main.search_engine.faq_docs),
        "modules": len(main.search_engine.module_map),
        "keywords": len(main.search_engine.keyword_map),
    }


@router.get("/trends")
async def trends(days: int = 7, user: str = Depends(verify_token)):
    """搜索趋势（从搜索日志文件读取）"""
    from datetime import date, timedelta
    from config import settings
    from collections import Counter

    today = date.today()
    daily_counts = Counter()

    # 从搜索日志解析每日搜索量
    log_file = settings.RUNTIME_DIR / "logs" / "search_queries.log"
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 1:
                date_str = parts[0][:10]  # YYYY-MM-DD
                daily_counts[date_str] += 1

    return {
        "trends": [
            {"date": (today - timedelta(days=i)).isoformat(), "count": daily_counts.get((today - timedelta(days=i)).isoformat(), 0)}
            for i in range(days)
        ]
    }


@router.get("/recent")
async def recent(user: str = Depends(verify_token)):
    """最近更新"""
    import main
    from datetime import datetime
    if main.search_engine is None:
        return {"recent": []}

    docs = []
    from config import settings
    from pathlib import Path
    for doc in main.search_engine.kb_docs[:12]:
        # 读取文件实际修改时间
        p = settings.PROJECT_DIR / doc["path"]
        if p.exists():
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        else:
            mtime = datetime.now().strftime("%Y-%m-%d %H:%M")
        docs.append({
            "title": doc.get("title", ""),
            "path": doc.get("path", ""),
            "dept": doc.get("dept", ""),
            "updated": mtime,
        })
    return {"recent": docs}


@router.get("/menu")
async def menu(user: str = Depends(verify_token)):
    """左侧菜单树（统一从数据库读取）"""
    from pathlib import Path
    from collections import defaultdict
    from repository import DBRepository

    repo = DBRepository()

    # 查询所有模块及其关联信息
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
        WHERE m.name IS NOT NULL
    """)

    # 获取所有部门（用于构建层级）
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

    # 部门知识树: 一级部门 → 二级部门 → 三级部门
    dept_tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        dept_id = r["dept_id"]
        if not dept_id:
            continue
        # 向上追溯：找到该部门在层级链中的位置
        chain = []
        current_id = dept_id
        while current_id and current_id in dept_map:
            chain.append(dept_map[current_id])
            current_id = dept_map[current_id].get("parent_id")

        # chain[0] 是最底层的部门，chain[-1] 是最顶层的
        if len(chain) >= 3:
            d1_name = chain[2]["name"]  # L1
            d2_name = chain[1]["name"]  # L2
            d3_name = chain[0]["name"]  # L3
        elif len(chain) == 2:
            d1_name = chain[1]["name"]  # L1
            d2_name = chain[0]["name"]  # L2
            d3_name = chain[0]["name"]  # L3 = L2
        else:
            d1_name = chain[0]["name"] if chain else "未分类"
            d2_name = d1_name
            d3_name = d1_name

        mod = r["module_name"]
        if mod:
            dept_tree[d1_name][d2_name][d3_name].append(mod)

    def convert(d):
        if isinstance(d, defaultdict):
            return {k: convert(v) for k, v in d.items()}
        return d

    # kb_dept: 从搜索引擎 kb_docs 路径解析
    import main
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
    """部门树（嵌套结构，含 doc_count 和 children）"""
    from repository import DBRepository
    repo = DBRepository()
    rows = repo._execute(
        "SELECT id, name, parent_id, level, code, dir_name FROM departments ORDER BY level, name"
    )

    # 构建 ID → 节点映射
    dept_map = {}
    for r in rows:
        dept_map[r["id"]] = {
            "id": r["id"], "name": r["name"],
            "parent_id": r["parent_id"], "level": r["level"],
            "code": r["code"] or "", "dir_name": r["dir_name"] or "",
            "doc_count": 0, "children": [],
        }

    # 构建树结构
    tree = []
    for r in rows:
        node = dept_map[r["id"]]
        parent_id = r["parent_id"]
        if parent_id and parent_id in dept_map:
            dept_map[parent_id]["children"].append(node)
        else:
            tree.append(node)

    return {"tree": tree}


@router.get("/departments/options")
async def departments_options(user: str = Depends(verify_token)):
    """部门选项"""
    from repository import DBRepository
    repo = DBRepository()
    rows = repo._execute("SELECT name, dir_name, code FROM departments WHERE code IS NOT NULL ORDER BY name")
    return {"options": [{"name": r["name"], "dir_name": r["dir_name"] or "", "code": r["code"] or ""} for r in rows]}


@router.get("/rebuild")
async def rebuild_index(user: str = Depends(verify_token)):
    """重建索引"""
    import main
    if main.search_engine:
        import shutil
        from config import settings
        cache_dir = settings.RUNTIME_DIR / "cache"
        for f in cache_dir.glob("*"):
            if f.is_file():
                f.unlink()
        main.search_engine = type(main.search_engine)()
        main.search_engine.load_all()
    return {"ok": True, "message": "索引已重建"}


@router.get("/reports")
async def reports(page: int = 1, user: str = Depends(verify_token)):
    """报表列表"""
    import main
    if main.search_engine is None:
        return {"reports": []}
    docs = []
    for doc in main.search_engine.report_docs if hasattr(main.search_engine, 'report_docs') else []:
        docs.append({"title": doc.get("title", ""), "path": doc.get("path", "")})
    return {"reports": docs}


@router.get("/logs")
async def logs(user: str = Depends(verify_token)):
    """日志查看"""
    from pathlib import Path
    from config import settings
    log_file = settings.RUNTIME_DIR / "logs" / "search_server.log"
    if not log_file.exists():
        return {"logs": []}
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    return {"logs": lines[-100:]}


@router.get("/hotwords")
async def hotwords(days: int = 7, limit: int = 20, user: str = Depends(verify_token)):
    """搜索热词（从 search_logs 表统计最近 N 天的热门查询）"""
    from repository import DBRepository
    from datetime import datetime, timedelta
    repo = DBRepository()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        rows = repo._execute(
            "SELECT query, COUNT(*) as cnt FROM search_logs "
            "WHERE created_at >= :since "
            "GROUP BY query ORDER BY cnt DESC LIMIT :limit",
            {"since": since, "limit": limit}
        )
        return {"hotwords": [{"word": r["query"], "count": r["cnt"]} for r in rows]}
    except Exception:
        # 表不存在或数据为空时返回空
        return {"hotwords": []}
