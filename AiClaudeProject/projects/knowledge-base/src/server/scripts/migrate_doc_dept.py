#!/usr/bin/env python3
"""将 SQLite 的 document_departments 数据迁移到 PostgreSQL"""
import sqlite3, psycopg2

sqlite = sqlite3.connect('/Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/projects/knowledge-base/runtime/knowledge.db')
sqlite.row_factory = sqlite3.Row
pg = psycopg2.connect('postgresql://zcy1@localhost:5432/knowledge_base')
pg.autocommit = True
cur = pg.cursor()

cur.execute('DELETE FROM document_departments')  # 清空，重新导入

rows = sqlite.execute('SELECT * FROM document_departments').fetchall()
count = 0
for r in rows:
    cur.execute('''
        INSERT INTO document_departments (document_path, department_id, is_primary, source, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (r['document_path'], r['department_id'], bool(r['is_primary']), r['source'] or 'manual',
          r['created_at'] or '2025-01-01', r['updated_at'] or '2025-01-01'))
    count += 1

cur.execute('SELECT COUNT(*) FROM document_departments')
print(f'Migrated: {count} rows, Total in PG: {cur.fetchone()[0]} rows')
pg.close()
sqlite.close()