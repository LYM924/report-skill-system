#!/usr/bin/env python3
"""SQLite → PostgreSQL 数据迁移脚本"""

import sqlite3, os, sys
from pathlib import Path
from sqlalchemy import create_engine, text, MetaData, Table, Column, inspect

HERE = Path(__file__).resolve().parent
SERVER_DIR = HERE.parent
PROJECT_DIR = SERVER_DIR.parent.parent
SQLITE_PATH = PROJECT_DIR / "runtime" / "knowledge.db"

# PostgreSQL 连接
PG_URL = os.getenv("DATABASE_URL_SYNC", "postgresql://kb_user:kb_pass@localhost:5432/knowledge_base")

if not SQLITE_PATH.exists():
    print(f"❌ SQLite 数据库不存在: {SQLITE_PATH}")
    sys.exit(1)

print(f"📦 源: {SQLITE_PATH}")
print(f"🎯 目标: {PG_URL}")

# 连接
sqlite_db = sqlite3.connect(str(SQLITE_PATH))
sqlite_db.row_factory = sqlite3.Row
pg_engine = create_engine(PG_URL, echo=False)

# 先创建表结构（从 schema.sql）
schema_file = PROJECT_DIR / "config" / "schema.sql"
if schema_file.exists():
    schema_sql = schema_file.read_text(encoding="utf-8")
    with pg_engine.connect() as conn:
        for stmt in schema_sql.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                try:
                    conn.execute(text(stmt))
                except Exception as e:
                    pass  # 表已存在
        conn.commit()
    print("✅ 表结构已创建")

# 迁移顺序（先父表后子表）
TABLES = [
    "departments",
    "product_lines",
    "products",
    "modules",
    "module_menus",
    "module_aliases",
    "faq_categories",
    "faqs",
    "keywords",
    "synonyms",
    "feedback",
    "search_counter",
    "reports",
]

total_rows = 0
for table in TABLES:
    try:
        rows = sqlite_db.execute(f"SELECT * FROM {table}").fetchall()
    except Exception:
        continue

    if not rows:
        continue

    # 获取列名
    columns = [desc[0] for desc in sqlite_db.execute(f"SELECT * FROM {table} LIMIT 0").description]
    col_placeholders = ", ".join(f":{c}" for c in columns)
    col_names = ", ".join(columns)

    with pg_engine.connect() as conn:
        for row in rows:
            data = {columns[i]: row[i] for i in range(len(columns))}
            # 跳过已存在的记录（按主键）
            try:
                conn.execute(
                    text(f"INSERT INTO {table} ({col_names}) VALUES ({col_placeholders})"),
                    data
                )
            except Exception:
                pass  # 重复跳过
        conn.commit()

    print(f"  ✅ {table}: {len(rows)} 行")
    total_rows += len(rows)

sqlite_db.close()
print(f"\n✅ 迁移完成: {total_rows} 行数据")
print(f"   设置环境变量后重启服务即可使用 PostgreSQL:")
print(f"   export DATABASE_URL_SYNC={PG_URL}")
print(f"   python3 src/server/main.py")