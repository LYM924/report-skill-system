#!/usr/bin/env python3
"""
从 产品模块索引_全量.md 导入完整模块数据到 SQLite 数据库。

解析 .md 文件中的层级结构：
  ## 事业部 → ### 二级部门 → #### 产品线,关联部门 → 表格行

用法:
  python3 src/server/import_full_modules.py
  python3 src/server/import_full_modules.py --dry-run
"""

import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent.parent  # knowledge-base/
RUNTIME_DIR = PROJECT_DIR / "runtime"
DB_PATH = RUNTIME_DIR / "knowledge.db"
INDEX_FILE = PROJECT_DIR.parent.parent / "其他文档区" / "产品模块索引_全量.md"


def parse_index(filepath):
    """解析模块索引文件，返回模块列表"""
    text = Path(filepath).read_text(encoding="utf-8")
    modules = []

    current_dept = ""       # 事业部（##）
    current_sub_dept = ""   # 二级部门（###）
    current_product = ""    # 所属产品（#### 中的第一个字段）
    current_product_line = ""  # 隐含在产品线或####中
    current_associated = ""  # 关联部门（#### 中的逗号分隔部分）

    for line in text.split("\n"):
        line = line.strip()

        # ## 事业部
        m = re.match(r"^##\s+(.+)", line)
        if m:
            current_dept = m.group(1).strip()
            continue

        # ### 二级部门（N个模块）
        m = re.match(r"^###\s+(.+?)（\d+个模块）", line)
        if m:
            current_sub_dept = m.group(1).strip()
            continue

        # #### 产品线,关联部门（N个模块）
        m = re.match(r"^####\s+(.+?)（\d+个模块）", line)
        if m:
            parts = m.group(1).strip()
            # 第一个逗号前是产品线，后面是关联部门
            if "," in parts:
                current_product_line = parts.split(",")[0].strip()
                current_associated = parts.split(",", 1)[1].strip()
            else:
                current_product_line = parts.strip()
                current_associated = ""
            continue

        # 表格行
        if line.startswith("|") and not line.startswith("|--") and not line.startswith("| 模块"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 5 and cells[0]:
                # | 模块 | 研发负责人 | 模块负责人 | 所属产品 | 所属产品线 | 说明 |
                module_name = cells[0]
                dev_owner = cells[1] if len(cells) > 1 else ""
                module_owner = cells[2] if len(cells) > 2 else ""
                product = cells[3] if len(cells) > 3 else ""
                product_line = cells[4] if len(cells) > 4 else current_product_line
                description = cells[5] if len(cells) > 5 else ""

                # 如果 product_line 为空，用上一级的
                if not product_line:
                    product_line = current_product_line

                modules.append({
                    "name": module_name,
                    "dept": current_dept,
                    "sub_dept": current_sub_dept,
                    "product": product,
                    "product_line": product_line,
                    "dev_owner": dev_owner,
                    "module_owner": module_owner,
                    "associated_dept": current_associated,
                    "description": description,
                })

    return modules


def update_schema(db):
    """更新数据库表结构，添加新字段"""
    try:
        db.execute("ALTER TABLE modules ADD COLUMN sub_dept TEXT")
    except sqlite3.OperationalError:
        pass  # 字段已存在
    try:
        db.execute("ALTER TABLE modules ADD COLUMN associated_dept TEXT")
    except sqlite3.OperationalError:
        pass

    # 确保 schema.sql 中的部门都存在于 departments 表
    schema_file = PROJECT_DIR / "config" / "schema.sql"
    if schema_file.exists():
        db.executescript(schema_file.read_text(encoding="utf-8"))
        db.commit()


def import_modules(db, modules, dry_run=False):
    """导入模块到数据库"""
    count = 0
    new_depts = set()
    new_lines = set()

    for mod in modules:
        # 获取或创建部门
        dept_name = mod["dept"]
        if dept_name:
            db.execute("INSERT OR IGNORE INTO departments (name) VALUES (?)", (dept_name,))
            row = db.execute("SELECT id FROM departments WHERE name = ?", (dept_name,)).fetchone()
            dept_id = row[0] if row else None
        else:
            dept_id = None

        # 获取或创建产品线
        pl_name = mod["product_line"]
        if pl_name:
            db.execute("INSERT OR IGNORE INTO product_lines (name) VALUES (?)", (pl_name,))
            row = db.execute("SELECT id FROM product_lines WHERE name = ?", (pl_name,)).fetchone()
            pl_id = row[0] if row else None
        else:
            pl_id = None

        # 获取或创建产品
        prod_name = mod["product"]
        if prod_name:
            db.execute(
                "INSERT OR IGNORE INTO products (name, product_line_id) VALUES (?, ?)",
                (prod_name, pl_id)
            )
            row = db.execute("SELECT id FROM products WHERE name = ?", (prod_name,)).fetchone()
            prod_id = row[0] if row else None
        else:
            prod_id = None

        if not dry_run:
            # 检查是否已存在
            existing = db.execute(
                "SELECT id FROM modules WHERE name = ? AND department_id = ?",
                (mod["name"], dept_id)
            ).fetchone()

            if existing:
                # 更新
                db.execute("""
                    UPDATE modules SET
                        product_id = ?, dev_owner = ?, module_owner = ?,
                        sub_dept = ?, associated_dept = ?, description = ?,
                        business_domain = ?
                    WHERE id = ?
                """, (prod_id, mod["dev_owner"], mod["module_owner"],
                      mod["sub_dept"], mod["associated_dept"], mod["description"],
                      mod["sub_dept"], existing[0]))
            else:
                # 插入
                db.execute("""
                    INSERT INTO modules (name, department_id, product_id,
                        dev_owner, module_owner, sub_dept, associated_dept,
                        description, business_domain)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (mod["name"], dept_id, prod_id,
                      mod["dev_owner"], mod["module_owner"],
                      mod["sub_dept"], mod["associated_dept"],
                      mod["description"], mod["sub_dept"]))

        count += 1

    if not dry_run:
        db.commit()

    return count


def main():
    dry_run = "--dry-run" in sys.argv

    if not INDEX_FILE.exists():
        print("❌ 文件不存在: %s" % INDEX_FILE)
        return

    print("%s解析 产品模块索引_全量.md ..." % ("[DRY RUN] " if dry_run else ""))
    modules = parse_index(INDEX_FILE)
    print("  解析到 %d 个模块" % len(modules))

    # 统计
    depts = set(m["dept"] for m in modules)
    print("  涉及 %d 个事业部" % len(depts))
    for d in sorted(depts):
        count = len([m for m in modules if m["dept"] == d])
        print("    %s: %d 个模块" % (d, count))

    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row

    update_schema(db)
    count = import_modules(db, modules, dry_run)

    # 验证
    total = db.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
    with_dept = db.execute("SELECT COUNT(*) FROM modules WHERE department_id IS NOT NULL").fetchone()[0]
    with_prod = db.execute("SELECT COUNT(*) FROM modules WHERE product_id IS NOT NULL").fetchone()[0]
    with_owner = db.execute("SELECT COUNT(*) FROM modules WHERE dev_owner != ''").fetchone()[0]

    print("\n%s导入完成: %d 个模块" % ("[DRY RUN] " if dry_run else "✅", count))
    print("  数据库模块总数: %d" % total)
    print("  关联部门: %d/%d (%.0f%%)" % (with_dept, total, with_dept/total*100 if total else 0))
    print("  关联产品: %d/%d (%.0f%%)" % (with_prod, total, with_prod/total*100 if total else 0))
    print("  有研发负责人: %d/%d (%.0f%%)" % (with_owner, total, with_owner/total*100 if total else 0))

    db.close()

    if dry_run:
        print("\n💡 使用 python3 src/server/import_full_modules.py 执行实际导入")


if __name__ == "__main__":
    main()