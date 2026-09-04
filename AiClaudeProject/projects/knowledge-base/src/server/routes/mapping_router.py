"""模块关联映射管理路由

提供模块→部门/产品/产品线/业务域的关联映射 CRUD + 级联更新 + 审计日志。
独立路由 /api/mapping/，与现有路由完全解耦。

级联更新策略（v3: ID+名称双写 + 触发器自动同步）：
  - 应用层：只更新 ID 字段（dept_id, module_id, product_id 等）
  - 触发器：ID 变更时自动更新对应名称列（dept, module, product 等）
  - 实体改名：触发器自动级联到所有引用方
"""
import json
import logging
import threading

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from auth import verify_token, require_admin
from repository import get_repo
from service.audit import log_action

router = APIRouter(tags=["模块映射管理"])
logger = logging.getLogger("mapping")


# ══════ 请求体定义 ══════

class ModuleCreate(BaseModel):
    name: str
    product_id: Optional[int] = None
    department_id: Optional[int] = None
    dept_ids: list[int] = []
    domain_ids: list[int] = []
    dev_owner: str = ""
    module_owner: str = ""


class ModuleUpdate(BaseModel):
    name: Optional[str] = None
    product_id: Optional[int] = None
    department_id: Optional[int] = None
    dept_ids: Optional[list[int]] = None
    domain_ids: Optional[list[int]] = None
    dev_owner: Optional[str] = None
    module_owner: Optional[str] = None


class ModuleStatusUpdate(BaseModel):
    status: int  # 0=草稿 1=正常 2=废弃


class DeptIdsBody(BaseModel):
    dept_ids: list[int] = []
    primary_dept_id: Optional[int] = None


class ProductUpdate(BaseModel):
    product_id: int


class DomainIdsBody(BaseModel):
    domain_ids: list[int] = []


class DomainCreate(BaseModel):
    name: str
    code: str = ""


class DomainUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None


class CascadePreview(BaseModel):
    module_id: int
    changes: dict


# ══════ 模块 CRUD ══════

@router.get("/mapping/modules")
async def list_modules(
    q: str = Query(""),
    product_line_id: int = Query(0),
    domain_id: int = Query(0),
    status: int = Query(-1),
    page: int = Query(1),
    page_size: int = Query(50, le=200),
    user: str = Depends(verify_token),
):
    """模块列表（含关联摘要，支持筛选分页）"""
    repo = get_repo()
    return repo.get_modules_page(
        product_line_id=product_line_id or 0,
        domain_id=domain_id or 0,
        status=status,
        q=q,
        page=page,
        page_size=page_size,
    )


@router.get("/mapping/modules/{module_id}")
async def get_module(module_id: int, user: str = Depends(verify_token)):
    """模块详情（含完整关联树）"""
    repo = get_repo()
    module = repo.get_module_by_id(module_id)
    if not module:
        return JSONResponse({"error": "模块不存在"}, status_code=404)
    # 附加关联数据统计
    stats = repo._execute_one("""
        SELECT
            (SELECT COUNT(*) FROM documents WHERE module_id = :mid AND is_deleted = FALSE) AS doc_count,
            (SELECT COUNT(*) FROM faqs WHERE module_id = :mid AND is_deleted = FALSE) AS faq_count,
            (SELECT COUNT(*) FROM keyword_mappings WHERE module_id = :mid AND is_deleted = FALSE) AS kw_count
    """, {"mid": module_id})
    module["stats"] = stats or {}
    return module


@router.post("/mapping/modules")
async def create_module(body: ModuleCreate, user: str = Depends(require_admin)):
    """新增模块（含初始关联）"""
    repo = get_repo()
    result = repo.create_module(body.dict())
    if "error" in result:
        return JSONResponse(result, status_code=400)
    log_action(user, "mapping.module.create", target=body.name)
    return result


@router.put("/mapping/modules/{module_id}")
async def update_module(module_id: int, body: ModuleUpdate, user: str = Depends(require_admin)):
    """修改模块关联 → 触发级联更新

    应用层只更新 ID 字段，名称由触发器自动同步。
    """
    repo = get_repo()
    old_module = repo.get_module_by_id(module_id)
    if not old_module:
        return JSONResponse({"error": "模块不存在"}, status_code=404)

    data = body.dict(exclude_none=True)
    cascade_summary = {}

    # ──── 1. 更新 modules 主表（触发器自动同步名称） ────
    main_fields = {k: v for k, v in data.items() if k in ("name", "product_id", "department_id", "dev_owner", "module_owner", "status")}
    if main_fields:
        repo.update_module(module_id, main_fields)

    # ──── 2. L3 部门关联变更 ────
    if "dept_ids" in data:
        dept_ids = data["dept_ids"]
        repo.set_module_departments(module_id, dept_ids)
        # 同步 document_departments（需要用文档 path 作为外键）
        doc_rows = repo._execute(
            "SELECT path FROM documents WHERE module_id = :mid AND is_deleted = FALSE",
            {"mid": module_id})
        for doc in doc_rows:
            try:
                repo.set_document_departments(doc["path"], dept_ids)
            except Exception:
                pass
        cascade_summary["document_departments_updated"] = len(doc_rows)

    # ──── 3. 产品变更级联 → 只改 documents.product_id ────
    # 触发器 sync_documents_product_name 会自动同步 product + product_line
    if "product_id" in data:
        count_row = repo._execute_one("""
            SELECT COUNT(*) AS c FROM documents WHERE module_id = :mid AND is_deleted = FALSE
        """, {"mid": module_id})
        doc_count = count_row["c"] if count_row else 0
        repo._execute_write("""
            UPDATE documents SET product_id = :pid
            WHERE module_id = :mid AND is_deleted = FALSE
        """, {"pid": data["product_id"], "mid": module_id})
        cascade_summary["documents_product_updated"] = doc_count

    # ──── 4. L2部门变更级联 → 只改 ID，名称由触发器同步 ────
    if "department_id" in data:
        # documents
        repo._execute_write("""
            UPDATE documents SET dept_id = :did
            WHERE module_id = :mid AND is_deleted = FALSE
        """, {"did": data["department_id"], "mid": module_id})
        # faqs
        repo._execute_write("""
            UPDATE faqs SET dept_id = :did
            WHERE module_id = :mid AND is_deleted = FALSE
        """, {"did": data["department_id"], "mid": module_id})
        # keyword_mappings
        repo._execute_write("""
            UPDATE keyword_mappings SET department_id = :did
            WHERE module_id = :mid AND is_deleted = FALSE
        """, {"did": data["department_id"], "mid": module_id})
        cascade_summary["dept_id_cascaded"] = True

    # ──── 5. 业务域变更 ────
    if "domain_ids" in data:
        repo.set_module_domains(module_id, data["domain_ids"])

    # ──── 6. 失效缓存 + 重建索引 ────
    try:
        from service.cache import cache_delete
        cache_delete('module_map', 'menu_data', 'dept_tree')
    except Exception:
        pass
    _background_rebuild_index()

    # ──── 7. 审计日志 ────
    repo.log_mapping_change(
        change_type="module_update",
        target_type="module",
        target_id=module_id,
        old_value={"product_id": old_module.get("product_id"), "department_id": old_module.get("department_id"),
                   "dept_ids": old_module.get("dept_ids", []), "domain_ids": old_module.get("domain_ids", [])},
        new_value=data,
        cascade_summary=cascade_summary,
        operator=user,
    )
    log_action(user, "mapping.module.update", target=str(module_id))

    # 返回更新后的模块
    updated = repo.get_module_by_id(module_id)
    return {"ok": True, "module": updated, "cascade_result": cascade_summary}


@router.put("/mapping/modules/{module_id}/status")
async def update_module_status(module_id: int, body: ModuleStatusUpdate,
                                user: str = Depends(require_admin)):
    """废弃/恢复模块"""
    repo = get_repo()
    if body.status not in (0, 1, 2):
        return JSONResponse({"error": "status 必须是 0(草稿)/1(正常)/2(废弃)"}, status_code=422)
    if body.status == 2:
        ok = repo.deprecate_module(module_id)
        action = "废弃"
    elif body.status == 1:
        ok = repo.restore_module(module_id)
        action = "恢复"
    else:
        result = repo.update_module(module_id, {"status": body.status})
        ok = result.get("ok", False) if isinstance(result, dict) else bool(result)
        action = "设为草稿"
    if not ok:
        return JSONResponse({"error": "模块不存在"}, status_code=404)
    repo.log_mapping_change("module_status_change", "module", module_id,
                           {"status": 1 if body.status == 2 else 2}, {"status": body.status},
                           None, user)
    log_action(user, f"mapping.module.{action}", target=str(module_id))
    return {"ok": True, "module_id": module_id, "status": body.status}


# ══════ 部门关联 ══════

@router.get("/mapping/modules/{module_id}/departments")
async def get_module_departments(module_id: int, user: str = Depends(verify_token)):
    """模块的 L3 部门列表"""
    repo = get_repo()
    rows = repo._execute("""
        SELECT md.department_id, md.is_primary, md.source, d.name as dept_name, d.level, d.parent_id
        FROM module_departments md
        JOIN departments d ON md.department_id = d.id
        WHERE md.module_id = :mid
        ORDER BY md.is_primary DESC, d.name
    """, {"mid": module_id})
    return {"departments": rows}


@router.post("/mapping/modules/{module_id}/departments")
async def set_module_departments(module_id: int, body: DeptIdsBody,
                                  user: str = Depends(require_admin)):
    """设置模块的 L3 部门关联（全量覆盖）"""
    repo = get_repo()
    old_ids = repo.get_module_dept_ids(module_id)
    result = repo.set_module_departments(module_id, body.dept_ids, body.primary_dept_id)
    repo.log_mapping_change("module_dept_update", "module", module_id,
                           {"dept_ids": old_ids}, {"dept_ids": body.dept_ids}, None, user)
    log_action(user, "mapping.module.dept_update", target=str(module_id))
    return result


# ══════ 产品关联 ══════

@router.put("/mapping/modules/{module_id}/product")
async def update_module_product(module_id: int, body: ProductUpdate,
                                 user: str = Depends(require_admin)):
    """修改模块所属产品（触发器自动同步 product + product_line 名称）"""
    repo = get_repo()
    old = repo.get_module_by_id(module_id)
    if not old:
        return JSONResponse({"error": "模块不存在"}, status_code=404)
    # 更新 modules 主表
    repo.update_module(module_id, {"product_id": body.product_id})
    # 级联：只改 documents.product_id，触发器自动同步名称
    repo._execute_write("""
        UPDATE documents SET product_id = :pid
        WHERE module_id = :mid AND is_deleted = FALSE
    """, {"pid": body.product_id, "mid": module_id})
    repo.log_mapping_change("module_product_change", "module", module_id,
                           {"product_id": old.get("product_id"), "product": old.get("product_name")},
                           {"product_id": body.product_id},
                           {"documents_updated": repo._execute_one(
                               "SELECT COUNT(*) AS c FROM documents WHERE module_id = :mid AND is_deleted = FALSE",
                               {"mid": module_id})["c"]},
                           user)
    log_action(user, "mapping.module.product_change", target=str(module_id))
    return {"ok": True}


# ══════ 业务域 CRUD ══════

@router.get("/mapping/domains")
async def list_domains(user: str = Depends(verify_token)):
    """业务域列表"""
    repo = get_repo()
    return {"domains": repo.get_all_domains()}


@router.post("/mapping/domains")
async def create_domain(body: DomainCreate, user: str = Depends(require_admin)):
    """新增业务域"""
    repo = get_repo()
    result = repo.create_domain(body.name, body.code)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    log_action(user, "mapping.domain.create", target=body.name)
    return result


@router.put("/mapping/domains/{domain_id}")
async def update_domain(domain_id: int, body: DomainUpdate, user: str = Depends(require_admin)):
    """修改业务域"""
    repo = get_repo()
    ok = repo.update_domain(domain_id, name=body.name, code=body.code)
    if not ok:
        return JSONResponse({"error": "业务域不存在或无变更"}, status_code=404)
    log_action(user, "mapping.domain.update", target=str(domain_id))
    return {"ok": True}


@router.delete("/mapping/domains/{domain_id}")
async def delete_domain(domain_id: int, user: str = Depends(require_admin)):
    """删除业务域（仅允许无模块关联时删除）"""
    repo = get_repo()
    ok = repo.delete_domain(domain_id)
    if not ok:
        return JSONResponse({"error": "业务域下有模块关联，无法删除"}, status_code=400)
    log_action(user, "mapping.domain.delete", target=str(domain_id))
    return {"ok": True}


@router.get("/mapping/modules/{module_id}/domains")
async def get_module_domains(module_id: int, user: str = Depends(verify_token)):
    """模块的业务域列表"""
    repo = get_repo()
    rows = repo._execute("""
        SELECT md.domain_id, md.is_primary, bd.name as domain_name, bd.code
        FROM module_domains md
        JOIN business_domains bd ON md.domain_id = bd.id
        WHERE md.module_id = :mid
        ORDER BY md.is_primary DESC, bd.name
    """, {"mid": module_id})
    return {"domains": rows}


@router.post("/mapping/modules/{module_id}/domains")
async def set_module_domains(module_id: int, body: DomainIdsBody,
                              user: str = Depends(require_admin)):
    """设置模块的业务域关联（全量覆盖）"""
    repo = get_repo()
    old_ids = repo.get_module_domain_ids(module_id)
    result = repo.set_module_domains(module_id, body.domain_ids)
    repo.log_mapping_change("module_domain_update", "module", module_id,
                           {"domain_ids": old_ids}, {"domain_ids": body.domain_ids}, None, user)
    log_action(user, "mapping.module.domain_update", target=str(module_id))
    return result


# ══════ 级联预览 ══════

@router.post("/mapping/preview")
async def preview_cascade(body: CascadePreview, user: str = Depends(require_admin)):
    """预览级联影响（不执行变更）"""
    repo = get_repo()
    return repo.preview_cascade(body.module_id, body.changes)


# ══════ 变更审计 ══════

@router.get("/mapping/change-logs")
async def get_change_logs(
    module_id: int = Query(0),
    change_type: str = Query(""),
    page: int = Query(1),
    page_size: int = Query(50, le=200),
    user: str = Depends(require_admin),
):
    """变更审计日志"""
    repo = get_repo()
    return repo.get_mapping_change_logs(
        module_id=module_id or None,
        change_type=change_type or None,
        page=page,
        page_size=page_size,
    )


# ══════ 辅助：产品线/业务域下拉选项 ══════

@router.get("/mapping/product-lines")
async def list_product_lines(user: str = Depends(verify_token)):
    """产品线下拉选项"""
    repo = get_repo()
    rows = repo._execute("""
        SELECT pl.id, pl.name,
               (SELECT COUNT(*) FROM products WHERE product_line_id = pl.id) AS product_count
        FROM product_lines pl ORDER BY pl.name
    """)
    return {"product_lines": rows}


@router.get("/mapping/products")
async def list_products(product_line_id: int = Query(0), user: str = Depends(verify_token)):
    """产品下拉选项"""
    repo = get_repo()
    if product_line_id:
        rows = repo._execute(
            "SELECT id, name, product_line_id FROM products WHERE product_line_id = :plid ORDER BY name",
            {"plid": product_line_id})
    else:
        rows = repo._execute("SELECT id, name, product_line_id FROM products ORDER BY name")
    return {"products": rows}


@router.get("/mapping/departments")
async def list_departments_for_mapping(user: str = Depends(verify_token)):
    """部门树（映射管理用，含L1/L2/L3完整层级）"""
    repo = get_repo()
    return {"departments": repo.get_department_tree()}


# ══════ 内部辅助 ══════

def _background_rebuild_index():
    """后台重建搜索索引"""
    def _rebuild():
        try:
            import main
            if main.search_engine is not None:
                main.search_engine = main.search_engine.rebuild_all()
        except Exception as e:
            logger.warning("索引重建失败: %s", e)
    threading.Thread(target=_rebuild, daemon=True).start()
