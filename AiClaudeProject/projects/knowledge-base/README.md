# 产品知识库系统 (Knowledge Base System)

产品业务知识管理 + 智能检索系统。

## 目录结构

```
knowledge-base/
├── README.md
├── SKILL.md                        # Claude Code Skill 入口
├── Product_Knowledge_Base.md       # 知识库主文档
├── FAQ知识库/                  # 🆕 FAQ 知识沉淀
│   ├── INDEX.md               # 摘要索引
│   ├── TEMPLATE.md            # FAQ 标准模板
│   ├── 数智财务组/            # 按业务组分级
│   └── export/                # 静态 HTML 导出
├── scripts/                   # 🆕 维护脚本
│   ├── faq_audit.py           # FAQ 审计脚本
│   ├── faq_export.py          # FAQ 静态页面导出
│   ├── faq_ticket_link.py     # FAQ ↔ 工单关联管理
│   └── faq_generate.py        # FAQ 自动生成
│   ├── 数智财务组/
│   │   ├── 浙里报/
│   │   ├── 孵化业务/
│   │   ├── 徽报账/
│   │   └── 数智财务组-直属/
│   ├── 免疫规划组/
│   ├── 电子档案组/
│   └── 数字化支撑组/
├── raw-docs/                       # 原始参考文档
│   ├── 数智财务组/
│   ├── 免疫规划组/
│   ├── 电子档案组/
│   └── 数字化支撑组/
└── shared-modules/                 # 共享模块
    ├── SKILL.md
    ├── 关键词库/                   # 关键词索引+搜索缓存
    ├── 智能检索工具/               # BM25 + FAISS 搜索引擎
    ├── 数智财务组/                 # 各业务组模块定义
    ├── 免疫规划组/
    ├── 电子档案组/
    ├── 数字化支撑组/
    ├── 双向链接枢纽.md
    └── 各部门产品业务模块.xlsx
```

## 共享模块说明

智能检索工具支持：
- BM25 关键词检索
- FAISS 向量语义搜索
- 关键词索引 + 同义词映射
- **🆕 FAQ 知识库浏览与搜索**（集成在 Web 界面中）

### 启动 Web 服务

```bash
cd shared-modules/智能检索工具/
pip install -r requirements.txt
python3 search_server.py
```

启动后访问 `http://localhost:8899`，即可使用：
- 🔍 **智能搜索**：输入关键词搜索产品知识库
- 📚 **FAQ 浏览**：点击 "FAQ 浏览" 按钮查看所有 FAQ，支持按部门筛选、点击展开详情

## 维护脚本

### FAQ 审计 (`scripts/faq_audit.py`)

扫描 FAQ 知识库，检查 frontmatter 完整性、过期内容、断链等。

```bash
python3 scripts/faq_audit.py          # 审计报告
python3 scripts/faq_audit.py --fix    # 审计 + 自动更新 INDEX.md
python3 scripts/faq_audit.py --json   # JSON 格式输出
```

### FAQ 静态导出 (`scripts/faq_export.py`)

将 FAQ 知识库导出为单文件 HTML，可直接浏览器打开或部署到静态服务器。

```bash
python3 scripts/faq_export.py              # 导出到 FAQ知识库/export/
python3 scripts/faq_export.py --serve      # 导出 + 启动本地预览
python3 scripts/faq_export.py --output /path/to/output/  # 指定输出目录
```

### FAQ ↔ 工单关联 (`scripts/faq_ticket_link.py`)

管理 FAQ 与工单的双向关联，支持从工单分析文档匹配 FAQ。

```bash
python3 scripts/faq_ticket_link.py                    # 查看关联总览
python3 scripts/faq_ticket_link.py --report           # 详细关联报告
python3 scripts/faq_ticket_link.py --orphan-faqs      # 查看无工单来源的 FAQ
python3 scripts/faq_ticket_link.py --scan-tickets     # 扫描工单文档匹配 FAQ
python3 scripts/faq_ticket_link.py --link FAQ-SZ-ZLB-001 202606301704475767058  # 添加工单关联
```

### FAQ 自动生成 (`scripts/faq_generate.py`)

从知识库文档和工单分析中提取 FAQ 种子，生成草稿待人工审核。

```bash
python3 scripts/faq_generate.py                    # 分析并输出建议
python3 scripts/faq_generate.py --drafts           # 生成草稿到 _drafts/
python3 scripts/faq_generate.py --source tickets   # 仅从工单分析生成
python3 scripts/faq_generate.py --source kb        # 仅从知识库生成
python3 scripts/faq_generate.py --drafts --apply   # 生成草稿并自动入库
```