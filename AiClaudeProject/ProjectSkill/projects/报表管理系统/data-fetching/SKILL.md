---
name: tech-support-weekly-report-data-fetching
description: 获取技术支持周报所需的全部原始数据，包括从 Confluence API 拉取历史周报和需求列表，以及从本地 Excel 读取工单明细和超期工单数据
---

# 技术支持周报 - 数据获取

## Overview

本 skill 负责获取生成技术支持周报所需的全部原始数据。数据来源有两类：

1. **Confluence API**（内网认证站点，必须用 curl + Bearer Token）
2. **本地 Excel 文件**（`AiClaudeProject/原始报表文档/技术支持工单明细.xlsx`）

## 一、Confluence 数据源

> **【强制规则】cf.cai-inc.com 为内网认证站点，必须使用 Bash + curl + Bearer Token 获取数据。禁止使用 WebFetch。**

- **实例**: `https://cf.cai-inc.com`
- **认证**: Bearer Token（已配置）
- **空间**: FCSY

### 1.1 获取最新周报列表

**周报父页面**: 26年技术支持周报 (pageId: 252657891)

```bash
curl -s -H "Authorization: Bearer <token>" \
  "https://cf.cai-inc.com/rest/api/content/252657891/child/page?limit=50"
```

获取单个页面详情：
```bash
curl -s -H "Authorization: Bearer <token>" \
  "https://cf.cai-inc.com/rest/api/content/{pageId}?expand=children.page,body.storage"
```

### 1.2 获取需求列表

**需求父页面**: 2026年浙里报需求 (pageId: 258705731)
**链接**: https://cf.cai-inc.com/pages/viewpage.action?pageId=258705731

```bash
curl -s -H "Authorization: Bearer <token>" \
  "https://cf.cai-inc.com/rest/api/content/258705731?expand=body.storage,title"
```

**需求表格字段**:

| 列名 | 说明 | 对应周报字段 |
|------|------|-------------|
| 需求产品模块 | 如"数智财务" | 用于路由到对应附录 |
| 需求名称 | 含需求ID和简要描述 | 需求名称 |
| 需求链接 | ipaas.cai-inc.com 链接 | 需求链接 |
| 状态 | 已完成/已确认/草稿等 | 需求状态 |
| 提交时间 | 需求提交日期 | — |
| 完成时间 | 预计/实际完成时间 | — |
| 跟进人 | 技术支持跟进人 | — |
| 产品 | 产品负责人 | — |

**解析需求表格的 Python 脚本**:

```python
import requests
from bs4 import BeautifulSoup

resp = requests.get(
    "https://cf.cai-inc.com/rest/api/content/258705731?expand=body.storage",
    headers={"Authorization": "Bearer <token>"}
)
html = resp.json()["body"]["storage"]["value"]
soup = BeautifulSoup(html, "html.parser")

# 解析第一个需求表格
table = soup.find("table")
rows = table.find_all("tr")[1:]  # 跳过表头

demands = {"数智财务": [], "免疫规划": [], "数字化支撑": [], "电子档案": []}

for row in rows:
    cols = row.find_all("td")
    if len(cols) < 4:
        continue

    module = cols[0].get_text(strip=True)          # 需求产品模块
    name = cols[1].get_text(strip=True)             # 需求名称
    link_el = cols[2].find("a")
    link = link_el["href"] if link_el else ""
    status = cols[3].get_text(strip=True)           # 状态

    if not module or not name:
        continue

    # 过滤：仅统计未完成的需求（排除"已完成"状态）
    if "已完成" in status:
        continue

    # 按产品模块归类
    if "数智财务" in module:
        demands["数智财务"].append({"name": name, "link": link, "status": status})
    elif "免疫规划" in module or "疫苗" in module:
        demands["免疫规划"].append({"name": name, "link": link, "status": status})
    elif "数字化" in module:
        demands["数字化支撑"].append({"name": name, "link": link, "status": status})
    elif "电子档案" in module:
        demands["电子档案"].append({"name": name, "link": link, "status": status})
```

## 二、本地 Excel 数据源

**文件位置**: `AiClaudeProject/原始报表文档/技术支持工单明细.xlsx`

### 2.1 工单明细数据字段

| 列 | 字段 | 说明 |
|----|------|------|
| A | 工单编号 | 工单唯一标识 |
| B | 事业部 | 如"翡翠事业部" |
| C | 二级部门 | 如"数智财务组"、"数字化支撑组"、"免疫规划组"、"电子档案组" |
| D | 三级部门 | 如"浙里报"、"数字化" |
| E | 模块 | 如"浙里报"、"收费平台"、"票据管理"、"预防接种"等 |
| F | 问题分类 | 如"正常技术排查"、"客满咨询类-基础咨询"等 |
| G | 提交时间 | 工单提交时间（datetime），用于筛选本周数据 |
| H | 是否超时 | "是"/"否" |
| I | 超期原因 | 如"外部超时"、"开发超时"、"运营超时" |
| J | 工单摘要 | 问题详细描述，含处理结果 — **工单问题分析的核心数据源** |

### 2.2 读取工单数据

```python
from openpyxl import load_workbook
from collections import Counter, defaultdict
import datetime

wb = load_workbook('AiClaudeProject/原始报表文档/技术支持工单明细.xlsx', data_only=True)
ws = wb.active

tickets = []
for row in ws.iter_rows(min_row=2, values_only=True):
    tid = str(row[0])
    time_val = row[6]  # 提交时间
    if time_val is None:
        continue
    if isinstance(time_val, datetime.datetime):
        d = time_val
    else:
        try:
            d = datetime.datetime.strptime(str(time_val)[:10], '%Y-%m-%d')
        except:
            continue
    tickets.append({
        "id": tid,
        "date": d,
        "dept2": row[2] or "",      # 二级部门
        "dept3": row[3] or "",      # 三级部门
        "module": row[4] or "",     # 模块
        "category": row[5] or "",   # 问题分类
        "time": str(time_val),
        "is_overdue": row[7] or "", # 是否超时
        "overdue_reason": row[8] or "",  # 超期原因
        "desc": row[9] or "",       # 工单摘要 -> 用于问题分析
    })
```

### 2.3 筛选本周数据

根据报告周期（如 2026-W22 = 5/29 - 6/5），筛选落在该日期范围内的工单：

```python
week_start = datetime.datetime(2026, 5, 29)
week_end = datetime.datetime(2026, 6, 5)
week_tickets = [t for t in tickets if week_start <= t['date'] <= week_end]
```

### 2.4 读取超期工单

```python
from openpyxl import load_workbook
from collections import defaultdict

wb = load_workbook('AiClaudeProject/原始报表文档/技术支持工单明细.xlsx', data_only=True)
ws = wb.active

overdue = defaultdict(list)  # 按业务组归类

for row in ws.iter_rows(min_row=2, values_only=True):
    if row[7] != '是':  # 是否超时
        continue

    tid = str(row[0])
    dept2 = str(row[2]) if row[2] else ""     # 二级部门
    module = str(row[4]) if row[4] else ""     # 模块
    reason = str(row[8]) if row[8] else ""     # 超期原因
    time = str(row[6]) if row[6] else ""       # 提交时间
    summary = str(row[9]) if row[9] else ""    # 工单摘要

    # 附录1（数智财务组 + 电子档案组）所有模块排除"外部超时"
    if dept2 in ["数智财务组", "电子档案组"] and "外部超时" in reason:
        continue

    # 按二级部门归类到业务组
    if dept2 in ["数智财务组", "电子档案组"]:
        group = "附录1"  # 数智财务 & 电子档案
    elif dept2 == "免疫规划组":
        group = "附录2"  # 免疫规划
    elif dept2 == "数字化支撑组":
        group = "附录3"  # 数字化支撑
    else:
        continue

    overdue[group].append({
        "id": tid,
        "dept2": dept2,
        "module": module,
        "reason": reason,
        "time": time,
        "summary": summary,
    })
```

## 三、数据获取流程

1. 确认报告周期（本周起止日期）
2. 从 `AiClaudeProject/原始报表文档/技术支持工单明细.xlsx` 读取全部工单数据
3. 按报告周期筛选本周工单
4. 从 Excel 提取超期工单（筛选"是否超时"="是"的行）
5. 从 Confluence 获取最新一期周报作为参考模板（可选，**必须使用 curl + Bearer Token**）
6. **从 Confluence 获取需求列表**（**必须使用 curl + Bearer Token，禁止 WebFetch**），过滤出所有未完成需求（排除"已完成"状态）

> 获取完成后的数据审计和核实确认，参见 `tech-support-weekly-report-data-audit` skill。