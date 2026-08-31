"""关键词管理路由（REST：GET/POST/PUT/DELETE /api/keywords，写 PostgreSQL 双表）

数据模型：
  keywords_v2(id, keyword UNIQUE, is_deleted)           ← 关键词实体
  keyword_mappings(keyword_id, module_id, department_id, department, kb_path, is_deleted) ← 映射
行为约定：
  - 删除均为软删除（is_deleted=TRUE）
  - 添加已软删关键词/映射时自动复活（不产生重复行，靠部分唯一索引 uq_km_kw_mod_active）
  - 内存 keyword_map 与 DB 同步，并落盘 save_cache
"""
from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from auth import verify_token
from repository import DBRepository
from routes.health import record_write_failure

router = APIRouter(tags=["关键词"])


class KeywordCreate(BaseModel):
    keyword: str
    module_id: Optional[int] = 0
    module: str = ""
    dept_id: Optional[int] = 0
    dept: str = ""


class KeywordUpdate(BaseModel):
    mapping_id: int
    keyword: Optional[str] = None
    module_id: Optional[int] = None
    module: str = ""
    dept_id: Optional[int] = None
    dept: str = ""


class KeywordDelete(BaseModel):
    mapping_id: Optional[int] = None
    keyword_id: Optional[int] = None


def _module_id_by_name(repo: DBRepository, module: str):
    if not module:
        return None
    row = repo._execute_one("SELECT id FROM modules WHERE name = ? LIMIT 1", (module,))
    return row["id"] if row else None


def _dept_id_by_name(repo: DBRepository, dept: str):
    """按部门名称解析 departments.id（与文档上传链路一致，保证部门名称+ID 双写）"""
    if not dept:
        return None
    row = repo._execute_one("SELECT id FROM departments WHERE name = ? LIMIT 1", (dept.strip(),))
    return row["id"] if row else None


@router.get("/keywords")
async def list_keywords(
    q: str = Query(""),
    page: int = Query(1),
    page_size: int = Query(200, le=200),
    user: str = Depends(verify_token),
):
    """关键词列表（DB 直查，按关键词聚合映射）"""
    repo = DBRepository()
    rows = repo.get_all_keywords_v2()  # dict: keyword -> [entry...]

    grouped = {}
    for kw, entries in rows.items():
        if q and q not in kw:
            continue
        item = grouped.setdefault(kw, {
            "keyword": kw, "mappings": [], "modules": [], "depts": [],
        })
        for e in entries:
            item["mappings"].append({
                "mapping_id": e.get("mapping_id"),
                "keyword_id": e.get("keyword_id"),
                "module": e.get("module", ""),
                "module_id": e.get("module_id"),
                "dept": e.get("dept", ""),
                "dept_id": e.get("dept_id"),
            })
            if e.get("module") and e["module"] not in item["modules"]:
                item["modules"].append(e["module"])
            if e.get("dept") and e["dept"] not in item["depts"]:
                item["depts"].append(e["dept"])

    items = sorted(grouped.values(), key=lambda x: -len(x["mappings"]))
    for g in items:
        g["count"] = len(g["mappings"])
    total = len(items)
    start = (page - 1) * page_size
    return {"keywords": items[start:start + page_size], "total": total, "page": page, "page_size": page_size}


@router.post("/keywords")
async def add_keyword(body: KeywordCreate, user: str = Depends(verify_token)):
    """添加关键词（写 keywords_v2 + keyword_mappings，软删复活）"""
    import main
    keyword = (body.keyword or "").strip()
    if not keyword:
        return JSONResponse({"error": "keyword 必填"}, status_code=422)
    if not body.module and not body.module_id:
        return JSONResponse({"error": "module 或 module_id 至少一个"}, status_code=422)

    repo = DBRepository()
    module_id = body.module_id or 0
    module_name = body.module or ""
    if not module_id and module_name:
        module_id = _module_id_by_name(repo, module_name) or 0
    # 部门：只传名称时按名称解析 ID，保证 department 名称+ID 双写落库
    dept_id = body.dept_id or 0
    if not dept_id and body.dept:
        dept_id = _dept_id_by_name(repo, body.dept) or 0

    result = repo.add_keyword(keyword, module_id, dept_id, body.dept or "")
    if "error" in result:
        record_write_failure("keyword_write")
        return JSONResponse(result, status_code=400)

    # 同步内存 keyword_map（搜索路由使用）+ 落盘缓存
    if main.search_engine is not None:
        main.search_engine.keyword_map[keyword].append({
            "module": module_name, "dept": body.dept or "", "domain": "", "kb_path": "",
            "note": "手动添加", "mapping_id": result.get("mapping_id"),
            "keyword_id": result.get("keyword_id"),
        })
        try:
            main.search_engine.save_cache()
        except Exception:
            pass
    return {"ok": True, "keyword": keyword, "mapping_id": result.get("mapping_id"),
            "keyword_id": result.get("keyword_id")}


@router.put("/keywords")
async def update_keyword(body: KeywordUpdate, user: str = Depends(verify_token)):
    """更新关键词映射（mapping_id 定位；None/0 清空外键；改名冲突返回 409）"""
    import main
    if not body.mapping_id:
        return JSONResponse({"error": "mapping_id 必填"}, status_code=422)

    repo = DBRepository()
    module_id = body.module_id
    module_name = body.module or ""
    if module_name and module_id in (None, 0):
        module_id = _module_id_by_name(repo, module_name)
    # 部门：传名称未传 ID 时按名称解析（None 且无名称 = 清空外键，保持原语义）
    dept_id = body.dept_id
    if body.dept and dept_id in (None, 0):
        dept_id = _dept_id_by_name(repo, body.dept)

    result = repo.update_keyword(
        body.mapping_id,
        keyword=body.keyword or None,
        module_id=module_id,
        dept_id=dept_id,
        dept=body.dept or "",
    )
    if "error" in result:
        status = 409 if "已存在" in result["error"] else 404
        return JSONResponse(result, status_code=status)

    # 同步内存：改名迁移 key、更新 entry 字段
    if main.search_engine is not None:
        km = main.search_engine.keyword_map
        old_kw = None
        for kw, entries in km.items():
            if any(e.get("mapping_id") == body.mapping_id for e in entries):
                old_kw = kw
                break
        new_kw = (body.keyword or old_kw or "").strip()
        if old_kw is not None and new_kw:
            entries = km.pop(old_kw, [])
            for e in entries:
                if e.get("mapping_id") == body.mapping_id:
                    e["module"] = module_name or e.get("module", "")
                    e["dept"] = body.dept or e.get("dept", "")
            km.setdefault(new_kw, []).extend(entries)
            try:
                main.search_engine.save_cache()
            except Exception:
                pass
    return {"ok": True, "mapping_id": body.mapping_id, "keyword": body.keyword}


@router.delete("/keywords")
async def delete_keyword(body: KeywordDelete, user: str = Depends(verify_token)):
    """删除关键词（mapping_id 删单映射；keyword_id 删全词；均为软删除）"""
    import main
    if not body.mapping_id and not body.keyword_id:
        return JSONResponse({"error": "mapping_id 或 keyword_id 至少一个"}, status_code=422)

    repo = DBRepository()
    if body.mapping_id:
        ok = repo.delete_mapping(body.mapping_id)
        if not ok:
            return JSONResponse({"error": f"映射 {body.mapping_id} 不存在或已删除"}, status_code=404)
        # 内存同步：移除该映射
        if main.search_engine is not None:
            km = main.search_engine.keyword_map
            for kw in list(km.keys()):
                km[kw] = [e for e in km[kw] if e.get("mapping_id") != body.mapping_id]
                if not km[kw]:
                    del km[kw]
            try:
                main.search_engine.save_cache()
            except Exception:
                pass
        return {"ok": True, "mapping_id": body.mapping_id}
    else:
        ok = repo.delete_keyword(body.keyword_id)
        if not ok:
            return JSONResponse({"error": f"关键词 {body.keyword_id} 不存在或已删除"}, status_code=404)
        if main.search_engine is not None:
            km = main.search_engine.keyword_map
            for kw in list(km.keys()):
                if any(e.get("keyword_id") == body.keyword_id for e in km[kw]):
                    del km[kw]
            try:
                main.search_engine.save_cache()
            except Exception:
                pass
        return {"ok": True, "keyword_id": body.keyword_id}
