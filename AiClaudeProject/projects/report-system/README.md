# 报表管理系统 (Report System)

翡翠技术支持周报/月报一键生成系统。

## 快速开始

```bash
# 1. 安装依赖
pip install openpyxl beautifulsoup4

# 2. 配置 Confluence Token（三选一）

# 方式A：.env 文件（推荐）
cp .env.example .env
# 编辑 .env 文件，填入你的 Token

# 方式B：环境变量
export CONFLUENCE_TOKEN="your_token"

# 方式C：命令行参数
python3 weekly_data.py --token YOUR_TOKEN --summary

# 3. 放入数据文件
cp 技术支持工单明细.xlsx data/

# 4. 运行
cd weekly-report/
python3 weekly_data.py --summary          # 查看本周数据摘要
python3 weekly_data.py --audit            # 审计数据
python3 weekly_data.py --publish          # 发布到 Confluence
```

## 目录结构

```
report-system/
├── README.md
├── requirements.txt
├── weekly-report/                  # 周报模块
│   ├── SKILL.md                    # Claude Code Skill 入口
│   ├── weekly_data.py              # 一键数据脚本
│   ├── data-fetching/SKILL.md      # 数据获取子技能
│   ├── data-audit/SKILL.md         # 数据审计子技能
│   └── output/SKILL.md             # 输出模板子技能
├── monthly-report/                 # 月报模块
│   ├── SKILL.md
│   ├── data-fetching/SKILL.md
│   └── data-audit/SKILL.md
├── data/                           # 输入数据（在这里放 Excel）
│   ├── README.md
│   └── 技术支持工单明细.xlsx
└── output/                         # 生成的报表
    ├── 周报/
    ├── 月报/
    └── 年度报表/
```

## CLI 参数

| 参数 | 说明 |
|------|------|
| `--week W30` | 指定周次 |
| `--excel /path/to/file.xlsx` | 指定 Excel 路径 |
| `--json` | 输出 JSON 数据 |
| `--summary` | 输出摘要 |
| `--audit` | 运行审计检查 |
| `--publish` | 发布到 Confluence |

## 环境变量

| 变量 | 说明 |
|------|------|
| `CONFLUENCE_TOKEN` | Confluence API Token（必需） |
| `WEEKLY_REPORT_EXCEL_PATH` | Excel 文件路径（可选） |