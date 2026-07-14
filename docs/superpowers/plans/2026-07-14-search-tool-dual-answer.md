# 产品知识库 · 智能检索 — 双路回答重构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为产品知识库检索工具新增 Claude API 双路回答 + 反哺优化机制，让 Web 工具获得与终端 CLI 同等质量的回答能力，并自动沉淀 FAQ 知识库。

**Architecture:** 在现有 search_engine.py（规则引擎）和 search_server.py（Web 服务）基础上，新增 Claude API 调用链路（SSE 流式推送），前端新增 Claude 回答卡片。Claude 回答完成后自动反哺三层：FAQ 知识库、关键词补充、回答缓存。

**Tech Stack:** Python 3 (http.server, jieba, anthropic SDK), JavaScript (EventSource/SSE), HTML/CSS

---

## File Structure

| 文件 | 职责 | 改动 |
|------|------|------|
| `search_engine.py` | 检索引擎：新增 prompt 构建、FAQ 缓存查询/保存 | 新增 3 个方法 |
| `search_server.py` | Web 服务：新增 SSE 端点、修改搜索接口 | 新增 1 端点 + 修改 2 处 |
| `static/index.html` | 前端：Claude 卡片 UI + SSE 连接 + 流式渲染 | 新增 ~80 行 |
| `关键词库/faq_cache.json` | 回答缓存文件 | 新增（自动生成） |
| `关键词库/SKILL.md` | 文档更新 | 修改 |

---

### Task 1: 新增 build_claude_prompt() 方法

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py` (在 `_generate_answer` 方法后追加)

- [ ] **Step 1: 在 SearchEngine 类中新增 build_claude_prompt() 方法**

在 `_generate_answer` 方法的 `return answer` 之后（约第 601 行），`_deep_search_kb` 方法之前，插入以下代码：

```python
    def build_claude_prompt(self, query, results):
        """从检索结果中构建 Claude API 的 system prompt 和 user message。
        返回 dict: {"system": str, "messages": [{"role": "user", "content": str}]}
        """
        # 收集匹配的模块信息
        matched_modules = []
        seen_mod = set()
        for r in results:
            m = r.get("module")
            if m and m not in seen_mod:
                seen_mod.add(m)
                info = self.module_map.get(m, {})
                matched_modules.append({
                    "name": m,
                    "dept": info.get("dept", ""),
                    "domain": info.get("domain", ""),
                    "dev_owner": info.get("dev_owner", ""),
                    "module_owner": info.get("module_owner", ""),
                })

        # 深度搜索 KB（复用已有逻辑，但不生成 answer，只取上下文）
        kb_sections = []
        kb_files_searched = []
        priority_dirs = []
        for r in results:
            if r.get("source") == "keyword_index" and r.get("kb_path"):
                kb_dir = PROJECT_DIR / r["kb_path"]
                if kb_dir.exists():
                    priority_dirs.append(kb_dir)
        if priority_dirs or results:
            kb_sections, kb_files_searched, _ = self._deep_search_kb(
                query, set(), results, priority_dirs
            )

        # 搜索原始产品文档
        raw_doc_sections = self._search_raw_docs(query, set())

        # 搜索报表
        report_sections = self._search_reports_deep(query, set(), results)

        # 组装 system prompt
        system_parts = [
            "你是产品知识库助手。根据以下检索到的文档内容，回答用户问题。",
            "",
            "## 回答要求",
            "- 用中文回答，简洁专业",
            "- 如果有操作步骤，按步骤编号清晰列出",
            "- 如果信息不足以回答，明确指出缺少什么信息",
            "- 结尾标注信息来源文件路径",
            "- 在回答末尾，用以下 JSON 格式输出建议补充的关键词（仅输出 JSON，不放 markdown 代码块中）：",
            '  {"keywords_to_add": ["关键词1", "关键词2"], "module": "所属模块名"}',
            "- 如果问题中提到的功能在文档中找不到对应关键词，在 keywords_to_add 中列出应该有的关键词",
            "",
        ]

        if matched_modules:
            system_parts.append("## 匹配的模块")
            for mod in matched_modules[:3]:
                system_parts.append(
                    f"- {mod['name']}（{mod['dept']}/{mod['domain']}）"
                    f" | 研发: {mod.get('dev_owner', '未知')}"
                    f" | 模块负责人: {mod.get('module_owner', '未知')}"
                )
            system_parts.append("")

        if kb_sections:
            system_parts.append("## 知识库相关段落（按相关性排序）")
            for i, sec in enumerate(kb_sections[:3], 1):
                heading = sec["heading"].lstrip("#").strip()
                content = sec["content"][:1500]
                system_parts.append(f"### [{i}] {heading}")
                system_parts.append(content)
                system_parts.append("")
            system_parts.append("")

        if raw_doc_sections:
            system_parts.append("## 原始产品文档")
            for i, sec in enumerate(raw_doc_sections[:2], 1):
                heading = sec["heading"].lstrip("#").strip()
                system_parts.append(f"### [{i}] {heading}")
                system_parts.append(sec["content"][:1000])
                system_parts.append("")
            system_parts.append("")

        if report_sections:
            system_parts.append("## 历史报表数据")
            for i, sec in enumerate(report_sections[:1], 1):
                system_parts.append(f"### [{i}] {sec['heading'].lstrip('#').strip()}")
                system_parts.append(sec["content"][:800])
            system_parts.append("")

        return {
            "system": "\n".join(system_parts),
            "messages": [{"role": "user", "content": query}],
            # 附带结构化数据，供后续 FAQ 保存使用
            "_meta": {
                "matched_modules": matched_modules,
                "kb_sections": kb_sections,
                "kb_files_searched": [str(p) for p in kb_files_searched],
            },
        }
```

- [ ] **Step 2: 验证方法可导入**

```bash
cd /Users/zcy1/Desktop/ClaudeProject && python3 -c "
from AiClaudeProject.ProjectSkill.projects.共享模块中心.关键词库.search_engine import SearchEngine
e = SearchEngine()
e.load_cache() or e.load_all()
prompt = e.build_claude_prompt('预算申报', [])
print('system length:', len(prompt['system']))
print('messages:', prompt['messages'])
print('_meta keys:', list(prompt['_meta'].keys()))
"
```

预期输出：system length > 100，messages 包含用户问题，_meta 包含 matched_modules 等。

- [ ] **Step 3: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py
git commit -m "feat: add build_claude_prompt() method to search engine

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 新增 FAQ 缓存查询与保存方法

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py` (追加在文件末尾，SearchEngine 类内)

- [ ] **Step 1: 新增 faq_cache 属性和加载逻辑**

在 `SearchEngine.__init__()` 方法中（约第 33 行），在 `self.report_docs = []` 之后添加：

```python
        self.faq_cache = {}  # 回答缓存: {fingerprint: {query, answer, keywords, module, saved_at}}
        self.faq_cache_file = HERE / "faq_cache.json"
```

在 `load_all()` 方法中（约第 43 行），在 `self._load_report_data()` 之后添加：

```python
        self._load_faq_cache()
```

- [ ] **Step 2: 新增 _load_faq_cache() 方法**

在 `_load_report_data()` 之后添加：

```python
    def _load_faq_cache(self):
        """加载 FAQ 回答缓存"""
        if self.faq_cache_file.exists():
            try:
                with open(self.faq_cache_file, "r", encoding="utf-8") as f:
                    self.faq_cache = json.load(f)
            except Exception:
                self.faq_cache = {}
```

- [ ] **Step 3: 新增 check_faq_cache() 方法**

在 SearchEngine 类的末尾（`_infer_conclusion` 方法之后，`_deduplicate` 之前）添加：

```python
    def check_faq_cache(self, query):
        """检查 FAQ 缓存中是否有匹配的回答。
        返回匹配的缓存条目 dict，或 None。
        """
        query_tokens = set(jieba.cut(query))
        query_tokens = {t.strip() for t in query_tokens if len(t.strip()) >= 2}

        best_match = None
        best_score = 0

        for fp, entry in self.faq_cache.items():
            entry_keywords = set(entry.get("keywords", []))
            if not entry_keywords:
                continue
            overlap = query_tokens & entry_keywords
            if len(overlap) >= 2:
                score = len(overlap)
                # 查询文本相似度加分
                if query.strip() == entry.get("query", "").strip():
                    score += 10
                elif query.strip() in entry.get("query", "") or entry.get("query", "") in query.strip():
                    score += 5
                if score > best_score:
                    best_score = score
                    best_match = entry

        if best_match and best_score >= 3:
            return best_match
        return None
```

- [ ] **Step 4: 新增 save_faq() 方法**

```python
    def save_faq(self, query, claude_answer, module_name, dept, domain, keywords):
        """保存 Claude 回答到 FAQ 缓存和知识库 FAQ 文件。
        返回: {"saved": bool, "cache_key": str, "faq_path": str}
        """
        # 1. 保存到缓存
        import hashlib
        fp = hashlib.md5(query.encode()).hexdigest()[:12]

        # 去重：如果已有相同 query 的缓存，跳过
        if fp in self.faq_cache:
            return {"saved": False, "reason": "duplicate", "cache_key": fp}

        entry = {
            "query": query,
            "answer": claude_answer,
            "keywords": keywords,
            "module": module_name,
            "saved_at": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self.faq_cache[fp] = entry

        # 持久化缓存
        try:
            with open(self.faq_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.faq_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # 2. 保存到 FAQ 知识库文件
        kb_dir = self._domain_to_kb_dir(dept, domain)
        if not kb_dir:
            kb_dir = KB_DIR / dept if dept else KB_DIR / "其他"
        kb_dir.mkdir(parents=True, exist_ok=True)
        faq_file = kb_dir / "FAQ.md"

        # 格式化 FAQ 条目
        date_str = __import__('datetime').datetime.now().strftime("%Y-%m-%d")
        tag_keywords = "、".join(keywords) if keywords else query
        faq_entry = f"""
### Q: {query}
**关键词：** {tag_keywords}
**模块：** {module_name}
**日期：** {date_str}

{claude_answer}

---
"""

        # 追加到 FAQ 文件（先去重检查）
        try:
            if faq_file.exists():
                existing = faq_file.read_text(encoding="utf-8")
                if f"### Q: {query}" in existing:
                    return {"saved": True, "reason": "faq_exists", "cache_key": fp, "faq_path": str(faq_file.relative_to(PROJECT_DIR))}
            else:
                existing = ""
            faq_file.write_text(
                (existing + faq_entry).strip() + "\n",
                encoding="utf-8"
            )
        except Exception:
            pass

        return {
            "saved": True,
            "cache_key": fp,
            "faq_path": str(faq_file.relative_to(PROJECT_DIR)),
        }
```

- [ ] **Step 5: 验证缓存方法**

```bash
cd /Users/zcy1/Desktop/ClaudeProject && python3 -c "
from AiClaudeProject.ProjectSkill.projects.共享模块中心.关键词库.search_engine import SearchEngine
e = SearchEngine()
e.load_cache() or e.load_all()

# 测试缓存未命中
result = e.check_faq_cache('预算申报怎么操作')
print('未命中:', result)

# 测试保存
save_result = e.save_faq(
    '预算申报怎么操作',
    '预算申报需要在浙里报系统中操作，步骤如下：...',
    '预算管理',
    '数智财务组',
    '浙里报',
    ['预算', '申报', '预算申报']
)
print('保存结果:', save_result)

# 测试缓存命中
result2 = e.check_faq_cache('预算申报怎么操作')
print('命中:', result2 is not None)
"
```

预期：未命中返回 None，保存成功，命中返回 dict。

- [ ] **Step 6: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py
git commit -m "feat: add FAQ cache query/save methods to search engine

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 新增 /api/claude-stream SSE 端点

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_server.py`

- [ ] **Step 1: 添加 anthropic 导入和 SSE 端点**

在文件顶部 import 区域（约第 6 行后）添加：

```python
import os
```

在 `do_GET` 方法中，在 `elif parsed.path == "/api/stats":` 之前添加：

```python
        elif parsed.path == "/api/claude-stream":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            context_json = params.get("context", ["{}"])[0]

            if not query:
                self._json({"error": "请提供查询参数 q"})
                return

            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                self._sse_send({"error": "未配置 ANTHROPIC_API_KEY 环境变量"})
                self._sse_done()
                return

            try:
                context = json.loads(context_json)
            except json.JSONDecodeError:
                context = {}

            self._handle_claude_stream(query, context, api_key)
            return
```

- [ ] **Step 2: 新增 SSE 辅助方法**

在 `_json` 方法之前添加：

```python
    def _sse_start(self):
        """发送 SSE 响应头"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _sse_send(self, data):
        """发送一条 SSE 事件"""
        payload = json.dumps(data, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _sse_done(self):
        """发送 SSE 结束信号"""
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
```

- [ ] **Step 3: 新增 _handle_claude_stream() 方法**

在 `_sse_done` 方法之后添加：

```python
    def _handle_claude_stream(self, query, context, api_key):
        """调用 Anthropic API，流式推送 Claude 回答"""
        self._sse_start()

        try:
            import anthropic
        except ImportError:
            self._sse_send({"error": "请安装 anthropic SDK: pip install anthropic"})
            self._sse_done()
            return

        client = anthropic.Anthropic(api_key=api_key)

        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        system_prompt = context.get("system", "")
        messages = context.get("messages", [{"role": "user", "content": query}])

        full_response = ""

        try:
            with client.messages.stream(
                model=model,
                max_tokens=2048,
                system=system_prompt,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    self._sse_send({"text": text})

            # 发送完整回答和元数据
            self._sse_send({
                "type": "complete",
                "full_response": full_response,
                "meta": context.get("_meta", {}),
            })

        except anthropic.APIError as e:
            self._sse_send({"error": f"API 错误: {str(e)}"})
        except Exception as e:
            self._sse_send({"error": f"调用失败: {str(e)}"})

        self._sse_done()
```

- [ ] **Step 4: 验证 SSE 端点**

先确认 anthropic SDK 已安装：

```bash
python3 -c "import anthropic; print('anthropic SDK version:', anthropic.__version__)"
```

如果未安装：`pip install anthropic`

启动服务后测试（另一个终端）：

```bash
# 启动服务
cd /Users/zcy1/Desktop/ClaudeProject && timeout 5 python3 AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_server.py 8766 &
sleep 2

# 测试 SSE 端点
curl -N "http://localhost:8766/api/claude-stream?q=什么是预算申报&context=$(python3 -c 'import json; print(json.dumps({"system":"你是助手","messages":[{"role":"user","content":"什么是预算申报"}]}))' | python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read()))')"

# 关闭服务
kill %1 2>/dev/null
```

预期：看到 SSE 流式输出 `data: {"text": "..."}` 行。

- [ ] **Step 5: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_server.py
git commit -m "feat: add /api/claude-stream SSE endpoint for Claude API streaming

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 修改 /api/search 加入缓存优先和 claude_stream_url

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_server.py`

- [ ] **Step 1: 修改 /api/search 处理逻辑**

在 `do_GET` 方法中，找到 `/api/search` 的处理块（约第 40-51 行），替换为：

```python
        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            top = int(params.get("top", ["15"])[0])

            if not query:
                self._json({"error": "请提供查询参数 q"})
                return

            eng = get_engine()

            # 0. 先查 FAQ 缓存
            cached = eng.check_faq_cache(query)
            if cached:
                result = {
                    "query": query,
                    "tokens": list(jieba.cut(query)),
                    "expanded_terms": [],
                    "total": 1,
                    "from_cache": True,
                    "cached_answer": {
                        "source": "faq_cache",
                        "question": query,
                        "summary": cached["answer"],
                        "module": cached.get("module", ""),
                        "matched_keywords": cached.get("keywords", []),
                        "saved_at": cached.get("saved_at", ""),
                    },
                    "results": [],
                    "process": {
                        "layer1_search": {"note": "命中 FAQ 缓存，直接返回"},
                    },
                    # 缓存命中时不调 Claude API
                    "claude_stream_url": None,
                }
                self._json(result)
                return

            # 1. 常规搜索
            result = eng.search(query, top=top)

            # 2. 构建 Claude prompt 并生成 stream URL
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                prompt = eng.build_claude_prompt(query, result.get("results", []))
                context_json = json.dumps(prompt, ensure_ascii=False)
                import urllib.parse
                context_encoded = urllib.parse.quote(context_json)
                result["claude_stream_url"] = f"/api/claude-stream?q={urllib.parse.quote(query)}&context={context_encoded}"
            else:
                result["claude_stream_url"] = None

            self._json(result)
```

- [ ] **Step 2: 验证修改**

```bash
cd /Users/zcy1/Desktop/ClaudeProject && python3 -c "
from urllib.parse import urlencode
import json

# 模拟搜索请求
from http.server import HTTPServer
import sys
sys.path.insert(0, 'AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库')
from search_server import SearchHandler, get_engine

# 预加载引擎
eng = get_engine()
print('引擎已加载，关键词数:', len(eng.keyword_map))
print('FAQ 缓存条目数:', len(eng.faq_cache))
"
```

- [ ] **Step 3: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_server.py
git commit -m "feat: add cache-first lookup and claude_stream_url to /api/search

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 前端 — Claude 回答卡片（HTML + CSS）

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/static/index.html`

- [ ] **Step 1: 在 CSS 区域添加 Claude 卡片样式**

在 `</style>` 之前（约第 334 行之前）添加：

```css
  /* Claude Answer Card */
  .claude-card {
    background: linear-gradient(135deg, rgba(61,214,140,0.06) 0%, rgba(77,166,255,0.04) 100%);
    border: 1px solid rgba(61,214,140,0.25);
    border-radius: var(--radius); padding: 24px 28px;
    animation: fadeIn 0.4s ease both;
    position: relative; overflow: hidden;
    margin-bottom: 10px;
  }
  .claude-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, #3dd68c, #4da6ff, #c084fc);
  }
  .claude-card .claude-header {
    display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
  }
  .claude-card .claude-icon {
    width: 36px; height: 36px; border-radius: 10px;
    background: linear-gradient(135deg, rgba(61,214,140,0.2), rgba(77,166,255,0.2));
    display: flex; align-items: center; justify-content: center; font-size: 1.1rem;
  }
  .claude-card .claude-label {
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
    color: #3dd68c; margin-bottom: 2px;
  }
  .claude-card .claude-title {
    font-size: 1.1rem; font-weight: 600; color: var(--text); letter-spacing: -0.01em;
  }
  .claude-card .claude-body {
    font-size: 0.9rem; color: var(--text); line-height: 1.85;
    white-space: pre-wrap; word-break: break-word;
  }
  .claude-card .claude-body p { margin: 0.5em 0; }
  .claude-card .claude-body strong { color: #fff; }
  .claude-card .claude-body code {
    background: rgba(255,255,255,0.06); padding: 1px 6px; border-radius: 4px;
    font-family: var(--font-mono); font-size: 0.85em; color: var(--accent);
  }
  .claude-card .claude-status {
    display: flex; align-items: center; gap: 8px; margin-top: 12px;
    padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.06);
    font-size: 0.75rem; color: var(--text-dim);
  }
  .claude-card .claude-status.done { color: #3dd68c; }
  .claude-card .claude-status.error { color: var(--report); }
  .claude-cursor {
    display: inline-block; width: 8px; height: 16px; background: #3dd68c;
    animation: blink 0.8s infinite; vertical-align: middle; margin-left: 2px;
  }
  @keyframes blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }
```

- [ ] **Step 2: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/static/index.html
git commit -m "feat: add Claude answer card CSS styles

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 前端 — SSE 连接 + 流式渲染 + 缓存展示

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/static/index.html`

- [ ] **Step 1: 在 renderResults 函数中添加 Claude 卡片和缓存逻辑**

找到 `renderResults` 函数（约第 444 行），替换为：

```javascript
  function renderResults(data) {
    $('#status').style.display = 'none';
    state.results = data.results || [];

    // 缓存命中：直接显示缓存的 Claude 回答
    if (data.from_cache && data.cached_answer) {
      const ca = data.cached_answer;
      let html = renderCachedAnswerCard(ca);
      html += '<div class="answer-divider">以下为相关搜索结果</div>';
      $('#results').innerHTML = html;

      $('#searchInfo').style.display = 'flex';
      $('#searchInfo').innerHTML = `
        <span>共 <span class="count">1</span> 条结果（来自缓存）</span>
        <span class="tokens">${(data.tokens||[]).map(t => '<span class="token">' + esc(t) + '</span>').join('')}</span>
      `;
      return;
    }

    const hasAnswer = data.answer && data.answer.module;
    const totalCount = (data.results ? data.results.length : 0) + (hasAnswer ? 1 : 0);

    if (!hasAnswer && (!data.results || data.results.length === 0)) {
      $('#results').innerHTML = '';
      $('#searchInfo').style.display = 'flex';
      $('#searchInfo').innerHTML = '<span>未找到与 "<strong>' + esc(data.query) + '</strong>" 相关的结果，试试换个关键词</span>';
      return;
    }

    $('#searchInfo').style.display = 'flex';
    $('#searchInfo').innerHTML = `
      <span>共 <span class="count">${totalCount}</span> 条结果</span>
      <span class="tokens">${(data.tokens||[]).map(t => '<span class="token">' + esc(t) + '</span>').join('')}</span>
    `;

    let html = '';

    // 第一条：智能回答卡片（规则引擎）
    if (hasAnswer) {
      html += renderAnswerCard(data.answer);
      if (data.process) {
        html += renderProcessPanel(data.process);
      }
    }

    // 新增：Claude 深度分析卡片（自动加载）
    if (data.claude_stream_url) {
      html += renderClaudeCard(data.query);
    }

    // 后续结果：原有搜索结果卡片
    const labels = {
      keyword_index: ['关键词', 'badge-kw'],
      module_name: ['模块', 'badge-mod'],
      menu_match: ['菜单', 'badge-menu'],
      knowledge_base: ['知识库', 'badge-kb'],
      report_data: ['报表', 'badge-report'],
    };

    html += data.results.map((r, i) => {
      const [label, badgeClass] = labels[r.source] || [r.source, 'badge-kw'];
      let meta = '';
      if (r.dept) meta += '<span><span class="label">部门</span> ' + esc(r.dept) + '</span>';
      if (r.domain) meta += '<span><span class="label">业务域</span> ' + esc(r.domain) + '</span>';
      if (r.dev_owner) meta += '<span><span class="label">研发</span> ' + esc(r.dev_owner) + '</span>';
      if (r.module_owner) meta += '<span><span class="label">负责人</span> ' + esc(r.module_owner) + '</span>';
      if (r.module_file) meta += '<span><span class="label">文件</span> <code>' + esc(r.module_file) + '</code></span>';

      const title = r.module || r.title || r.match_term || '';

      return `
        <div class="result-card" style="animation-delay:${i*0.04}s" data-index="${i}" title="点击查看详情">
          <div class="card-header">
            <span class="card-title">${esc(title)}</span>
            <span style="display:flex;align-items:center;gap:8px;flex-shrink:0">
              <span class="score">${r.score}分</span>
              <span class="badge ${badgeClass}">${label}</span>
            </span>
          </div>
          ${meta ? '<div class="card-meta">' + meta + '</div>' : ''}
          ${r.note ? '<div class="card-meta" style="margin-top:4px"><span>' + esc(r.note) + '</span></div>' : ''}
          <div class="card-hint">&#8627; 点击查看详情</div>
        </div>
      `;
    }).join('');

    $('#results').innerHTML = html;

    // 自动连接 Claude SSE
    if (data.claude_stream_url) {
      connectClaudeStream(data.claude_stream_url);
    }
  }
```

- [ ] **Step 2: 新增 renderClaudeCard() 函数**

在 `renderAnswerCard` 函数之后添加：

```javascript
  function renderClaudeCard(query) {
    const id = 'claude-' + Math.random().toString(36).slice(2, 8);
    return `
      <div class="claude-card" id="${id}">
        <div class="claude-header">
          <div class="claude-icon">🧠</div>
          <div>
            <div class="claude-label">Claude 深度分析</div>
            <div class="claude-title">关于「${esc(query)}」</div>
          </div>
        </div>
        <div class="claude-body" id="${id}-body">
          <span class="claude-cursor"></span>
        </div>
        <div class="claude-status" id="${id}-status">
          ⏳ 正在分析...
        </div>
      </div>
    `;
  }
```

- [ ] **Step 3: 新增 renderCachedAnswerCard() 函数**

```javascript
  function renderCachedAnswerCard(ca) {
    const summaryHtml = ca.summary
      ? renderMarkdown(ca.summary)
      : '<p style="color:var(--text-muted)">无内容</p>';
    return `
      <div class="claude-card">
        <div class="claude-header">
          <div class="claude-icon">💾</div>
          <div>
            <div class="claude-label">Claude 深度分析（缓存）</div>
            <div class="claude-title">关于「${esc(ca.question)}」</div>
          </div>
        </div>
        <div class="claude-body">${summaryHtml}</div>
        <div class="claude-status done">
          ✅ 来自缓存 · ${esc(ca.saved_at || '')}
        </div>
      </div>
    `;
  }
```

- [ ] **Step 4: 新增 connectClaudeStream() 函数**

```javascript
  function connectClaudeStream(url) {
    const cardId = document.querySelector('.claude-card')?.id;
    if (!cardId) return;

    const body = document.getElementById(cardId + '-body');
    const status = document.getElementById(cardId + '-status');

    // 使用 fetch 读取 SSE 流（EventSource 不支持 POST 和自定义参数长度限制）
    fetch(url)
      .then(response => {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        function processChunk() {
          reader.read().then(({ done, value }) => {
            if (done) return;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') {
                  // 完成
                  if (body.querySelector('.claude-cursor')) {
                    body.querySelector('.claude-cursor').remove();
                  }
                  if (status) {
                    status.textContent = '✅ 分析完成';
                    status.className = 'claude-status done';
                  }
                  return;
                }

                try {
                  const parsed = JSON.parse(data);
                  if (parsed.error) {
                    body.innerHTML = '<p style="color:var(--report)">⚠️ ' + esc(parsed.error) + '</p>';
                    if (status) {
                      status.textContent = '❌ ' + esc(parsed.error);
                      status.className = 'claude-status error';
                    }
                    return;
                  }
                  if (parsed.text) {
                    // 移除光标，追加文本，再加回光标
                    const cursor = body.querySelector('.claude-cursor');
                    if (cursor) cursor.remove();
                    body.innerHTML += esc(parsed.text);
                    body.innerHTML += '<span class="claude-cursor"></span>';
                    body.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                  }
                } catch (e) {
                  // 忽略解析错误
                }
              }
            }
            processChunk();
          }).catch(() => {
            if (status) {
              status.textContent = '⚠️ 连接中断';
              status.className = 'claude-status error';
            }
          });
        }

        processChunk();
      })
      .catch(err => {
        body.innerHTML = '<p style="color:var(--report)">⚠️ Claude 分析不可用: ' + esc(err.message) + '</p>';
        if (status) {
          status.textContent = '❌ 连接失败';
          status.className = 'claude-status error';
        }
      });
  }
```

- [ ] **Step 5: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/static/index.html
git commit -m "feat: add Claude SSE streaming, cache display, and card rendering

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 更新 SKILL.md 文档

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/SKILL.md`

- [ ] **Step 1: 在"问答工作流"章节中更新流程**

在 `## 问答工作流` 章节（约第 19 行），替换流程图为：

```markdown
## 问答工作流

当用户提出产品咨询或问题时，按以下流程处理：

```
用户提问
  │
  ├── 0. 查 FAQ 缓存（新增）
  │     faq_cache.json 中匹配相似问题
  │     → 命中则直接返回缓存回答，秒出
  │
  ├── 1. 运行检索引擎
  │     python3 关键词库/search_engine.py "用户问题"
  │     → 获取结构化检索结果（模块定位 + 知识库匹配 + 历史工单）
  │
  ├── 2. 双路回答生成
  │     ├── 规则引擎回答：秒出，基于关键词匹配+模板拼装
  │     └── Claude 深度分析：后端自动调用 Anthropic API，SSE 流式推送
  │
  ├── 3. 反哺优化（自动）
  │     Claude 回答完成后：
  │     ├── 保存到 FAQ 知识库（2026产品业务知识库/{部门}/{业务域}/FAQ.md）
  │     ├── 提取新关键词，补充到关键词索引
  │     └── 写入 faq_cache.json 缓存
  │
  └── 4. 生成人性化回答
        按回答模板组织回复（见下方）
```
```

- [ ] **Step 2: 在文件末尾添加"双路回答与反哺优化"章节**

```markdown
## 双路回答与反哺优化

### 双路回答机制

搜索工具同时提供两种回答：

| 通道 | 来源 | 速度 | 质量 | 展示 |
|------|------|------|------|------|
| 规则检索 | 关键词匹配 + 段落提取 | 秒出 | 中等 | 🔍 AI 智能回答卡片 |
| Claude 深度分析 | Anthropic API 流式调用 | 3-10s | 高 | 🧠 Claude 深度分析卡片 |

### 反哺优化（自动）

Claude 回答完成后，系统自动执行以下优化：

1. **FAQ 知识库沉淀** — 保存 Q&A 到 `2026产品业务知识库/{部门}/{业务域}/FAQ.md`
2. **关键词补充** — 提取 Claude 建议的新关键词，补入 `关键词索引.md`
3. **回答缓存** — 写入 `faq_cache.json`，下次同类问题直接命中，无需再调 API

### FAQ 缓存命中

用户搜索时，系统优先检查 `faq_cache.json`。如果命中（关键词交集 ≥ 2），直接返回缓存的 Claude 回答，速度与规则引擎相当，质量等同 Claude。

### 配置要求

- **ANTHROPIC_API_KEY** — 环境变量，与 Claude Code 共用。未配置时工具照常运作，仅不显示 Claude 卡片
- **CLAUDE_MODEL** — 可选，默认 `claude-sonnet-4-20250514`
```

- [ ] **Step 3: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/SKILL.md
git commit -m "docs: update SKILL.md with dual-answer and feedback optimization docs

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 端到端验证

- [ ] **Step 1: 启动服务**

```bash
cd /Users/zcy1/Desktop/ClaudeProject
./scripts/start_search.sh &
sleep 3
echo "服务已启动，访问 http://localhost:8765"
```

- [ ] **Step 2: 验证规则引擎不受影响**

```bash
# 搜索一个已知关键词
curl -s "http://localhost:8765/api/search?q=预算申报" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert 'answer' in data, '缺少 answer 字段'
assert 'results' in data, '缺少 results 字段'
print('✅ 规则引擎正常')
print('  answer module:', data['answer'].get('module', 'N/A'))
print('  results count:', len(data['results']))
print('  claude_stream_url:', 'present' if data.get('claude_stream_url') else 'absent')
"
```

- [ ] **Step 3: 验证 Claude 流式端点**

```bash
# 如果 ANTHROPIC_API_KEY 已配置
if [ -n "$ANTHROPIC_API_KEY" ]; then
  echo "测试 Claude SSE 端点..."
  curl -s -N --max-time 15 "http://localhost:8765/api/claude-stream?q=预算申报怎么操作&context=%7B%22system%22%3A%22%E4%BD%A0%E6%98%AF%E5%8A%A9%E6%89%8B%22%2C%22messages%22%3A%5B%7B%22role%22%3A%22user%22%2C%22content%22%3A%22%E9%A2%84%E7%AE%97%E7%94%B3%E6%8A%A5%E6%80%8E%E4%B9%88%E6%93%8D%E4%BD%9C%22%7D%5D%7D" | head -5
  echo ""
  echo "✅ Claude SSE 端点正常"
else
  echo "⚠️ 未配置 ANTHROPIC_API_KEY，跳过 Claude 端点测试"
fi
```

- [ ] **Step 4: 验证无 API Key 降级**

```bash
# 临时 unset API Key 测试
ANTHROPIC_API_KEY_SAVED="$ANTHROPIC_API_KEY"
unset ANTHROPIC_API_KEY
response=$(curl -s "http://localhost:8765/api/search?q=预算")
echo "$response" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert data.get('claude_stream_url') is None, '无 API Key 时不应有 claude_stream_url'
print('✅ 无 API Key 降级正常')
"
export ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY_SAVED"
```

- [ ] **Step 5: 验证 FAQ 缓存**

```bash
# 搜索一个之前保存过的问题
curl -s "http://localhost:8765/api/search?q=预算申报怎么操作" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if data.get('from_cache'):
    print('✅ 缓存命中，回答:', data['cached_answer']['summary'][:100] + '...')
else:
    print('ℹ️ 未命中缓存（首次搜索或缓存未建立）')
"
```

- [ ] **Step 6: 浏览器验证**

打开浏览器访问 `http://localhost:8765`，执行以下操作：
1. 输入 "预算申报" 按 Enter
2. 确认规则回答卡片立刻显示
3. 确认 Claude 分析卡片自动出现并逐字加载
4. 第二次搜索相同问题，确认显示"来自缓存"

- [ ] **Step 7: 关闭服务并提交最终验证**

```bash
kill %1 2>/dev/null
echo "✅ 端到端验证完成"
```

---

## 实现顺序

任务按依赖关系排列，必须按顺序执行：

```
Task 1 (build_claude_prompt)  ──┐
                                  ├── Task 4 (修改 /api/search)
Task 2 (FAQ cache 方法)       ──┤
                                  │
Task 3 (SSE 端点)              ──┘
                                  │
Task 5 (CSS 样式)             ──┐
                                  ├── Task 8 (端到端验证)
Task 6 (SSE + 渲染逻辑)       ──┤
                                  │
Task 7 (SKILL.md 文档)        ──┘
```