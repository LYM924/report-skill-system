#!/usr/bin/env python3
"""
数据迁移脚本：从文件系统导入结构化数据到 SQLite 数据库。

用法:
  python3 src/server/migrate_to_db.py           # 执行迁移
  python3 src/server/migrate_to_db.py --dry-run  # 预览，不写入
"""

import json
import re
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent.parent  # knowledge-base/
DATA_DIR = PROJECT_DIR / "data"
CONFIG_DIR = PROJECT_DIR / "config"
RUNTIME_DIR = PROJECT_DIR / "runtime"
DB_PATH = RUNTIME_DIR / "knowledge.db"


def init_db(db):
    """初始化数据库表结构"""
    schema_file = CONFIG_DIR / "schema.sql"
    if schema_file.exists():
        db.executescript(schema_file.read_text(encoding="utf-8"))
        db.commit()
        print("✅ Schema 已初始化")
    else:
        print("⚠️  schema.sql 未找到，跳过初始化")


def migrate_modules(db, dry_run=False):
    """从 data/modules/*.md 导入模块数据"""
    print("\n📦 迁移模块数据...")
    modules_dir = DATA_DIR / "modules"
    if not modules_dir.exists():
        print("  ⚠️  modules 目录不存在")
        return

    count = 0
    for md_file in sorted(modules_dir.rglob("*.md")):
        if md_file.name in ("SKILL.md", "zlb_menu.md"):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not fm_match:
            continue
        fm = fm_match.group(1)

        def get_field(name, default=""):
            # 先尝试顶层字段
            m = re.search(rf"^{name}:\s*(.+)$", fm, re.MULTILINE)
            if m:
                return m.group(1).strip()
            # 再尝试 metadata 下的嵌套字段
            m = re.search(rf"^\s+{name}:\s*(.+)$", fm, re.MULTILINE)
            if m:
                return m.group(1).strip()
            return default

        # 模块名来自文件名
        module_name = md_file.stem

        # 获取或创建部门
        dept_name = get_field("department", "")
        dept_id = None
        if dept_name:
            row = db.execute("SELECT id FROM departments WHERE name = ?", (dept_name,)).fetchone()
            if row:
                dept_id = row[0]

        # 获取或创建产品线
        product_line_name = get_field("product_line", "")
        product_line_id = None
        if product_line_name:
            db.execute("INSERT OR IGNORE INTO product_lines (name) VALUES (?)", (product_line_name,))
            row = db.execute("SELECT id FROM product_lines WHERE name = ?", (product_line_name,)).fetchone()
            if row:
                product_line_id = row[0]

        # 获取或创建产品
        product_name = get_field("product", "")
        product_id = None
        if product_name:
            db.execute(
                "INSERT OR IGNORE INTO products (name, product_line_id) VALUES (?, ?)",
                (product_name, product_line_id)
            )
            row = db.execute("SELECT id FROM products WHERE name = ?", (product_name,)).fetchone()
            if row:
                product_id = row[0]

        # 模块描述
        description = get_field("description", "")
        body = text[fm_match.end():]
        if not description:
            # 从正文 key 取
            desc_m = re.search(r"## 关键词\s*\n(.+?)(?:\n##|\n\Z)", body, re.DOTALL)
            if desc_m:
                description = desc_m.group(1).strip()

        if not dry_run:
            db.execute(
                """INSERT INTO modules (name, department_id, product_id, dev_owner, module_owner,
                   appendix, business_domain, description, path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (module_name, dept_id, product_id,
                 get_field("dev_owner", ""), get_field("module_owner", ""),
                 get_field("appendix", ""), get_field("business_domain", ""),
                 description, str(md_file.relative_to(PROJECT_DIR)))
            )
            module_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            # 菜单映射
            menu_section = re.search(r"## 菜单映射\s*\n(.+?)(?:\n##|\n\Z)", body, re.DOTALL)
            if menu_section:
                for line in menu_section.group(1).strip().split("\n"):
                    if line.startswith("|") and not line.startswith("|--") and not line.startswith("| 一级"):
                        cells = [c.strip() for c in line.split("|")[1:-1]]
                        if len(cells) >= 3:
                            db.execute(
                                "INSERT INTO module_menus (module_id, level1, level2, level3) VALUES (?, ?, ?, ?)",
                                (module_id, cells[0] if len(cells) > 0 else "",
                                 cells[1] if len(cells) > 1 else "",
                                 cells[2] if len(cells) > 2 else "")
                            )
                        elif len(cells) == 2:
                            db.execute(
                                "INSERT INTO module_menus (module_id, level1, level2) VALUES (?, ?, ?)",
                                (module_id, cells[0], cells[1])
                            )
                        elif len(cells) == 1 and cells[0] and cells[0] != "-":
                            db.execute(
                                "INSERT INTO module_menus (module_id, level1) VALUES (?, ?)",
                                (module_id, cells[0])
                            )

        count += 1

    if not dry_run:
        db.commit()
    print(f"  {'[DRY RUN] ' if dry_run else ''}导入 {count} 个模块")


def migrate_keywords(db, dry_run=False):
    """从 config/关键词索引.md 导入关键词数据"""
    print("\n📝 迁移关键词索引...")
    keyword_file = CONFIG_DIR / "keyword_index.md"
    if not keyword_file.exists():
        print("  ⚠️  关键词索引.md 未找到")
        return

    text = keyword_file.read_text(encoding="utf-8")
    current_dept = ""
    current_domain = ""
    count = 0

    for line in text.split("\n"):
        dept_match = re.match(r"^###\s+(.+?)\s*[·•]\s*(.+)$", line)
        if dept_match:
            current_dept = dept_match.group(1).strip()
            current_domain = dept_match.group(2).strip()
            continue

        if line.startswith("|") and not line.startswith("|--") and not line.startswith("| 关键词"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 5 and cells[0] and cells[1]:
                keyword = cells[0]
                module_name = cells[1]
                if len(cells) >= 7:
                    dept = cells[3] if cells[3] else current_dept
                    domain = cells[4] if cells[4] else current_domain
                    kb_path = cells[5] if len(cells) > 5 else ""
                    note = cells[6] if len(cells) > 6 else ""
                else:
                    dept = cells[2] if len(cells) > 2 and cells[2] else current_dept
                    domain = cells[3] if len(cells) > 3 and cells[3] else current_domain
                    kb_path = cells[4] if len(cells) > 4 and cells[4] else ""
                    note = cells[5] if len(cells) > 5 else ""

                # 查找 module_id
                module_id = None
                if module_name:
                    row = db.execute("SELECT id FROM modules WHERE name = ?", (module_name,)).fetchone()
                    if row:
                        module_id = row[0]

                if not dry_run:
                    db.execute(
                        "INSERT INTO keywords (keyword, module_id, department, domain, kb_path, note) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (keyword, module_id, dept, domain, kb_path, note)
                    )
                count += 1

    if not dry_run:
        db.commit()
    print(f"  {'[DRY RUN] ' if dry_run else ''}导入 {count} 条关键词")


def migrate_synonyms(db, dry_run=False):
    """从 config/synonyms.json 导入同义词"""
    print("\n📖 迁移同义词...")
    syn_file = CONFIG_DIR / "synonyms.json"
    if not syn_file.exists():
        print("  ⚠️  synonyms.json 未找到")
        return

    with open(syn_file, "r", encoding="utf-8") as f:
        synonyms = json.load(f)

    count = 0
    for word, aliases in synonyms.items():
        for alias in aliases:
            if not dry_run:
                db.execute(
                    "INSERT INTO synonyms (word, synonym) VALUES (?, ?)",
                    (word, alias)
                )
            count += 1

    if not dry_run:
        db.commit()
    print(f"  {'[DRY RUN] ' if dry_run else ''}导入 {count} 条同义词 ({len(synonyms)} 个词根)")


def migrate_search_counter(db, dry_run=False):
    """从 runtime/search_counter.json 导入搜索统计"""
    print("\n📊 迁移搜索统计...")
    counter_file = RUNTIME_DIR / "search_counter.json"
    if not counter_file.exists():
        print("  ⚠️  search_counter.json 未找到")
        return

    with open(counter_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for key, value in data.items():
        if isinstance(value, (int, float)):
            if not dry_run:
                db.execute(
                    "INSERT OR REPLACE INTO search_counter (key, value) VALUES (?, ?)",
                    (key, int(value))
                )
            count += 1

    if not dry_run:
        db.commit()
    print(f"  {'[DRY RUN] ' if dry_run else ''}导入 {count} 条统计")


def verify(db):
    """验证迁移结果"""
    print("\n🔍 验证迁移结果:")
    print(f"  部门: {db.execute('SELECT COUNT(*) FROM departments').fetchone()[0]}")
    print(f"  产品线: {db.execute('SELECT COUNT(*) FROM product_lines').fetchone()[0]}")
    print(f"  产品: {db.execute('SELECT COUNT(*) FROM products').fetchone()[0]}")
    print(f"  模块: {db.execute('SELECT COUNT(*) FROM modules').fetchone()[0]}")
    print(f"  菜单: {db.execute('SELECT COUNT(*) FROM module_menus').fetchone()[0]}")
    print(f"  关键词: {db.execute('SELECT COUNT(*) FROM keywords').fetchone()[0]}")
    print(f"  同义词: {db.execute('SELECT COUNT(*) FROM synonyms').fetchone()[0]}")
    print(f"  统计: {db.execute('SELECT COUNT(*) FROM search_counter').fetchone()[0]}")


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"{'[DRY RUN] ' if dry_run else ''}数据迁移: 文件 → SQLite")
    print(f"数据库: {DB_PATH}")

    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row

    init_db(db)
    migrate_modules(db, dry_run)
    migrate_keywords(db, dry_run)
    migrate_synonyms(db, dry_run)
    migrate_search_counter(db, dry_run)

    if not dry_run:
        verify(db)

    db.close()

    if dry_run:
        print("\n💡 使用 python3 src/server/migrate_to_db.py 执行实际迁移")
    else:
        print(f"\n✅ 迁移完成！数据库: {DB_PATH}")


if __name__ == "__main__":
    main()