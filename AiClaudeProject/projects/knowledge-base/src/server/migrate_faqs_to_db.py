#!/usr/bin/env python3
"""FAQ 数据库迁移脚本 - 将 data/faq/ 下的 .md 文件导入 SQLite faqs 表

用法:
    python3 migrate_faqs_to_db.py            # 迁移（幂等）
    python3 migrate_faqs_to_db.py --dry-run  # 预览模式，不实际写入
    python3 migrate_faqs_to_db.py --force    # 强制重新导入全部
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent.parent  # src/server/ -> knowledge-base/
DATA_DIR = PROJECT_DIR / "data"
RUNTIME_DIR = PROJECT_DIR / "runtime"
DB_PATH = RUNTIME_DIR / "knowledge.db"

import sqlite3


def parse_faq(text, rel_path):
    """解析 FAQ markdown 文件，返回新字段结构"""
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return None
    fm = fm_match.group(1)
    body = text[fm_match.end():]

    def get_field(name, default=""):
        m = re.search(rf"^{name}:\s*(.+)$", fm, re.MULTILINE)
        return m.group(1).strip().strip('"').strip("'") if m else default

    tags = get_field("keywords", "[]")
    if tags.startswith("["):
        try:
            tags = json.loads(tags)
        except Exception:
            # 兼容不带引号的格式: [发票, 开票, 失败]
            tags = [k.strip().strip("'\"") for k in tags.strip("[]").split(",") if k.strip()]
    else:
        tags = [k.strip() for k in tags.split(",") if k.strip()]

    old_status = get_field("status", "active")
    status_map = {"active": 1, "outdated": 2, "deprecated": 3, "draft": 0}
    status_int = status_map.get(old_status, 1)

    q_match = re.search(r'##\s*问题描述\s*\n+(.+?)(?=\n##|\n---|\Z)', body, re.DOTALL)
    faq_question = q_match.group(1).strip()[:500] if q_match else get_field("title", "")

    return {
        "faq_code": get_field("id"),
        "faq_title": get_field("title"),
        "faq_question": faq_question,
        "faq_answer": body.strip(),
        "content": text,
        "dept": get_field("dept"),
        "sub_module": get_field("sub_module"),
        "module": get_field("module"),
        "scene": get_field("scene"),
        "tags": tags,
        "status": status_int,
        "source_file_name": str(rel_path).split("/")[-1] if rel_path else "",
        "file_path": str(rel_path),
        "version_from": get_field("version_from"),
        "create_time": get_field("created"),
        "update_time": get_field("reviewed"),
    }


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    force = "--force" in args

    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row

    # 确保表存在（先删旧表，再建新表）
    schema_file = PROJECT_DIR / "config" / "schema.sql"
    db.execute("DROP TABLE IF EXISTS faqs")
    db.execute("DROP TABLE IF EXISTS faq_categories")
    if schema_file.exists():
        db.executescript(schema_file.read_text(encoding="utf-8"))
        db.commit()

    # 扫目录
    faq_dir = DATA_DIR / "faq"
    if not faq_dir.exists():
        print("FAQ 目录不存在")
        return

    total = 0
    imported = 0
    skipped = 0
    updated = 0

    for md_file in sorted(faq_dir.rglob("*.md")):
        if md_file.name in ("INDEX.md", "TEMPLATE.md"):
            continue
        total += 1
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  ⚠ 无法读取: {md_file.name} - {e}")
            continue

        rel_path = md_file.relative_to(PROJECT_DIR)
        faq = parse_faq(text, rel_path)
        if not faq or not faq["faq_code"]:
            print(f"  ⚠ 无法解析: {md_file.name}")
            continue

        faq_code = faq["faq_code"]
        existing = db.execute("SELECT id FROM faqs WHERE faq_code = ?", (faq_code,)).fetchone()

        if existing and not force:
            skipped += 1
            continue

        if dry_run:
            action = "UPDATE" if existing else "INSERT"
            print(f"  [{action}] {faq_code} | {faq['faq_title']} | {faq['dept']}/{faq['sub_module']}")
            continue

        db.execute("""
            INSERT OR REPLACE INTO faqs (faq_code, faq_title, faq_question, faq_answer, content,
            dept, sub_module, module, scene, tags, status, source_file_name, file_path,
            version_from, create_time, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            faq_code, faq["faq_title"], faq["faq_question"], faq["faq_answer"], faq["content"],
            faq["dept"], faq["sub_module"], faq["module"], faq["scene"],
            json.dumps(faq["tags"], ensure_ascii=False) if faq["tags"] else "[]",
            faq["status"], faq["source_file_name"], faq["file_path"],
            faq["version_from"], faq["create_time"], faq["update_time"],
        ))

        if existing:
            updated += 1
            print(f"  ✏  {faq_code} | {faq['faq_title']}")
        else:
            imported += 1
            print(f"  ✅ {faq_code} | {faq['faq_title']}")

    db.commit()

    # 自动将 FAQ 关键词加入 jieba 自定义词典
    try:
        import jieba, logging
        jieba.setLogLevel(logging.WARNING)
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT DISTINCT tags FROM faqs WHERE is_deleted = 0").fetchall()
        added = 0
        for row in rows:
            try:
                tags = json.loads(row["tags"])
                for tag in tags:
                    if len(tag) >= 2 and not any(c in tag for c in '，。；：！？、'):
                        jieba.add_word(tag, freq=80, tag='n')
                        added += 1
            except Exception:
                pass
        if added > 0:
            print(f"  📝 已将 {added} 个 FAQ 关键词加入 jieba 词典")
    except Exception:
        pass

    # 更新缓存版本，触发下次服务启动时重建索引
    db.execute("INSERT OR REPLACE INTO search_counter (key, value) VALUES ('cache_version', ?)",
              (int(__import__('time').time()),))
    db.commit()

    # 自动触发服务端重建索引（如果服务在运行）
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:8000/api/rebuild", timeout=5)
        print("  🔄 已触发搜索服务重建索引")
    except Exception:
        pass  # 服务未运行，下次启动时自动重建

    # 验证
    count = db.execute("SELECT COUNT(*) as cnt FROM faqs").fetchone()["cnt"]
    db.close()

    if dry_run:
        print(f"\n📊 预览: 共 {total} 个文件，{skipped} 个已存在，{total - skipped} 个待导入")
    else:
        print(f"\n📊 迁移完成: {total} 个文件 → DB {count} 条记录")
        print(f"   新增: {imported} | 更新: {updated} | 跳过: {skipped}")
        print(f"   数据库: {DB_PATH}")


if __name__ == "__main__":
    main()