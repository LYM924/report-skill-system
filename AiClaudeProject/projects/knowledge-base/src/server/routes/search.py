"""搜索路由"""
import os, uuid, time, json
from fastapi import APIRouter, Query, Depends
import main
from auth import verify_token

router = APIRouter(tags=["搜索"])

# 会话存储（用于 AI 总结流式推送）
SESSION_STORE = {}


@router.get("/search")
async def search(
    q: str = Query(..., description="搜索关键词"),
    top: int = Query(15),
    page: int = Query(1),
    page_size: int = Query(10, le=50),
    user: str = Depends(verify_token),
):
    """智能搜索"""
    if main.search_engine is None:
        return {"error": "搜索引擎未就绪"}
    result = main.search_engine.search(q, top=top)
    all_results = result.get("results", [])
    start = (page - 1) * page_size
    paged = all_results[start:start + page_size]
    result["results"] = paged
    result["page"] = page
    result["page_size"] = page_size
    result["has_more"] = start + page_size < len(all_results)

    # 异步记录搜索日志（用于热词统计）
    try:
        from repository import DBRepository
        repo = DBRepository()
        repo._execute_write(
            "INSERT INTO search_logs (query, result_count, source) VALUES (:q, :cnt, 'web')",
            {"q": q, "cnt": len(all_results)}
        )
    except Exception:
        pass  # 日志记录失败不影响搜索

    # quick_summary
    ans = result.get("answer") or {}
    result["quick_summary"] = {
        "module": ans.get("module", ""),
        "dept": ans.get("dept", ""),
        "owner": ans.get("module_owner", ""),
        "snippet": ans.get("summary", "")[:200] if ans.get("summary") else "",
    }

    # Claude AI 总结
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key and main.search_engine:
        prompt = main.search_engine.build_rag_prompt(q, result.get("results", []))
        sid = uuid.uuid4().hex[:12]
        SESSION_STORE[sid] = {"prompt": prompt, "query": q, "created": time.time()}
        # 清理过期会话
        now = time.time()
        for k in list(SESSION_STORE.keys()):
            if now - SESSION_STORE[k].get("created", 0) > 600:
                del SESSION_STORE[k]
        result["claude_stream_url"] = f"/api/claude-stream?sid={sid}"
    else:
        result["claude_stream_url"] = None

    return result


@router.get("/claude-stream")
async def claude_stream(sid: str = Query(...)):
    """Claude AI 流式总结（SSE）"""
    from fastapi.responses import StreamingResponse
    import anthropic

    session = SESSION_STORE.get(sid)
    if not session:
        return {"error": "会话已过期，请重新搜索"}

    async def generate():
        try:
            api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", "")
            base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
            auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")

            client_kwargs = {}
            if base_url:
                client_kwargs["base_url"] = base_url
            if auth_token:
                client_kwargs["auth_token"] = auth_token
            else:
                client_kwargs["api_key"] = api_key

            client = anthropic.Anthropic(**client_kwargs)
            model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
            prompt = session.get("prompt", {})
            system = prompt.get("system", "")
            messages = prompt.get("messages", [{"role": "user", "content": session.get("query", "")}])

            with client.messages.stream(
                model=model, max_tokens=4096, system=system, messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
                yield f"data: {json.dumps({'type': 'complete'})}\n\n"
                yield "data: [DONE]\n\n"

        except anthropic.RateLimitError as e:
            yield f"data: {json.dumps({'error': 'rate_limit', 'message': 'AI 服务调用频率过高，请稍后重试', 'hint': '当前 API 配额已用尽，您仍可查看搜索结果和 FAQ 文档'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': 'api_error', 'message': f'AI 服务异常: {str(e)}'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/suggest")
async def suggest(q: str = Query(..., description="搜索提示词")):
    """搜索建议"""
    if main.search_engine is None:
        return {"suggestions": []}
    # 从关键词索引匹配
    suggestions = []
    for kw in main.search_engine.keyword_map:
        if q in kw and len(kw) >= 2:
            suggestions.append(kw)
        if len(suggestions) >= 10:
            break
    return {"suggestions": suggestions[:10]}
