---
name: tech-support-weekly-report
description: Use when generating weekly technical support reports (技术支持周报), especially for 翡翠 (Feicui) business unit. Trigger when user mentions weekly report, 周报, technical support report, 技术支持周报, or needs to compile ticket/work-order analysis across business groups.
---

# 技术支持周报生成

## Overview

基于本地工单明细数据（`原始报表文档/技术支持工单明细.xlsx`）和 Confluence 上现有周报模板，生成标准化的技术支持周报。工单问题分析、TOP问题分析、高频问题分析等均从技术支持工单明细.xlsx 的工单摘要字段提取数据。

## 工作流程

本 skill 按以下三个阶段依次执行，每个阶段由对应的子 skill 负责：

```
数据获取 → 数据审计核实确认 → 最终结果输出
    ↓            ↓               ↓
data-fetching  data-audit      output
```

### 阶段一：数据获取

使用 `tech-support-weekly-report-data-fetching` skill 获取全部原始数据：

- 从 Confluence API（curl + Bearer Token）拉取最新周报参考和需求列表
- 从本地 Excel（`AiClaudeProject/原始报表文档/技术支持工单明细.xlsx`）读取工单明细和超期工单
- 按报告周期筛选本周数据

### 阶段二：数据审计核实确认

使用 `tech-support-weekly-report-data-audit` skill 对数据进行审计：

- 工单统计分析（总量、趋势、分类、模块分布）
- TOP 问题关键词归类和统计
- 高频问题详情编写（含质量检查清单）
- 超期工单归类（含各附录排除规则）
- 两小时完结率四舍五入取整 + 达标判断
- 需求状态过滤和业务模块归属映射
- 最终自检清单

### 阶段三：最终结果输出

使用 `tech-support-weekly-report-output` skill 生成最终报告：

- 简述（故障情况、工单量、两小时处理率、TOP问题）
- 业务指标详情表格（含上周对比、趋势标注）
- 附录1：数智财务 & 电子档案工单数据分析
- 附录2：免疫规划工单数据分析
- 附录3：数字化支撑工单数据分析

输出路径：`AiClaudeProject/{日期}_报表管理系统/周报/{周次}-技术支持周报.md`

## 数据来源

| 来源 | 方式 | 用途 |
|------|------|------|
| Confluence (cf.cai-inc.com) | curl + Bearer Token（禁止 WebFetch） | 历史周报参考、需求列表 |
| 技术支持工单明细.xlsx | openpyxl 本地读取 | 工单问题分析、TOP问题、超期工单 |

## Confluence 关键页面

- **周报父页面**: 26年技术支持周报 (pageId: 252657891)
- **需求父页面**: 2026年浙里报需求 (pageId: 258705731)
- **空间**: FCSY

<!--
## 拆分记录

原始 SKILL.md（835行）已拆分为三个子 skill：

```
报表管理系统/
├── SKILL.md              (64行)  - 主编排器，定义三阶段工作流
├── data-fetching/
│   └── SKILL.md          (229行) - 数据获取：Confluence API(curl+Bearer Token) + 本地Excel(openpyxl)
├── data-audit/
│   └── SKILL.md          (376行) - 数据审计核实确认：工单统计、TOP问题归类、高频问题详情、超期归类、达标判断、质量检查
└── output/
    └── SKILL.md          (278行) - 最终结果输出：简述模板、业务指标详情表格、三个附录完整模板

子 skill 名称：
- tech-support-weekly-report-data-fetching
- tech-support-weekly-report-data-audit
- tech-support-weekly-report-output

  三个子 skill 的职责划分：
  ┌────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │               子Skill              │                                                                   职责                                                                   │
  ├────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ tech-support-weekly-report-data-fe │ Confluence API（curl + Bearer Token）拉取周报/需求数据；openpyxl 读取本地工单明细 Excel；按周期筛选；超期工单提取                        │
  │ tching                             │                                                                                                                                          │
  ├────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ tech-support-weekly-report-data-au │ 工单统计分析；TOP 问题关键词归类；高频问题详情编写+质量检查清单；超期工单归类规则（附录1排除外部超时）；两小时完结率取整+达标判断；需求  │
  │ dit                                │ 状态过滤；业务模块归属映射；最终自检清单                                                                                                 │
  ├────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ tech-support-weekly-report-output  │ 简述模板；业务指标详情表格；三个附录完整模板；TOP需求链接输出格式；报告输出路径                                                          │
  └────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  主 SKILL.md 从 835 行精简到 64 行，作为入口编排三个阶段的执行顺序：数据获取 → 数据审计核实确认 → 最终结果输出。

执行顺序：数据获取 → 数据审计核实确认 → 最终结果输出
-->