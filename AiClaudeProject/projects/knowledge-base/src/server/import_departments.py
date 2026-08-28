#!/usr/bin/env python3
"""
import_departments.py - 从 zcy_deptment.md 解析部门树并导入数据库

用法: python3 import_departments.py
"""

import re
import sqlite3
from pathlib import Path
from pypinyin import lazy_pinyin, Style

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent
DB_PATH = PROJECT_DIR.parent / "runtime" / "knowledge.db"
DEPT_FILE = Path("/Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/其他文档区/zcy_deptment.md")


def parse_tree(filepath):
    """解析部门树文件，返回节点列表"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.strip().split('\n')
    nodes = []

    for line in lines:
        if not line.strip():
            continue
        stripped = line.lstrip(' │├└─')
        indent_raw = len(line) - len(stripped)

        match = re.match(r'^(.+?)\s*\((\d+)\)\s*$', stripped)
        if match:
            name = match.group(1).strip()
            dept_id = int(match.group(2))
        else:
            if stripped.startswith('...'):
                continue
            name = stripped.strip()
            dept_id = None

        level = indent_raw // 4  # 0=root, 1=一级部门, 2=二级...
        nodes.append({'id': dept_id, 'name': name, 'level': level})

    # Build parent relationships
    last_at_level = {}
    for i, node in enumerate(nodes):
        level = node['level']
        parent_level = level - 1

        if parent_level in last_at_level:
            parent_idx = last_at_level[parent_level]
            node['parent_id'] = nodes[parent_idx]['id']
        else:
            node['parent_id'] = None

        last_at_level[level] = i
        for l in list(last_at_level.keys()):
            if l > level:
                del last_at_level[l]

    return nodes


def generate_code(name, existing_codes):
    """生成唯一部门编码（拼音首字母）"""
    name = re.sub(r'\s*\(.*?\)', '', name)
    name = re.sub(r'（.*?）', '', name)
    py = ''.join(lazy_pinyin(name, style=Style.FIRST_LETTER))
    code = py.upper()[:6]
    if code in existing_codes:
        py2 = ''.join([p[0] for p in lazy_pinyin(name)])
        code = py2.upper()[:6]
    if code in existing_codes:
        i = 2
        while f"{code}{i}" in existing_codes:
            i += 1
        code = f"{code}{i}"
    existing_codes.add(code)
    return code


def generate_dir_name(name):
    """生成英文目录名"""
    name = re.sub(r'\s*\(.*?\)', '', name)
    name = re.sub(r'（.*?）', '', name)
    py = '_'.join(lazy_pinyin(name))
    return py.lower()


def import_departments(nodes, db_path):
    """导入部门数据到数据库"""
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row

    old_count = db.execute("SELECT COUNT(*) as c FROM departments").fetchone()['c']
    print(f'旧部门数: {old_count}')

    # Clear existing
    db.execute("DELETE FROM departments")
    db.execute("DELETE FROM sqlite_sequence WHERE name='departments'")

    # Generate codes
    existing_codes = set()
    dept_code_map = {}
    for node in nodes:
        if node['id']:
            code = generate_code(node['name'], existing_codes)
            dept_code_map[node['id']] = code

    # Insert
    inserted = 0
    skipped = 0
    for node in nodes:
        if not node['id']:
            skipped += 1
            continue

        code = dept_code_map.get(node['id'], '')
        dir_name = generate_dir_name(node['name'])

        db.execute("""
            INSERT INTO departments (id, name, parent_id, level, code, dir_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            node['id'], node['name'], node.get('parent_id'),
            node['level'], code, dir_name,
        ))
        inserted += 1

    db.commit()

    # Verify
    count = db.execute("SELECT COUNT(*) as c FROM departments").fetchone()['c']
    print(f'新部门数: {count} (插入 {inserted}, 跳过 {skipped})')

    # Level stats
    print('\n=== 层级统计 ===')
    for lv in range(1, 5):
        cnt = db.execute("SELECT COUNT(*) as c FROM departments WHERE level = ?", (lv,)).fetchone()['c']
        if cnt > 0:
            print(f'  Level {lv}: {cnt} 个部门')

    # Level 1 departments
    print('\n=== 一级部门 (事业部/子公司) ===')
    rows = db.execute("SELECT id, name, code FROM departments WHERE level = 1 ORDER BY name").fetchall()
    for r in rows:
        children = db.execute("SELECT COUNT(*) as c FROM departments WHERE parent_id = ?", (r['id'],)).fetchone()['c']
        print(f'  [{r["code"]}] {r["name"]} → {children} 个子部门')

    db.commit()
    db.close()
    print('\n✅ 导入完成!')


if __name__ == "__main__":
    nodes = parse_tree(DEPT_FILE)
    print(f'解析到 {len(nodes)} 个节点')
    import_departments(nodes, DB_PATH)