"""文档管理路由：列表/详情/图片代理/元数据更新/上传

安全约定：所有用户提供的路径经 service.paths.safe_data_path 校验，
必须解析到 DATA_DIR 内（防路径穿越）。
"""
import ast
import datetime
import json
import logging
import os
import re
import threading

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

import main
from auth import verify_token, require_admin
from config import settings
from repository import get_repo
from repository.dept_mapping import get_dept_path, get_submodule_path
from service.paths import safe_data_path
from service.audit import log_action
from routes.health import record_write_failure

router = APIRouter(tags=["文档"])

_mod_cache = None
_mod_cache_time = 0
_MOD_CACHE_TTL = 300  # 模块映射缓存 5 分钟自动过期（映射修改后最多延迟 5 分钟生效）

IMAGE_TYPES = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
    "webp": "image/webp", "svg": "image/svg+xml", "bmp": "image/bmp",
}


class UploadBody(BaseModel):
    filename: str = ""
    content: str = ""
    dept: str = ""
    module: str = ""
    dept_id: int = 0      # 前端选择器携带的唯一部门 ID（优先于名称）
    module_id: int = 0    # 前端选择器携带的唯一模块 ID（优先于名称）


def _get_module_map():
    global _mod_cache, _mod_cache_time
    import time
    if _mod_cache is not None and (time.time() - _mod_cache_time) < _MOD_CACHE_TTL:
        return _mod_cache
    from repository import get_repo
    repo = get_repo()
    _mod_cache = repo.get_module_product_map()
    _mod_cache_time = time.time()
    return _mod_cache


def _resolve_kw_ids(dept: str, sub_module: str, repo,
                    dept_id: int = 0, module_id: int = 0):
    """解析关键词写入所需的 module_id/dept_id（NULL 安全）

    前端携带的 ID 优先（唯一标识，避免同名歧义）；未携带时按名称解析——
    dept_id 按用户选择的部门名（不取模块行——modules 表部门关联是旧组织
    架构）；module_id 优先「部门+名称」联合匹配，无匹配回退名称唯一查找。
    """
    resolved_dept = dept_id or repo.resolve_dept_id(dept)
    resolved_module = module_id or (
        repo.resolve_module_id(sub_module, dept_name=dept) if sub_module else None
    )
    return resolved_module, resolved_dept


@router.get("/documents")
async def list_documents(
    module: str = Query(""),
    dept_id: str = Query(""),
    page: int = Query(1),
    page_size: int = Query(200, le=500),
    user: str = Depends(verify_token),
):
    """文档列表（DB 直查，按 updated_at 倒序）

    数据源：documents 表（is_deleted=FALSE），不再遍历内存 kb_docs，
    保证列表与 DB 实时一致，消除"列表显示但操作 404"的不一致风险。
    """
    mod_map = _get_module_map()
    repo = get_repo()

    # DB 直查：dept_id 过滤走 document_departments 关联表
    did = int(dept_id) if dept_id and dept_id.isdigit() else 0
    rows = repo.get_documents_page(dept_id=did)

    docs = []
    for row in rows:
        doc_path = row.get("path", "")
        # 排除 FAQ 路径（FAQ 有独立列表）
        if doc_path.startswith("data/faq/"):
            continue

        doc_title = row.get("title", "") or ""
        doc_module = row.get("module") or ""
        doc_dept = row.get("dept") or ""
        doc_product = row.get("product") or ""
        doc_product_line = row.get("product_line") or ""
        doc_keywords = row.get("keywords") or []
        # DB keywords 可能是 list 或逗号分隔字符串
        if isinstance(doc_keywords, str):
            doc_keywords = [k.strip() for k in doc_keywords.split(",") if k.strip()]

        # 产品/产品线：优先用 DB 记录，空时从模块表补充
        cat = {}
        if doc_module:
            info = mod_map.get(doc_module)
            if info:
                cat = dict(info)
                cat["module"] = doc_module
        if not cat:
            for mod_name, info in mod_map.items():
                if mod_name in doc_title or mod_name in doc_path:
                    cat = dict(info)
                    cat["module"] = mod_name
                    break

        # 修改时间：优先取 DB updated_at，回退取文件 mtime
        updated = ""
        full_path = safe_data_path(doc_path)
        if full_path and full_path.exists():
            try:
                mtime = os.path.getmtime(str(full_path))
                updated = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        # 无意义标题（数字-数字-数字）时取文件 H1
        name = doc_title
        if not name or (len(name) < 12 and any(c.isdigit() for c in name) and name.count("-") >= 2):
            if full_path and full_path.exists():
                try:
                    text = full_path.read_text(encoding="utf-8")
                    for line in text.split("\n"):
                        if line.startswith("# ") and not line.startswith("## "):
                            h1 = line[2:].strip()
                            if h1 and not (len(h1) < 12 and all(c in "0123456789 -·." for c in h1)):
                                name = h1
                                break
                except Exception:
                    pass

        d = {
            "id": doc_path,
            "db_id": row.get("id"),
            "name": name or doc_path.split("/")[-1],
            "path": doc_path,
            "dept": doc_dept or cat.get("dept", ""),
            "dept_id": row.get("dept_id") or None,
            # 产品/产品线：文档自身记录优先，模块映射仅作兜底（避免 mod_map 覆盖文档实际值）
            "product": doc_product or cat.get("product", ""),
            "product_line": doc_product_line or cat.get("product_line", ""),
            "module": doc_module or cat.get("module", ""),
            "module_id": row.get("module_id") or None,
            "keywords": doc_keywords,
            "updated": updated,
        }

        if module:
            if module not in (d["dept"], d["product"], d["product_line"], d["module"]):
                continue

        docs.append((d, updated))

    # 按修改时间倒序
    docs.sort(key=lambda x: x[1], reverse=True)
    all_docs = [d for d, _ in docs]
    start = (page - 1) * page_size
    return {"documents": all_docs[start:start + page_size], "total": len(all_docs),
            "page": page, "page_size": page_size}


def _rewrite_images(content: str, doc_dir: str) -> str:
    """相对路径图片改写为 /api/image?path= 代理地址"""
    def repl(m):
        alt = m.group(1)
        src = m.group(2).strip()
        if src.startswith(("http://", "https://", "/api/image", "data:")):
            return m.group(0)
        img = (settings.DATA_DIR / doc_dir / src).resolve()
        try:
            img.relative_to(settings.DATA_DIR.resolve())
            if img.exists():
                rel = str(img.relative_to(settings.PROJECT_DIR))
                from urllib.parse import quote
                return f"![{alt}](/api/image?path={quote(rel)})"
        except Exception:
            pass
        return m.group(0)
    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, content)


@router.get("/document")
async def get_document(path: str = Query(..., description="文档路径"), user: str = Depends(verify_token)):
    """文档详情（正文 + frontmatter，图片改走代理）

    数据源优先级：文件系统 → DB documents.content 回退。
    文件缺失不直接 404，改从 DB 读取（与 FAQ 详情修复逻辑一致）。
    """
    full_path = safe_data_path(path)
    if full_path and full_path.exists():
        content = full_path.read_text(encoding="utf-8")
    else:
        # 文件缺失：回退从 DB 读取
        repo = get_repo()
        db_row = repo.get_document_by_path(path)
        if db_row and db_row.get("content"):
            content = db_row["content"]
            if full_path:
                logging.getLogger(__name__).warning("文档文件已缺失，回退读 DB: %s", path)
        else:
            return JSONResponse({"error": "文档不存在"}, status_code=404)

    fm = {}
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    doc_dir = os.path.dirname(path)
    return {
        "path": path,
        "content": _rewrite_images(content, doc_dir),
        "frontmatter": fm,
        "title": fm.get("title", path.split("/")[-1]),
    }


@router.get("/image")
async def get_image(path: str = Query(...), user: str = Depends(verify_token)):
    """图片代理（扩展名白名单，仅限 DATA_DIR 内）"""
    full_path = safe_data_path(path)
    if not full_path or not full_path.exists():
        return JSONResponse({"error": "图片不存在"}, status_code=404)
    ext = full_path.suffix.lower().lstrip(".")
    if ext not in IMAGE_TYPES:
        return Response(content=full_path.read_bytes(), media_type="application/octet-stream")
    return Response(content=full_path.read_bytes(), media_type=IMAGE_TYPES[ext])


def _update_frontmatter(content: str, dept: str, product: str, keywords: str, new_title: str, module: str = "") -> str:
    """更新/创建 frontmatter 中的部门、模块、产品、关键词、标题字段"""
    has_fm = content.startswith("---")
    if has_fm:
        parts = content.split("---", 2)
        if len(parts) < 3:
            has_fm = False
    if has_fm:
        fm_lines = parts[1].split("\n")
        updated = {"dept": dept, "product": product, "keywords": keywords, "title": new_title}
        if module:
            updated["module"] = module
        seen = set()
        out = []
        for line in fm_lines:
            stripped = line.strip()
            matched = False
            for key, val in updated.items():
                if not val or key in seen:
                    continue
                prefixes = {
                    "dept": ("dept:", "department:"),
                    "product": ("product:", "domain:"),
                    "keywords": ("keywords:",),
                    "title": ("title:",),
                    "module": ("module:",),
                }[key]
                if stripped.startswith(prefixes):
                    out.append(f"{key}: {val}")
                    seen.add(key)
                    matched = True
                    break
            if not matched:
                out.append(line)
        for key, val in updated.items():
            if val and key not in seen:
                out.append(f"{key}: {val}")
        return "---\n" + "\n".join(out) + "\n---" + parts[2]
    else:
        fm = "---\n"
        if new_title:
            fm += f"title: {new_title}\n"
        if dept:
            fm += f"dept: {dept}\n"
        if module:
            fm += f"module: {module}\n"
        if product:
            fm += f"product: {product}\n"
        if keywords:
            fm += f"keywords: {keywords}\n"
        fm += "---\n\n"
        return fm + content


@router.get("/document/update")
async def update_document(
    path: str = Query(..., description="文档路径"),
    dept: str = Query(""),
    dept_ids: str = Query(""),
    product: str = Query(""),
    module: str = Query(""),
    module_id: int = Query(0),
    keywords: str = Query(""),
    new_filename: str = Query(""),
    user: str = Depends(require_admin),
):
    """文档元数据更新：改名 / frontmatter 字段 / 部门关联 / 模块关联

    DB 优先原则：
    - 文件缺失时不直接 404，先查 DB 有记录则继续（允许后续重建恢复文件）
    - 改名后同步更新 DB documents.path 和内存 kb_docs（防三方不一致）
    - 编辑后同步更新 documents 表的 dept/dept_id/module/module_id/product/product_line 列（立即生效）
    """
    full_path = safe_data_path(path)
    file_exists = full_path and full_path.exists()

    # 文件缺失时检查 DB 是否有记录（有记录 = 可操作，缺失文件靠重建恢复）
    if not file_exists:
        repo = get_repo()
        db_row = repo.get_document_by_path(path)
        if not db_row:
            return JSONResponse({"error": "文档不存在"}, status_code=404)
        logging.getLogger(__name__).warning("文档文件已缺失，按 DB 记录继续更新: %s", path)

    renamed = False
    new_path = path  # 追踪最终路径

    # 1. 改名（仅文件存在时可执行）
    if new_filename and file_exists:
        new_name = new_filename.strip()
        if not new_name.endswith(".md"):
            new_name += ".md"
        if "/" in new_name or "\\" in new_name:
            return JSONResponse({"error": "文件名不能包含路径分隔符"}, status_code=422)
        target = full_path.parent / new_name
        if target.exists() and target != full_path:
            return JSONResponse({"error": "同名文件已存在"}, status_code=400)
        full_path.rename(target)
        full_path = target
        renamed = True
        new_path = str(full_path.relative_to(settings.PROJECT_DIR))
    elif new_filename and not file_exists:
        # 文件缺失但用户想改名：仅更新 DB 中的 path 字段
        new_name = new_filename.strip()
        if not new_name.endswith(".md"):
            new_name += ".md"
        if "/" in new_name or "\\" in new_name:
            return JSONResponse({"error": "文件名不能包含路径分隔符"}, status_code=422)
        old_dir = os.path.dirname(path)
        new_path = (old_dir + "/" + new_name) if old_dir else new_name
        renamed = True

    # 2. frontmatter 更新（仅文件存在时）
    if file_exists:
        content = full_path.read_text(encoding="utf-8")
        new_title = new_filename.replace(".md", "") if new_filename else ""
        content = _update_frontmatter(content, dept, product, keywords, new_title, module=module)
        full_path.write_text(content, encoding="utf-8")

    # 3. DB 同步：改名后更新 DB path + 重新 save_document（确保 DB 与文件一致）
    repo = get_repo()
    if renamed and new_path != path:
        repo.update_document_path(path, new_path)
        # 同步内存 kb_docs 中的 path
        if main.search_engine is not None:
            main.search_engine.remove_kb_doc(path)
            # 从 DB 重新读取该文档的元数据加入内存
            db_row = repo.get_document_by_path(new_path)
            if db_row:
                main.search_engine.add_kb_doc({
                    "path": new_path,
                    "title": db_row.get("title", ""),
                    "dept": db_row.get("dept", ""),
                    "module": db_row.get("module", ""),
                    "domain": db_row.get("module", ""),
                    "content_sample": (db_row.get("content") or "")[:5000],
                })

    # 4. 部门关联（document_departments）
    resolved_dept_ids = []
    if dept_ids:
        try:
            resolved_dept_ids = [int(i) for i in dept_ids.split(",") if i.strip().isdigit()]
            repo.set_document_departments(new_path, resolved_dept_ids)
        except Exception:
            record_write_failure("doc_dept_link")

    # 5. 解析 module_id / dept_id（ID 优先，名称回退）
    resolved_module_id = module_id or None
    if not resolved_module_id and module:
        resolved_module_id = repo.resolve_module_id(module)
    resolved_dept_id = resolved_dept_ids[-1] if resolved_dept_ids else None
    if not resolved_dept_id and dept:
        resolved_dept_id = repo.resolve_dept_id(dept)

    # 6. 从模块映射表回填缺失字段（选了模块但没手动填 dept/product 时自动补全）
    mod_map = _get_module_map()
    mod_info = mod_map.get(module, {}) if module else {}
    if module and mod_info:
        # dept 回填优先用 L3 关联部门（与 associated_dept_ids 对应），而非 L2
        if not dept and mod_info.get("associated_dept"):
            dept = mod_info["associated_dept"].split(",")[0].strip()
        if not dept and mod_info.get("dept"):
            dept = mod_info["dept"]
        if not product and mod_info.get("product"):
            product = mod_info["product"]
        if not resolved_dept_id and mod_info.get("associated_dept_ids"):
            # 取第一个关联的L3部门ID
            first_id = mod_info["associated_dept_ids"].split(",")[0].strip()
            if first_id.isdigit():
                resolved_dept_id = int(first_id)
        if not resolved_dept_id and dept:
            resolved_dept_id = repo.resolve_dept_id(dept)
        # 如果 document_departments 关联为空，从模块关联部门自动建立
        if not resolved_dept_ids and mod_info.get("associated_dept_ids"):
            try:
                auto_dept_ids = [int(i.strip()) for i in mod_info["associated_dept_ids"].split(",") if i.strip().isdigit()]
                if auto_dept_ids:
                    repo.set_document_departments(new_path, auto_dept_ids)
                    resolved_dept_ids = auto_dept_ids
                    if not resolved_dept_id:
                        resolved_dept_id = auto_dept_ids[-1]
            except Exception:
                pass

    # 7. 同步更新 documents 表元数据（确保列表立即显示最新值）
    resolved_product = product or mod_info.get("product", "")
    resolved_product_line = mod_info.get("product_line", "")
    try:
        repo.update_document_meta(
            new_path,
            dept=dept or None,
            dept_id=resolved_dept_id,
            module=module or None,
            module_id=resolved_module_id,
            product=resolved_product or None,
            product_line=resolved_product_line or None,
        )
    except Exception as e:
        logging.getLogger(__name__).warning("documents 元数据更新失败 path=%s: %s", new_path, e)

    # 7. 后台重建索引（确保 BM25/向量索引与 DB 一致）
    def _rebuild():
        try:
            if main.search_engine is not None:
                main.search_engine = main.search_engine.rebuild_all()
        except Exception:
            pass
    threading.Thread(target=_rebuild, daemon=True).start()

    # 失效相关缓存（保证写后立即读一致）
    from service.cache import cache_delete, DOCS_WRITE_KEYS
    cache_delete(*DOCS_WRITE_KEYS)

    log_action(user, "doc.update", target=path)
    return {"ok": True, "path": new_path, "renamed": renamed}


@router.get("/document/dept-ids")
async def get_document_dept_ids(
    path: str = Query(..., description="文档路径"),
    user: str = Depends(verify_token),
):
    """获取文档关联的部门 ID 列表（从 document_departments 表）"""
    repo = get_repo()
    ids = repo.get_document_dept_ids(path)
    return {"dept_ids": ids}


@router.get("/document/delete")
async def delete_document(
    id: int = Query(0, description="文档ID（优先）"),
    path: str = Query("", description="文档路径（ID缺失时使用）"),
    user: str = Depends(require_admin),
):
    """删除文档：DB 软删除（主）+ 清理关联 + 物理删文件（辅）+ 重建索引

    入参优先级：id > path。ID 为整数无编码歧义，推荐使用。

    全链路清理：
    1. documents 表 is_deleted = TRUE
    2. document_departments 关联清除
    3. keyword_mappings 关联清除
    4. 物理删 .md 文件（缺失不阻断）
    5. 内存 kb_docs 移除
    6. 缓存失效
    7. 后台重建 BM25/向量索引
    """
    repo = get_repo()

    # ID 优先：按 id 查出 path，再执行删除
    if id:
        row = repo._execute_one(
            "SELECT path FROM documents WHERE id = :id AND is_deleted = FALSE",
            {"id": id}
        )
        if not row:
            return JSONResponse({"error": "文档不存在"}, status_code=404)
        path = row["path"]

    if not path:
        return JSONResponse({"error": "需要提供 id 或 path"}, status_code=422)

    # 路径安全验证
    full_path = safe_data_path(path)
    if not full_path or not str(full_path).startswith(str(settings.DATA_DIR / "knowledge")):
        return JSONResponse({"error": "路径非法"}, status_code=400)

    # DB 软删除（主操作）
    repo = get_repo()
    result = repo.delete_document(path)
    if not result.get("ok"):
        return JSONResponse({"error": result.get("error", "文档不存在")}, status_code=404)

    # 清理关联数据
    try:
        repo.clear_document_departments(path)
    except Exception:
        record_write_failure("doc_dept_clear")
    try:
        repo.clear_document_keywords(path)
    except Exception:
        record_write_failure("doc_keyword_clear")

    # 物理删文件（辅，缺失不阻断）
    if full_path.exists():
        full_path.unlink()
    else:
        logging.getLogger(__name__).warning("文档文件已缺失，仅 DB 软删除: %s", path)

    # 清理内存索引
    if main.search_engine is not None:
        main.search_engine.remove_kb_doc(path)

    # 失效缓存
    from service.cache import cache_delete, DOCS_WRITE_KEYS
    cache_delete(*DOCS_WRITE_KEYS)

    # 后台重建索引
    def _rebuild():
        try:
            if main.search_engine is not None:
                main.search_engine = main.search_engine.rebuild_all()
        except Exception:
            pass
    threading.Thread(target=_rebuild, daemon=True).start()

    log_action(user, "doc.delete", target=path)
    return {"ok": True, "message": "已删除"}


def _body_is_intact(body: str, final: str) -> bool:
    """校验正文在重排后逐行完整保留（顺序不变，仅允许注入区块穿插）。

    文档格式允许转换，但正文内容一行都不能丢——此为硬性保证，
    校验失败时调用方必须退回"原内容不动"的兜底模板。
    """
    body_lines = [l.rstrip() for l in body.split("\n") if l.strip()]
    it = iter(final.split("\n"))
    try:
        for bl in body_lines:
            while True:
                if next(it).rstrip() == bl:
                    break
        return True
    except StopIteration:
        return False


def _clean_html_artifacts(text: str) -> str:
    """清理 HTML 转 Markdown 残留：<br> → 换行、\\- → -、&nbsp; → 空格

    只做格式清理不删除内容，正文完整性要求不变。
    """
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = text.replace("\\-", "-")
    text = text.replace("&nbsp;", " ")
    return text


def _format_kb_document(title: str, dept: str, module: str, product: str, product_line: str,
                        body: str, kw_list: list, today: str, rel_prefix: str,
                        domain: str = "", doc_type: str = "") -> str:
    """按统一规范组装知识库文档：frontmatter + 字段表 + 目录 + 关键词 + 版本迭代时间线 + 正文 + 双向链接

    规范见 SKILL.md「原始文档 → 知识库转换规范」，字段表格式对齐存量文档（例：
    智慧门诊-20251113-免疫规划-智慧门诊.md），双向链接按文件位置计算相对路径。
    """
    # 版本迭代时间线【总目录】：正文 ##/### 标题逐行生成（替代链接式目录）。
    # ### 标题带日期时提取时间（周/月报一周内多次发版靠时间列区分），
    # 无日期的 ### 与 ## 章节时间留空；标题列保证无日期的行可读。
    rows = []
    has_dated = False
    date_re = re.compile(r"(\d{4}[-./年]\d{1,2}(?:[-./月]\d{1,2})?日?)")
    for line in body.split("\n"):
        if line.startswith("### "):
            heading = line[4:].strip()
            m = date_re.search(heading)
            if m:
                has_dated = True
                entry_date = m.group(1).replace("年", "-").replace("月", "-").replace("日", "").replace(".", "-").replace("/", "-")
                entry_title = date_re.sub("", heading).strip(" -–—:")
            else:
                entry_date, entry_title = "", heading
            rows.append((entry_date, entry_title))
        elif line.startswith("## "):
            rows.append(("", line[3:].strip()))
    if rows:
        toc_md = ("## 版本迭代时间线【总目录】\n\n"
                  "| 版本迭代时间 | 标题 | 关联部门 | 产品线 | 产品 | 关键词 | 附录 |\n"
                  "|-------------|------|---------|--------|------|--------|------|\n"
                  + "\n".join(
                      f"| {d} | {t.replace('|', chr(92) + '|')} | {dept} | {product_line} | {product} | "
                      f"{'、'.join(kw_list[:5]) or '-'} |  |"
                      for d, t in rows
                  ) + "\n")
    else:
        toc_md = "## 版本迭代时间线【总目录】\n\n（正文无标题章节）\n"

    kw_md = " ".join(f"`{k}`" for k in kw_list) if kw_list else "（无）"
    now = datetime.datetime.now().isoformat()
    return f"""---
title: {title}
dept: {dept}
dept3: {dept}
module: {module}
product: {product}
product_line: {product_line}
domain: {domain}
type: {doc_type or ("版本迭代" if has_dated else "")}
date: {today}
keywords: {json.dumps(kw_list, ensure_ascii=False)}
appendix: ""
related_modules: []
imported: {now}
---

# {title}

| 字段 | 值 |
|------|-----|
| 所属部门 | {dept} |
| 产品模块 | {module} |
| 所属产品 | {product} |
| 所属产品线 | {product_line} |
| 附录 |  |

## 关键词

{kw_md}

{toc_md}
{body.strip()}

## 双向链接

| 链接类型 | 目标 |
|---------|------|
| 📇 关键词索引 | [关键词索引]({rel_prefix}/ProjectSkill/projects/共享模块中心/关键词库/关键词索引.md) |
| 📁 模块文件 | [共享模块中心/{dept}/{module}/]({rel_prefix}/ProjectSkill/projects/共享模块中心/{dept}/{module}/) |
| 📊 报表 | [2026报表数据知识库/]({rel_prefix}/2026报表数据知识库/) |
"""


async def _upload_document(filename: str, content: str, dept: str, module: str,
                           dept_id: int = 0, module_id: int = 0) -> dict:
    """上传文档公共逻辑（POST JSON / GET query 共用）

    dept_id/module_id 优先于名称使用（前端选择器携带唯一 ID，避免同名歧义）；
    传 ID 未传名称时由服务端反查名称用于目录与落库。
    """
    from keyword_extractor import get_extractor, build_extractor_idf

    if not content or not content.strip():
        return {"error": "content 必填"}
    # 清理 NUL 字节：PG text 字段拒绝 \x00，会导致 documents 写入静默失败（文档不可见）
    content = content.replace("\x00", "")
    repo = get_repo()
    # 前端携带 ID 时：ID 优先，名称缺失则按 ID 反查
    if dept_id and not dept:
        dept = repo.get_department_name(dept_id)
    if module_id and not module:
        module = repo.get_module_name(module_id)
    dept = dept or "数智财务组"
    module = module or "浙里报"

    # 文件名 sanitize（防穿越）
    safe_name = (filename or "").replace("/", "-").replace("\\", "-").replace(" ", "-").strip()
    if not safe_name:
        safe_name = f"doc_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.md"
    if not safe_name.endswith(".md"):
        safe_name += ".md"

    # 剥离原 frontmatter（如有），正文统一由模板重排
    body = content
    if content.strip().startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]
    # 标题：正文首个 H1（提取后从正文移除，由模板统一生成主标题）
    title = safe_name.replace(".md", "")
    body_lines = body.split("\n")
    for i, line in enumerate(body_lines):
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            body_lines = body_lines[:i] + body_lines[i + 1:]
            break
    body = "\n".join(body_lines).strip("\n")
    # 剩余 H1 降级为 H2（统一单 H1 结构，对齐例A：主标题下均为 ## 章节）
    body = "\n".join(
        f"##{line[1:]}" if line.startswith("# ") else line
        for line in body.split("\n")
    )
    # 清理 HTML 残留（<br>、\-、&nbsp;）
    body = _clean_html_artifacts(body)

    # 关键词：自动提取（TF-IDF+TextRank），不足 5 个用关键词索引在正文中兜底
    kw_list = []
    try:
        extractor = get_extractor()
        if not extractor._built:
            build_extractor_idf(str(settings.DATA_DIR))
        kw_list = extractor.extract(content, top_k=10)
    except Exception:
        kw_list = []
    if len(kw_list) < 5 and main.search_engine is not None:
        for kw in main.search_engine.keyword_map:
            if len(kw) >= 2 and kw in content and kw not in kw_list:
                kw_list.append(kw)
            if len(kw_list) >= 10:
                break

    # 路径
    dept_dir = get_dept_path(dept) or "other"
    module_dir = get_submodule_path(module) or "other"
    target_dir = settings.DATA_DIR / "knowledge" / dept_dir / module_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / safe_name

    # 产品/产品线/产品域：从模块表自动解析（模块 → 产品 → 产品线）
    today = datetime.date.today().strftime("%Y%m%d")
    mod_info = _get_module_map().get(module, {})
    product = mod_info.get("product", "")
    product_line = mod_info.get("product_line", "")
    domain = mod_info.get("domain", "")

    # 统一模板组装（frontmatter + 字段表 + 目录 + 关键词 + 总目录 + 正文 + 双向链接）
    # 双向链接目标（ProjectSkill、2026报表数据知识库）位于 AiClaudeProject/ 下，
    # 相对路径以 AiClaudeProject 根为基准计算
    ai_root = settings.PROJECT_DIR.parent.parent  # AiClaudeProject/
    rel_prefix = os.path.relpath(ai_root, target_dir).replace(os.sep, "/")
    final_content = _format_kb_document(
        title, dept, module, product, product_line, body, kw_list, today, rel_prefix, domain
    )
    # 内容完整性兜底：正文任何一行丢失都禁止重排，退回"原内容原样"的最小模板
    if not _body_is_intact(body, final_content):
        now_iso = datetime.datetime.now().isoformat()
        final_content = f"""---
title: {title}
dept: {dept}
dept3: {dept}
module: {module}
product: {product}
product_line: {product_line}
domain: {domain}
type: ""
date: {today}
keywords: {json.dumps(kw_list, ensure_ascii=False)}
appendix: ""
related_modules: []
imported: {now_iso}
---

{content}
"""
        record_write_failure("content_integrity_fallback")
    file_path.write_text(final_content, encoding="utf-8")
    rel_path = str(file_path.relative_to(settings.PROJECT_DIR))

    # 关键词双表写入
    m_id, d_id = None, None
    try:
        m_id, d_id = _resolve_kw_ids(dept, module, repo, dept_id=dept_id, module_id=module_id)
        for kw in kw_list:
            repo.add_keyword(kw, m_id or 0, d_id or 0, dept, kb_path=rel_path)
    except Exception:
        record_write_failure("keyword_write")

    # 写 documents 表 + 部门关联。
    # kb_docs 由 _load_knowledge_base 从 documents 表优先加载（有数据时不扫文件系统），
    # 部门知识库视图按 document_departments 过滤——不写这两处，上传的文档任何视图都看不到。
    try:
        repo.save_document({
            "path": rel_path, "filename": safe_name, "title": title,
            "content": final_content, "dept": dept, "dept_id": d_id,
            "module": module, "module_id": m_id,
            "product": product, "product_line": product_line,
            "date": today, "keywords": kw_list,
        })
        if d_id:
            repo.set_document_departments(rel_path, [d_id])
        # 回读校验：documents 行必须真实存在，否则文档在视图里永远不可见
        if not repo.document_exists(rel_path):
            logging.getLogger(__name__).error("documents 行回读校验失败: %s", rel_path)
            record_write_failure("document_write_verify")
    except Exception as e:
        # 记录异常详情——此前静默吞掉导致用户上传后文档不可见且无日志可查
        logging.getLogger(__name__).error("documents 写入失败 path=%s: %s", rel_path, e)
        record_write_failure("document_write")

    # 增量索引 + 内存 kb_docs（失败后台全量重建，重建会从 documents 表读回该文档）
    try:
        main.search_engine.add_to_index(rel_path, final_content, dept, module)
        if main.search_engine is not None:
            main.search_engine.add_kb_doc({
                "path": rel_path,
                "dept": dept,
                "dept3": dept,
                "domain": module,
                "product": product,
                "module": module,
                "date": today,
                "title": title,
                "content_sample": final_content[:5000],
                "keywords": kw_list,
            })
    except Exception:
        def _rebuild():
            try:
                if main.search_engine is not None:
                    main.search_engine = main.search_engine.rebuild_all()
            except Exception:
                pass
        threading.Thread(target=_rebuild, daemon=True).start()

    # 失效相关缓存（保证写后立即读一致）
    from service.cache import cache_delete, DOCS_WRITE_KEYS
    cache_delete(*DOCS_WRITE_KEYS)

    return {"ok": True, "path": rel_path, "filename": safe_name, "dept": dept, "module": module}


@router.post("/document/upload")
async def upload_document(body: UploadBody, user: str = Depends(require_admin)):
    """上传文档（POST JSON body）"""
    result = await _upload_document(body.filename, body.content, body.dept, body.module,
                                    dept_id=body.dept_id, module_id=body.module_id)
    if "error" in result:
        return JSONResponse(result, status_code=422)
    log_action(user, "doc.upload", target=result.get("filename", body.filename))
    return result


@router.get("/document/upload")
async def upload_document_get(
    filename: str = Query(""),
    content: str = Query(""),
    dept: str = Query(""),
    module: str = Query(""),
    dept_id: int = Query(0),
    module_id: int = Query(0),
    user: str = Depends(require_admin),
):
    """上传文档（GET query，兼容旧客户端）"""
    result = await _upload_document(filename, content, dept, module,
                                    dept_id=dept_id, module_id=module_id)
    if "error" in result:
        return JSONResponse(result, status_code=422)
    log_action(user, "doc.upload", target=result.get("filename", filename))
    return result
