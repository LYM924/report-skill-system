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
