"""关键词管理路由"""
from fastapi import APIRouter, Query, Depends
from auth import verify_token

router = APIRouter(tags=["关键词"])


@router.get("/keywords")
async def list_keywords(user: str = Depends(verify_token)):
    """关键词列表"""
    import main
    if main.search_engine is None:
        return {"keywords": []}

    keywords = []
    for kw, entries in main.search_engine.keyword_map.items():
        for entry in entries:
            keywords.append({
                "keyword": kw,
                "module": entry.get("module", ""),
                "dept": entry.get("dept", ""),
                "domain": entry.get("domain", ""),
            })
    return {"keywords": keywords}


@router.get("/keywords/add")
async def add_keyword(
    keyword: str = Query(...),
    module: str = Query(...),
    dept: str = Query(""),
    user: str = Depends(verify_token),
):
    """添加关键词"""
    import main
    if main.search_engine is None:
        return {"error": "搜索引擎未就绪"}

    main.search_engine.keyword_map[keyword].append({
        "module": module, "dept": dept, "domain": "", "kb_path": "", "note": "手动添加"
    })
    return {"ok": True}


@router.get("/keywords/delete")
async def delete_keyword(
    keyword: str = Query(...),
    user: str = Depends(verify_token),
):
    """删除关键词"""
    import main
    if main.search_engine is None:
        return {"error": "搜索引擎未就绪"}

    if keyword in main.search_engine.keyword_map:
        del main.search_engine.keyword_map[keyword]
    return {"ok": True}
