#!/usr/bin/env python3
"""Export a Markdown file to PDF using weasyprint.

Usage:
    python scripts/export_pdf.py docs/reports/weekly/2026-W22.md
"""
import argparse
import ctypes
import os
import sys
from pathlib import Path

# Preload system libraries for weasyprint on macOS.
# SIP strips DYLD_* from system Python, so cffi.dlopen() can't find
# Homebrew-installed libs. We monkey-patch cffi's dlopen to try
# absolute paths from common Homebrew prefixes first.
if sys.platform == "darwin":
    _BREW_PREFIXES = [
        "/opt/homebrew/lib",
        "/usr/local/lib",
    ]
    _orig_dlopen = None

    def _patched_dlopen(ffi_self, name, flags=0):
        if os.path.sep not in name:
            for prefix in _BREW_PREFIXES:
                candidate = os.path.join(prefix, name)
                if os.path.exists(candidate):
                    try:
                        return _orig_dlopen(ffi_self, candidate, flags)
                    except OSError:
                        continue
        return _orig_dlopen(ffi_self, name, flags)

    import cffi
    _orig_dlopen = cffi.FFI.dlopen
    cffi.FFI.dlopen = _patched_dlopen

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
