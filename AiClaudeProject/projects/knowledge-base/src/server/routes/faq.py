"""FAQ 路由"""
import json
from fastapi import APIRouter, Query, Depends
from auth import verify_token
from config import settings

router = APIRouter(tags=["FAQ"])

PROJECT_DIR = settings.PROJECT_DIR


@router.get("/faq")
async def list_faqs(
    id: str = Query(""),
    user: str = Depends(verify_token),
):
    """FAQ 列表 / 详情"""
    import main
    if main.search_engine is None:
        return {"faqs": [], "error": "搜索引擎未就绪"}

    if id:
        # 返回单个 FAQ
        for doc in main.search_engine.faq_docs:
            if doc.get("faq_id") == id:
                faq_path = PROJECT_DIR / doc["path"]
                if faq_path.exists():
                    raw = faq_path.read_text(encoding="utf-8")
                    content = raw
                    if raw.startswith("---"):
                        parts = raw.split("---", 2)
                        if len(parts) >= 3:
                            content = parts[2].lstrip("\n")
                    return {
                        "title": doc.get("title", ""),
                        "dept": doc.get("dept", ""),
                        "path": doc.get("path", ""),
                        "content": content,
                        "id": id,
                    }
        return {"error": "FAQ 不存在"}

    # 返回列表
    faqs = []
    for doc in main.search_engine.faq_docs:
        faqs.append({
            "id": doc.get("faq_id", ""),
            "title": doc.get("title", ""),
            "dept": doc.get("dept", ""),
            "sub_module": doc.get("sub_module", ""),
            "keywords": doc.get("keywords", []),
            "path": doc.get("path", ""),
        })
    return {"faqs": faqs}


@router.get("/faq/delete")
async def delete_faq(
    path: str = Query(..., description="FAQ 路径"),
    user: str = Depends(verify_token),
):
    """删除 FAQ"""
    import main
    faq_path = PROJECT_DIR / path
    if not faq_path.exists():
        return {"error": "FAQ 不存在"}
    faq_path.unlink()
    # 重建索引
    if search_engine:
        main.search_engine.faq_docs = [d for d in main.search_engine.faq_docs if d.get("path") != path]
        main.search_engine.kb_docs = [d for d in main.search_engine.kb_docs if d.get("path") != path]
    return {"ok": True, "message": "已删除"}


@router.get("/faq/suggest")
async def faq_suggest(
    q: str = Query(""),
    user: str = Depends(verify_token),
):
    """FAQ 归属建议"""
    import main
    if main.search_engine is None:
        return {"suggestions": []}
    suggestions = main.search_engine.suggest(q)
    return {"suggestions": suggestions}


@router.get("/faq/similar")
async def faq_similar(
    path: str = Query(""),
    user: str = Depends(verify_token),
):
    """相似 FAQ 推荐"""
    import main
    if main.search_engine is None:
        return {"similar": []}
    # 简化实现：返回空列表
    return {"similar": []}


@router.get("/faq/save")
async def save_faq(
    id: str = Query(""),
    title: str = Query(""),
    keywords: str = Query(""),
    dept: str = Query(""),
    sub_module: str = Query(""),
    module: str = Query(""),
    content: str = Query(""),
    status: str = Query("draft"),
    user: str = Depends(verify_token),
):
    """保存 FAQ"""
    import datetime, re as _re
    from pathlib import Path
    from repository.dept_mapping import get_dept_path, get_submodule_path
    from keyword_extractor import get_extractor, build_extractor_idf
    from config import settings

    if not title or not dept:
        return {"error": "title 和 dept 为必填参数"}

    dept_path = get_dept_path(dept)
    sub_path = get_submodule_path(sub_module) if sub_module else ""
    faq_dir = settings.DATA_DIR / "faq" / dept_path / (sub_path or "")
    faq_dir.mkdir(parents=True, exist_ok=True)

    if not id:
        dept_codes = {"数智财务组": "SZ", "免疫规划组": "YM", "电子档案组": "DZ", "数字化支撑组": "ZH"}
        dept_code = dept_codes.get(dept, "XX")
        mod_code = sub_module[:3] if sub_module else "XXX"
        existing = list(faq_dir.glob("*.md"))
        id = f"FAQ-{dept_code}-{mod_code}-{len(existing)+1:03d}"

    safe_title = title.replace("/", "-").replace("?", "").replace(":", "")
    file_path = faq_dir / f"{safe_title}.md"

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list and content:
        try:
            extractor = get_extractor()
            if not extractor._built:
                build_extractor_idf(str(settings.DATA_DIR))
            kw_list = extractor.extract(content, top_k=10)
        except Exception:
            kw_list = []

    today = datetime.date.today().isoformat()
    safe_content = content
    if safe_content.strip().startswith("---"):
        parts = safe_content.split("---", 2)
        if len(parts) >= 3:
            safe_content = parts[2].lstrip("\n")

    file_content = f"""---
id: {id}
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
    file_path.write_text(file_content, encoding="utf-8")

    # 重建 FAQ 索引
    import main
    if main.search_engine:
        main.search_engine.faq_docs = []
        main.search_engine._load_faq_knowledge()
        main.search_engine.kb_docs = [d for d in main.search_engine.kb_docs if not d.get('path', '').startswith('data/faq/')]
        for faq in main.search_engine.faq_docs:
            content_sample = faq.get('content_sample', '') or ''
            main.search_engine.kb_docs.append({
                "path": faq.get('path', ''),
                "dept": faq.get('dept', ''),
                "domain": faq.get('sub_module', ''),
                "title": f"[FAQ] {faq.get('title', '')}",
                "content_sample": content_sample[:5000],
            })
        main.search_engine._load_bm25_index()

    return {"ok": True, "faq_id": id, "path": str(file_path.relative_to(settings.PROJECT_DIR))}
