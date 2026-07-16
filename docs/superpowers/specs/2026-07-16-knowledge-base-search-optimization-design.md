# 产品知识库检索优化 - 设计方案

> 日期：2026-07-16
> 状态：已确认，待实施

## 1. 问题分析

当前产品知识库检索系统（`search_engine.py`）存在以下核心问题：

| 问题 | 根因 | 影响 |
|------|------|------|
| 语义匹配缺失 | 纯关键词 `text.count()` 匹配，同义词库仅 195 行 | 同义不同词搜索不到 |
| 排序精度不足 | 评分固定分值（15/12/10/8），无位置权重，无文档级预筛选 | 低相关文档排在高相关前面 |
| 回答质量不稳定 | `_build_summary` 130 行复杂规则拼接，`_find_child` 硬编码 heading 关键词 | 章节匹配经常失败 |
| FAQ 缓存为空 | 缓存机制已就绪但从未填充数据 | 高频问题无法秒出 |

## 2. 架构设计

从当前 **单路串行** 升级为 **多路并行 + 分层路由**：

```
用户提问
  │
  ├── 1. 查询意图分类（how-to / what-is / troubleshooting / who-owns）
  │
  ├── 2. 并行检索
  │     ├── ① FAQ 缓存（embedding 相似度匹配，<100ms）
  │     │     └── 命中 → 直接返回，跳过后续
  │     ├── ② 关键词索引（jieba + 同义词 + 拼音，<50ms）
  │     └── ③ 向量检索（sentence-transformers → FAISS，<200ms）
  │
  ├── 3. 两阶段排序
  │     ├── S1: BM25 文档级筛选（Top-10 文档）
  │     └── S2: 段落级精细匹配（Top-5 段落）
  │
  └── 4. 混合回答
        ├── 规则引擎：快速摘要（模块定位 + 关键信息提取）
        └── Claude：流式深度分析（完整 context，结构化输出）
```

**关键变化：**
- 从 `顺序搜索 5 个源 → 合并排序` 变为 `并行搜索 3 路 → 统一排序`
- 新增 `向量检索` 通道，解决语义匹配问题
- FAQ 缓存从"可选项"升级为"第一优先级"
- 两阶段排序替代当前的单阶段全扫描

## 3. 两阶段检索 + 排序优化

### S1: 文档级 BM25 排序

**替换当前做法：** 不再逐文件读前 5000 字符做 `text.count(term)` 计数，而是建倒排索引 + BM25。

```python
class BM25Index:
    def __init__(self):
        self.documents = []       # [(doc_id, path, dept, domain)]
        self.inverted_index = {}  # term -> {doc_id: term_frequency}
        self.doc_lengths = {}     # doc_id -> total_terms
        self.avg_dl = 0
        self.N = 0

    def build(self, kb_docs):
        """从 KB 文件构建倒排索引（一次性，缓存到磁盘 bm25_index.pkl）"""
        for doc in kb_docs:
            tokens = list(jieba.cut(doc['content']))
            # 记录词频、文档长度
            ...

    def search(self, query_terms, k=10):
        """BM25(D, Q) = Σ IDF(qi) * (f(qi,D) * (k1+1)) / (f(qi,D) + k1*(1-b+b*|D|/avgdl))"""
        # k1=1.5, b=0.75（中文文档标准参数）
        ...
```

### S2: 段落级精细匹配

对文档级筛选出的 Top-10 文档，做段落级多维评分：

```python
def _fine_rank_paragraphs(self, doc_paths, query_terms, query_embedding=None):
    score = 0
    # 1. 关键词 BM25 分数（40%）
    # 2. 向量相似度（35%）
    # 3. 标题/位置匹配（15%）- FAQ 区域加权 +2.0
    # 4. 文档新鲜度（10%）- 一年内不降权，超过一年线性衰减
```

### 评分权重总览

| 维度 | 权重 | 说明 |
|------|------|------|
| BM25 关键词 | 40% | 基础文本匹配 |
| 向量相似度 | 35% | 语义匹配 |
| 标题/位置匹配 | 15% | 标题命中加分，FAQ 区域加权 |
| 文档新鲜度 | 10% | 最新版本优先 |

## 4. FAQ 缓存 + 向量检索

### FAQ 缓存优化

**种子数据批量填充：** 从 KB 文件的 FAQ 章节 + 模块文件关键词提取 50-100 条种子 FAQ，一次性写入 `faq_cache.json`。

**缓存匹配升级为 embedding 相似度：**

```python
def check_faq_cache(self, query):
    query_embedding = self._get_embedding(query)
    for fp, entry in self.faq_cache.items():
        sim = cosine_similarity(query_embedding, entry['embedding'])
        if sim > 0.85:    # 高相似度，直接返回
            return entry
        if sim > best_score:
            best_score = sim
    return best_entry if best_score > 0.75 else None
```

### 向量检索

| 组件 | 选型 | 理由 |
|------|------|------|
| Embedding 模型 | `paraphrase-multilingual-MiniLM-L12-v2` | 120MB，中文效果好，本地 CPU 推理 ~50ms |
| 向量索引 | FAISS (CPU) | Facebook 开源，内存索引，毫秒级检索 |
| 向量维度 | 384 | MiniLM 输出维度 |

**索引构建：** `--rebuild` 时对全部 KB 段落（~870 个向量）生成 embedding，序列化到 `vector_index.faiss`。

**内存占用：** 870 × 384 × 4 bytes ≈ 1.3MB，完全可接受。

## 5. 回答生成优化

### 并行混合策略

```
用户提问
  ├── 通道 A: 规则引擎快速摘要（纯本地，<100ms）
  │     输出: 模块定位 + 一句话摘要 + 文档链接
  │
  └── 通道 B: Claude 流式分析（SSE 推送，首字 1-2s）
        输出: 完整业务回答 + 操作步骤 + JSON 关键词建议

前端先展示通道 A 结果 → Claude 到达后替换为完整回答
```

### 规则引擎精简

`_build_summary` 从 130 行精简到 ~50 行，只做 3 件事：
1. 模块定位（`_select_best_module`）
2. 提取最佳段落前 200 字
3. 组装返回

不再做复杂的章节匹配和回答合成，这些交给 Claude。

### Claude Prompt 结构化

```python
system = """你是产品知识库助手。

## 回答策略
- 功能咨询：说明功能位置、菜单路径、操作步骤
- 问题排查：列出常见原因、排查步骤、负责人
- 概念解释：给出定义、适用范围、相关配置

## 输出格式
1. 先给出 1-2 句结论
2. 操作步骤用编号清晰列出
3. 注意事项单独列出
4. 结尾标注信息来源

## 末尾输出 JSON（不放 markdown 代码块中）
{"keywords_to_add": ["新关键词"], "module": "所属模块", "confidence": "high|medium|low"}
"""
```

### 反哺闭环（保持现有逻辑）

Claude 回答完成后自动：
1. 写入 `faq_cache.json`（带 embedding 向量）
2. 追加到 `{部门}/{业务域}/FAQ.md`
3. 提取新关键词提示补充到关键词索引

## 6. 实施计划

### Phase 1（P0，预计 1-2 天）：快速见效

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 1.1 | FAQ 种子数据填充：从 KB 文件 FAQ 章节 + 模块文件关键词提取 50-100 条种子 FAQ | `search_engine.py` 新增 `seed_faq_cache()` |
| 1.2 | BM25 文档索引：新建 `BM25Index` 类，`--rebuild` 时构建倒排索引，缓存到 `bm25_index.pkl` | `search_engine.py` 新增类 |
| 1.3 | 两阶段排序：S1 BM25 筛选 Top-10 文档 → S2 段落级精细匹配 | `search_engine.py` 修改 `search()` 和 `_deep_search_kb()` |
| 1.4 | 精简规则引擎：`_build_summary` 从 130 行精简到 ~50 行 | `search_engine.py` 修改 `_build_summary()` |
| 1.5 | 验证：跑 20 条典型查询，对比优化前后结果 | 手工测试 |

### Phase 2（P1，预计 2-3 天）：语义升级

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 2.1 | 安装依赖：`sentence-transformers`, `faiss-cpu` | `requirements.txt` 新增 |
| 2.2 | 向量索引：新建 `VectorIndex` 类，`--rebuild` 时对全部 KB 段落生成 embedding | `search_engine.py` 新增类 |
| 2.3 | 并行检索：FAQ 缓存 + 关键词索引 + 向量检索 三路并行 | `search_engine.py` 修改 `search()` |
| 2.4 | 缓存匹配升级：`check_faq_cache()` 从关键词交集改为 embedding 相似度 | `search_engine.py` 修改 |
| 2.5 | embedding 缓存：FAQ 缓存条目保存时附带 embedding 向量 | `search_engine.py` 修改 `save_faq()` |
| 2.6 | 验证：对比语义相近查询的召回率 | 手工测试 |

### Phase 3（P2，预计 1 天）：回答质量 + 规范

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 3.1 | Claude Prompt 升级：结构化 prompt（意图分类 + 输出格式约束 + JSON schema） | `search_engine.py` 修改 `build_claude_prompt()` |
| 3.2 | 前端并行展示：规则摘要先展示，Claude 流式结果到达后替换 | `static/index.html` 修改 |
| 3.3 | KB 模板规范文档：明确 FAQ/操作步骤/规则说明等 heading 命名标准 | `产品知识库/SKILL.md` 更新 |
| 3.4 | 端到端验证：完整流程测试，确认 FAQ 缓存自学习正常工作 | 手工测试 |

### 文件变更总览

```
共享模块中心/关键词库/
├── search_engine.py       ← 主要修改（新增 BM25Index、VectorIndex 类，修改 search/build_summary 等）
├── search_server.py       ← 小改（并行展示逻辑）
├── faq_cache.json         ← 新增（种子数据填充）
├── bm25_index.pkl         ← 新增（BM25 倒排索引缓存）
├── vector_index.faiss     ← 新增（FAISS 向量索引）
├── synonyms.json          ← 小改（补全同义词）
├── requirements.txt       ← 新增（sentence-transformers, faiss-cpu）
└── static/index.html      ← 小改（并行展示 UI）
```

## 7. 验收标准

| 指标 | 当前 | 目标 |
|------|------|------|
| FAQ 缓存命中率 | 0% | Phase 1 后 >30%，Phase 2 后 >50% |
| 语义相近查询召回率 | 低（依赖同义词） | Phase 2 后 >80% |
| 规则引擎回答速度 | ~200ms | <100ms |
| 首屏可看时间 | 3-10s（等 Claude） | <100ms（规则摘要），完整回答 3-10s |
| 搜索排序 Top-3 准确率 | 未度量 | Phase 1 后人工评估 >70% |