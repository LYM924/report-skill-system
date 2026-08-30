"""FAQ 路由：列表/详情/保存/删除/导入/归属建议/相似推荐/浏览计数

数据流约定（修复后）：
  - 保存：写一份 .md 文件 + 写 faqs 表（save_faq write_file=False 单文件） + 关键词双表 + 重建内存索引
  - 删除：物理删文件（限 data/faq/ 内）+ faqs 表软删除 + 重建内存索引
  - 向量索引在变更后由后台线程全量重建（避免 BM25/向量脱节）
"""
import datetime
import json
import re
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import main
from auth import verify_token
from config import settings
from repository import DBRepository
from repository.base import FAQ
from repository.dept_mapping import get_dept_path, get_submodule_path
from service.paths import safe_data_path
from routes.health import record_write_failure

router = APIRouter(tags=["FAQ"])

DEPT_CODES = {"数智财务组": "SZ", "免疫规划组": "YM", "电子档案组": "DZ", "数字化支撑组": "ZH"}
STATUS_MAP = {"active": 1, "outdated": 2, "deprecated": 3, "draft": 0}


class ImportBody(BaseModel):
    pass  # 导入走 multipart，占位


def _rebuild_vector_in_background():
    """后台线程重建向量索引（耗时操作）"""
    def _run():
        try:
            if main.search_engine is not None:
                main.search_engine.rebuild_vector_index_async()
        except Exception:
            pass
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _reload_after_faq_change(rebuild_vector: bool = True):
    """FAQ 变更后：同步重建 FAQ 内存结构+BM25，向量后台重建"""
    if main.search_engine is not None:
        main.search_engine.reload_faqs()
    if rebuild_vector:
        _rebuild_vector_in_background()


def _resolve_kw_ids(dept: str, sub_module: str, repo: DBRepository):
    """解析关键词写入所需的 module_id/dept_id（外键，NULL 安全）"""
    module_id, dept_id = None, None
    if sub_module:
        row = repo._execute_one("SELECT id, department_id FROM modules WHERE name = ? LIMIT 1", (sub_module,))
        if row:
            module_id = row["id"]
            dept_id = row["department_id"]
    if not dept_id and dept:
        row = repo._execute_one("SELECT id FROM departments WHERE name = ? LIMIT 1", (dept,))
        dept_id = row["id"] if row else None
    return module_id, dept_id


@router.get("/faq")
async def list_faqs(id: str = Query(""), user: str = Depends(verify_token)):
    """FAQ 列表 / 详情"""
    if main.search_engine is None:
        return {"faqs": [], "error": "搜索引擎未就绪"}

    if id:
        for doc in main.search_engine.faq_docs:
            if doc.get("faq_id") == id:
                p = safe_data_path(doc["path"])
                if p and p.exists():
                    raw = p.read_text(encoding="utf-8")
                    content = raw
                    if raw.startswith("---"):
                        parts = raw.split("---", 2)
                        if len(parts) >= 3:
                            content = parts[2].lstrip("\n")
                    return {
                        "title": doc.get("title", ""),
                        "dept": doc.get("dept", ""),
                        "sub_module": doc.get("sub_module", ""),
                        "keywords": doc.get("keywords", []),
                        "path": doc.get("path", ""),
                        "content": content,
                        "id": id,
                    }
        return JSONResponse({"error": "FAQ 不存在"}, status_code=404)

    faqs = []
    for doc in main.search_engine.faq_docs:
        faqs.append({
            "id": doc.get("faq_id", ""),
            "title": doc.get("title", ""),
            "dept": doc.get("dept", ""),
            "sub_module": doc.get("sub_module", ""),
            "module": doc.get("module", ""),
            "keywords": doc.get("keywords", []),
            "path": doc.get("path", ""),
        })
    return {"faqs": faqs}


@router.get("/faq/delete")
async def delete_faq(path: str = Query(...), user: str = Depends(verify_token)):
    """删除 FAQ：物理删文件（限 data/faq/ 内）+ DB 软删除 + 重建索引"""
    p = safe_data_path(path)
    if not p or not str(p).startswith(str(settings.DATA_DIR / "faq")):
        return JSONResponse({"error": "路径非法"}, status_code=400)
    if not p.exists():
        return JSONResponse({"error": "FAQ 不存在"}, status_code=404)

    p.unlink()
    repo = DBRepository()
    try:
        repo.delete_faq(path)
    except Exception:
        record_write_failure("faq_delete")
        return JSONResponse({"error": "FAQ 删除失败（数据库）"}, status_code=500)

    _reload_after_faq_change()
    return {"ok": True, "message": "已删除"}


@router.get("/faq/suggest")
async def faq_suggest(title: str = Query(""), keywords: str = Query(""),
                      user: str = Depends(verify_token)):
    """FAQ 归属建议：对关键词索引投票得出最可能的部门/模块"""
    if main.search_engine is None:
        return {"dept": "", "module": "", "dept_votes": [], "module_votes": []}

    tokens = [t.strip() for t in (title + " " + keywords).split(",") if t.strip()]
    if title and not keywords:
        tokens = [title] + [t.strip() for t in title.split() if len(t.strip()) >= 2]
    dept_votes, module_votes = {}, {}
    for token in tokens:
        if not token:
            continue
        for kw, entries in main.search_engine.keyword_map.items():
            if kw in token or token in kw:
                for e in entries[:3]:
                    d, m = e.get("dept", ""), e.get("module", "")
                    if d:
                        dept_votes[d] = dept_votes.get(d, 0) + 1
                    if m:
                        module_votes[m] = module_votes.get(m, 0) + 1

    best_dept = max(dept_votes, key=dept_votes.get) if dept_votes else "数智财务组"
    best_module = max(module_votes, key=module_votes.get) if module_votes else "浙里报"
    return {
        "dept": best_dept,
        "module": best_module,
        "dept_votes": sorted(dept_votes.items(), key=lambda x: -x[1])[:5],
        "module_votes": sorted(module_votes.items(), key=lambda x: -x[1])[:5],
    }


@router.get("/faq/similar")
async def faq_similar(keywords: str = Query(""), user: str = Depends(verify_token)):
    """相似 FAQ 推荐：标题命中+3 / 关键词命中+2，取前 5"""
    if main.search_engine is None:
        return {"faqs": []}
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        return {"faqs": []}
    scored = []
    for faq in main.search_engine.faq_docs:
        score = 0
        for kw in kw_list:
            if kw in faq.get("title", ""):
                score += 3
            for fkw in faq.get("keywords", []):
                if kw in fkw or fkw in kw:
                    score += 2
        if score > 0:
            scored.append({
                "id": faq.get("faq_id", ""),
                "title": faq.get("title", ""),
                "keywords": faq.get("keywords", []),
                "dept": faq.get("dept", ""),
                "score": score,
            })
    scored.sort(key=lambda x: -x["score"])
    return {"faqs": scored[:5]}


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
    """保存 FAQ：单文件 + faqs 表 + 关键词双表 + 重建索引

    带 id = 更新已有 FAQ（按 faq_code 幂等 upsert）；不带 id = 新增并生成 FAQ-{部门}-{模块}-{NNN}
    """
    if not title or not dept:
        return JSONResponse({"error": "title 和 dept 为必填参数"}, status_code=422)

    from keyword_extractor import get_extractor, build_extractor_idf

    dept_path = get_dept_path(dept) or "other"
    sub_path = get_submodule_path(sub_module) if sub_module else ""
    faq_dir = settings.DATA_DIR / "faq" / dept_path / sub_path
    faq_dir.mkdir(parents=True, exist_ok=True)

    # 生成/复用 FAQ 编码
    if not id:
        repo = DBRepository()
        row = repo._execute_one(
            "SELECT code FROM departments WHERE name = ? AND code IS NOT NULL LIMIT 1", (dept,))
        dept_code = row["code"] if row else DEPT_CODES.get(dept, "XX")
        mod_code = sub_module[:3] if sub_module else "XXX"
        existing = list(faq_dir.glob("*.md"))
        id = f"FAQ-{dept_code}-{mod_code}-{len(existing) + 1:03d}"

    # 关键词：显式提供 → 拆分；否则自动提取
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list and content:
        try:
            extractor = get_extractor()
            if not extractor._built:
                build_extractor_idf(str(settings.DATA_DIR))
            kw_list = extractor.extract(content, top_k=10)
        except Exception:
            kw_list = []

    # 保留既有 related/tickets（编辑场景）
    related, tickets = [], []
    old_file = faq_dir / f"{id}.md"
    if old_file.exists():
        try:
            old_raw = old_file.read_text(encoding="utf-8")
            for line in old_raw.split("\n"):
                if line.startswith("related:"):
                    try:
                        related = json.loads(line.split(":", 1)[1].strip() or "[]")
                    except Exception:
                        pass
                if line.startswith("tickets:"):
                    try:
                        tickets = json.loads(line.split(":", 1)[1].strip() or "[]")
                    except Exception:
                        pass
        except Exception:
            pass

    # 内容清洗：剥离夹带的 frontmatter
    safe_content = content
    if safe_content.strip().startswith("---"):
        parts = safe_content.split("---", 2)
        if len(parts) >= 3:
            safe_content = parts[2].lstrip("\n")

    today = datetime.date.today().isoformat()
    file_content = f"""---
id: {id}
title: {title}
keywords: {json.dumps(kw_list, ensure_ascii=False)}
module: {module}
dept: {dept}
sub_module: {sub_module}
scene: ""
status: {status}
version_from: ""
created: {today}
reviewed: {today}
related: {json.dumps(related, ensure_ascii=False)}
tickets: {json.dumps(tickets, ensure_ascii=False)}
---

# {title}

{safe_content}
"""
    file_path = faq_dir / f"{id}.md"
    file_path.write_text(file_content, encoding="utf-8")
    rel_path = str(file_path.relative_to(settings.PROJECT_DIR))

    # 写 faqs 表（write_file=False：文件已由本路由写入，避免双文件）
    repo = DBRepository()
    faq = FAQ(
        faq_code=id, faq_title=title, faq_question=title, faq_answer=safe_content,
        content=file_content, path=rel_path, tags=kw_list, dept=dept,
        sub_module=sub_module, module=module, scene="",
        status=STATUS_MAP.get(status, 0), sort_num=0, view_count=0,
        source_file_name=f"{id}.md", version_from="",
        related=related, tickets=tickets,
        update_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        is_deleted=0,
    )
    try:
        repo.save_faq(faq, write_file=False)
    except Exception as e:
        record_write_failure("faq_save")
        # 文件已写入，DB 失败不阻断（启动 bulk_import 会兜底回导）
        return {"ok": True, "faq_id": id, "path": rel_path,
                "warning": f"数据库写入失败（已写入文件）: {e}"}

    # 关键词双表写入（复活式 upsert）
    try:
        m_id, d_id = _resolve_kw_ids(dept, sub_module, repo)
        for kw in kw_list:
            repo.add_keyword(kw, m_id or 0, d_id or 0, dept, kb_path=rel_path)
    except Exception:
        record_write_failure("keyword_write")

    _reload_after_faq_change()
    return {"ok": True, "faq_id": id, "path": rel_path}


@router.post("/faq/import")
@router.get("/faq/import")
async def faq_import(
    file: UploadFile = None,
    background_tasks: BackgroundTasks = None,
    user: str = Depends(verify_token),
):
    """FAQ Excel 批量导入（multipart）：写 .md 文件 + 回导 faqs 表 + 重建索引"""
    if file is None:
        return JSONResponse({"error": "需要上传 Excel 文件（multipart file 字段）"}, status_code=422)
    try:
        import openpyxl
        from io import BytesIO
        data = await file.read()
        wb = openpyxl.load_workbook(BytesIO(data))
        ws = wb.active
    except Exception as e:
        return JSONResponse({"error": f"Excel 解析失败: {e}"}, status_code=400)

    # 列名映射
    header = [str(c.value or "").strip() for c in ws[1]]
    col_map = {}
    for idx, name in enumerate(header):
        if name in ("标题", "问题", "title"):
            col_map.setdefault("title", idx)
        elif name in ("关键词", "keywords", "标签", "tags"):
            col_map.setdefault("keywords", idx)
        elif name in ("部门", "dept", "业务组"):
            col_map.setdefault("dept", idx)
        elif name in ("模块", "module", "子模块"):
            col_map.setdefault("module", idx)
        elif name in ("描述", "问题描述", "description", "现象"):
            col_map.setdefault("desc", idx)
        elif name in ("解决", "方案", "solution", "答案", "answer", "方法"):
            col_map.setdefault("solution", idx)
    if "title" not in col_map:
        return JSONResponse({"error": "缺少标题列"}, status_code=422)

    success, fail = 0, 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        title = str(row[col_map["title"]] or "").strip() if col_map["title"] < len(row) else ""
        if len(title) < 4 or title.isdigit():
            fail += 1
            continue
        dept = str(row[col_map.get("dept", 0)] or "数智财务组").strip() if col_map.get("dept", 0) < len(row) else "数智财务组"
        module = str(row[col_map.get("module", 0)] or "").strip() if col_map.get("module", 0) < len(row) else ""
        kws = str(row[col_map.get("keywords", 0)] or "").strip() if col_map.get("keywords", 0) < len(row) else ""
        desc = str(row[col_map.get("desc", 0)] or "").strip() if col_map.get("desc", 0) < len(row) else ""
        solution = str(row[col_map.get("solution", 0)] or "").strip() if col_map.get("solution", 0) < len(row) else ""

        dept_path = get_dept_path(dept) or "other"
        sub_path = get_submodule_path(module) if module else ""
        faq_dir = settings.DATA_DIR / "faq" / dept_path / sub_path
        faq_dir.mkdir(parents=True, exist_ok=True)
        safe_title = title.replace("/", "-").replace("?", "").replace(":", "")
        kw_list = [k.strip() for k in kws.split(",") if k.strip()]
        existing = list(faq_dir.glob("*.md"))
        faq_code = f"FAQ-{DEPT_CODES.get(dept, 'XX')}-{module[:3] if module else 'XXX'}-{len(existing) + 1:03d}"
        today = datetime.date.today().isoformat()
        content_md = f"""---
id: {faq_code}
title: {title}
keywords: {json.dumps(kw_list, ensure_ascii=False)}
module: {module}
dept: {dept}
sub_module: {module}
scene: ""
status: active
version_from: ""
created: {today}
reviewed: {today}
related: []
tickets: []
---

# {title}

## 问题描述
{desc}

## 原因分析

## 解决方法
{solution}
"""
        (faq_dir / f"{safe_title}.md").write_text(content_md, encoding="utf-8")
        success += 1

    # 回导 faqs 表（幂等）+ 重建索引
    repo = DBRepository()
    try:
        repo.bulk_import_faqs()
    except Exception:
        record_write_failure("faq_save")
    _reload_after_faq_change()
    return {"ok": True, "success": success, "fail": fail}


@router.get("/faq/view")
async def faq_view(id: str = Query(...), user: str = Depends(verify_token)):
    """FAQ 浏览次数 +1"""
    repo = DBRepository()
    try:
        repo._execute_write("UPDATE faqs SET view_count = view_count + 1 WHERE faq_code = ?", (id,))
    except Exception:
        record_write_failure("faq_save")
    return {"ok": True}
