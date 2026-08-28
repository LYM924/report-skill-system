# 产品智能知识库 - 全面优化记录

> 日期：2026-08-21 ~ 2026-08-22
> 范围：内容质量、架构重构、搜索优化、数据库引入、报表系统、全量模块导入

---

## 一、已完成的优化

### 1. 内容质量（P0）

| 优化项 | 做法 | 成果 |
|--------|------|------|
| 修复知识文档日期 | 新建 `src/scripts/fix_dates.py`，从文件名/正文提取真实日期 | 23 篇占位日期 `20260101` 全部修复 |
| 填充知识文档关键词 | 运行 `extract_kb_keywords.py`，从正文提取关键词 | 67/80 篇文档填充关键词，关键词索引新增 140 条 |
| 重写薄 FAQ | 按基准 FAQ 结构重写 11 篇 FAQ | 35-44 行 → 85-138 行，补充原因分析表格、分场景方案、排查要点 |
| 修复 FAQ 格式 | 修复未满月 FAQ 的 ID、关键词、残留 JSON | 1 篇修复 |

### 2. 内容补充（P1）

| 优化项 | 做法 | 成果 |
|--------|------|------|
| 补充缺失部门知识文档 | 基于模块文件创建知识文档 | 电子档案组 1 篇 + 数字化支撑组 2 篇 |
| 修复 FAQ INDEX.md | 运行 `faq_audit.py --fix` | INDEX.md 从 1 篇 → 12 篇 |
| 转换 .docx 文件 | Python 提取 .docx 文本转 .md | 2 个 Word 文档转换为 Markdown |

### 3. 架构重构

| 优化项 | 做法 | 成果 |
|--------|------|------|
| 三层目录分离 | 代码/数据/运行时分离 | `src/` `data/` `config/` `runtime/` 清晰分层 |
| Repository 数据访问层 | 抽象接口 + 文件实现 + 数据库实现 | `base.py` + `file_repo.py` + `db_repo.py` |
| SQLite 数据库 | 结构化数据（模块/关键词/同义词/反馈/统计）入库 | 71 模块 + 1,676 关键词 + 535 同义词 |
| 数据迁移脚本 | 一键从文件导入数据库 | `src/server/migrate_to_db.py` |
| 拆分超大组件 | ManagePanel.jsx 提取子组件 | 774 行 → 390 行，4 个新文件 |
| 提取共享常量 | DEPT_OPTIONS 统一到 constants.js | 消除 4 处重复定义 |
| 提取纯函数 | search_utils.py | search_engine.py 从 2,195 行 → 2,157 行 |
| React Context | AppContext 替代 props drilling | `isDark`/`selectedDoc` 等无需层层传递 |

### 4. 搜索优化

| 优化项 | 做法 | 成果 |
|--------|------|------|
| 搜索反馈 | 后端 `/api/feedback` + 前端 👍👎 按钮 | 反馈数据持久化到 SQLite |
| 搜索 query 持久化 | localStorage 保存，刷新后恢复 | 刷新不丢失搜索输入 |
| 查询意图识别 | 常见查询→目标模块映射表 | 搜"报销"自动加权浙里报结果 |
| 时效性加权 | 按文档日期计算新鲜度加分 | 3 个月内 +3，半年内 +2，一年内 +1 |
| 结果多样性 | 同模块最多展示 3 条 | 避免单一模块霸占结果 |
| 搜索建议加速 | SQLite LIKE 查询替代遍历 | 建议响应更快 |

### 5. 前端体验

| 优化项 | 做法 | 成果 |
|--------|------|------|
| 搜索反馈按钮 | ResultCard 增加 👍👎 | 用户可评价搜索结果 |
| 搜索 query 持久化 | 刷新后恢复搜索框内容 | 用户体验提升 |

### 6. 报表数据改造（P1）

| 优化项 | 做法 | 成果 |
|--------|------|------|
| 报表数据入库 | 新建 `reports` 表，12 篇周报导入 SQLite | 报表元数据可查询、可筛选 |
| 报表路径统一 | 报表从 `report-system/output/` 迁移到 `data/reports/` | 部署时无需外部依赖 |
| 报表 API 增强 | `/api/reports` 支持分类筛选（周报/月报/年度） | 前端可按类别浏览 |
| ReportBrowser 升级 | 卡片视图 + 分类筛选 + 周次标签 + 摘要预览 | 用户体验提升 |
| Confluence 同步脚本 | 新建 `sync_confluence_reports.py` | 一键从 Confluence 拉取周报数据 |
| 数据库报表查询 | DBRepository 优先从 DB 读取报表 | 查询更快，支持 SQL 筛选 |

### 7. 全量模块导入（2026-08-22）

| 优化项 | 做法 | 成果 |
|--------|------|------|
| 全量模块解析 | 从 `产品模块索引_全量.md` 解析 349 个模块 | 数据库模块从 71 → 420 个 |
| 三级部门树 | departments 表重建为 `parent_id` 自引用树形结构 | 支持 事业部→二级部门→三级部门 联动 |
| 模块完整关联 | 每个模块关联一级/二级/三级部门 + 产品 + 产品线 | 100% 关联率 |
| 冗余字段清理 | 删除 keywords.department/domain、modules.sub_dept/associated_dept | 数据规范化 |
| 唯一约束 + 时间戳 | 添加 modules(name, department_id) 唯一索引 + created_at/updated_at | 数据完整性保障 |
| 数据库设计评估 | 生成 `数据库设计评估_2026-08-21.md` | 全面评估 + 问题修复 |

### 8. 其他优化（2026-08-22）

| 优化项 | 做法 | 成果 |
|--------|------|------|
| 中文文件名规范化 | `config/关键词索引.md` → `config/keyword_index.md`，更新 5 处引用 | 跨平台部署更安全 |
| extract_kb_keywords.py 路径修复 | 修复旧 SHARED_CENTER 引用为 DATA_DIR/CONFIG_DIR | 脚本可正常使用 |
| FAQ 编辑修复 | RightPanel 中 FAQ 路径判断兼容新路径 `faq/` | 左侧菜单→FAQ→点击可编辑 |
| 报表路径修复 | 数据库报表路径补全 `data/` 前缀 | 右侧面板报表预览正常 |
| 报表数据验证 | 验证 12 篇报表加载、搜索、API 响应 | 全部通过 |

---

## 二、未做的优化（有明确理由）

| 优化项 | 决策 | 理由 |
|--------|:---:|------|
| 拆分 search_engine.py | ❌ 不拆分 | 105 次共享状态访问，耦合太深，拆了更乱 |
| 引入 react-router | ❌ 不引入 | 内部工具不需要 URL 分享，当前状态路由够用 |
| 文档全文入库（方案A） | ❌ 暂不做 | 80 篇文档量不大，.md 文件可读性更好，git diff 可见 |

---

## 三、数据库构建升级方案分析

### 背景

当前数据库（SQLite）已存储结构化数据（模块、关键词、同义词、反馈、统计）。文档内容（.md 文件）暂未入库。以下是三种方案的分析。

### 方案对比

| | 方案A：SQLite FTS5 | 方案B：PostgreSQL | 方案C：保持文件（当前） |
|---|---|---|---|
| **做法** | 文档全文存入 SQLite，用 FTS5 全文索引 | 升级到 PostgreSQL，用 tsvector 全文搜索 | 文档保留 .md 文件，仅元数据入 DB |
| **依赖** | 无（Python 内置 sqlite3） | 需安装 PostgreSQL + psycopg2 | 无 |
| **搜索性能** | ⭐⭐⭐ 中等（FTS5 是 C 实现） | ⭐⭐⭐⭐⭐ 优秀（tsvector + GIN 索引） | ⭐⭐ 当前 BM25 + FAISS |
| **全文检索** | FTS5 内置，替代 BM25 | tsvector + GIN 索引，替代 BM25 | 依赖 BM25（pickle）和 FAISS（向量） |
| **语义搜索** | FAISS 保留 | FAISS 保留 | FAISS 保留 |
| **拼音搜索** | pypinyin 保留 | pypinyin 保留 | pypinyin 保留 |
| **部署复杂度** | 低（1 个 .db 文件） | 高（需数据库服务 + 环境搭建） | 最低 |
| **数据迁移** | 一次性导入（~100 行脚本） | 一次性导入 + 环境搭建 | 无需 |
| **备份** | 1 个 .db 文件 | pg_dump 备份 | 文件 + DB 分开备份 |
| **文档可读性** | ⭐⭐ 需 SQL 查询 | ⭐⭐ 需 SQL 查询 | ⭐⭐⭐⭐⭐ git diff 直接可见 |
| **Docker 镜像** | ~200MB（无模型依赖） | ~300MB（含 PG） | ~2GB（含 sentence-transformers 模型） |
| **适合场景** | 小团队、内网部署 | 正式生产环境、大团队 | 当前阶段（80 篇文档） |

### 方案A：SQLite FTS5（推荐中期方案）

```sql
-- 新增文档表
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    dept TEXT, module TEXT, product TEXT,
    date TEXT, keywords TEXT,
    path TEXT, created_at TEXT, updated_at TEXT
);

-- FTS5 全文索引（替代 BM25）
CREATE VIRTUAL TABLE documents_fts USING fts5(
    title, content, keywords,
    content='documents', content_rowid='id'
);
```

```python
# DBRepository 新增全文搜索
def search_documents(self, query: str) -> list[Document]:
    rows = self.db.execute(
        "SELECT * FROM documents_fts WHERE documents_fts MATCH ? LIMIT 20",
        (query,)
    ).fetchall()
    return [self._row_to_document(r) for r in rows]
```

**收益**：
- 部署从 150+ 个文件 + 5 个依赖 → 1 个 .db 文件 + 3 个依赖
- 去掉 BM25 索引文件（bm25_index.pkl）
- 去掉 sentence-transformers 模型（400MB），Docker 镜像从 2GB → 200MB
- 保留 FAISS 和 pypinyin，搜索质量不降级

**代价**：
- git diff 看不到文档变更（需额外同步流程）
- 编辑文档需先改 .md 再同步到 DB

### 方案B：PostgreSQL（推荐长期方案）

```python
# pg_repo.py - 仅需新增一个文件
class PGRepository(KnowledgeRepository):
    def __init__(self, dsn: str):
        self.db = psycopg2.connect(dsn)
    
    def search_documents(self, query: str):
        return self.db.execute(
            "SELECT *, ts_rank(to_tsvector('chinese', content), "
            "plainto_tsquery('chinese', %s)) AS rank "
            "FROM documents WHERE to_tsvector('chinese', content) "
            "@@ plainto_tsquery('chinese', %s) "
            "ORDER BY rank DESC LIMIT 20", (query, query)
        ).fetchall()
```

**切换只需一行**：
```python
# search_server.py
repo = PGRepository("postgresql://localhost/knowledge")
```

**收益**：
- 专业全文搜索（中文分词、权重排序、高亮）
- 支持并发读写，适合多用户
- 成熟的备份恢复工具链

**从方案A升级到方案B**：
- Schema 完全相同（标准 SQL）
- 迁移工具：`sqlite3 → CSV → PostgreSQL` 或 Python 脚本
- 代码改动：新增 `pg_repo.py`（~200 行），改一行配置
- 搜索引擎、前端全部零改动

### 升级路径

```
当前（方案C）              中期（方案A）              长期（方案B）
文件 + SQLite 元数据  →  SQLite FTS5 全文  →  PostgreSQL 全文
部署：150+ 文件          部署：1 个 .db 文件      部署：PostgreSQL 服务
搜索：BM25 + FAISS       搜索：FTS5 + FAISS        搜索：tsvector + FAISS
依赖：5 个 pip 包        依赖：3 个 pip 包         依赖：4 个 pip 包
镜像：~2GB               镜像：~200MB              镜像：~300MB
```

### 升级信号

| 指标 | 当前 | 升级到方案A 阈值 | 升级到方案B 阈值 |
|------|:---:|:---:|:---:|
| 文档数量 | 80 篇 | 200+ 篇 | 500+ 篇 |
| 部署依赖烦恼 | 无 | 模型下载慢/失败 | 需要高可用 |
| 搜索速度 | 毫秒级 | 秒级延迟 | 多用户并发慢 |
| 团队规模 | 1-2 人 | 3-5 人 | 5+ 人协作 |
| 数据一致性要求 | 低 | 中 | 高（需事务） |

### 当前建议

**保持方案C**（当前状态）。理由：
- 80 篇文档量不大，文件碎片不是问题
- git diff 可读性是真实优势（编辑→diff→提交 流程简单）
- 部署已有 Docker/脚本，不构成瓶颈
- 架构已通过 Repository 模式做好扩展准备，升级时机成熟时成本极低

---

## 四、后续建议

### 短期（1-2 周内）

| 优先级 | 建议 | 说明 |
|:---:|------|------|
| P0 | 补充更多 FAQ | 从工单分析中提取高频问题，目标 50+ 篇 FAQ |
| P0 | 知识文档标题规范化 | 把日期格式标题改为描述性标题 |
| P1 | 搜索无结果分析 | 记录搜索无结果的 query，针对性地补充内容 |
| P1 | 反馈数据利用 | 积累足够 👍👎 数据后，用于调整搜索排序 |
| P1 | 增加文档浏览量统计 | 记录哪些文档被查看最多 |

### 中期（1-3 个月）

| 优先级 | 建议 | 说明 |
|:---:|------|------|
| P1 | 拼写纠错 | 编辑距离匹配关键词库，容错用户输入 |
| P1 | 搜索热词看板 | 可视化展示搜索趋势和热词 |
| P2 | 文档版本管理 | 记录文档更新历史，支持版本对比 |
| P2 | 权限管理 | 按部门控制文档编辑权限 |
| P2 | CI/CD 自动化 | 文档变更自动重建索引，前端自动部署 |

### 长期（3-6 个月）

| 优先级 | 建议 | 说明 |
|:---:|------|------|
| P2 | 升级 PostgreSQL | 当文档量 >500 篇或团队 >5 人时 |
| P2 | 文档全文入库 | SQLite FTS5 或 PostgreSQL tsvector 全文搜索 |
| P2 | AI 自动摘要 | 用 LLM 自动生成文档摘要和 FAQ 草案 |
| P2 | 多语言支持 | 英文搜索和文档翻译 |

---

## 五、当前架构总览

```
knowledge-base/
├── config/                    ← 配置（synonyms.json, 关键词索引.md, schema.sql）
├── data/                      ← 知识数据（Git 跟踪 + 备份）
│   ├── knowledge/             ← 68 篇知识文档（.md）
│   ├── faq/                   ← 12 篇 FAQ（.md）
│   ├── raw-docs/              ← 70 篇原始文档（.md）
│   └── modules/               ← 71 个模块定义（.md，备用）
├── docs/                      ← 项目文档
├── runtime/                   ← 运行时生成（.gitignore）
│   ├── cache/                 ← BM25/FAISS 索引文件
│   ├── logs/                  ← 服务日志
│   ├── static/                ← 前端构建产物
│   ├── knowledge.db           ← SQLite 数据库（结构化数据）
│   ├── search_counter.json    ← 搜索统计
│   └── feedback.jsonl         ← 搜索反馈
└── src/                       ← 源代码
    ├── server/                ← Python 后端
    │   ├── repository/        ← 数据访问层
    │   │   ├── base.py        ← 抽象接口
    │   │   ├── file_repo.py   ← 文件系统实现
    │   │   └── db_repo.py     ← 数据库实现
    │   ├── search_engine.py   ← 搜索引擎（意图检测+时效性+多样性）
    │   ├── search_server.py   ← HTTP API 服务
    │   ├── search_utils.py    ← 纯工具函数
    │   ├── migrate_to_db.py   ← 数据迁移脚本
    │   ├── bm25_index.py      ← BM25 全文索引
    │   └── vector_index.py    ← FAISS 语义向量
    ├── web/                   ← React 前端
    │   └── src/components/    ← 组件（已拆分）
    └── scripts/               ← 维护脚本
        ├── fix_dates.py       ← 日期修复
        ├── kb_migrate.py      ← 文档迁移
        ├── faq_audit.py       ← FAQ 审计
        └── ...
```

## 六、数据库 Schema

| 表 | 用途 | 数据量 |
|----|------|:---:|
| departments | 部门 | 20 |
| product_lines | 产品线 | 7 |
| products | 产品 | 按需 |
| modules | 模块定义 | 71 |
| module_menus | 模块菜单映射 | 250 |
| keywords | 关键词索引 | 1,676 |
| synonyms | 同义词 | 535 |
| feedback | 搜索反馈 | 按需 |
| search_counter | 搜索统计 | 按需 |

## 七、搜索流程

```
用户输入
  │
  ├── 1. jieba 分词
  ├── 2. 查询意图识别 → 匹配模块加权
  ├── 3. 同义词 + 拼音扩展
  ├── 4. 6 路并行搜索
  │     ├── 关键词索引（DB 查询）
  │     ├── 模块名匹配
  │     ├── KB 文档（BM25）
  │     ├── 报表（BM25）
  │     ├── FAQ（关键词+标题+内容）
  │     └── 向量语义（FAISS）
  ├── 5. 意图加权 + 时效性加权
  ├── 6. 去重 + 多样性过滤
  └── 7. 排序输出
```

## 八、部署说明

```bash
# 1. 安装依赖
cd src/server && pip install -r requirements.txt

# 2. 初始化数据库（首次）
python3 src/server/migrate_to_db.py

# 3. 构建前端
cd src/web && npm install && npm run build

# 4. 启动服务
cd src/server && python3 search_server.py 8765
```

---

> 📝 本文档记录了 2026-08-21 完成的全部优化工作。后续优化请在此文档基础上追加。