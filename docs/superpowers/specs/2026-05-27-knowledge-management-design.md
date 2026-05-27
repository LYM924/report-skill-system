# 知识管理与报告系统 — 设计文档

## 概述

构建一套本地运行的知识管理与报告系统，包含两大模块：

1. **报告系统**：通过 YAML 数据 + Jinja2 模板生成周报/月报/半年报，支持 Markdown + Web + PDF 多格式输出
2. **知识库站点**：基于 MkDocs Material 的产品需求知识库 + 问题知识库，支持搜索、分类、导航

跨部门使用（产品、研发、运营），本地运行按需分享。

## 目录结构

```
ClaudeProject/
├── mkdocs.yml                  # MkDocs 配置（站点结构、主题、插件）
├── requirements.txt            # Python 依赖
│
├── docs/                       # 知识库（MkDocs 站点源文件）
│   ├── index.md                # 首页
│   ├── requirements/           # 产品需求知识库
│   │   ├── index.md            # 需求总览
│   │   └── <module>/           # 按模块分目录
│   │       ├── index.md        # 模块概览
│   │       └── YYYY-MM-DD-xxx.md  # 具体需求文档
│   ├── issues/                 # 问题知识库
│   │   ├── index.md            # 问题总览
│   │   └── <module>/
│   │       ├── index.md
│   │       └── YYYY-MM-DD-xxx.md
│   └── reports/                # 归档的报告（只读）
│       ├── weekly/
│       ├── monthly/
│       └── semiannual/
│
├── templates/                  # 报告模板
│   ├── weekly.j2               # 周报 Jinja2 模板
│   ├── monthly.j2              # 月度分析模板
│   ├── semiannual.j2           # 半年度分析模板
│   └── report-base.css         # PDF 导出样式
│
├── data/                       # 报告数据源（模板填充数据）
│   ├── weekly/                 # 按周编号存放 YAML
│   │   └── _template.yaml
│   ├── monthly/
│   │   └── _template.yaml
│   └── semiannual/
│       └── _template.yaml
│
├── scripts/                    # 工具脚本
│   ├── report.py               # 报告生成 CLI
│   ├── new_requirement.py      # 快速创建需求文档脚手架
│   ├── new_issue.py            # 快速创建问题文档脚手架
│   └── export_pdf.py           # Markdown → PDF 导出
│
└── site/                       # 构建产物（gitignore）
```

## 报告模板设计

### 数据格式

三种报告类型各有 YAML 数据模板，侧重不同：

**周报**（轻量，聚焦本周进度）：

```yaml
period: "2026年第22周 (5/25 - 5/29)"
modules:
  - name: "模块名"
    done: ["完成项"]
    next: ["下周计划"]
    risks: ["风险项"]
summary: "本周总结"
```

**月报**（加横向对比和趋势）：

```yaml
period: "2026年5月"
modules:
  - name: "模块名"
    completed: 8
    in_progress: 3
    blocked: 1
    issues_resolved: 12
    issues_new: 5
    highlights: ["亮点"]
    next_month: ["下月计划"]
summary: "..."
```

**半年报**（加里程碑回顾和趋势）：

```yaml
period: "2026年上半年 (1月 - 6月)"
modules:
  - name: "模块名"
    total_requirements: 45
    total_issues: 30
    milestone: ["里程碑"]
    trend: "趋势描述"
summary: "..."
```

### 生成流程

```
data/<type>/<period>.yaml  →  Jinja2 模板渲染  →  docs/reports/<type>/<period>.md  →  (可选) PDF
```

### CLI 用法

```bash
python scripts/report.py weekly 2026-W22           # 生成周报
python scripts/report.py monthly 2026-05           # 生成月报
python scripts/report.py semiannual 2026-H1        # 生成半年报
python scripts/report.py weekly 2026-W22 --pdf     # 同时导出 PDF
```

## 知识库文档结构

### 需求知识库（docs/requirements/）

每条需求一个 Markdown 文件，按模块分目录，文件名带日期前缀。

模板字段：

```markdown
---
status: 已上线          # 规划中 / 开发中 / 已上线 / 已废弃
priority: P0            # P0 / P1 / P2 / P3
created: 2026-05-15
owner: 张三
module: 用户中心
---

# 需求标题
## 背景
## 功能描述
## 验收标准
## 关联文档
## 变更记录
```

### 问题知识库（docs/issues/）

结构类似，侧重追溯和经验沉淀。

模板字段：

```markdown
---
status: 已解决          # 待排查 / 处理中 / 已解决 / 已关闭
severity: S1            # S0(事故) / S1(严重) / S2(一般) / S3(建议)
created: 2026-03-10
module: 用户中心
tags: [SSO, 超时]
---

# 问题标题
## 现象
## 根因
## 解决方案
## 经验教训
## 相关需求/问题
```

### MkDocs 站点导航

```yaml
nav:
  - 首页: index.md
  - 需求知识库:
    - 总览: requirements/index.md
    - 用户中心: requirements/user-center/index.md
    - 订单系统: requirements/order-system/index.md
  - 问题知识库:
    - 总览: issues/index.md
    - 用户中心: issues/user-center/index.md
    - 订单系统: issues/order-system/index.md
  - 工作报告:
    - 周报: reports/weekly/
    - 月报: reports/monthly/
    - 半年报: reports/semiannual/
```

## 脚本工具层

### report.py — 报告生成 CLI

读取 `data/<type>/<period>.yaml` → Jinja2 渲染 → 输出 Markdown 到 `docs/reports/<type>/`。`--pdf` 选项调用 weasyprint 转 PDF。

### new_requirement.py / new_issue.py — 脚手架

```bash
python scripts/new_requirement.py "SSO单点登录" --module user-center
python scripts/new_issue.py "支付回调超时" --module order-system --severity S1
```

自动填入日期前缀、状态默认值，基于 `_template.md` 创建文档。

### export_pdf.py — PDF 导出

基于 weasyprint，使用 `templates/report-base.css` 统一样式。

## 工作流

### 日常使用

```
录入需求和问题（脚手架创建 md） → mkdocs serve（实时预览站点） → 团队本地访问 localhost:8000
```

### 报告周期

```
填写 YAML 数据 → report.py 生成渲染 → 站点中归档查看 + 导出 PDF 分享
```

## 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| 文档站点 | MkDocs Material | 纯 Python，搜索/导航/标签完善 |
| 报告模板 | Jinja2 | Python 原生模板引擎 |
| PDF 导出 | weasyprint | Python HTML/CSS → PDF |
| 数据格式 | YAML | 可读性好，非技术人员友好 |

## 模块依赖

```
requirements.txt:
  mkdocs-material
  jinja2
  pyyaml
  weasyprint
```
