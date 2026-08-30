# 产品知识库系统 (Knowledge Base System)

产品业务知识管理 + 智能检索系统（端口 8000）。

## 架构

```
React 前端 (src/web, Vite 构建到 runtime/static)
    ↓ HTTP /api/*
FastAPI 后端 (src/server/main.py + routes/, uvicorn)
    ↓
SearchEngine 内存搜索引擎（jieba 分词 + BM25 + FAISS 向量 + 关键词路由 + FAQ 缓存）
    ↓
DBRepository（PostgreSQL 主数据源） + 文件系统（data/*.md 内容权威）
```

- **后端唯一实现**：FastAPI（`src/server/main.py`）。旧实现 search_server.py 已彻底删除（git 历史可查）。
- **数据库**：PostgreSQL `knowledge_base`（连接串见 `.env` 的 `DATABASE_URL_SYNC`）；PG 不可用时自动回退 SQLite（`runtime/knowledge.db` 按需自动创建，不入库）。
- **Schema 管理**：统一由 `config/migrations/*.sql` 演进（幂等脚本，psql 应用），禁止手工双份 schema。
- **鉴权**：JWT（`POST /api/auth/login`，账号 `ADMIN_USER`/`ADMIN_PASS` 见 `.env`），除登录与静态资源外全部接口需 `Authorization: Bearer <token>`。
- **多用户与配置中心**：`users` 表（管理员可创建/重置/删除账号）；每个用户在 Web 界面「系统管理 → 配置中心」保存自己的 AI 模型/API地址/AppKey（加密存储、界面脱敏、立即生效），AI 总结/问答按本人配置调用；未配置用户回退服务器 `.env` 默认值。

## 启动

```bash
# 后端（8000）
./start.sh
# 或：cd src/server && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000

# 前端（改动后需重新构建）
cd src/web && npx vite build   # 输出到 runtime/static
```

## 冒烟测试（每改必跑）

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
AUTH_TOKEN="$TOKEN" ./scripts/smoke_test.sh localhost:8000 --write
```

## 健康检查

`GET /api/health`（需 token）：数据源类型、引擎状态、Schema 契约校验（列存在性/唯一索引）、写失败计数、行数概要。

## 数据流约定

| 数据 | 存储位置 | 说明 |
|---|---|---|
| 知识文档/FAQ/报表内容 | `data/**/*.md` | 内容权威；DB 存索引与元数据 |
| 文档元数据 | `documents` 表 | 启动时装载进内存搜索引擎 |
| FAQ 元数据 | `faqs` 表 | 保存=写文件+写表（双写一致）；删除=物理删文件+软删表 |
| 关键词 | `keywords_v2` + `keyword_mappings` | 双表方案；软删除+复活式 upsert；部分唯一索引防重复 |
| 搜索日志 | `search_logs` 表 | /api/search 写入（query/纠错词/耗时/是否命中答案/UA/IP哈希） |
| 反馈 | `feedback` + `search_counter` | 有用/无用计数 → 满意度 |
| 索引缓存 | `runtime/cache/*` | BM25/向量/FAQ 缓存；FAQ 变更后 BM25 同步重建、向量后台重建 |

## 已知设计决策

- FAQ 变更后向量索引由后台线程全量重建（`/api/rebuild` 或保存/删除触发），期间向量召回可能滞后。
- `document_departments` 以 `document_path` 为关联键（线上规范），`document_id` 为迁移遗留列暂不使用。
- 关键词映射 `module_id` 可为 NULL（部门级关键词），NULL 不参与唯一约束（PG 语义）。
