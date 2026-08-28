#!/usr/bin/env python3
"""
Confluence 周报数据同步脚本

从 Confluence 周报页面拉取数据，保存为 .md 文件到 data/reports/ 目录。

用法:
  python3 src/server/sync_confluence_reports.py           # 拉取所有周报
  python3 src/server/sync_confluence_reports.py --page 252657891  # 指定页面ID
  python3 src/server/sync_confluence_reports.py --dry-run  # 预览，不写入

环境变量（在 .env 或 settings.json 中配置）:
  CONFLUENCE_BASE_URL  - Confluence 地址（默认 https://cf.cai-inc.com）
  CONFLUENCE_TOKEN     - Confluence API Token
  CONFLUENCE_SPACE     - Confluence 空间（默认 FCSY）
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent.parent  # knowledge-base/
DATA_DIR = PROJECT_DIR / "data"
REPORTS_DIR = DATA_DIR / "reports" / "周报"
RUNTIME_DIR = PROJECT_DIR / "runtime"
DB_PATH = RUNTIME_DIR / "knowledge.db"

# 从环境变量读取配置
CONFLUENCE_BASE = os.environ.get("CONFLUENCE_BASE_URL", "https://cf.cai-inc.com")
CONFLUENCE_TOKEN = os.environ.get("CONFLUENCE_TOKEN", "")
CONFLUENCE_SPACE = os.environ.get("CONFLUENCE_SPACE", "FCSY")

# 周报页面父级ID（从 settings.local.json 读取）
WEEKLY_REPORT_PARENT = os.environ.get("CONFLUENCE_WEEKLY_REPORT_PARENT", "252657891")


def fetch_confluence_page(page_id):
    """获取 Confluence 页面内容"""
    url = f"{CONFLUENCE_BASE}/rest/api/content/{page_id}?expand=body.storage,children.page,version"
    req = Request(url)
    req.add_header("Authorization", f"Bearer {CONFLUENCE_TOKEN}")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ❌ 获取页面失败: {e}")
        return None


def fetch_child_pages(parent_id):
    """获取子页面列表"""
    url = f"{CONFLUENCE_BASE}/rest/api/content/{parent_id}/child/page?limit=50&expand=version"
    req = Request(url)
    req.add_header("Authorization", f"Bearer {CONFLUENCE_TOKEN}")

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("results", [])
    except Exception as e:
        print(f"  ❌ 获取子页面失败: {e}")
        return []


def confluence_html_to_md(html):
    """简单的 Confluence HTML → Markdown 转换"""
    # 移除 HTML 标签
    text = re.sub(r"<[^>]+>", "", html)
    # 解码 HTML 实体
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # 清理多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def save_to_db(title, content, week, year, category, path):
    """保存到数据库"""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row

    # 检查是否已存在
    existing = db.execute("SELECT id FROM reports WHERE path = ?", (path,)).fetchone()
    if existing:
        db.execute("""
            UPDATE reports SET title=?, content=?, week=?, year=?, category=?, dept_summary=?
            WHERE id=?
        """, (title, content, week, year, category, content[:500], existing["id"]))
    else:
        db.execute("""
            INSERT INTO reports (title, week, year, category, content, path, dept_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, week, year, category, content, path, content[:500]))

    db.commit()
    db.close()


def save_to_file(title, content, week, year):
    """保存为 .md 文件"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{year}-W{week}-技术支持周报.md"
    filepath = REPORTS_DIR / filename
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def main():
    dry_run = "--dry-run" in sys.argv
    page_id = None
    for arg in sys.argv:
        if arg.startswith("--page="):
            page_id = arg.split("=")[1]
    if not page_id:
        page_id = WEEKLY_REPORT_PARENT

    if not CONFLUENCE_TOKEN:
        print("❌ 请设置 CONFLUENCE_TOKEN 环境变量")
        print("   或在 .claude/settings.local.json 中配置")
        return

    print(f"📡 连接 Confluence: {CONFLUENCE_BASE}")
    print(f"  父页面: {page_id}")

    # 获取子页面列表
    children = fetch_child_pages(page_id)
    print(f"  子页面: {len(children)} 个")

    count = 0
    for child in children:
        title = child["title"]
        child_id = child["id"]

        # 提取周次
        week = ""
        year = datetime.now().year
        m = re.search(r"W(\d+)", title)
        if m:
            week = m.group(1)
        m = re.search(r"(\d{4})年", title)
        if m:
            year = int(m.group(1))

        category = "周报"
        if "月报" in title:
            category = "月报"
        elif "年度" in title:
            category = "年度报表"

        print(f"  [{category}] {title} (W{week})")

        if not dry_run:
            # 获取完整内容
            page = fetch_confluence_page(child_id)
            if page and "body" in page:
                html = page["body"]["storage"]["value"]
                content = confluence_html_to_md(html)
                content = f"# {title}\n\n{content}"

                # 保存到文件
                filepath = save_to_file(title, content, week, year)
                rel_path = f"data/reports/周报/{year}-W{week}-技术支持周报.md"

                # 保存到数据库
                save_to_db(title, content, week, year, category, rel_path)
                count += 1

    if dry_run:
        print(f"\n💡 预览完成，共 {count} 个报表")
        print("   使用 python3 src/server/sync_confluence_reports.py 执行实际同步")
    else:
        print(f"\n✅ 同步完成，共 {count} 个报表")
        print(f"   文件: {REPORTS_DIR}")
        print(f"   数据库: {DB_PATH}")


if __name__ == "__main__":
    main()