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
