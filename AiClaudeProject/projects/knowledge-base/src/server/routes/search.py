"""搜索路由：/api/search、/api/claude-stream、/api/suggest、/api/search/related、
/api/feedback、/api/rag、/api/chat"""
import hashlib
import json
import os
import time
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import main
from auth import verify_token
from service import claude_stream as claude_service
from routes.health import record_write_failure

router = APIRouter(tags=["搜索"])

# AI 总结会话（sid → prompt），进程内存储，600 秒过期
SESSION_STORE = {}
SESSION_TTL = 600


class MessageBody(BaseModel):
    message: str = ""


def _prune_sessions():
    now = time.time()
    for k in list(SESSION_STORE.keys()):
        if now - SESSION_STORE[k].get("created", 0) > SESSION_TTL:
            del SESSION_STORE[k]


def _write_search_log(q: str, normalized_q: str, result_count: int, has_answer: bool,
                      search_time_ms: int, request: Request):
    """写 search_logs 表（失败只计数不阻断，Schema 契约由 /api/health 暴露）"""
    try:
        from repository import DBRepository
        repo = DBRepository()
        ua = (request.headers.get("user-agent", "") or "")[:500]
        ip_hash = hashlib.sha256((request.client.host if request.client else "").encode()).hexdigest()[:16]
        repo._execute_write(
            "INSERT INTO search_logs (query, normalized_q, result_count, has_answer, "
            "search_time_ms, source, user_agent, ip_hash) "
            "VALUES (:q, :nq, :cnt, :ha, :ms, 'web', :ua, :ip)",
            {"q": q[:2000], "nq": normalized_q[:2000] if normalized_q else None,
             "cnt": result_count, "ha": has_answer, "ms": search_time_ms,
             "ua": ua, "ip": ip_hash},
        )
    except Exception:
        record_write_failure("search_log")


def _apply_scope(results: list, scope: str) -> list:
    """搜索范围过滤：all 全部 / doc 排除FAQ / faq 仅FAQ"""
    if scope == "faq":
        return [r for r in results if r.get("source") == "faq_knowledge"]
    if scope == "doc":
        return [r for r in results if r.get("source") != "faq_knowledge"]
    return results


@router.get("/search")
async def search(
    q: str = Query(..., description="搜索关键词"),
    top: int = Query(15),
    page: int = Query(1),
    page_size: int = Query(10, le=50),
    scope: str = Query("all", description="all | doc | faq"),
    request: Request = None,
    user: str = Depends(verify_token),
):
    """智能搜索（含 FAQ 缓存命中、搜索日志、AI 总结会话）"""
    if main.search_engine is None:
        return {"error": "搜索引擎未就绪"}
    eng = main.search_engine

    # 1. FAQ 缓存命中检查（向量相似度 >0.85 直接返回）
    cached = eng.check_faq_cache(q)
    if cached:
        try:
            from repository import DBRepository
            DBRepository().increment_counter("faq_hits")
        except Exception:
            pass
        return {
            "query": q, "from_cache": True,
            "cached_answer": cached,
            "answer": {
                "source": "faq_cache",
                "question": cached.get("question", q),
                "summary": cached.get("summary", ""),
                "module": cached.get("module", ""),
                "matched_keywords": cached.get("keywords", []),
            },
            "results": [], "total": 0, "page": page, "page_size": page_size,
            "has_more": False, "claude_stream_url": None,
        }

    # 2. 常规搜索（计时 + 范围过滤 + 分页）
    t0 = time.time()
    result = eng.search(q, top=top)
    search_ms = int((time.time() - t0) * 1000)

    all_results = _apply_scope(result.get("results", []), scope)
    start = (page - 1) * page_size
    paged = all_results[start:start + page_size]
    result["results"] = paged
    result["total"] = len(all_results)
    result["page"] = page
    result["page_size"] = page_size
    result["has_more"] = start + page_size < len(all_results)

    # 3. 搜索日志（含纠错词、耗时、是否有答案、UA、IP 哈希）
    correction = result.get("correction") or {}
    normalized = correction.get("corrected", "") if correction.get("has_correction") else ""
    _write_search_log(q, normalized, len(all_results), bool(result.get("answer")), search_ms, request)

    # 4. quick_summary（前端快捷展示）
    ans = result.get("answer") or {}
    result["quick_summary"] = {
        "module": ans.get("module", ""),
        "dept": ans.get("dept", ""),
        "owner": ans.get("module_owner", ""),
        "snippet": (ans.get("summary") or "")[:200],
    }

    # 5. AI 总结会话（按当前用户的 AI 配置判断可用性）
    from service import ai_config as ai_cfg
    if ai_cfg.resolve_ai_config(user or ""):
        try:
            prompt = eng.build_rag_prompt(q, paged)
            sid = uuid.uuid4().hex[:12]
            SESSION_STORE[sid] = {"prompt": prompt, "query": q, "created": time.time(),
                                  "username": user or ""}
            _prune_sessions()
            result["claude_stream_url"] = f"/api/claude-stream?sid={sid}"
        except Exception:
            result["claude_stream_url"] = None
    else:
        result["claude_stream_url"] = None

    return result


@router.get("/claude-stream")
async def claude_stream(
    sid: str = Query(...),
    deep: int = Query(0),
    user: str = Depends(verify_token),
):
    """Claude AI 流式总结（SSE，会话来自 /api/search 返回的 sid）"""
    session = SESSION_STORE.get(sid)
    if not session:
        return {"error": "会话已过期，请重新搜索"}
    try:
        from repository import DBRepository
        DBRepository().increment_counter("ai_summaries")
    except Exception:
        pass
    # 按会话所属用户的 AI 配置取模型/密钥（用户配置优先，服务器环境回退）
    from service import ai_config as ai_cfg
    cfg = ai_cfg.resolve_ai_config(session.get("username", ""))
    if not cfg:
        return {"error": "未配置 AI 服务（请在 系统管理→配置中心 保存你的 AI 配置）"}
    prompt = session.get("prompt", {})
    system = prompt.get("system", "")
    messages = prompt.get("messages", [{"role": "user", "content": session.get("query", "")}])
    return StreamingResponse(
        claude_service.sse_generate_cfg(cfg, system=system, messages=messages, deep=bool(deep)),
        media_type="text/event-stream",
    )


@router.get("/suggest")
async def suggest(q: str = Query(..., description="搜索提示词"), user: str = Depends(verify_token)):
    """搜索建议（三源：DB 关键词 LIKE → 内存关键词索引 → FAQ 标题）"""
    suggestions = []
    # 1. DB：keywords_v2 模糊匹配
    try:
        from repository import DBRepository
        repo = DBRepository()
        rows = repo._execute(
            "SELECT DISTINCT keyword FROM keywords_v2 WHERE keyword LIKE ? AND is_deleted = FALSE LIMIT 10",
            (f"%{q}%",),
        )
        suggestions = [r["keyword"] for r in rows]
    except Exception:
        suggestions = []
    if main.search_engine is not None:
        # 2. 内存关键词索引
        for kw in main.search_engine.keyword_map:
            if kw not in suggestions and q in kw and len(kw) >= 2:
                suggestions.append(kw)
            if len(suggestions) >= 10:
                break
        # 3. FAQ 标题
        for faq in main.search_engine.faq_docs:
            t = faq.get("title", "")
            if t and t not in suggestions and q in t:
                suggestions.append(t)
            if len(suggestions) >= 10:
                break
    return {"suggestions": suggestions[:10]}


@router.get("/search/related")
async def related_searches(q: str = Query(...), user: str = Depends(verify_token)):
    """相关搜索推荐（关键词共享模块 + 向量相似 FAQ 标题 + 热词）"""
    if main.search_engine is None:
        return {"related": [], "query": q}
    return {"related": main.search_engine.get_related_searches(q, limit=6), "query": q}


@router.get("/feedback")
@router.post("/feedback")
async def feedback(
    q: str = Query(""),
    result_id: str = Query(""),
    result_path: str = Query(""),
    type: str = Query("", description="useful | not_useful"),
    user: str = Depends(verify_token),
):
    """搜索反馈（写 feedback 表 + search_counter 计数）"""
    if type not in ("useful", "not_useful"):
        return {"error": "type 必须是 useful 或 not_useful"}
    try:
        from repository import DBRepository
        repo = DBRepository()
        repo.save_feedback(q, result_id, result_path, type)
    except Exception:
        record_write_failure("keyword_write")  # 复用写失败计数通道
        return {"error": "反馈保存失败"}
    return {"ok": True}


def _user_ai_cfg(user: str):
    """按用户名解析 AI 配置；无配置返回 None"""
    from service import ai_config as ai_cfg
    return ai_cfg.resolve_ai_config(user or "")


def _sse_with_cfg(cfg: dict, system: str, messages: list):
    """用解析出的配置发起 SSE 流（按协议自动选择 anthropic/openai 通道）"""
    return StreamingResponse(
        claude_service.sse_generate_cfg(cfg, system=system, messages=messages),
        media_type="text/event-stream",
    )


async def _chat_impl(message: str, user: str):
    cfg = _user_ai_cfg(user)
    if not cfg:
        return {"error": "未配置 AI 服务（请在 系统管理→配置中心 保存你的 AI 配置）"}
    try:
        from repository import DBRepository
        DBRepository().increment_counter("ai_summaries")
    except Exception:
        pass
    system = "你是企业内部知识库 AI 助手，请用中文简洁专业地回答用户问题。"
    return _sse_with_cfg(cfg, system, [{"role": "user", "content": message}])


@router.get("/chat")
async def chat(message: str = Query(""), user: str = Depends(verify_token)):
    """纯 AI 聊天（SSE，不检索知识库）"""
    return await _chat_impl(message, user)


@router.post("/chat")
async def chat_post(body: MessageBody, user: str = Depends(verify_token)):
    """纯 AI 聊天（SSE，POST JSON body）"""
    return await _chat_impl(body.message, user)


async def _rag_impl(message: str, user: str):
    if main.search_engine is None:
        return {"error": "搜索引擎未就绪"}
    if not message:
        return {"error": "message 必填"}
    cfg = _user_ai_cfg(user)
    if not cfg:
        return {"error": "未配置 AI 服务（请在 系统管理→配置中心 保存你的 AI 配置）"}
    try:
        from repository import DBRepository
        DBRepository().increment_counter("ai_summaries")
    except Exception:
        pass

    results = main.search_engine.search(message, top=5)
    try:
        prompt = main.search_engine.build_rag_prompt(message, results.get("results", []))
    except Exception:
        prompt = {"system": "", "messages": [{"role": "user", "content": message}], "sources": []}
    return _sse_with_cfg(cfg, prompt.get("system", ""), prompt.get("messages", []))


@router.get("/rag")
async def rag(message: str = Query(""), user: str = Depends(verify_token)):
    """RAG 智能问答（SSE，query 参数）"""
    return await _rag_impl(message, user)


@router.post("/rag")
async def rag_post(body: MessageBody, user: str = Depends(verify_token)):
    """RAG 智能问答（SSE，POST JSON body）"""
    return await _rag_impl(body.message, user)
