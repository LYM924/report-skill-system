# report-skill-system

AI 辅助技术支持工作台：产品知识库、报表生成与知识沉淀。

## 项目结构

```
AiClaudeProject/
├── 2026产品业务知识库/   # 产品业务知识沉淀（按业务模块分区）
├── 2026报表数据知识库/   # 周报/月报数据
├── projects/
│   ├── knowledge-base/   # 智能知识库系统（FastAPI + React + PostgreSQL，端口8000）
│   └── report-system/    # 报表管理系统
├── ProjectSkill/         # Claude Code 技能
└── 其他文档区/           # 架构分析报告、实施方案等文档
```

## 智能知识库系统

详见 `AiClaudeProject/projects/knowledge-base/README.md`：
- 启动：`./start.sh`（FastAPI + uvicorn，8000 端口）
- 前端改动后需 `cd src/web && npx vite build`
- 冒烟测试：`AUTH_TOKEN=xxx ./scripts/smoke_test.sh localhost:8000 --write`
- 数据库迁移：`config/migrations/*.sql`（幂等，psql 应用）
- Web 登录后可在「系统管理 → 配置中心」配置自己的 AI 模型与 AppKey
