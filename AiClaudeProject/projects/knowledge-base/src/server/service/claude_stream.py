"""Claude 流式响应服务（SSE 生成器，供 /api/claude-stream、/api/chat、/api/rag 复用）"""
import json
import os

import anthropic


def _client_kwargs():
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    api_key = auth_token or os.environ.get("ANTHROPIC_API_KEY", "")
    kwargs = {}
    if base_url:
        kwargs["base_url"] = base_url
    if auth_token:
        kwargs["auth_token"] = auth_token
    else:
        kwargs["api_key"] = api_key
    return kwargs


def default_model() -> str:
    return os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", ""))


async def sse_generate(system: str = "", messages: list = None, max_tokens: int = 4096, deep: bool = False):
    """异步生成器：输出 SSE data: 行（text / complete / error / [DONE]）"""
    if deep:
        system = (system or "") + "\n\n【深度分析模式】请对上述问题做更深入全面的分析，涵盖背景、根因、影响范围与建议。"
    try:
        client = anthropic.Anthropic(**_client_kwargs())
        with client.messages.stream(
            model=default_model(), max_tokens=max_tokens, system=system, messages=messages or [],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"
            yield "data: [DONE]\n\n"
    except anthropic.RateLimitError:
        yield f"data: {json.dumps({'error': 'rate_limit', 'message': 'AI 服务调用频率过高，请稍后重试', 'hint': '当前 API 配额已用尽，您仍可查看搜索结果和 FAQ 文档'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': 'api_error', 'message': f'AI 服务异常: {str(e)}'})}\n\n"
