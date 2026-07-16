# 产品知识库检索优化 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将产品知识库检索从纯关键词匹配升级为 BM25 + 向量语义检索 + FAQ 缓存的三路并行架构，同时优化回答生成质量。

**Architecture:** 新增 `BM25Index`（倒排索引 + BM25 排序）和 `VectorIndex`（sentence-transformers + FAISS）两个独立模块，SearchEngine 集成三路并行检索。规则引擎精简为快速摘要，Claude 负责深度回答，前端并行展示。

**Tech Stack:** Python 3, jieba, sentence-transformers, faiss-cpu, pickle, Anthropic API (SSE)

---

## 文件结构

```
共享模块中心/关键词库/
├── bm25_index.py          ← 新增：BM25Index 类（倒排索引 + BM25 排序）
├── vector_index.py        ← 新增：VectorIndex 类（sentence-transformers + FAISS）
├── search_engine.py       ← 修改：集成 BM25/Vector，精简 _build_summary，升级 prompt
├── search_server.py       ← 修改：并行展示逻辑
├── faq_cache.json         ← 新增：种子数据填充 + 自学习积累
├── bm25_index.pkl         ← 新增：BM25 倒排索引缓存（自动生成）
├── vector_index.faiss     ← 新增：FAISS 向量索引（自动生成）
├── vector_meta.pkl        ← 新增：向量索引元数据（自动生成）
├── requirements.txt       ← 新增：sentence-transformers, faiss-cpu
├── synonyms.json          ← 修改：补全同义词
└── static/index.html      ← 修改：并行展示 UI
```

---

### Task 1: Create BM25Index class

**Files:**
- Create: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/bm25_index.py`

- [ ] **Step 1: Create bm25_index.py with full BM25Index implementation**

```python
#!/usr/bin/env python3
"""BM25 文档检索引擎 - 倒排索引 + BM25 排序算法"""
import pickle
import math
import logging
from collections import defaultdict

import jieba
jieba.setLogLevel(logging.WARNING)


class BM25Index:
    """BM25 文档检索引擎。

    用法:
        bm25 = BM25Index()
        bm25.build([{'path': '...', 'content': '...', 'dept': '...', 'domain': '...'}, ...])
        results = bm25.search(['关键词1', '关键词2'], k=10)
        bm25.save('bm25_index.pkl')
        bm25.load('bm25_index.pkl')
    """

    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.documents = []       # [(doc_id, path, dept, domain)]
        self.inverted_index = defaultdict(dict)  # term -> {doc_id: term_frequency}
        self.doc_lengths = {}     # doc_id -> total_terms
        self.avg_dl = 0
        self.N = 0

    def build(self, kb_docs):
        """从 KB 文档列表构建倒排索引。

        kb_docs: list of dict, each with keys: path, content, dept, domain
        """
        self.documents = []
        self.inverted_index = defaultdict(dict)
        self.doc_lengths = {}

        for i, doc in enumerate(kb_docs):
            doc_id = i
            self.documents.append((
                doc_id,
                doc.get('path', ''),
                doc.get('dept', ''),
                doc.get('domain', ''),
            ))

            text = doc.get('content', '')
            tokens = [t.strip() for t in jieba.cut(text) if len(t.strip()) >= 1]
            self.doc_lengths[doc_id] = len(tokens)

            term_freq = defaultdict(int)
            for token in tokens:
                term_freq[token] += 1

            for term, freq in term_freq.items():
                self.inverted_index[term][doc_id] = freq

        self.N = len(self.documents)
        total_len = sum(self.doc_lengths.values())
        self.avg_dl = total_len / self.N if self.N > 0 else 1

    def _idf(self, term):
        """计算 IDF（逆文档频率），使用 BM25 标准公式"""
        df = len(self.inverted_index.get(term, {}))
        return math.log((self.N - df + 0.5) / (df + 0.5) + 1)

    def search(self, query_terms, k=10):
        """BM25 搜索，返回 Top-K 文档的 (path, score) 列表。

        query_terms: list of str, 已经过分词和扩展的查询词列表
        """
        scores = defaultdict(float)

        for term in query_terms:
            if term not in self.inverted_index:
                continue
            idf = self._idf(term)
            for doc_id, tf in self.inverted_index[term].items():
                doc_len = self.doc_lengths.get(doc_id, 1)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_dl)
                scores[doc_id] += idf * numerator / denominator

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
        return [(self.documents[doc_id][1], score) for doc_id, score in ranked]

    def save(self, path):
        """序列化到磁盘（pickle 格式）"""
        data = {
            'k1': self.k1, 'b': self.b,
            'documents': self.documents,
            'inverted_index': dict(self.inverted_index),
            'doc_lengths': self.doc_lengths,
            'avg_dl': self.avg_dl, 'N': self.N,
        }
        with open(path, 'wb') as f:
            pickle.dump(data, f)

    def load(self, path):
        """从磁盘加载"""
        with open(path, 'rb') as f:
            data = pickle.load(f)
        self.k1 = data['k1']
        self.b = data['b']
        self.documents = data['documents']
        self.inverted_index = defaultdict(dict, data['inverted_index'])
        self.doc_lengths = data['doc_lengths']
        self.avg_dl = data['avg_dl']
        self.N = data['N']
        return True
```

- [ ] **Step 2: Verify BM25Index works standalone**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 -c "
from bm25_index import BM25Index
bm25 = BM25Index()
docs = [
    {'path': 'a.md', 'content': '预算管理模块支持预算申报和预算执行功能', 'dept': '数智财务组', 'domain': '浙里报'},
    {'path': 'b.md', 'content': '疫苗管理支持HPV疫苗接种和免疫程序配置', 'dept': '免疫规划组', 'domain': '免疫规划组'},
]
bm25.build(docs)
results = bm25.search(['预算', '申报'], k=2)
print('BM25 results:', results)
assert len(results) > 0
assert 'a.md' in results[0][0]
print('BM25Index works correctly')
"
```

Expected: `BM25Index works correctly`

- [ ] **Step 3: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/bm25_index.py
git commit -m "feat: add BM25Index class for document-level search ranking

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Integrate BM25Index into SearchEngine

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py`

- [ ] **Step 1: Add import and init**

At the top of `search_engine.py`, after the existing imports (line 14), add:

```python
from bm25_index import BM25Index
```

In `SearchEngine.__init__` (line 33), after `self.faq_cache_file = HERE / "faq_cache.json"`, add:

```python
        self.bm25 = None
        self.bm25_cache_file = HERE / "bm25_index.pkl"
```

- [ ] **Step 2: Add _load_bm25_index method**

In the `SearchEngine` class, after `_load_faq_cache` (line 235), add:

```python
    def _load_bm25_index(self):
        """加载或构建 BM25 索引"""
        self.bm25 = BM25Index()
        if self.bm25_cache_file.exists():
            self.bm25.load(str(self.bm25_cache_file))
            return

        # 首次构建：读取所有 KB 文件全文
        kb_contents = []
        for doc in self.kb_docs:
            full_path = PROJECT_DIR / doc['path']
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding='utf-8')
            except Exception:
                content = ''
            kb_contents.append({
                'path': doc['path'],
                'content': content,
                'dept': doc.get('dept', ''),
                'domain': doc.get('domain', ''),
            })

        if kb_contents:
            self.bm25.build(kb_contents)
            self.bm25.save(str(self.bm25_cache_file))
```

- [ ] **Step 3: Add _load_bm25_index to load_all**

In `load_all` (line 45), after `self._load_faq_cache()`, add:

```python
        self._load_bm25_index()
```

- [ ] **Step 4: Add BM25 save to save_cache**

In `save_cache` (line 1569), after saving the JSON cache, add:

```python
        # Also save BM25 index
        if self.bm25 and self.bm25.N > 0:
            self.bm25.save(str(self.bm25_cache_file))
```

- [ ] **Step 5: Verify integration**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 search_engine.py "预算申报" --rebuild --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Total results:', data['total'])
print('BM25 loaded:', 'bm25' in str(data.get('process', {})))
"
```

Expected: `Total results:` shows a number >0, BM25 index is built

- [ ] **Step 6: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py
git commit -m "feat: integrate BM25Index into SearchEngine with auto-build on --rebuild

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Implement two-stage ranking in _deep_search_kb

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py`

- [ ] **Step 1: Rewrite _deep_search_kb to use BM25 for document filtering**

Replace the current `_deep_search_kb` method (lines 750-855) with the new version. The key change: S1 uses BM25 to get Top-10 documents, S2 does paragraph-level fine matching.

```python
    def _deep_search_kb(self, query, expanded, results, priority_dirs=None):
        """两阶段深度搜索 KB 文档。

        S1: BM25 文档级筛选 → Top-10 文档
        S2: 段落级精细匹配 → Top-5 段落
        """
        sections = []
        search_terms = list(expanded) + [query]

        # S1: BM25 文档级筛选
        if self.bm25 and self.bm25.N > 0:
            doc_results = self.bm25.search(search_terms, k=10)
            doc_paths = [p for p, score in doc_results]
        else:
            # Fallback: 使用原有的 priority_dirs + kb_paths 逻辑
            doc_paths = self._collect_kb_paths_fallback(results, priority_dirs)

        # S2: 段落级精细匹配
        for path in doc_paths[:10]:
            full_path = PROJECT_DIR / path
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding='utf-8')
            except Exception:
                continue

            segments = self._split_by_heading(content, path)
            for seg in segments:
                if seg['heading'] == '(文档开头)':
                    continue

                # 多维评分
                keyword_score = self._match_score(seg['content'], search_terms)
                heading_score = self._match_score(seg['heading'], search_terms) * 3
                parent_heading_score = self._match_score(
                    seg.get('parent_heading', ''), search_terms
                ) * 1.5

                # FAQ 区域加权
                is_faq = any(kw in seg['heading'] for kw in ['FAQ', '常见问题', '故障', '排查'])
                faq_bonus = 2.0 if is_faq else 0

                # 文档新鲜度
                date = self._extract_date_from_path(path)
                freshness = 1.0
                if date:
                    from datetime import date as date_type
                    days_ago = (date_type.today() - date).days
                    if days_ago > 365:
                        freshness = max(0.5, 1.0 - (days_ago - 365) / 365)

                total_score = (
                    keyword_score * 0.4
                    + heading_score * 0.25
                    + parent_heading_score * 0.15
                    + faq_bonus * 0.1
                ) * freshness

                if total_score >= 0.5:
                    images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', seg['content'])
                    sections.append({
                        'path': path,
                        'heading': seg['heading'],
                        'parent_heading': seg.get('parent_heading', ''),
                        'content': seg['content'][:1500],
                        'images': [{'alt': alt, 'src': src} for alt, src in images],
                        'score': total_score,
                        'line_start': seg.get('line_start', 0),
                    })

        sections.sort(key=lambda s: s['score'], reverse=True)

        chapter_group = None
        if sections:
            chapter_group = self._build_chapter_group(sections[0])

        return sections[:5], doc_paths[:10], chapter_group

    def _collect_kb_paths_fallback(self, results, priority_dirs=None):
        """Fallback: 当 BM25 不可用时，从 results 和 priority_dirs 收集 KB 文档路径"""
        paths = []
        if priority_dirs:
            for d in priority_dirs:
                for f in sorted(d.rglob('*.md'), reverse=True):
                    paths.append(str(f.relative_to(PROJECT_DIR)))
        for r in results:
            if r.get('source') == 'knowledge_base' and r.get('path'):
                if r['path'] not in paths:
                    paths.append(r['path'])
        return paths

    def _extract_date_from_path(self, path):
        """从文件路径中提取日期，如 2026-07-07_版本迭代.md → date(2026, 7, 7)"""
        import re
        from datetime import date
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', path)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
        return None
```

- [ ] **Step 2: Verify two-stage ranking**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 search_engine.py "HPV疫苗怎么接种" --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
proc = data.get('process', {})
layer2 = proc.get('layer2_deep_search', {})
print('KB files searched:', layer2.get('kb_files_searched', []))
print('Sections found:', layer2.get('sections_found', 0))
top = layer2.get('top_sections', [])
if top:
    print('Top section:', top[0]['heading'], 'score:', top[0]['score'])
"
```

Expected: Should find relevant sections about HPV/疫苗 in the immune planning group knowledge base

- [ ] **Step 3: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py
git commit -m "feat: implement two-stage ranking with BM25 doc filtering + paragraph fine-matching

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Simplify _build_summary rule engine

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py`

- [ ] **Step 1: Replace _build_summary with simplified version**

Replace the current `_build_summary` method (lines 1132-1262) and its helper methods `_find_child`, `_clean_text`, `_format_steps`, `_extract_status_table`, `_generate_takeaway_v2`, `_generate_takeaway`, `_extract_first_feature`, `_extract_action`, `_infer_conclusion` with the simplified version:

```python
    def _build_summary(self, query, matched_modules, kb_sections,
                       raw_doc_sections, report_sections, chapter_group=None):
        """快速摘要：只做模块定位 + 关键信息提取，完整回答交给 Claude。

        精简为 ~50 行，仅做 3 件事：
        1. 模块定位
        2. 提取最佳段落前 200 字
        3. 组装返回
        """
        parts = []

        # 判断问题类型
        is_how = any(kw in query for kw in ['怎么', '如何', '怎样', '怎么办', '操作'])
        is_what = any(kw in query for kw in ['什么是', '是什么', '功能说明', '介绍'])
        is_yes_no = any(kw in query for kw in ['可以', '能不能', '是否', '支持', '有没有', '会不会'])

        if is_yes_no:
            parts.append('✅ **支持。**' if any(
                kw in (kb_sections[0]['content'] if kb_sections else '')
                for kw in ['支持', '新增', '增加', '可以']
            ) else '❌ **暂不支持。**')
        elif is_how:
            parts.append(f'🔧 **关于「{query}」的处理方案：**')
        elif is_what:
            parts.append(f'📖 **关于「{query}」的说明：**')
        else:
            parts.append(f'📖 **查询结果：**')

        # 模块定位
        if matched_modules:
            mod = matched_modules[0]
            parts.append(
                f'📍 所属模块：「{mod["name"]}」'
                + (f'（{mod.get("domain", "")} / {mod.get("dept", "")}）' if mod.get('domain') else '')
                + (f'，负责人：{mod.get("module_owner", "")}' if mod.get('module_owner') else '')
                + (f'（研发 {mod.get("dev_owner", "")}）' if mod.get('dev_owner') else '')
            )

        # 最佳段落摘要
        if kb_sections:
            best = kb_sections[0]
            content = best['content']
            # 简单清理：去图片语法、去 markdown 标记
            content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
            content = re.sub(r'\*\*', '', content)
            content = re.sub(r'#{1,4}\s+', '', content)
            if len(content) > 200:
                content = content[:200] + '...'
            parts.append(f'\n{content.strip()}')

            # 文档位置
            kb_rel = best['path'].replace('2026产品业务知识库/', '')
            parts.append(f'\n📁 知识库：`{kb_rel}` (第{best.get("line_start", "?")}行附近)')

        # 原始文档引用
        if raw_doc_sections:
            raw = raw_doc_sections[0]
            raw_rel = raw['path'].replace('原始产品文档/', '')
            parts.append(f'📄 原始文档：`{raw_rel}`')

        return '\n'.join(parts) if parts else f'关于「{query}」，未在知识库中找到直接相关内容。建议尝试更具体的关键词或联系相关模块负责人。'
```

- [ ] **Step 2: Verify simplified summary**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 search_engine.py "预算申报怎么操作" --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
answer = data.get('answer', {})
if answer:
    print('Summary:', answer.get('summary', '')[:300])
    print('Module:', answer.get('module', ''))
"
```

Expected: Summary shows module location + snippet, no longer has complex chapter-group parsing

- [ ] **Step 3: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py
git commit -m "refactor: simplify _build_summary to ~50 lines, delegate full answer to Claude

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: FAQ seed data population

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py`

- [ ] **Step 1: Add seed_faq_cache method to SearchEngine**

In `SearchEngine` class, after the `_load_faq_cache` method, add:

```python
    def seed_faq_cache(self):
        """从 KB 文件和模块文件提取种子 FAQ，批量写入 faq_cache.json。

        来源1: KB 文件中的 FAQ/常见问题章节
        来源2: 模块文件关键词 → 生成"什么是XX"类问题
        """
        import hashlib
        from datetime import datetime

        seeds = []
        seen_queries = set()

        # 来源1: KB 文件中的 FAQ 章节
        for doc in self.kb_docs:
            full_path = PROJECT_DIR / doc['path']
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding='utf-8')
            except Exception:
                continue

            # 查找 FAQ 章节
            faq_match = re.search(
                r'##\s*(?:FAQ|常见问题|故障库|常见问题&故障库).*?\n(.*?)(?=\n##\s+\w|\Z)',
                content, re.DOTALL
            )
            if faq_match:
                # 提取 Q&A 对：### Q: xxx\n...\n### Q: 或 ## 结束
                qa_pairs = re.findall(
                    r'###\s*Q:\s*(.+?)\n(.*?)(?=\n###\s*Q:|\n##\s|\Z)',
                    faq_match.group(1), re.DOTALL
                )
                for q, a in qa_pairs:
                    q = q.strip()
                    if q in seen_queries:
                        continue
                    seen_queries.add(q)
                    seeds.append({
                        'query': q,
                        'answer': a.strip()[:800],
                        'keywords': [t.strip() for t in jieba.cut(q) if len(t.strip()) >= 2],
                        'module': doc.get('domain', ''),
                        'dept': doc.get('dept', ''),
                        'domain': doc.get('domain', ''),
                    })

        # 来源2: 模块文件关键词 → 生成基础问答
        for mod_name, info in self.module_map.items():
            keywords = info.get('keywords', [])
            for kw in keywords[:3]:
                q = f'{kw}是什么'
                if q in seen_queries:
                    continue
                seen_queries.add(q)
                dept = info.get('dept', '')
                domain = info.get('domain', '')
                owner = info.get('module_owner', '')
                dev = info.get('dev_owner', '')
                owner_str = f'{owner}（研发 {dev}）' if dev else owner
                answer = (
                    f'{kw}属于「{mod_name}」模块'
                    + (f'（{domain} / {dept}）' if domain else '')
                    + (f'，由{owner_str}负责。' if owner_str else '。')
                )
                seeds.append({
                    'query': q,
                    'answer': answer,
                    'keywords': [kw, mod_name],
                    'module': mod_name,
                    'dept': dept,
                    'domain': domain,
                })

        # 批量写入
        for seed in seeds:
            fp = hashlib.md5(seed['query'].encode()).hexdigest()[:12]
            if fp not in self.faq_cache:
                self.faq_cache[fp] = {
                    'query': seed['query'],
                    'answer': seed['answer'],
                    'keywords': seed['keywords'],
                    'module': seed['module'],
                    'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                }

        # 持久化
        with open(self.faq_cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.faq_cache, f, ensure_ascii=False, indent=2)

        return len(seeds)
```

- [ ] **Step 2: Add --seed-faq CLI flag**

In `main()` (line 1596), after `--rebuild` argument, add:

```python
    parser.add_argument("--seed-faq", action="store_true", help="填充 FAQ 种子数据")
```

And before the query check, add:

```python
    if args.seed_faq:
        engine = SearchEngine()
        engine._load_synonyms()
        engine._load_keyword_index()
        engine._load_module_files()
        engine._load_knowledge_base()
        engine._load_faq_cache()
        count = engine.seed_faq_cache()
        print(f"FAQ 种子数据已填充，共 {count} 条")
        sys.exit(0)
```

- [ ] **Step 3: Run seed-faq**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 search_engine.py --seed-faq
```

Expected: `FAQ 种子数据已填充，共 XX 条` (should be 50+)

- [ ] **Step 4: Verify FAQ cache works**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 -c "
from search_engine import SearchEngine
eng = SearchEngine()
eng._load_faq_cache()
print(f'FAQ cache entries: {len(eng.faq_cache)}')
for fp, entry in list(eng.faq_cache.items())[:3]:
    print(f'  - {entry[\"query\"][:50]}')
"
```

Expected: FAQ cache has entries, showing sample queries

- [ ] **Step 5: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/faq_cache.json
git commit -m "feat: add FAQ seed data population from KB files and module keywords

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Verify Phase 1

**Files:** None (manual verification)

- [ ] **Step 1: Run rebuild with all Phase 1 changes**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 search_engine.py "测试" --rebuild 2>&1 | head -5
```

Expected: No errors, search completes

- [ ] **Step 2: Test 5 typical queries and check results**

```bash
python3 search_engine.py "怎么提交报销单" --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Query:', data['query'])
print('Total results:', data['total'])
ans = data.get('answer', {})
if ans:
    print('Module:', ans.get('module', ''))
    print('Dept:', ans.get('dept', ''))
    print('Summary preview:', ans.get('summary', '')[:150])
"

python3 search_engine.py "HPV疫苗接种" --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Query:', data['query'])
print('Total results:', data['total'])
ans = data.get('answer', {})
if ans:
    print('Module:', ans.get('module', ''))
"

python3 search_engine.py "预算指标怎么配置" --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Query:', data['query'])
print('Total results:', data['total'])
ans = data.get('answer', {})
if ans:
    print('Module:', ans.get('module', ''))
"
```

Expected: Each query returns module name and relevant results

- [ ] **Step 3: Check BM25 index file exists**

```bash
ls -la /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/bm25_index.pkl
```

Expected: File exists with reasonable size

- [ ] **Step 4: Check FAQ cache file exists and has entries**

```bash
python3 -c "
import json
with open('/Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/faq_cache.json') as f:
    data = json.load(f)
print(f'FAQ cache entries: {len(data)}')
"
```

Expected: 50+ entries

---

### Task 7: Install dependencies for Phase 2

**Files:**
- Create: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```txt
sentence-transformers>=2.2.0
faiss-cpu>=1.7.0
numpy>=1.21.0
```

- [ ] **Step 2: Install dependencies**

```bash
pip3 install sentence-transformers faiss-cpu
```

Expected: Packages install successfully. On first run, sentence-transformers will download the MiniLM model (~120MB).

- [ ] **Step 3: Verify imports work**

```bash
python3 -c "
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
print('All imports OK')
print('FAISS version:', faiss.__version__)
"
```

Expected: `All imports OK` with FAISS version

- [ ] **Step 4: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/requirements.txt
git commit -m "feat: add requirements.txt with sentence-transformers and faiss-cpu

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Create VectorIndex class

**Files:**
- Create: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/vector_index.py`

- [ ] **Step 1: Create vector_index.py with full VectorIndex implementation**

```python
#!/usr/bin/env python3
"""向量检索引擎 - sentence-transformers + FAISS 语义检索"""
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss


class VectorIndex:
    """向量语义检索引擎。

    用法:
        vi = VectorIndex()
        vi.build([{'path': '...', 'heading': '...', 'content': '...'}, ...])
        results = vi.search('查询文本', k=10)
        vi.save('vector_index.faiss', 'vector_meta.pkl')
        vi.load('vector_index.faiss', 'vector_meta.pkl')
    """

    def __init__(self, model_name='paraphrase-multilingual-MiniLM-L12-v2'):
        self.model = SentenceTransformer(model_name)
        self.index = None       # FAISS IndexFlatIP
        self.sections = []      # [{path, heading, content}]
        self.dim = 384          # MiniLM 输出维度

    def build(self, kb_segments):
        """对 KB 段落列表生成 embedding 并建 FAISS 索引。

        kb_segments: list of dict, each with keys: path, heading, content
        """
        embeddings = []
        self.sections = []

        for seg in kb_segments:
            text = seg.get('content', '')
            if len(text) < 50:
                continue
            # 取前 512 字符做 embedding（平衡速度和语义覆盖）
            emb = self.model.encode(text[:512], convert_to_numpy=True)
            embeddings.append(emb)
            self.sections.append({
                'path': seg.get('path', ''),
                'heading': seg.get('heading', ''),
                'content': text[:1500],
            })

        if not embeddings:
            return

        emb_matrix = np.array(embeddings).astype('float32')
        # L2 归一化，使内积等价于余弦相似度
        faiss.normalize_L2(emb_matrix)
        self.index = faiss.IndexFlatIP(self.dim)
        self.index.add(emb_matrix)

    def encode(self, text):
        """编码单条文本为归一化向量"""
        emb = self.model.encode(text[:512], convert_to_numpy=True)
        emb = emb.astype('float32').reshape(1, -1)
        faiss.normalize_L2(emb)
        return emb

    def search(self, query, k=10):
        """向量检索 Top-K 段落。返回 [{path, heading, content, score}, ...]"""
        if self.index is None:
            return []

        query_emb = self.encode(query)
        scores, indices = self.index.search(query_emb, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.sections):
                continue
            sec = self.sections[idx].copy()
            sec['score'] = float(score)
            results.append(sec)

        return results

    def save(self, index_path, meta_path):
        """保存 FAISS 索引和元数据到磁盘"""
        if self.index is not None:
            faiss.write_index(self.index, str(index_path))
        with open(meta_path, 'wb') as f:
            pickle.dump({'sections': self.sections, 'dim': self.dim}, f)

    def load(self, index_path, meta_path):
        """从磁盘加载 FAISS 索引和元数据"""
        import os
        if os.path.exists(str(index_path)):
            self.index = faiss.read_index(str(index_path))
        if os.path.exists(str(meta_path)):
            with open(meta_path, 'rb') as f:
                data = pickle.load(f)
            self.sections = data['sections']
            self.dim = data.get('dim', 384)
        return True
```

- [ ] **Step 2: Verify VectorIndex works standalone**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 -c "
from vector_index import VectorIndex
vi = VectorIndex()
segments = [
    {'path': 'a.md', 'heading': '预算申报', 'content': '预算申报是指单位向财政部门提交年度预算的过程，包括项目预算申报和基本支出预算申报。'},
    {'path': 'b.md', 'heading': '疫苗接种', 'content': 'HPV疫苗接种适用于9-45岁女性，按0-2-6月三针法完成全程接种。'},
    {'path': 'c.md', 'heading': '报销流程', 'content': '报销流程包括提交报销单、审批、审核、财务结算四个步骤。'},
]
vi.build(segments)
results = vi.search('怎么提交报销', k=2)
print('Vector search results:')
for r in results:
    print(f'  {r[\"heading\"]}: score={r[\"score\"]:.4f}')
assert len(results) > 0
print('VectorIndex works correctly')
"
```

Expected: `VectorIndex works correctly` with results showing "报销流程" as top match

- [ ] **Step 3: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/vector_index.py
git commit -m "feat: add VectorIndex class with sentence-transformers + FAISS for semantic search

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: Integrate VectorIndex into SearchEngine

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py`

- [ ] **Step 1: Add import and init for VectorIndex**

At the top of `search_engine.py`, after the BM25 import:

```python
from vector_index import VectorIndex
```

In `SearchEngine.__init__`, after the BM25 lines:

```python
        self.vector = None
        self.vector_index_file = HERE / "vector_index.faiss"
        self.vector_meta_file = HERE / "vector_meta.pkl"
```

- [ ] **Step 2: Add _load_vector_index method**

After `_load_bm25_index`, add:

```python
    def _load_vector_index(self):
        """加载或构建向量索引"""
        self.vector = VectorIndex()
        if self.vector_index_file.exists() and self.vector_meta_file.exists():
            self.vector.load(str(self.vector_index_file), str(self.vector_meta_file))
            return

        # 首次构建：对所有 KB 文档段落生成 embedding
        segments = []
        for doc in self.kb_docs:
            full_path = PROJECT_DIR / doc['path']
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding='utf-8')
            except Exception:
                continue
            for seg in self._split_by_heading(content, doc['path']):
                if seg['heading'] == '(文档开头)' and len(seg['content']) < 100:
                    continue
                if len(seg['content']) >= 50:
                    segments.append({
                        'path': doc['path'],
                        'heading': seg['heading'],
                        'content': seg['content'],
                    })

        if segments:
            self.vector.build(segments)
            self.vector.save(str(self.vector_index_file), str(self.vector_meta_file))
```

- [ ] **Step 3: Add vector search to the search() method**

In `search()` method (line 246), add vector search alongside keyword search. After the existing search calls (line 259-262), add:

```python
        # 3b. 向量语义检索（新增）
        vec_results = self._search_vector(query, expanded)
```

And add the results:

```python
        results.extend(vec_results)
```

- [ ] **Step 4: Add _search_vector method**

In `SearchEngine` class, add:

```python
    def _search_vector(self, query, expanded):
        """向量语义检索 KB 段落"""
        results = []
        if self.vector is None or self.vector.index is None:
            return results

        vec_results = self.vector.search(query, k=10)
        for sec in vec_results:
            results.append({
                'source': 'vector_search',
                'match_type': 'semantic',
                'match_term': query,
                'path': sec['path'],
                'heading': sec['heading'],
                'snippets': [sec['content'][:200]],
                'score': min(sec.get('score', 0) * 10, 9),
            })

        return results
```

- [ ] **Step 5: Add _load_vector_index to load_all**

In `load_all`, after `self._load_bm25_index()`, add:

```python
        self._load_vector_index()
```

- [ ] **Step 6: Verify parallel retrieval**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 search_engine.py "报销流程" --rebuild --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
proc = data.get('process', {})
layer1 = proc.get('layer1_search', {})
sources = layer1.get('sources', {})
print('Sources:', sources)
# Check vector_search results exist
for r in data.get('results', [])[:5]:
    print(f'  [{r[\"source\"]}] score={r[\"score\"]} path={r.get(\"path\",\"\")[:50]}')
"
```

Expected: Sources include `vector_search` results alongside keyword results

- [ ] **Step 7: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py
git commit -m "feat: integrate VectorIndex into SearchEngine for semantic parallel search

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: Upgrade FAQ cache matching to embedding similarity

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py`

- [ ] **Step 1: Replace check_faq_cache with embedding-based matching**

Replace the current `check_faq_cache` method (lines 1454-1482) with:

```python
    def check_faq_cache(self, query):
        """用 embedding 相似度匹配 FAQ 缓存。

        返回匹配的缓存条目 dict，或 None。
        """
        if not self.faq_cache:
            return None

        # 如果 VectorIndex 可用，用其模型做 embedding
        if self.vector and self.vector.model:
            query_emb = self.vector.encode(query)
        else:
            # Fallback: 关键词交集匹配
            return self._check_faq_cache_fallback(query)

        best_score = 0
        best_entry = None

        for fp, entry in self.faq_cache.items():
            cached_emb = entry.get('embedding')
            if cached_emb is None:
                continue
            cached_emb = np.array(cached_emb).astype('float32').reshape(1, -1)
            faiss.normalize_L2(cached_emb)
            sim = float(np.dot(query_emb, cached_emb.T)[0][0])

            if sim > 0.85:  # 高相似度，直接返回
                return entry
            if sim > best_score:
                best_score = sim
                best_entry = entry

        return best_entry if best_score > 0.75 else None

    def _check_faq_cache_fallback(self, query):
        """关键词交集 fallback（当 VectorIndex 不可用时）"""
        query_tokens = set(jieba.cut(query))
        query_tokens = {t.strip() for t in query_tokens if len(t.strip()) >= 2}

        best_match = None
        best_score = 0

        for fp, entry in self.faq_cache.items():
            entry_keywords = set(entry.get('keywords', []))
            if not entry_keywords:
                continue
            overlap = query_tokens & entry_keywords
            if len(overlap) >= 2:
                score = len(overlap)
                if query.strip() == entry.get('query', '').strip():
                    score += 10
                if score > best_score:
                    best_score = score
                    best_match = entry

        return best_match if best_score >= 3 else None
```

- [ ] **Step 2: Add numpy import at top of search_engine.py**

After existing imports, add:

```python
import numpy as np
```

- [ ] **Step 3: Update save_faq to include embedding**

In `save_faq` method (line 1484), after building the entry dict, add:

```python
        # 附带 embedding 向量
        if self.vector and self.vector.model:
            try:
                emb = self.vector.encode(query)
                entry['embedding'] = emb.tolist()[0]
            except Exception:
                pass
```

- [ ] **Step 4: Verify embedding-based cache matching**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 -c "
from search_engine import SearchEngine
eng = SearchEngine()
eng.load_all()

# Test with a query similar to a cached one
cached = eng.check_faq_cache('HPV疫苗怎么接种')
if cached:
    print('Cache hit:', cached.get('query', '')[:50])
else:
    print('Cache miss - checking fallback...')
    cached = eng._check_faq_cache_fallback('HPV疫苗怎么接种')
    if cached:
        print('Fallback hit:', cached.get('query', '')[:50])
    else:
        print('No cache match')
"
```

Expected: Either cache hit or meaningful message

- [ ] **Step 5: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py
git commit -m "feat: upgrade FAQ cache matching to embedding similarity with fallback

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 11: Verify Phase 2

**Files:** None (manual verification)

- [ ] **Step 1: Full rebuild with vector index**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 search_engine.py "测试" --rebuild --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Total results:', data['total'])
proc = data.get('process', {})
layer1 = proc.get('layer1_search', {})
sources = layer1.get('sources', {})
print('Sources:', json.dumps(sources, ensure_ascii=False))
"
```

Expected: No errors, sources include vector_search

- [ ] **Step 2: Test semantic matching with similar queries**

```bash
python3 search_engine.py "怎么报销" --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
ans = data.get('answer', {})
print('Query: 怎么报销')
print('Module:', ans.get('module', ''))
print('Top results:')
for r in data.get('results', [])[:3]:
    print(f'  [{r[\"source\"]}] score={r[\"score\"]} {r.get(\"path\",\"\")[:60]}')
"

python3 search_engine.py "报销单如何提交" --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
ans = data.get('answer', {})
print('Query: 报销单如何提交')
print('Module:', ans.get('module', ''))
print('Top results:')
for r in data.get('results', [])[:3]:
    print(f'  [{r[\"source\"]}] score={r[\"score\"]} {r.get(\"path\",\"\")[:60]}')
"
```

Expected: Both queries should return similar results (semantic matching working)

- [ ] **Step 3: Verify vector index files exist**

```bash
ls -la /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/vector_index.faiss
ls -la /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/vector_meta.pkl
```

Expected: Both files exist

---

### Task 12: Upgrade Claude prompt to structured format

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py`

- [ ] **Step 1: Replace build_claude_prompt with structured version**

Replace the current `build_claude_prompt` method (lines 615-748) with:

```python
    def build_claude_prompt(self, query, results):
        """构建结构化 Claude API prompt。

        返回 dict: {"system": str, "messages": [{"role": "user", "content": str}]}
        """
        # 收集匹配的模块信息
        matched_modules = []
        seen_mod = set()
        for r in results:
            m = r.get('module')
            if m and m not in seen_mod:
                seen_mod.add(m)
                info = self.module_map.get(m, {})
                matched_modules.append({
                    'name': m,
                    'dept': info.get('dept', ''),
                    'domain': info.get('domain', ''),
                    'dev_owner': info.get('dev_owner', ''),
                    'module_owner': info.get('module_owner', ''),
                })

        # 深度搜索 KB
        tokens = list(jieba.cut(query))
        tokens = [t.strip() for t in tokens if len(t.strip()) >= 1]
        expanded = self._expand_tokens(tokens) if tokens else set()

        kb_sections, kb_files_searched, _ = self._deep_search_kb(
            query, expanded, results
        )
        raw_doc_sections = self._search_raw_docs(query, expanded)
        report_sections = self._search_reports_deep(query, expanded, results)

        # 结构化 system prompt
        system = """你是产品知识库助手，服务于数智财务（浙里报/孵化业务/徽报账）、电子档案、免疫规划、数字化支撑等全部业务模块的用户咨询。

## 回答策略
根据问题类型采用不同策略：
- **功能咨询**（怎么用/在哪里/如何操作）：说明功能位置、菜单路径、操作步骤，按步骤编号列出
- **问题排查**（报错/不能用/故障）：列出常见原因、排查步骤、负责人
- **概念解释**（什么是/功能说明/介绍）：给出定义、适用范围、相关配置
- **模块查询**（谁负责/归属哪个模块）：给出模块名、部门、负责人

## 回答格式要求
1. 先给出 1-2 句明确结论
2. 如有操作步骤，用编号清晰列出每一步
3. 如有注意事项/限制条件，单独列出
4. 结尾标注信息来源文档路径

## 重要规则
- 用中文回答，详细、专业、完整
- 如果文档内容足够回答，直接给出准确答案
- 如果文档内容部分相关但不完整，先给出文档中的信息，再结合你的知识补充
- 如果文档完全不相关，不要编造，诚实说明

## 在回答末尾输出以下 JSON（不要放在 markdown 代码块中，直接输出）
{"keywords_to_add": ["建议补充的关键词1", "关键词2"], "module": "所属模块名", "confidence": "high|medium|low"}
"""

        # 组装 user message
        user_parts = [f"## 用户问题\n{query}\n"]

        if matched_modules:
            user_parts.append("## 匹配的模块")
            for mod in matched_modules[:3]:
                user_parts.append(
                    f"- {mod['name']}（{mod['dept']}/{mod['domain']}）"
                    f" | 研发: {mod.get('dev_owner', '未知')}"
                    f" | 模块负责人: {mod.get('module_owner', '未知')}"
                )
            user_parts.append("")

        if kb_sections:
            seen_files = set()
            full_docs = []
            for sec in kb_sections:
                path = sec.get('path', '')
                if path and path not in seen_files:
                    seen_files.add(path)
                    try:
                        full_path = PROJECT_DIR / path
                        if full_path.exists():
                            full_content = full_path.read_text(encoding='utf-8')
                            if len(full_content) > 12000:
                                full_content = full_content[:12000] + '\n\n...(内容过长，已截断)...'
                            full_docs.append({
                                'path': path,
                                'content': full_content,
                                'score': sec.get('score', 0),
                            })
                    except Exception:
                        pass
                if len(full_docs) >= 3:
                    break

            user_parts.append("## 知识库文档（完整内容）")
            for i, doc in enumerate(full_docs, 1):
                rel_path = doc['path'].replace('2026产品业务知识库/', '')
                user_parts.append(f"### 文档{i}: {rel_path}")
                user_parts.append(doc['content'])
                user_parts.append("")

        if raw_doc_sections:
            user_parts.append("## 原始产品文档")
            for i, sec in enumerate(raw_doc_sections[:2], 1):
                heading = sec['heading'].lstrip('#').strip()
                user_parts.append(f"### [{i}] {heading}")
                user_parts.append(sec['content'][:1000])
                user_parts.append("")

        if report_sections:
            user_parts.append("## 历史报表数据")
            for i, sec in enumerate(report_sections[:1], 1):
                user_parts.append(f"### [{i}] {sec['heading'].lstrip('#').strip()}")
                user_parts.append(sec['content'][:800])
            user_parts.append("")

        user_parts.append("请根据以上文档内容回答用户问题。")

        return {
            'system': system,
            'messages': [{'role': 'user', 'content': '\n'.join(user_parts)}],
            '_meta': {
                'matched_modules': matched_modules,
                'kb_sections': kb_sections,
                'kb_files_searched': [str(p) for p in kb_files_searched],
            },
        }
```

- [ ] **Step 2: Verify prompt structure**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 -c "
from search_engine import SearchEngine
eng = SearchEngine()
eng.load_all()
result = eng.search('怎么报销', top=5)
prompt = eng.build_claude_prompt('怎么报销', result.get('results', []))
print('System prompt length:', len(prompt['system']))
print('Messages:', len(prompt['messages']))
print('Has meta:', '_meta' in prompt)
# Check structured output format
assert '回答策略' in prompt['system']
assert '输出格式' in prompt['system']
assert 'keywords_to_add' in prompt['system']
print('Prompt structure verified')
"
```

Expected: `Prompt structure verified`

- [ ] **Step 3: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_engine.py
git commit -m "feat: upgrade Claude prompt to structured format with intent-based strategies

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 13: Frontend parallel display

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/static/index.html`
- Modify: `AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_server.py`

Read the current index.html first to understand the structure, then modify.

- [ ] **Step 1: Read current index.html**

```bash
wc -l /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/static/index.html
```

- [ ] **Step 2: Modify search_server.py to include quick_summary in API response**

In `search_server.py`, in the `do_GET` method for `/api/search`, after the search results, add the quick summary to the response:

```python
            # After result = eng.search(query, top=top), add:
            # Quick summary for immediate display
            ans = result.get('answer', {})
            result['quick_summary'] = {
                'module': ans.get('module', ''),
                'dept': ans.get('dept', ''),
                'owner': ans.get('module_owner', ''),
                'snippet': ans.get('summary', '')[:200] if ans.get('summary') else '',
            }
```

- [ ] **Step 3: Modify index.html to show quick summary first, then Claude stream**

In the JavaScript section of `index.html`, find the search handler function and modify it to:

1. Display `quick_summary` immediately in a "快速摘要" card
2. Show a loading spinner for "Claude 深度分析中..."
3. When SSE stream arrives, replace the loading spinner with the full Claude answer

```javascript
// After receiving search results:
function displayResults(data) {
    // 1. Show quick summary immediately
    if (data.quick_summary && data.quick_summary.module) {
        const summaryCard = document.getElementById('quick-summary');
        summaryCard.innerHTML = `
            <div class="card summary-card">
                <div class="card-header">🔍 快速定位</div>
                <div class="card-body">
                    <p><strong>模块：</strong>${data.quick_summary.module}</p>
                    <p><strong>部门：</strong>${data.quick_summary.dept || '未知'}</p>
                    <p><strong>负责人：</strong>${data.quick_summary.owner || '未知'}</p>
                    <p>${data.quick_summary.snippet || ''}</p>
                </div>
            </div>`;
        summaryCard.style.display = 'block';
    }

    // 2. Show Claude loading placeholder
    const claudeCard = document.getElementById('claude-answer');
    claudeCard.innerHTML = `
        <div class="card claude-card">
            <div class="card-header">🧠 Claude 深度分析中...</div>
            <div class="card-body"><div class="spinner"></div></div>
        </div>`;
    claudeCard.style.display = 'block';

    // 3. Start SSE stream if available
    if (data.claude_stream_url) {
        streamClaudeAnswer(data.claude_stream_url);
    }
}

function streamClaudeAnswer(url) {
    const eventSource = new EventSource(url);
    const claudeCard = document.getElementById('claude-answer');
    let answerHtml = '';

    eventSource.onmessage = function(event) {
        if (event.data === '[DONE]') {
            eventSource.close();
            return;
        }
        const data = JSON.parse(event.data);
        if (data.text) {
            answerHtml += data.text;
            claudeCard.innerHTML = `
                <div class="card claude-card">
                    <div class="card-header">🧠 Claude 深度分析</div>
                    <div class="card-body">${marked.parse(answerHtml)}</div>
                </div>`;
        }
        if (data.error) {
            claudeCard.innerHTML = `
                <div class="card claude-card">
                    <div class="card-header">🧠 Claude 深度分析</div>
                    <div class="card-body error">${data.error}</div>
                </div>`;
            eventSource.close();
        }
    };

    eventSource.onerror = function() {
        eventSource.close();
    };
}
```

- [ ] **Step 4: Verify frontend changes**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 search_server.py 8765 &
sleep 2
# Check the page loads
curl -s http://localhost:8765/ | head -5
# Clean up
kill %1 2>/dev/null
```

Expected: Server starts, page loads

- [ ] **Step 5: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/static/index.html
git add AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库/search_server.py
git commit -m "feat: add parallel display - quick summary first, Claude stream replaces

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 14: Update KB template documentation

**Files:**
- Modify: `AiClaudeProject/ProjectSkill/projects/产品知识库/SKILL.md`

- [ ] **Step 1: Add heading naming standards to SKILL.md**

After the "标准目录结构" section (line 135), add:

```markdown
## 标准章节命名规范

> 为确保检索引擎能准确提取内容，知识库文件中的章节标题必须使用以下标准命名。

### 版本迭代文档章节

| 章节用途 | 标准标题 | 说明 |
|---------|---------|------|
| 功能说明 | `### 功能说明` | 描述功能是什么、解决什么问题 |
| 背景与目标 | `### 背景与目标` | 为什么做这个功能 |
| 规则说明 | `### 规则说明` 或 `### 业务规则` | 业务逻辑、校验规则、限制条件 |
| 操作步骤 | `### 操作步骤` 或 `### 使用流程` | 按步骤编号描述用户操作 |
| 配置说明 | `### 配置说明` 或 `### 相关配置项` | 后台开关、参数配置 |
| 注意事项 | `### 注意事项` 或 `### 已知问题` | 限制条件、兼容问题、临时方案 |

### FAQ 文档章节

| 章节用途 | 标准标题 | 说明 |
|---------|---------|------|
| 常见问题 | `## FAQ` 或 `## 常见问题` | FAQ 章节入口 |
| 单个问题 | `### Q: {问题描述}` | 每个 FAQ 条目 |
| 故障排查 | `## 常见问题&故障库` | 问题和故障排查合并章节 |

### 检索优先级

检索引擎对以下章节有加权：
- **FAQ 章节**（标题含 `FAQ`/`常见问题`/`故障`/`排查`）：段落评分 +2.0
- **操作步骤章节**（标题含 `操作步骤`/`步骤`/`流程`）：回答生成时优先提取
- **规则说明章节**（标题含 `规则说明`/`规则`/`限制`）：how-to 查询时作为补充说明
```

- [ ] **Step 2: Commit**

```bash
git add AiClaudeProject/ProjectSkill/projects/产品知识库/SKILL.md
git commit -m "docs: add standard heading naming conventions for KB search optimization

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 15: End-to-end verification

**Files:** None (manual verification)

- [ ] **Step 1: Full rebuild**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 search_engine.py "测试" --rebuild 2>&1 | head -5
```

Expected: No errors

- [ ] **Step 2: Test FAQ cache hit**

```bash
python3 -c "
from search_engine import SearchEngine
eng = SearchEngine()
eng.load_all()
# Test a query that should be in FAQ cache
cached = eng.check_faq_cache('预算是什么')
print('FAQ cache hit:', cached is not None)
if cached:
    print('Matched:', cached.get('query', ''))
"
```

Expected: FAQ cache hit for seeded queries

- [ ] **Step 3: Test semantic matching**

```bash
python3 search_engine.py "怎么提交报销" --json 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
vec_results = [r for r in data.get('results', []) if r.get('source') == 'vector_search']
kw_results = [r for r in data.get('results', []) if r.get('source') == 'keyword_index']
print(f'Vector results: {len(vec_results)}')
print(f'Keyword results: {len(kw_results)}')
print('Both sources active:', len(vec_results) > 0 and len(kw_results) > 0)
"
```

Expected: Both vector and keyword results present

- [ ] **Step 4: Test search server**

```bash
cd /Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/ProjectSkill/projects/共享模块中心/关键词库
python3 search_server.py 8765 &
sleep 2
curl -s "http://localhost:8765/api/search?q=报销流程" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Query:', data.get('query', ''))
print('Has quick_summary:', 'quick_summary' in data)
print('Has results:', len(data.get('results', [])) > 0)
print('Has claude_stream_url:', data.get('claude_stream_url') is not None)
"
kill %1 2>/dev/null
```

Expected: Query returns with quick_summary, results, and claude_stream_url

- [ ] **Step 5: Verify all acceptance criteria**

| 指标 | 检查方式 | 预期 |
|------|---------|------|
| FAQ 缓存条目 | `len(eng.faq_cache)` | >50 |
| 两路检索并行 | search results 含 vector_search + keyword_index | 两路都有结果 |
| 规则引擎摘要 | answer.summary 长度 | <300 字 |
| 结构化 prompt | build_claude_prompt 输出含 `回答策略` | 包含 |
| 缓存用 embedding | check_faq_cache 使用 vector.encode | 见 Task 10 验证 |

- [ ] **Step 6: Final commit**

```bash
git status
git add -A
git commit -m "chore: final verification of Phase 1-3 search optimization

Co-Authored-By: Claude <noreply@anthropic.com>"
```