"""学习中心路由：/api/learning/*

自学习闭环的 API 层：
  - 候选列表/统计
  - 手动提取知识
  - 用户反馈自动学习
  - 审核通过/拒绝
  - 过期清理
"""
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from auth import verify_token, require_admin
from repository import get_repo
from service import learning_service

router = APIRouter(tags=["学习中心"])

logger = logging.getLogger("learning")

# 状态映射
STATUS_LABELS = {0: "待审核", 1: "已通过", 2: "已拒绝", 3: "已过期"}


class ExtractBody(BaseModel):
    query: str = ""
    answer: str = ""
    session_id: str = ""


class ApproveBody(BaseModel):
    title: str = ""
    summary: str = ""
    dept: str = ""
    module: str = ""
    keywords: list = None


class AutoLearnBody(BaseModel):
    query: str = ""
    answer: str = ""
    feedback_id: int = 0
    session_id: str = ""


@router.get("/learning/candidates")
async def list_candidates(
    status: int = Query(None, description="0待审核/1已通过/2已拒绝/3已过期，不传=全部"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: str = Depends(verify_token),
):
    """学习候选列表（分页，待审核优先）"""
    repo = get_repo()
    result = learning_service.list_candidates(repo, status=status,
                                               page=page, page_size=page_size)
    # 附加状态标签
    for c in result.get("candidates", []):
        c["status_label"] = STATUS_LABELS.get(c["status"], "未知")
    return result


@router.get("/learning/stats")
async def learning_stats(user: str = Depends(verify_token)):
    """学习中心统计"""
    repo = get_repo()
    return learning_service.get_learning_stats(repo)


@router.post("/learning/extract")
async def extract_knowledge(body: ExtractBody, user: str = Depends(verify_token)):
    """手动触发：从问答中提取知识（SSE 流式返回提取结果）

    前端调用后先获取提取结果，用户确认后再提交到候选池。
    """
    if not body.query or not body.answer:
        return JSONResponse({"error": "query 和 answer 必填"}, status_code=422)

    # 流式返回 AI 提取结果
    from service import ai_config as ai_cfg
    from service import claude_stream as claude_service

    cfg = ai_cfg.resolve_ai_config(user or "")
    if not cfg:
        return JSONResponse({"error": "未配置 AI 服务"}, status_code=400)

    prompt = learning_service.LEARNING_EXTRACT_PROMPT.format(
        query=body.query[:500], answer=body.answer[:2000])
    system = "你是一个精确的知识提取工具，只输出 JSON，不输出任何其他内容。"

    return StreamingResponse(
        claude_service.sse_generate_cfg(
            cfg, system=system,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        ),
        media_type="text/event-stream",
    )


@router.post("/learning/submit")
async def submit_candidate(
    query: str = Query(""),
    answer: str = Query(""),
    summary: str = Query(""),
    dept: str = Query(""),
    module: str = Query(""),
    keywords: str = Query("[]"),
    source: str = Query("manual"),
    session_id: str = Query(""),
    user: str = Depends(verify_token),
):
    """提交学习候选（用户确认后调用）

    将已提取/已编辑的知识条目写入候选池。
    """
    import json
    if not query or not answer:
        return JSONResponse({"error": "query 和 answer 必填"}, status_code=422)

    try:
        kw_list = json.loads(keywords) if isinstance(keywords, str) else keywords
    except (json.JSONDecodeError, TypeError):
        kw_list = []

    repo = get_repo()
    result = learning_service.save_candidate(
        repo, query=query, answer=answer, source=source,
        summary=summary, dept=dept, module=module,
        keywords=kw_list, session_id=session_id,
        created_by=user or "",
    )
    return result


class SubmitBody(BaseModel):
    query: str = ""
    answer: str = ""
    summary: str = ""
    dept: str = ""
    module: str = ""
    keywords: list = None
    source: str = "manual"
    session_id: str = ""


@router.post("/learning/submit-json")
async def submit_candidate_json(body: SubmitBody, user: str = Depends(verify_token)):
    """提交学习候选（JSON body 版本，推荐）"""
    if not body.query or not body.answer:
        return JSONResponse({"error": "query 和 answer 必填"}, status_code=422)

    repo = get_repo()
    result = learning_service.save_candidate(
        repo, query=body.query, answer=body.answer, source=body.source,
        summary=body.summary, dept=body.dept, module=body.module,
        keywords=body.keywords or [], session_id=body.session_id,
        created_by=user or "",
    )
    return result


@router.post("/learning/auto")
async def auto_learn_from_feedback(body: AutoLearnBody, user: str = Depends(verify_token)):
    """用户反馈 👍 时自动触发学习（后台异步）

    不阻塞反馈接口，直接保存原始问答到候选池，
    后续由管理员在「学习中心」审核。
    """
    if not body.query:
        return JSONResponse({"error": "query 必填"}, status_code=422)

    repo = get_repo()
    # 直接保存问答，source 标记为 user_feedback
    result = learning_service.save_candidate(
        repo, query=body.query, answer=body.answer or "",
        source="user_feedback", feedback_id=body.feedback_id,
        session_id=body.session_id, created_by=user or "",
    )

    # 后台异步尝试 AI 提取（不阻塞返回）
    if result.get("ok") and body.answer:
        try:
            import asyncio

            async def _bg_extract():
                extracted = await learning_service.extract_knowledge(
                    body.query, body.answer, user=user)
                if extracted and extracted.get("summary"):
                    # 更新候选的 summary/dept/module/keywords
                    import json
                    try:
                        with repo.engine.connect() as conn:
                            from sqlalchemy import text as sql_text
                            conn.execute(sql_text("""
                                UPDATE learning_candidates
                                SET summary = :summary, dept = :dept, module = :module,
                                    keywords = :keywords, source = 'ai_extract',
                                    update_time = :now
                                WHERE id = :id
                            """), {
                                "summary": extracted.get("summary", "")[:1000],
                                "dept": extracted.get("dept", "")[:100],
                                "module": extracted.get("module", "")[:200],
                                "keywords": json.dumps(
                                    extracted.get("keywords", []), ensure_ascii=False),
                                "now": __import__("datetime").datetime.now().strftime(
                                    "%Y-%m-%d %H:%M:%S"),
                                "id": result["id"],
                            })
                            conn.commit()
                    except Exception as e:
                        logger.warning(f"后台 AI 提取更新失败: {e}")

            # 尝试在后台运行（不阻塞当前请求）
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(_bg_extract())
            except RuntimeError:
                pass  # 无事件循环则跳过
        except Exception as e:
            logger.warning(f"auto_learn 后台提取启动失败: {e}")

    return result


@router.post("/learning/approve/{candidate_id}")
async def approve_candidate(
    candidate_id: int,
    body: ApproveBody = None,
    user: str = Depends(require_admin),
):
    """审核通过学习候选 → 自动创建 FAQ

    管理员可同时提交编辑内容（title/summary/dept/module/keywords）。
    """
    repo = get_repo()
    edits = None
    if body:
        edits = {}
        if body.title:
            edits["title"] = body.title
        if body.summary:
            edits["summary"] = body.summary
        if body.dept:
            edits["dept"] = body.dept
        if body.module:
            edits["module"] = body.module
        if body.keywords:
            edits["keywords"] = body.keywords

    result = learning_service.approve_candidate(
        repo, candidate_id, reviewer=user or "", edits=edits)
    return result


@router.post("/learning/reject/{candidate_id}")
async def reject_candidate(
    candidate_id: int,
    note: str = Query("", description="拒绝原因"),
    user: str = Depends(require_admin),
):
    """审核拒绝学习候选"""
    repo = get_repo()
    return learning_service.reject_candidate(
        repo, candidate_id, reviewer=user or "", note=note)


@router.post("/learning/expire")
async def expire_candidates(
    days: int = Query(30, description="超过多少天未审核自动过期"),
    user: str = Depends(require_admin),
):
    """清理过期学习候选（超期未审核的标记为过期）"""
    repo = get_repo()
    expired = learning_service.expire_old_candidates(repo, days=days)
    return {"ok": True, "expired_count": expired}
