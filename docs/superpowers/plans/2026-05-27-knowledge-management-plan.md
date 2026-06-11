# Knowledge Management System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local knowledge management system with MkDocs Material site for requirements/issues knowledge base, and Jinja2-based report generation pipeline for weekly/monthly/semiannual reports with Markdown + Web + PDF output.

**Architecture:** MkDocs Material serves as the documentation site (`docs/` directory). Report generation is a separate Python CLI pipeline: YAML data files → Jinja2 templates → rendered Markdown → archived into `docs/reports/` so they appear in the site. Scaffold scripts accelerate creation of new requirement/issue documents. PDF export via weasyprint.

**Tech Stack:** Python 3, MkDocs Material, Jinja2, PyYAML, weasyprint

---

## File Map

| File | Purpose |
|------|---------|
| `mkdocs.yml` | MkDocs site config, nav, theme, plugins |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Exclude site/, __pycache__, etc. |
| `docs/index.md` | Site home page |
| `docs/requirements/index.md` | Requirements knowledge base overview |
| `docs/requirements/_template.md` | New requirement document template |
| `docs/issues/index.md` | Issues knowledge base overview |
| `docs/issues/_template.md` | New issue document template |
| `templates/weekly.j2` | Jinja2 template for weekly report |
| `templates/monthly.j2` | Jinja2 template for monthly report |
| `templates/semiannual.j2` | Jinja2 template for semiannual report |
| `templates/report-base.css` | CSS for PDF export styling |
| `data/weekly/_template.yaml` | Weekly report data template |
| `data/monthly/_template.yaml` | Monthly report data template |
| `data/semiannual/_template.yaml` | Semiannual report data template |
| `scripts/report.py` | Report generation CLI |
| `scripts/new_requirement.py` | Requirement scaffold CLI |
| `scripts/new_issue.py` | Issue scaffold CLI |
| `scripts/export_pdf.py` | Markdown → PDF export CLI |

---

### Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `mkdocs.yml`

- [ ] **Step 1: Create requirements.txt**

```bash
cat > requirements.txt << 'EOF'
mkdocs-material>=9.0
jinja2>=3.1
pyyaml>=6.0
weasyprint>=60.0
EOF
```

- [ ] **Step 2: Create .gitignore**

```bash
cat > .gitignore << 'EOF'
site/
__pycache__/
*.pyc
.pdf
EOF
```

- [ ] **Step 3: Create mkdocs.yml**

```yaml
site_name: 产品知识库
site_description: 产品需求与问题知识库
theme:
  name: material
  language: zh
  features:
    - navigation.sections
    - navigation.expand
    - search.suggest
    - search.highlight
plugins:
  - search
markdown_extensions:
  - pymdownx.superfences
  - pymdownx.tasklist:
      custom_checkbox: true
  - toc:
      permalink: true
nav:
  - 首页: index.md
  - 需求知识库:
      - 总览: requirements/index.md
  - 问题知识库:
      - 总览: issues/index.md
  - 工作报告:
      - 周报: reports/weekly/
      - 月报: reports/monthly/
      - 半年报: reports/semiannual/
```

- [ ] **Step 4: Install dependencies and verify MkDocs**

Run: `pip install -r requirements.txt`
Then: `mkdocs --version`
Expected: mkdocs version output

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore mkdocs.yml
git commit -m "chore: initialize project with MkDocs Material and dependencies"
```

---

### Task 2: Knowledge Base Structure and Templates

**Files:**
- Create: `docs/index.md`
- Create: `docs/requirements/index.md`
- Create: `docs/requirements/_template.md`
- Create: `docs/issues/index.md`
- Create: `docs/issues/_template.md`

- [ ] **Step 1: Create site home page**

Write `docs/index.md`:

```markdown
# 产品知识库

欢迎使用产品知识库。这里汇集了产品需求文档、问题沉淀和工作报告。

## 快速导航

- [需求知识库](requirements/) — 按模块整理的产品需求文档
- [问题知识库](issues/) — 问题记录与经验沉淀
- [工作报告](reports/) — 周报、月报、半年报归档
```

- [ ] **Step 2: Create requirements overview**

Write `docs/requirements/index.md`:

```markdown
# 需求知识库

按模块整理的产品需求文档。

## 模块列表

| 模块 | 需求数 | 最近更新 |
|------|--------|----------|
| 用户中心 | - | - |
| 订单系统 | - | - |

> 使用 `python scripts/new_requirement.py "需求标题" --module <模块名>` 快速创建新需求文档。
```

- [ ] **Step 3: Create requirement template**

Write `docs/requirements/_template.md`:

```markdown
---
status: 规划中
priority: P2
created: {{ date }}
owner:
module: {{ module }}
---

# {{ title }}

## 背景

## 功能描述

## 验收标准

- [ ] 待补充

## 关联文档

- 设计稿:
- 技术方案:

## 变更记录

| 日期 | 变更 |
|------|------|
| {{ date }} | 创建 |
```

- [ ] **Step 4: Create issues overview**

Write `docs/issues/index.md`:

```markdown
# 问题知识库

问题记录、根因分析与经验沉淀。

## 模块列表

| 模块 | 问题数 | 未解决 | 严重问题 |
|------|--------|--------|----------|
| 用户中心 | - | - | - |
| 订单系统 | - | - | - |

> 使用 `python scripts/new_issue.py "问题标题" --module <模块名>` 快速创建新问题文档。
```

- [ ] **Step 5: Create issue template**

Write `docs/issues/_template.md`:

```markdown
---
status: 待排查
severity: S2
created: {{ date }}
module: {{ module }}
tags: []
---

# {{ title }}

## 现象

## 根因

## 解决方案

## 经验教训

## 相关需求/问题
```

- [ ] **Step 6: Verify MkDocs serves the site**

Run: `mkdocs serve`
Open: `http://localhost:8000`
Expected: Site loads with navigation, home page content visible

- [ ] **Step 7: Commit**

```bash
git add docs/
git commit -m "feat: add knowledge base structure and document templates"
```

---

### Task 3: Report Jinja2 Templates

**Files:**
- Create: `templates/weekly.j2`
- Create: `templates/monthly.j2`
- Create: `templates/semiannual.j2`

- [ ] **Step 1: Create weekly report template**

Write `templates/weekly.j2`:

```markdown
# 周报 — {{ period }}

## 本周进展

{% for module in modules %}
### {{ module.name }}

| 类型 | 内容 |
|------|------|
| 已完成 | {% for item in module.done %}- {{ item }}{% if not loop.last %}<br>{% endif %}{% else %}-{% endfor %} |
| 下周计划 | {% for item in module.next %}- {{ item }}{% if not loop.last %}<br>{% endif %}{% else %}-{% endfor %} |
| 风险 | {% for item in module.risks %}- {{ item }}{% if not loop.last %}<br>{% endif %}{% else %}无{% endfor %} |

{% endfor %}

## 总结

{{ summary }}
```

- [ ] **Step 2: Create monthly report template**

Write `templates/monthly.j2`:

```markdown
# 月报 — {{ period }}

## 各模块数据总览

| 模块 | 本月完成 | 进行中 | 阻塞 | 问题已解决 | 新增问题 |
|------|----------|--------|------|------------|----------|
{% for module in modules %}| {{ module.name }} | {{ module.completed }} | {{ module.in_progress }} | {{ module.blocked }} | {{ module.issues_resolved }} | {{ module.issues_new }} |
{% endfor %}

## 各模块详情

{% for module in modules %}
### {{ module.name }}

**本月亮点：**
{% for h in module.highlights %}
- {{ h }}
{% else %}
- 无
{% endfor %}

**下月计划：**
{% for p in module.next_month %}
- {{ p }}
{% else %}
- 无
{% endfor %}

{% endfor %}

## 总结

{{ summary }}
```

- [ ] **Step 3: Create semiannual report template**

Write `templates/semiannual.j2`:

```markdown
# 半年报 — {{ period }}

## 各模块总览

| 模块 | 需求总数 | 问题总数 | 里程碑 |
|------|----------|----------|--------|
{% for module in modules %}| {{ module.name }} | {{ module.total_requirements }} | {{ module.total_issues }} | {% for m in module.milestone %}{{ m }}{% if not loop.last %}, {% endif %}{% else %}-{% endfor %} |
{% endfor %}

## 各模块详情

{% for module in modules %}
### {{ module.name }}

**趋势分析：** {{ module.trend }}

**关键里程碑：**
{% for m in module.milestone %}
- {{ m }}
{% else %}
- 无
{% endfor %}

{% endfor %}

## 总结

{{ summary }}
```

- [ ] **Step 4: Commit**

```bash
git add templates/
git commit -m "feat: add Jinja2 report templates for weekly, monthly, semiannual"
```

---

### Task 4: Report Data Templates

**Files:**
- Create: `data/weekly/_template.yaml`
- Create: `data/monthly/_template.yaml`
- Create: `data/semiannual/_template.yaml`

- [ ] **Step 1: Create weekly data template**

Write `data/weekly/_template.yaml`:

```yaml
period: ""
modules:
  - name: ""
    done: []
    next: []
    risks: []
summary: ""
```

- [ ] **Step 2: Create monthly data template**

Write `data/monthly/_template.yaml`:

```yaml
period: ""
modules:
  - name: ""
    completed: 0
    in_progress: 0
    blocked: 0
    issues_resolved: 0
    issues_new: 0
    highlights: []
    next_month: []
summary: ""
```

- [ ] **Step 3: Create semiannual data template**

Write `data/semiannual/_template.yaml`:

```yaml
period: ""
modules:
  - name: ""
    total_requirements: 0
    total_issues: 0
    milestone: []
    trend: ""
summary: ""
```

- [ ] **Step 4: Commit**

```bash
git add data/
git commit -m "feat: add YAML data templates for reports"
```

---

### Task 5: Report Generation Script

**Files:**
- Create: `scripts/report.py`

- [ ] **Step 1: Create report.py**

Write `scripts/report.py`:

```python
#!/usr/bin/env python3
"""Report generation CLI.

Usage:
    python scripts/report.py weekly 2026-W22
    python scripts/report.py monthly 2026-05
    python scripts/report.py semiannual 2026-H1
    python scripts/report.py weekly 2026-W22 --pdf
"""
import argparse
import sys
from pathlib import Path
from datetime import date

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "docs" / "reports"

TYPE_MAP = {
    "weekly": "weekly",
    "monthly": "monthly",
    "semiannual": "semiannual",
}


def main():
    parser = argparse.ArgumentParser(description="Generate a report from YAML data + Jinja2 template.")
    parser.add_argument("type", choices=["weekly", "monthly", "semiannual"], help="Report type")
    parser.add_argument("period", help="Period identifier, e.g. 2026-W22, 2026-05, 2026-H1")
    parser.add_argument("--pdf", action="store_true", help="Also export to PDF")
    args = parser.parse_args()

    report_type = args.type
    period = args.period

    data_file = DATA_DIR / report_type / f"{period}.yaml"
    if not data_file.exists():
        print(f"Error: data file not found: {data_file}", file=sys.stderr)
        print(f"  Copy the template: cp data/{report_type}/_template.yaml data/{report_type}/{period}.yaml", file=sys.stderr)
        sys.exit(1)

    with open(data_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template(f"{report_type}.j2")
    output = template.render(**data, generated_at=str(date.today()))

    output_dir = OUTPUT_DIR / report_type
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{period}.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"Generated: {output_file}")

    if args.pdf:
        from scripts.export_pdf import md_to_pdf
        pdf_path = md_to_pdf(output_file)
        print(f"PDF exported: {pdf_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test with a sample data file**

First copy template and fill in sample data:

```bash
cp data/weekly/_template.yaml data/weekly/2026-W22.yaml
```

Edit `data/weekly/2026-W22.yaml`:

```yaml
period: "2026年第22周 (5/25 - 5/29)"
modules:
  - name: "用户中心"
    done: ["登录页重构完成"]
    next: ["个人设置页开发"]
    risks: []
  - name: "订单系统"
    done: ["退款流程优化上线"]
    next: ["批量发货功能"]
    risks: ["物流接口延迟"]
summary: "本周整体进度正常"
```

Run: `python scripts/report.py weekly 2026-W22`
Expected: `Generated: docs/reports/weekly/2026-W22.md`

- [ ] **Step 3: Verify generated report content**

Read `docs/reports/weekly/2026-W22.md` — should contain the rendered markdown with the sample data filled in.

- [ ] **Step 4: Commit**

```bash
git add scripts/report.py data/weekly/2026-W22.yaml docs/reports/weekly/2026-W22.md
git commit -m "feat: add report generation script with sample weekly report"
```

---

### Task 6: Scaffold Scripts

**Files:**
- Create: `scripts/new_requirement.py`
- Create: `scripts/new_issue.py`

- [ ] **Step 1: Create new_requirement.py**

Write `scripts/new_requirement.py`:

```python
#!/usr/bin/env python3
"""Create a new requirement document from template.

Usage:
    python scripts/new_requirement.py "SSO单点登录" --module user-center
"""
import argparse
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "requirements" / "_template.md"
REQUIREMENTS_DIR = ROOT / "docs" / "requirements"


def slugify(title):
    import re
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug.strip("-")


def main():
    parser = argparse.ArgumentParser(description="Create a new requirement document.")
    parser.add_argument("title", help="Requirement title")
    parser.add_argument("--module", required=True, help="Module name, e.g. user-center")
    parser.add_argument("--priority", default="P2", choices=["P0", "P1", "P2", "P3"])
    parser.add_argument("--status", default="规划中", choices=["规划中", "开发中", "已上线", "已废弃"])
    parser.add_argument("--owner", default="")
    args = parser.parse_args()

    today = str(date.today())
    filename = f"{today}-{slugify(args.title)}.md"
    module_dir = REQUIREMENTS_DIR / args.module
    module_dir.mkdir(parents=True, exist_ok=True)

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("{{ title }}", args.title)
    content = content.replace("{{ module }}", args.module)
    content = content.replace("{{ date }}", today)
    content = content.replace("status: 规划中", f"status: {args.status}")
    content = content.replace("priority: P2", f"priority: {args.priority}")
    if args.owner:
        content = content.replace("owner:", f"owner: {args.owner}")

    output_path = module_dir / filename
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Update module index if it doesn't exist
    module_index = module_dir / "index.md"
    if not module_index.exists():
        with open(module_index, "w", encoding="utf-8") as f:
            f.write(f"# {args.module}\n\n")

    print(f"Created: {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create new_issue.py**

Write `scripts/new_issue.py`:

```python
#!/usr/bin/env python3
"""Create a new issue document from template.

Usage:
    python scripts/new_issue.py "支付回调超时" --module order-system --severity S1
"""
import argparse
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "issues" / "_template.md"
ISSUES_DIR = ROOT / "docs" / "issues"


def slugify(title):
    import re
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug.strip("-")


def main():
    parser = argparse.ArgumentParser(description="Create a new issue document.")
    parser.add_argument("title", help="Issue title")
    parser.add_argument("--module", required=True, help="Module name, e.g. order-system")
    parser.add_argument("--severity", default="S2", choices=["S0", "S1", "S2", "S3"])
    parser.add_argument("--status", default="待排查", choices=["待排查", "处理中", "已解决", "已关闭"])
    args = parser.parse_args()

    today = str(date.today())
    filename = f"{today}-{slugify(args.title)}.md"
    module_dir = ISSUES_DIR / args.module
    module_dir.mkdir(parents=True, exist_ok=True)

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("{{ title }}", args.title)
    content = content.replace("{{ module }}", args.module)
    content = content.replace("{{ date }}", today)
    content = content.replace("status: 待排查", f"status: {args.status}")
    content = content.replace("severity: S2", f"severity: {args.severity}")

    output_path = module_dir / filename
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    module_index = module_dir / "index.md"
    if not module_index.exists():
        with open(module_index, "w", encoding="utf-8") as f:
            f.write(f"# {args.module}\n\n")

    print(f"Created: {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Test scaffold scripts**

```bash
python scripts/new_requirement.py "SSO单点登录" --module user-center --priority P0
python scripts/new_issue.py "支付回调超时" --module order-system --severity S1
```

Expected output: Two files created in respective module directories.

Verify:
- `docs/requirements/user-center/2026-05-27-sso-dan-dian-deng-lu.md` exists with correct frontmatter
- `docs/issues/order-system/2026-05-27-zhi-fu-hui-tiao-chao-shi.md` exists with correct frontmatter

- [ ] **Step 4: Commit**

```bash
git add scripts/new_requirement.py scripts/new_issue.py docs/requirements/user-center/ docs/issues/order-system/
git commit -m "feat: add scaffold scripts for requirements and issues"
```

---

### Task 7: PDF Export

**Files:**
- Create: `templates/report-base.css`
- Create: `scripts/export_pdf.py`

- [ ] **Step 1: Create PDF stylesheet**

Write `templates/report-base.css`:

```css
@page {
  size: A4;
  margin: 2cm;
  @top-center {
    content: element(pageHeader);
  }
}

body {
  font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  font-size: 12pt;
  line-height: 1.8;
  color: #333;
}

h1 { font-size: 20pt; margin-top: 0; border-bottom: 2px solid #4051b5; padding-bottom: 8px; }
h2 { font-size: 16pt; margin-top: 24pt; color: #4051b5; }
h3 { font-size: 14pt; margin-top: 20pt; }

table {
  width: 100%;
  border-collapse: collapse;
  margin: 12pt 0;
}
th, td {
  border: 1px solid #ddd;
  padding: 6pt 10pt;
  text-align: left;
}
th { background-color: #f5f5f5; font-weight: bold; }

code { background: #f5f5f5; padding: 2px 4px; border-radius: 3px; }
```

- [ ] **Step 2: Create export_pdf.py**

Write `scripts/export_pdf.py`:

```python
#!/usr/bin/env python3
"""Export a Markdown file to PDF using weasyprint.

Usage:
    python scripts/export_pdf.py docs/reports/weekly/2026-W22.md
"""
import argparse
import sys
from pathlib import Path

import markdown
from weasyprint import HTML

ROOT = Path(__file__).resolve().parent.parent
CSS_FILE = ROOT / "templates" / "report-base.css"


def md_to_pdf(md_path):
    md_path = Path(md_path)
    if not md_path.exists():
        print(f"Error: file not found: {md_path}", file=sys.stderr)
        sys.exit(1)

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    md_ext = markdown.Markdown(extensions=["tables", "fenced_code", "toc"])
    html_body = md_ext.convert(md_content)

    html_doc = f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="utf-8"><title>Report</title></head>
<body>{html_body}</body>
</html>"""

    pdf_path = md_path.with_suffix(".pdf")
    HTML(string=html_doc).write_pdf(str(pdf_path), stylesheets=[str(CSS_FILE)])
    return pdf_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Markdown to PDF.")
    parser.add_argument("path", help="Path to .md file")
    args = parser.parse_args()
    result = md_to_pdf(args.path)
    print(f"PDF exported: {result}")
```

- [ ] **Step 3: Update requirements.txt with markdown dependency**

Edit `requirements.txt` to add `markdown>=3.4`:

```bash
echo "markdown>=3.4" >> requirements.txt
pip install markdown
```

- [ ] **Step 4: Test PDF export**

```bash
python scripts/export_pdf.py docs/reports/weekly/2026-W22.md
```

Expected: `PDF exported: docs/reports/weekly/2026-W22.pdf`

- [ ] **Step 5: Commit**

```bash
git add templates/report-base.css scripts/export_pdf.py requirements.txt
git commit -m "feat: add PDF export with weasyprint"
```

---

### Task 8: End-to-End Verification

- [ ] **Step 1: Verify MkDocs site serves all content**

```bash
mkdocs serve
```

Open `http://localhost:8000` and verify:
- Home page loads
- Requirements section navigable
- Issues section navigable
- Reports → Weekly shows the sample 2026-W22 report

- [ ] **Step 2: Verify full report workflow**

```bash
# Create a new monthly data file from template
cp data/monthly/_template.yaml data/monthly/2026-05.yaml
# Edit with sample data, then:
python scripts/report.py monthly 2026-05
# Should generate docs/reports/monthly/2026-05.md
```

- [ ] **Step 3: Verify scaffold → edit → serve cycle**

```bash
python scripts/new_requirement.py "测试需求" --module user-center
# Verify file created, then mkdocs serve to see it in navigation
```

- [ ] **Step 4: Verify PDF export**

```bash
python scripts/export_pdf.py docs/reports/monthly/2026-05.md
# Verify PDF is generated and opens correctly
```

- [ ] **Step 5: Commit**

```bash
git add data/monthly/2026-05.yaml docs/reports/monthly/2026-05.md
git commit -m "feat: add sample monthly report and verify workflow"
```

---

## Self-Review

### 1. Spec Coverage

| Spec Section | Task |
|---|---|
| Directory structure | Task 1, 2, 3, 4 |
| Report data format (YAML) | Task 4 |
| Report Jinja2 templates | Task 3 |
| Report generation CLI | Task 5 |
| Knowledge base doc structure | Task 2 |
| Requirement template | Task 2 (Step 3) |
| Issue template | Task 2 (Step 5) |
| Scaffold scripts | Task 6 |
| PDF export | Task 7 |
| MkDocs site config | Task 1 (Step 3) |
| Site navigation | Task 1 (Step 3) |

### 2. Placeholder Scan

No TBD, TODO, or incomplete sections found. All code is complete with actual implementations.

### 3. Type Consistency

- All file paths consistent across tasks
- Template variables (`{{ title }}`, `{{ module }}`, `{{ date }}`) match between templates (Task 2) and scaffold scripts (Task 6)
- YAML field names match between data templates (Task 4) and Jinja2 templates (Task 3)
- `report.py` imports `md_to_pdf` from `scripts.export_pdf` — the function exists in Task 7
