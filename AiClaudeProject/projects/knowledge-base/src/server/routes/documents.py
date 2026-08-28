"""文档管理路由"""
import json, re, os
from datetime import datetime
from fastapi import APIRouter, Query, Depends
from auth import verify_token
from config import settings

router = APIRouter(tags=["文档"])

_mod_cache = None

def _get_module_map():
    global _mod_cache
    if _mod_cache is not None:
        return _mod_cache
    from repository import DBRepository
    repo = DBRepository()
    rows = repo._execute("""
        SELECT m.name as module_name,
               p.name as product_name, pl.name as product_line_name,
               d.name as dept_name, m.business_domain
        FROM modules m
        LEFT JOIN products p ON m.product_id = p.id
        LEFT JOIN product_lines pl ON p.product_line_id = pl.id
        LEFT JOIN departments d ON m.department_id = d.id
    """)
    _mod_cache = {}
    for r in rows:
        if r["module_name"]:
            _mod_cache[r["module_name"]] = {
                "product": r["product_name"] or "",
                "product_line": r["product_line_name"] or "",
                "dept": r["dept_name"] or "",
                "domain": r["business_domain"] or "",
            }
    return _mod_cache

@router.get("/documents")
async def list_documents(
    module: str = Query(""),
    dept_id: str = Query(""),
    page_size: int = Query(200, le=500),
    user: str = Depends(verify_token),
):
    """文档列表"""
    import main
    if main.search_engine is None:
        return {"documents": [], "total": 0}

    mod_map = _get_module_map()
    docs = []
    for doc in main.search_engine.kb_docs:
        doc_path = doc.get("path", "")
        if doc_path.startswith("data/faq/"):
            continue

        full_path = settings.PROJECT_DIR / doc_path
        keywords = []
        updated = ""
        if full_path.exists():
            try:
                mtime = os.path.getmtime(str(full_path))
                updated = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
            try:
                text = full_path.read_text(encoding="utf-8")
                fm = {}
                fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        line = line.strip()
                        if line.startswith("keywords:"):
                            kw_str = line.split(":", 1)[1].strip()
                            try:
                                import ast
                                keywords = ast.literal_eval(kw_str)
                            except Exception:
                                keywords = [k.strip().strip("'\"") for k in kw_str.strip("[]").split(",") if k.strip()]
            except Exception:
                pass

        doc_title = doc.get("title", "")
        cat = {}
        for mod_name, info in mod_map.items():
            if mod_name in doc_title or mod_name in doc_path:
                cat = info
                break

        d = {
            "id": doc_path,
            "name": doc.get("title", ""),
            "path": doc_path,
            "dept": cat.get("dept", doc.get("dept", "")),
            "product": cat.get("product", doc.get("domain", "")),
            "product_line": cat.get("product_line", ""),
            "module": cat.get("module", ""),
            "keywords": keywords,
            "updated": updated,
        }

        name = d["name"]
        if not name or (len(name) < 12 and any(c.isdigit() for c in name) and name.count("-") >= 2):
            try:
                text = full_path.read_text(encoding="utf-8")
                fm_title = ""
                fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split("\n"):
                        if line.strip().startswith("title:"):
                            fm_title = line.split(":", 1)[1].strip()
                            break
                if fm_title and not (len(fm_title) < 12 and all(c in "0123456789 -·." for c in fm_title)):
                    d["name"] = fm_title
                else:
                    for line in text.split("\n"):
                        if line.startswith("# ") and not line.startswith("## "):
                            h1 = line[2:].strip()
                            if h1 and not (len(h1) < 12 and all(c in "0123456789 -·." for c in h1)):
                                d["name"] = h1
                                break
            except Exception:
                pass

        if module:
            if module not in (d["dept"], d["product"], d["product_line"], d["module"]):
                continue

        docs.append(d)

    return {"documents": docs[:page_size], "total": len(docs)}


@router.get("/document")
async def get_document(
    path: str = Query(..., description="文档路径"),
    user: str = Depends(verify_token),
):
    """文档详情"""
    full_path = settings.PROJECT_DIR / path
    if not full_path.exists():
        return {"error": "文档不存在"}
    content = full_path.read_text(encoding="utf-8")
    fm = {}
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return {
        "path": path,
        "content": content,
        "frontmatter": fm,
        "title": fm.get("title", path.split("/")[-1]),
    }
