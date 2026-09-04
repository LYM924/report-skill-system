#!/usr/bin/env python3
"""产品知识库 MCP Server

通过 MCP 协议暴露知识库的搜索、FAQ、文档、关键词等功能，
供 Claude Code / 通义灵码 / 其他 AI 工具直接调用。

架构：MCP Server(本地) → HTTP → FastAPI 后端(共享) → PostgreSQL

配置方式：
  在 Claude Code 的 settings.json 中添加 mcpServers：
  {
    "mcpServers": {
      "knowledge-base": {
        "command": "python3",
        "args": ["/path/to/knowledge-base/src/mcp/server.py"],
        "env": {
          "KB_API_URL": "http://localhost:8000",
          "KB_USERNAME": "admin",
          "KB_PASSWORD": "admin123"
        }
      }
    }
  }
"""

import os
import httpx
from mcp.server.mcpserver import MCPServer

# ════════════════ 配置 ════════════════

KB_API_URL = os.getenv("KB_API_URL", "http://localhost:8000")
KB_USERNAME = os.getenv("KB_USERNAME", "admin")
KB_PASSWORD = os.getenv("KB_PASSWORD", "admin123")

# ════════════════ 认证 ════════════════

_token_cache: dict = {"token": ""}


async def _get_token() -> str:
    """获取 JWT Token（简单缓存，不过期不重登）"""
    if _token_cache["token"]:
        return _token_cache["token"]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{KB_API_URL}/api/auth/login",
            json={"username": KB_USERNAME, "password": KB_PASSWORD},
        )
        data = resp.json()
        if "token" in data:
            _token_cache["token"] = data["token"]
            return data["token"]
        raise RuntimeError(f"登录失败: {data}")


async def _api_get(path: str, params: dict | None = None) -> dict:
    """调用知识库 GET API（自动带 Token）"""
    token = await _get_token()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{KB_API_URL}{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp.json()


# ════════════════ MCP Server ════════════════

mcp = MCPServer(
    name="产品知识库",
    title="产品业务知识库",
    description="产品业务知识库 MCP Server，包含 FAQ、知识文档、关键词索引等，支持智能搜索、部门/模块浏览、FAQ 查询。",
    instructions="产品业务知识库，包含 FAQ、知识文档、关键词索引等。支持智能搜索、部门/模块浏览、FAQ 查询等。",
)


@mcp.tool()
async def search(query: str, scope: str = "all", top: int = 10) -> str:
    """搜索知识库

    Args:
        query: 搜索关键词，如"参考价合规"、"浙里报报销"
        scope: 搜索范围 all/doc/faq，默认 all
        top: 返回结果数，默认 10
    """
    data = await _api_get("/api/search", {"q": query, "scope": scope, "top": top})

    results = data.get("results", [])
    faqs = data.get("faqs", [])
    answer = data.get("answer", "") or data.get("cached_answer", "")

    parts = []
    if answer:
        parts.append(f"📝 AI 摘要:\n{answer}")
    if results:
        parts.append("📄 搜索结果:")
        for i, r in enumerate(results[:top], 1):
            mod = r.get("module", "")
            dept = r.get("dept", "")
            title = r.get("title", r.get("name", ""))
            score = r.get("score", 0)
            parts.append(f"  {i}. [{dept}/{mod}] {title} (得分:{score:.1f})")
            snippet = r.get("snippet", "")
            if snippet:
                parts.append(f"     {snippet[:150]}")
    if faqs:
        parts.append("❓ 相关 FAQ:")
        for i, f in enumerate(faqs[:5], 1):
            parts.append(f"  {i}. [{f.get('id', '')}] {f.get('title', '')}")

    return "\n".join(parts) if parts else "未找到相关结果"


@mcp.tool()
async def faq_list() -> str:
    """获取 FAQ 列表，返回所有 FAQ 的编码、标题、部门、模块"""
    data = await _api_get("/api/faq")
    faqs = data.get("faqs", [])

    if not faqs:
        return "暂无 FAQ"

    lines = [f"共 {len(faqs)} 条 FAQ:\n"]
    for f in faqs[:50]:
        dept = f.get("dept", "")
        mod = f.get("sub_module", "") or f.get("module", "")
        lines.append(f"  [{f.get('id', '')}] {f.get('title', '')} — {dept}/{mod}")

    if len(faqs) > 50:
        lines.append(f"\n  ... 共 {len(faqs)} 条，仅显示前 50 条")

    return "\n".join(lines)


@mcp.tool()
async def faq_detail(id: str) -> str:
    """获取 FAQ 详情

    Args:
        id: FAQ 编码，如 FAQ-DZMC-XXX-001
    """
    data = await _api_get("/api/faq", {"id": id})

    if "error" in data:
        return f"❌ {data['error']}"

    parts = [
        f"📌 {data.get('title', '')}",
        f"   编码: {id}",
        f"   部门: {data.get('dept', '')}",
        f"   模块: {data.get('sub_module', '') or data.get('module', '')}",
        f"   关键词: {', '.join(data.get('keywords', [])) or '无'}",
    ]
    if data.get("content"):
        parts.append(f"\n📖 内容:\n{data['content'][:3000]}")

    return "\n".join(parts)


@mcp.tool()
async def document_list(module: str = "") -> str:
    """获取知识文档列表

    Args:
        module: 按模块/产品名筛选，留空返回全部
    """
    params = {}
    if module:
        params["module"] = module

    data = await _api_get("/api/documents", params)

    docs = data.get("documents", [])
    if not docs:
        return "暂无文档"

    lines = [f"共 {data.get('total', len(docs))} 篇文档:\n"]
    for d in docs[:50]:
        dept = d.get("dept", "")
        mod = d.get("module", "")
        name = d.get("name", d.get("title", ""))
        lines.append(f"  [{d.get('db_id', d.get('id', ''))}] {name} — {dept}/{mod}")

    if len(docs) > 50:
        lines.append(f"\n  ... 共 {data.get('total', len(docs))} 篇，仅显示前 50 篇")

    return "\n".join(lines)


@mcp.tool()
async def keyword_search(keyword: str) -> str:
    """按关键词搜索，返回该关键词关联的部门/模块

    Args:
        keyword: 关键词，如"参考价"、"报销"、"招标"
    """
    data = await _api_get("/api/keywords", {"q": keyword})
    keywords = data.get("keywords", [])

    if not keywords:
        return f"未找到关键词「{keyword}」"

    lines = [f"关键词搜索「{keyword}」匹配 {data.get('total', len(keywords))} 条:\n"]
    for kw in keywords[:20]:
        k = kw.get("keyword", "")
        mappings = kw.get("mappings", [])
        if mappings:
            for m in mappings[:3]:
                dept = m.get("dept", "")
                mod = m.get("module", "")
                lines.append(f"  「{k}」→ {dept}/{mod}")
        else:
            depts = kw.get("depts", [])
            mods = kw.get("modules", [])
            lines.append(f"  「{k}」→ 部门:{','.join(depts)} 模块:{','.join(mods)}")

    return "\n".join(lines)


@mcp.tool()
async def dept_tree() -> str:
    """获取部门-模块树形结构"""
    data = await _api_get("/api/departments/tree")
    tree = data.get("tree", [])

    if not tree:
        return "暂无部门数据"

    def _render(node: dict, indent: int = 0) -> list[str]:
        prefix = "  " * indent
        icon = "🏢" if indent == 0 else "📂" if node.get("children") else "📄"
        doc_count = node.get("doc_count", "")
        count_str = f" ({doc_count}篇)" if doc_count else ""
        lines = [f"{prefix}{icon} {node.get('name', '')}{count_str}"]
        for child in node.get("children", []):
            lines.extend(_render(child, indent + 1))
        return lines

    lines = [f"共 {data.get('total_docs', 0)} 篇文档\n"]
    for node in tree:
        lines.extend(_render(node))

    return "\n".join(lines)


@mcp.tool()
async def health_check() -> str:
    """检查知识库后端健康状态"""
    data = await _api_get("/api/health")

    parts = [
        f"数据库: {data.get('db_type', '?')}",
        f"引擎: {'✅ 就绪' if data.get('engine_ready') else '❌ 未就绪'}",
    ]

    drift = data.get("drift", {})
    if drift.get("ok"):
        parts.append("漂移: ✅ 数据一致")
    else:
        for w in drift.get("warnings", []):
            parts.append(f"漂移: ⚠️ {w}")

    counts = data.get("counts", {})
    if counts and "error" not in counts:
        parts.append(
            f"数据量: FAQ={counts.get('faqs', 0)} "
            f"文档={counts.get('documents', 0)} "
            f"关键词={counts.get('keywords_v2', 0)}"
        )

    return "\n".join(parts)


# ════════════════ 启动 ════════════════

if __name__ == "__main__":
    mcp.run(transport="stdio")
