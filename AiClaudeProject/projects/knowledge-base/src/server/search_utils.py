"""
search_utils.py - 搜索引擎纯工具函数

从 search_engine.py 提取的无状态辅助函数，不依赖 self.* 属性。
"""

import re


# ── 文本提取 ──

def extract_title(text):
    """从 Markdown 文本中提取文档标题（第一个 # 标题）"""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return ""


def extract_snippets(text, terms, max_snippets=2, context_len=60):
    """从文本中提取包含搜索词的摘要片段"""
    snippets = []
    for term in terms:
        if not term or len(term) < 2:
            continue
        idx = text.lower().find(term.lower())
        if idx >= 0:
            start = max(0, idx - context_len)
            end = min(len(text), idx + len(term) + context_len)
            snippet = text[start:end].strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."
            if snippet not in snippets:
                snippets.append(snippet)
        if len(snippets) >= max_snippets:
            break
    return snippets


# ── 评分与排序 ──

def match_score(text, terms):
    """计算文本与搜索词的匹配分数"""
    if not text or not terms:
        return 0
    text_lower = text.lower()
    score = 0
    for term in terms:
        if not term:
            continue
        count = text_lower.count(term.lower())
        if count > 0:
            score += min(count, 5)  # 高频词上限 5 分
    return score


def deduplicate(results):
    """按 (source, module, path) 去重，保留最高分"""
    seen = {}
    for r in results:
        key = (r.get("source", ""), r.get("module", ""), r.get("path", ""))
        if key not in seen or r.get("score", 0) > seen[key].get("score", 0):
            seen[key] = r
    return list(seen.values())


def rank(results, query, expanded):
    """按分数降序排列，同分按：匹配词数 → 关键词匹配率 → 新鲜度"""
    def sort_key(r):
        score = r.get("score", 0)
        match_count = len(r.get("match_terms", []))
        # 关键词匹配率：匹配词数 / 查询词数（越高越相关）
        query_terms = len([t for t in expanded if len(t) >= 2])
        match_ratio = min(match_count / max(query_terms, 1), 1.0) if query_terms > 0 else 0
        # 新鲜度：从 path 提取日期，越新越好
        freshness = 0
        path = r.get("path", "") or r.get("kb_path", "")
        import re as _re
        m = _re.search(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})', path)
        if m:
            try:
                freshness = int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3))
            except Exception:
                pass
        # 浏览量：FAQ 被点击越多越靠前
        view_count = r.get("view_count", 0)
        return (score, match_count, round(match_ratio, 2), freshness, view_count)
    return sorted(results, key=sort_key, reverse=True)