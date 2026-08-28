#!/usr/bin/env python3
"""
SQLite → PostgreSQL 全量数据迁移脚本
使用方法: python3 migrate_to_pg.py
前提: PostgreSQL 已启动，schema_v3.sql 已执行
"""

import sqlite3
import psycopg2
import os
from datetime import datetime

PG_URL = "postgresql://zcy1@localhost:5432/knowledge_base"
SQLITE_PATH = os.path.join(os.path.dirname(__file__), "../../../runtime/knowledge.db")

def migrate():
    sqlite = sqlite3.connect(SQLITE_PATH)
    sqlite.row_factory = sqlite3.Row
    pg = psycopg2.connect(PG_URL)
    pg.autocommit = True
    cur = pg.cursor()

    now = datetime.now().isoformat()

    def update_seq(table):
        """更新 PostgreSQL 序列，防止后续 INSERT 冲突"""
        cur.execute(f"SELECT setval('{table}_id_seq', (SELECT COALESCE(MAX(id), 0) FROM {table}))")

    def migrate_table(src_table, dst_table, columns, transform=None):
        """通用迁移：从 SQLite 读，写入 PostgreSQL"""
        cur.execute(f"SELECT COUNT(*) FROM {dst_table}")
        existing = cur.fetchone()[0]
        if existing > 0:
            print(f"  ⏭ {dst_table}: 已有 {existing} 条，跳过")
            return

        rows = sqlite.execute(f"SELECT * FROM {src_table}").fetchall()
        if not rows:
            print(f"  ⏭ {dst_table}: 源表无数据")
            return

        cols_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        insert_sql = f"INSERT INTO {dst_table} ({cols_str}) VALUES ({placeholders})"

        count = 0
        for row in rows:
            vals = []
            for col in columns:
                v = row[col] if col in row.keys() else None
                if transform and col in transform:
                    v = transform[col](v)
                vals.append(v)
            try:
                cur.execute(insert_sql, vals)
                count += 1
            except Exception as e:
                print(f"    跳过 {src_table} id={row['id']}: {e}")

        update_seq(dst_table)
        print(f"  ✅ {dst_table}: {count} 条")

    print("=" * 60)
    print("开始迁移 SQLite → PostgreSQL")
    print("=" * 60)

    # 1. departments (无 FK)
    print("\n📦 第1步: 组织架构")
    migrate_table("departments", "departments",
                  ["id", "name", "parent_id", "level", "code", "dir_name"])

    # 2. product_lines
    migrate_table("product_lines", "product_lines", ["id", "name"])

    # 3. products
    migrate_table("products", "products", ["id", "name", "product_line_id"])

    # 4. modules
    print("\n📦 第2步: 模块")
    migrate_table("modules", "modules",
                  ["id", "name", "department_id", "product_id",
                   "dev_owner", "module_owner", "appendix", "business_domain",
                   "description", "path"])

    # 5. module_menus
    migrate_table("module_menus", "module_menus",
                  ["id", "module_id", "level1", "level2", "level3"])

    # 6. module_aliases
    migrate_table("module_aliases", "module_aliases",
                  ["id", "module_id", "alias"])

    # 7. keywords_v2
    print("\n📦 第3步: 关键词")
    migrate_table("keywords_v2", "keywords_v2",
                  ["id", "keyword", "created_at", "updated_at", "is_deleted"])

    # 8. keyword_mappings
    migrate_table("keyword_mappings", "keyword_mappings",
                  ["id", "keyword_id", "module_id", "department_id",
                   "department", "domain", "kb_path", "note",
                   "created_at", "updated_at", "is_deleted"])

    # 9. synonyms
    print("\n📦 第4步: 同义词")
    migrate_table("synonyms", "synonyms", ["id", "word", "synonym"])

    # 10. faqs
    print("\n📦 第5步: FAQ")
    migrate_table("faqs", "faqs",
                  ["id", "faq_code", "faq_title", "faq_question", "faq_answer",
                   "content", "category_id", "dept", "sub_module", "module",
                   "scene", "status", "sort_num", "view_count",
                   "source_file_name", "file_path", "version_from",
                   "create_user", "update_user", "create_time", "update_time", "is_deleted"],
                  transform={"tags": lambda v: v if v else "{}",
                             "related": lambda v: v if v else "{}",
                             "tickets": lambda v: v if v else "{}"})

    # 11. document_departments
    print("\n📦 第6步: 文档关联")
    migrate_table("document_departments", "document_departments",
                  ["id", "document_path", "department_id", "is_primary", "source",
                   "created_at", "updated_at"])

    # 12. search_counter
    print("\n📦 第7步: 其他")
    migrate_table("search_counter", "search_counter", ["key", "value"])

    # 13. feedback
    migrate_table("feedback", "feedback", ["id", "query", "result_id", "result_path", "type", "created_at"])

    # 14. faq_categories (empty in SQLite, skip)

    print("\n" + "=" * 60)
    print("迁移完成！验证数据量：")
    print("=" * 60)
    for t in ["departments", "modules", "module_menus", "module_aliases",
              "keywords_v2", "keyword_mappings", "synonyms", "faqs",
              "document_departments", "search_counter", "feedback"]:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t:30s} {cur.fetchone()[0]} 条")

    pg.close()
    sqlite.close()

if __name__ == "__main__":
    migrate()