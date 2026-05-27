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
