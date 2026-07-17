---
name: tech-support-monthly-report-output
description: 生成技术支持月报的最终输出，包括核心摘要看板、趋势图数据、问题类型分布、高频问题分析、需求完成情况、工作总结与下月计划等完整模板
---

# 技术支持月报 - 最终结果输出

## Overview

本 skill 负责将已审计确认的数据填充到月报模板中，生成最终报告。仅在 `tech-support-monthly-report-data-audit` 技能的数据审计全部通过后执行。

**输出路径**: `AiClaudeProject/2026报表数据知识库/月报/{月份}-技术支持月报.md`

> **路径规则**：所有报表（周报、月报、年报、其他报表）统一保存在 `2026报表数据知识库/` 目录下的对应子文件夹中，**禁止**每次新建日期目录。

---

## 报告结构

```
# {{Report_Month}} 技术支持月报

## 一、核心摘要（关键指标卡）
## 二、工单数据趋势图（按周）
## 三、问题类型分布图
## 四、主要问题TOP图
## 五、用户数据量趋势图（按周）
## 六、咨询量趋势图（按周）
## 七、故障数据趋势图（按周）
## 八、业务组月度指标汇总
## 九、当月主要高频问题分析
## 十、当月主要解决的问题
## 十一、当月需求完成情况
## 十二、本月工作总结与下月计划
```

---

## 一、核心摘要

| 指标 | 本月 | 上月 | 环比变化 | 目标值 | 达标情况 |
|:---|:---:|:---:|:---:|:---:|:---:|
| 客满工单总量 | {{Total_Customer_Tickets}} | {{Last_Customer_Tickets}} | {{Customer_Tickets_Change}} | — | — |
| 技术工单总量 | {{Total_Tech_Tickets}} | {{Last_Tech_Tickets}} | {{Tech_Tickets_Change}} | — | — |
| 技术支持解决率 | {{Total_Solved_Rate}}% | {{Last_Solved_Rate}}% | {{Solved_Rate_Change}} | ≥85% | {{Solved_Rate_Status}} |
| 2小时工单完成率 | {{Total_2H_Rate}}% | {{Last_2H_Rate}}% | {{Total_2H_Change}} | ≥95% | {{Total_2H_Status}} |
| P1/P2故障数 | {{Total_P1P2_Count}} | {{Last_P1P2_Count}} | {{P1P2_Change}} | 0 | {{P1P2_Status}} |
| P3/P4故障数 | {{Total_P3P4_Count}} | {{Last_P3P4_Count}} | {{P3P4_Change}} | — | — |
| 月活跃用户（UV，万） | {{Total_UV}} | {{Last_UV}} | {{UV_Change}} | — | — |
| 月咨询量 | {{Total_Consult}} | {{Last_Consult}} | {{Consult_Change}} | — | — |

---

## 二、工单数据趋势图

> **图表类型**：折线图（按周展示当月趋势）

| 日期（周） | 第1周 | 第2周 | 第3周 | 第4周 | 第5周（如有） |
|:---|:---:|:---:|:---:|:---:|:---:|
| 客满工单数 | {{W1_Customer}} | {{W2_Customer}} | {{W3_Customer}} | {{W4_Customer}} | {{W5_Customer}} |
| 技术工单数 | {{W1_Tech}} | {{W2_Tech}} | {{W3_Tech}} | {{W4_Tech}} | {{W5_Tech}} |
| 技术支持解决工单数 | {{W1_Solved}} | {{W2_Solved}} | {{W3_Solved}} | {{W4_Solved}} | {{W5_Solved}} |
| 2小时完成率（%） | {{W1_2H}} | {{W2_2H}} | {{W3_2H}} | {{W4_2H}} | {{W5_2H}} |

**趋势分析**：
- {{Trend_Analysis_1}}
- {{Trend_Analysis_2}}
- {{Trend_Analysis_3}}

---

## 三、问题类型分布图

> **图表类型**：饼图/环形图

| 问题类型 | 工单数量 | 占比 |
|:---|:---:|:---:|
| 功能咨询/使用指导 | {{Type_Consult_Count}} | {{Type_Consult_Ratio}}% |
| 系统故障/异常报错 | {{Type_Bug_Count}} | {{Type_Bug_Ratio}}% |
| 数据问题/订正 | {{Type_Data_Count}} | {{Type_Data_Ratio}}% |
| 需求/优化建议 | {{Type_Demand_Count}} | {{Type_Demand_Ratio}}% |
| 权限/账号问题 | {{Type_Permission_Count}} | {{Type_Permission_Ratio}}% |
| 配置/环境问题 | {{Type_Config_Count}} | {{Type_Config_Ratio}}% |
| 其他 | {{Type_Other_Count}} | {{Type_Other_Ratio}}% |
| **合计** | **{{Total_Type_Count}}** | **100%** |

**问题类型分析**：
- {{Type_Analysis_1}}
- {{Type_Analysis_2}}

---

## 四、主要问题TOP图

> **图表类型**：柱状图

| 排名 | 问题描述 | 所属业务 | 工单量 | 占比 |
|:---:|:---|:---|:---:|:---:|
| 1 | {{Top1_Issue}} | {{Top1_Business}} | {{Top1_Count}} | {{Top1_Ratio}}% |
| 2 | {{Top2_Issue}} | {{Top2_Business}} | {{Top2_Count}} | {{Top2_Ratio}}% |
| 3 | {{Top3_Issue}} | {{Top3_Business}} | {{Top3_Count}} | {{Top3_Ratio}}% |
| 4 | {{Top4_Issue}} | {{Top4_Business}} | {{Top4_Count}} | {{Top4_Ratio}}% |
| 5 | {{Top5_Issue}} | {{Top5_Business}} | {{Top5_Count}} | {{Top5_Ratio}}% |
| 其他 | 其他问题汇总 | — | {{Other_Issue_Count}} | {{Other_Issue_Ratio}}% |

**主要问题分析**：
- {{Top_Analysis_1}}
- {{Top_Analysis_2}}
- {{Top_Analysis_3}}

---

## 五、用户数据量趋势图

> **图表类型**：折线图（按周展示当月趋势）

| 日期（周） | 第1周 | 第2周 | 第3周 | 第4周 | 第5周（如有） |
|:---|:---:|:---:|:---:|:---:|:---:|
| 数智财务-UV（万） | {{F_UV_W1}} | {{F_UV_W2}} | {{F_UV_W3}} | {{F_UV_W4}} | {{F_UV_W5}} |
| 免疫规划-UV（万） | {{I_UV_W1}} | {{I_UV_W2}} | {{I_UV_W3}} | {{I_UV_W4}} | {{I_UV_W5}} |
| 数字化支撑-UV（万） | {{D_UV_W1}} | {{D_UV_W2}} | {{D_UV_W3}} | {{D_UV_W4}} | {{D_UV_W5}} |
| **全业务合计-UV（万）** | **{{T_UV_W1}}** | **{{T_UV_W2}}** | **{{T_UV_W3}}** | **{{T_UV_W4}}** | **{{T_UV_W5}}** |

**用户量趋势分析**：
- {{UV_Trend_Analysis_1}}
- {{UV_Trend_Analysis_2}}

---

## 六、咨询量趋势图

> **图表类型**：折线图（按周展示当月趋势）

| 日期（周） | 第1周 | 第2周 | 第3周 | 第4周 | 第5周（如有） |
|:---|:---:|:---:|:---:|:---:|:---:|
| 数智财务-咨询量 | {{F_Consult_W1}} | {{F_Consult_W2}} | {{F_Consult_W3}} | {{F_Consult_W4}} | {{F_Consult_W5}} |
| 免疫规划-咨询量 | {{I_Consult_W1}} | {{I_Consult_W2}} | {{I_Consult_W3}} | {{I_Consult_W4}} | {{I_Consult_W5}} |
| 数字化支撑-咨询量 | {{D_Consult_W1}} | {{D_Consult_W2}} | {{D_Consult_W3}} | {{D_Consult_W4}} | {{D_Consult_W5}} |
| **全业务合计-咨询量** | **{{T_Consult_W1}}** | **{{T_Consult_W2}}** | **{{T_Consult_W3}}** | **{{T_Consult_W4}}** | **{{T_Consult_W5}}** |

**咨询量趋势分析**：
- {{Consult_Trend_Analysis_1}}
- {{Consult_Trend_Analysis_2}}
- {{Consult_Trend_Analysis_3}}

---

## 七、故障数据趋势图

> **图表类型**：折线图/柱状图组合（按周展示当月趋势）

| 日期（周） | 第1周 | 第2周 | 第3周 | 第4周 | 第5周（如有） | 月度累计 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| P1/P2故障（累计） | {{P1P2_W1}} | {{P1P2_W2}} | {{P1P2_W3}} | {{P1P2_W4}} | {{P1P2_W5}} | {{P1P2_Total}} |
| P3/P4故障（累计） | {{P3P4_W1}} | {{P3P4_W2}} | {{P3P4_W3}} | {{P3P4_W4}} | {{P3P4_W5}} | {{P3P4_Total}} |
| 外部故障（累计） | {{ExtBug_W1}} | {{ExtBug_W2}} | {{ExtBug_W3}} | {{ExtBug_W4}} | {{ExtBug_W5}} | {{ExtBug_Total}} |
| 故障总数（新增） | {{Bug_New_W1}} | {{Bug_New_W2}} | {{Bug_New_W3}} | {{Bug_New_W4}} | {{Bug_New_W5}} | {{Bug_New_Total}} |

**故障趋势分析**：
- {{Bug_Trend_Analysis_1}}
- {{Bug_Trend_Analysis_2}}
- {{Bug_Trend_Analysis_3}}

---

## 八、业务组月度指标汇总

| 业务组 | 客满工单 | 技术工单 | 解决率 | 2H完成率 | P1/P2 | P3/P4 | UV（万） | 咨询量 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 数智财务 | {{F_Customer_Month}} | {{F_Tech_Month}} | {{F_SolvedRate_Month}}% | {{F_2H_Month}}% | {{F_P1P2_Month}} | {{F_P3P4_Month}} | {{F_UV_Month}} | {{F_Consult_Month}} |
| 免疫规划 | {{I_Customer_Month}} | {{I_Tech_Month}} | {{I_SolvedRate_Month}}% | {{I_2H_Month}}% | {{I_P1P2_Month}} | {{I_P3P4_Month}} | {{I_UV_Month}} | {{I_Consult_Month}} |
| 数字化支撑 | {{D_Customer_Month}} | {{D_Tech_Month}} | {{D_SolvedRate_Month}}% | {{D_2H_Month}}% | {{D_P1P2_Month}} | {{D_P3P4_Month}} | {{D_UV_Month}} | {{D_Consult_Month}} |
| 电子档案 | {{A_Customer_Month}} | {{A_Tech_Month}} | {{A_SolvedRate_Month}}% | {{A_2H_Month}}% | {{A_P1P2_Month}} | {{A_P3P4_Month}} | — | — |

---

## 九、当月主要高频问题分析

### 9.1 高频问题详情

| 序号 | 问题分类 | 问题描述 | 出现频次 | 影响业务 | 根本原因 | 临时解决方案 | 长期改进措施 |
|:---:|:---|:---|:---:|:---|:---|:---|:---|
| 1 | {{Category1}} | {{Desc1}} | {{Freq1}} | {{Business1}} | {{RootCause1}} | {{TempSolution1}} | {{LongSolution1}} |
| 2 | {{Category2}} | {{Desc2}} | {{Freq2}} | {{Business2}} | {{RootCause2}} | {{TempSolution2}} | {{LongSolution2}} |
| 3 | {{Category3}} | {{Desc3}} | {{Freq3}} | {{Business3}} | {{RootCause3}} | {{TempSolution3}} | {{LongSolution3}} |
| 4 | {{Category4}} | {{Desc4}} | {{Freq4}} | {{Business4}} | {{RootCause4}} | {{TempSolution4}} | {{LongSolution4}} |
| 5 | {{Category5}} | {{Desc5}} | {{Freq5}} | {{Business5}} | {{RootCause5}} | {{TempSolution5}} | {{LongSolution5}} |

### 9.2 高频问题根因归类

| 根因类型 | 问题数量 | 占比 |
|:---|:---:|:---:|
| 系统Bug/代码缺陷 | {{Root_Bug_Count}} | {{Root_Bug_Ratio}}% |
| 数据同步/一致性问题 | {{Root_Data_Count}} | {{Root_Data_Ratio}}% |
| 用户操作/认知问题 | {{Root_User_Count}} | {{Root_User_Ratio}}% |
| 配置/部署问题 | {{Root_Config_Count}} | {{Root_Config_Ratio}}% |
| 第三方依赖问题 | {{Root_Third_Count}} | {{Root_Third_Ratio}}% |
| 需求缺失/设计缺陷 | {{Root_Design_Count}} | {{Root_Design_Ratio}}% |

---

## 十、当月主要解决的问题

| 序号 | 问题描述 | 所属业务 | 问题类型 | 解决日期 | 解决方案 | 状态 |
|:---:|:---|:---|:---:|:---:|:---|:---|
| 1 | {{Resolved1}} | {{R_Business1}} | {{R_Type1}} | {{R_Date1}} | {{R_Solution1}} | 已解决 |
| 2 | {{Resolved2}} | {{R_Business2}} | {{R_Type2}} | {{R_Date2}} | {{R_Solution2}} | 已解决 |
| 3 | {{Resolved3}} | {{R_Business3}} | {{R_Type3}} | {{R_Date3}} | {{R_Solution3}} | 已解决 |
| 4 | {{Resolved4}} | {{R_Business4}} | {{R_Type4}} | {{R_Date4}} | {{R_Solution4}} | 已解决 |
| 5 | {{Resolved5}} | {{R_Business5}} | {{R_Type5}} | {{R_Date5}} | {{R_Solution5}} | 已解决 |

---

## 十一、当月需求完成情况

| 序号 | 需求名称 | 所属业务 | 关联工单量 | 需求状态 | 预计上线时间 | 实际上线时间 |
|:---:|:---|:---|:---:|:---|:---:|:---:|
| 1 | {{Demand1}} | {{D_Business1}} | {{D_Count1}} | {{D_Status1}} | {{D_PlanDate1}} | {{D_ActualDate1}} |
| 2 | {{Demand2}} | {{D_Business2}} | {{D_Count2}} | {{D_Status2}} | {{D_PlanDate2}} | {{D_ActualDate2}} |
| 3 | {{Demand3}} | {{D_Business3}} | {{D_Count3}} | {{D_Status3}} | {{D_PlanDate3}} | {{D_ActualDate3}} |
| 4 | {{Demand4}} | {{D_Business4}} | {{D_Count4}} | {{D_Status4}} | {{D_PlanDate4}} | {{D_ActualDate4}} |

---

## 十二、本月工作总结与下月计划

### 12.1 本月工作亮点
- {{Highlight_1}}
- {{Highlight_2}}
- {{Highlight_3}}

### 12.2 本月工作不足
- {{Weakness_1}}
- {{Weakness_2}}

### 12.3 下月重点工作计划
| 序号 | 工作计划 | 负责人 | 预计完成时间 | 优先级 |
|:---:|:---|:---:|:---:|:---:|
| 1 | {{Plan_1}} | {{Owner_1}} | {{PlanDate_1}} | {{Priority_1}} |
| 2 | {{Plan_2}} | {{Owner_2}} | {{PlanDate_2}} | {{Priority_2}} |
| 3 | {{Plan_3}} | {{Owner_3}} | {{PlanDate_3}} | {{Priority_3}} |
| 4 | {{Plan_4}} | {{Owner_4}} | {{PlanDate_4}} | {{Priority_4}} |

---

## 附录：数据来源说明

| 数据项 | 数据来源 |
|:---|:---|
| 工单数据 | {{Ticket_DataSource}} |
| 用户量/咨询量数据 | {{UV_DataSource}} |
| 故障数据 | {{Bug_DataSource}} |
| 需求数据 | {{Demand_DataSource}} |

---

## 使用说明

1. **数据填充**：将所有 `{{Variable_Name}}` 替换为当月实际数据。
2. **图表可视化建议**：
   - **趋势图**（工单、用户量、咨询量、故障）：建议使用**折线图**，可清晰展示变化趋势。
   - **分布图**（问题类型）：建议使用**饼图/环形图**，直观展示占比。
   - **主要问题图**：建议使用**柱状图**，便于对比各问题的工单量。
3. **趋势符号**：
   - `▲` 或 `↑` 表示上升
   - `▼` 或 `↓` 表示下降
   - `—` 或 `→` 表示持平
4. **周数划分**：可根据当月实际日历调整周数（通常为4-5周）。
5. **业务组扩展**：如有新增业务组，可参照现有格式扩展表格行。
6. **自定义图表**：在实际使用时，建议使用 **Metabase、Tableau、Excel 图表** 或 **ECharts** 等工具根据上述数据表生成可视化图表，嵌入月报中。

---

## 输出流程

1. 确认报告周期（本月起止日期，按自然月：1日→月末）
2. 按本 skill 模板结构，将 `tech-support-monthly-report-data-audit` skill 审计确认后的数据逐项填入
3. 对比上月数据，标注趋势（▲/▼/—）
4. 按两小时完结率 ≥ 95% 达标标准，判断各业务组达标/不达标（**注意：必须先四舍五入取整后再判断**）
5. **【最终自检】检查所有两小时完结率是否已四舍五入取整**，确认核心摘要和各表格中的值均不保留小数位
6. 输出文件到 `AiClaudeProject/2026报表数据知识库/月报/{月份}-技术支持月报.md`