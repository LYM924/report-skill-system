---
name: tech-support-monthly-report
description: Use when generating monthly technical support reports (技术支持月报), especially for 翡翠 (Feicui) business unit. Trigger when user mentions monthly report, 月报, technical support monthly report, 技术支持月报, or needs to compile monthly ticket/work-order analysis across business groups.
---

# 技术支持月报生成

## Overview

基于本地工单明细数据（`原始报表文档/技术支持工单明细.xlsx`）和 Confluence 上现有月报模板，生成标准化的技术支持月报。月报在周报基础上增加了更多可视化维度和总结性分析，包括核心摘要看板、月度趋势图（按周）、问题类型分布、根因归类、工作亮点/不足、下月计划等。

## 工作流程

本 skill 按以下三个阶段依次执行，每个阶段由对应的子 skill 负责：

```
数据获取 → 数据审计核实确认 → 最终结果输出
    ↓            ↓               ↓
data-fetching  data-audit      output
```

### 阶段一：数据获取

使用 `tech-support-monthly-report-data-fetching` skill 获取全部原始数据：

- 从 Confluence API（curl + Bearer Token）拉取最新月报参考和需求列表
- 从本地 Excel（`AiClaudeProject/原始报表文档/技术支持工单明细.xlsx`）读取工单明细和超期工单
- 按自然月周期筛选本月数据

### 阶段二：数据审计核实确认

使用 `tech-support-monthly-report-data-audit` skill 对数据进行审计：

- 核心摘要指标审计（客满工单、技术工单、解决率、2H完结率、故障数、UV、咨询量）
- 按周汇总趋势数据审计（工单、用户量、咨询量、故障）
- 问题类型分布统计和审计
- TOP 问题关键词归类和统计
- 高频问题详情编写（含长期改进措施）
- 高频问题根因归类（6类根因占比）
- 已解决问题核实
- 超期工单归类（含各附录排除规则）
- 两小时完结率四舍五入取整 + 达标判断
- 需求状态过滤和业务模块归属映射
- 工作总结与下月计划合理性检查
- 最终自检清单

### 阶段三：最终结果输出

使用 `tech-support-monthly-report-output` skill 生成最终报告，包含 12 个部分：

1. 核心摘要（关键指标卡，含环比变化和达标判断）
2. 工单数据趋势图（按周折线图）
3. 问题类型分布图（饼图/环形图）
4. 主要问题TOP图（柱状图）
5. 用户数据量趋势图（按周折线图）
6. 咨询量趋势图（按周折线图）
7. 故障数据趋势图（按周组合图）
8. 业务组月度指标汇总
9. 当月主要高频问题分析（含根因归类）
10. 当月主要解决的问题
11. 当月需求完成情况
12. 本月工作总结与下月计划

输出路径：`AiClaudeProject/2026报表数据知识库/月报/{月份}-技术支持月报.md`

## 数据来源

| 来源 | 方式 | 用途 |
|------|------|------|
| Confluence (cf.cai-inc.com) | curl + Bearer Token（禁止 WebFetch） | 历史月报参考、需求列表、数据看板 |
| 技术支持工单明细.xlsx | openpyxl 本地读取 | 工单问题分析、TOP问题、超期工单、问题类型分布 |

## Confluence 关键页面

- **月报父页面**: 26年技术支持月报 (pageId: 252657891)
- **需求父页面**: 2026年浙里报需求 (pageId: 258705731)
- **翡翠月报数据看板**: (pageId: 278883515)
- **空间**: FCSY

## 与周报的关系

月报和周报共享相同的数据来源（Confluence + 本地 Excel）和相同的子 skill 结构（data-fetching / data-audit / output），区别在于：

| 维度 | 周报 | 月报 |
|------|------|------|
| 报告周期 | 周五→周四 | 自然月（1日→月末） |
| 对比基准 | 较上周 | 较上月 |
| 趋势粒度 | 按日 | 按周（4-5周） |
| 分析深度 | 工单级问题分析 | 统计级趋势分析 + 根因归类 |
| 特有内容 | 三个附录工单详情 | 核心摘要看板、问题类型分布、根因归类、工作总结与下月计划 |
| 输出路径 | `周报/` | `月报/` |

执行顺序：数据获取 → 数据审计核实确认 → 最终结果输出