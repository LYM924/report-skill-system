#!/usr/bin/env python3
"""
乐采事业部模块与部门关联数据更新脚本

根据 Excel 数据更新 PostgreSQL 数据库：
1. 修正模块→产品映射（AI工具/插件错配）
2. 细化模块department_id（L1→L2/L3）
3. 插入缺失模块
4. 补全模块描述/负责人
5. 写入module_menus多对多部门关联
"""

import openpyxl
import psycopg2
from datetime import datetime
from collections import defaultdict

# ═══════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════
DB_URL = "postgresql://zcy1@localhost:5432/knowledge_base"
EXCEL_PATH = "/Users/zcy1/Downloads/乐采事业部模块与部门关联数据.xlsx"

# ═══════════════════════════════════════════
# 数据库部门 ID 映射（从 DB 查询固化）
# ═══════════════════════════════════════════
DEPT_NAME_TO_ID = {}
PRODUCT_NAME_TO_ID = {}
PRODUCT_LINE_NAME_TO_ID = {}


def load_db_mappings(cur):
    """从数据库加载名称→ID映射"""
    global DEPT_NAME_TO_ID, PRODUCT_NAME_TO_ID, PRODUCT_LINE_NAME_TO_ID

    cur.execute("SELECT id, name, parent_id, level FROM departments")
    for row in cur.fetchall():
        DEPT_NAME_TO_ID[row[1]] = {
            "id": row[0],
            "parent_id": row[2],
            "level": row[3],
        }

    cur.execute("SELECT id, name, product_line_id FROM products")
    for row in cur.fetchall():
        PRODUCT_NAME_TO_ID[row[1]] = {"id": row[0], "product_line_id": row[2]}

    cur.execute("SELECT id, name FROM product_lines")
    for row in cur.fetchall():
        PRODUCT_LINE_NAME_TO_ID[row[1]] = row[0]

    print(f"  部门: {len(DEPT_NAME_TO_ID)}, 产品: {len(PRODUCT_NAME_TO_ID)}, 产品线: {len(PRODUCT_LINE_NAME_TO_ID)}")


def read_excel():
    """读取 Excel，返回按模块名分组的聚合数据"""
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb["Sheet1"]

    # module_name → {desc, dev_owner, module_owner, product, product_line, domain,
    #                depts: [(l3, l2, l1), ...]}
    modules = defaultdict(lambda: {
        "desc": "",
        "dev_owner": "",
        "module_owner": "",
        "product": "",
        "product_line": "",
        "domain": "",
        "depts": [],  # list of (l3_name, l2_name, l1_name)
    })

    for row in ws.iter_rows(min_row=2, values_only=True):
        module, desc, rd_lead, mod_lead, dept_l3, dept_l2, dept_l1, product, product_line, domain = row
        if not module:
            continue

        m = modules[module]
        # 取第一个非空描述
        if desc and not m["desc"]:
            m["desc"] = desc
        if rd_lead and not m["dev_owner"]:
            m["dev_owner"] = rd_lead
        if mod_lead and not m["module_owner"]:
            m["module_owner"] = mod_lead or ""
        if product and not m["product"]:
            m["product"] = product
        if product_line and not m["product_line"]:
            m["product_line"] = product_line
        if domain and not m["domain"]:
            m["domain"] = domain

        # 去重添加部门关联
        dept_tuple = (dept_l3 or "", dept_l2 or "", dept_l1 or "")
        if dept_tuple not in m["depts"]:
            m["depts"].append(dept_tuple)

    return dict(modules)


def resolve_primary_dept_id(depts_list):
    """从模块的部门关联列表中，确定 primary department_id

    优先取 L2 部门 ID（模块的行政归属）。
    如果 L2 部门名同时也是 L3（如 产品设计部、质量测评部），
    取该部门 ID 本身。
    """
    if not depts_list:
        return None

    # 统计最常见的 L2 部门
    l2_counts = defaultdict(int)
    for l3, l2, l1 in depts_list:
        if l2:
            l2_counts[l2] += 1

    if not l2_counts:
        # 退回 L1
        for l3, l2, l1 in depts_list:
            if l1 and l1 in DEPT_NAME_TO_ID:
                return DEPT_NAME_TO_ID[l1]["id"]
        return None

    # 取出现最多的 L2
    primary_l2 = max(l2_counts, key=l2_counts.get)

    if primary_l2 in DEPT_NAME_TO_ID:
        return DEPT_NAME_TO_ID[primary_l2]["id"]

    return None


def build_module_menus_rows(module_db_id, depts_list):
    """为模块构建 module_menus 行数据

    每个部门关联生成一条 (module_id, level1, level2, level3)
    """
    rows = []
    for l3, l2, l1 in depts_list:
        rows.append((module_db_id, l1 or "-", l2 or "-", l3 or "-"))
    return rows


def run_update():
    """主更新逻辑"""
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # 1. 加载 DB 映射
        print("📋 加载数据库映射...")
        load_db_mappings(cur)

        # 2. 读取 Excel
        print("📋 读取 Excel 数据...")
        excel_modules = read_excel()
        print(f"  Excel 模块数: {len(excel_modules)}")

        # 3. 加载现有模块
        print("📋 加载现有模块...")
        cur.execute("""
            SELECT m.id, m.name, m.department_id, m.product_id, m.description,
                   m.dev_owner, m.module_owner, m.business_domain
            FROM modules m
            WHERE m.is_deleted = FALSE
        """)
        existing_modules = {}
        for row in cur.fetchall():
            existing_modules[row[1]] = {
                "id": row[0],
                "name": row[1],
                "department_id": row[2],
                "product_id": row[3],
                "description": row[4] or "",
                "dev_owner": row[5] or "",
                "module_owner": row[6] or "",
                "business_domain": row[7] or "",
            }
        print(f"  DB 活跃模块数: {len(existing_modules)}")

        # ═══════════════════════════════════════
        # 统计变更
        # ═══════════════════════════════════════
        stats = {
            "modules_updated": 0,
            "modules_inserted": 0,
            "product_id_fixed": 0,
            "dept_id_updated": 0,
            "desc_updated": 0,
            "dev_owner_updated": 0,
            "mod_owner_updated": 0,
            "menus_deleted": 0,
            "menus_inserted": 0,
            "errors": [],
        }

        # ═══════════════════════════════════════
        # 4. 更新/插入模块
        # ═══════════════════════════════════════
        all_menu_rows = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for module_name, excel_data in excel_modules.items():
            product_name = excel_data["product"]
            product_id = None
            if product_name and product_name in PRODUCT_NAME_TO_ID:
                product_id = PRODUCT_NAME_TO_ID[product_name]["id"]
            elif product_name:
                stats["errors"].append(f"产品未找到: {product_name} (模块: {module_name})")

            primary_dept_id = resolve_primary_dept_id(excel_data["depts"])

            if module_name in existing_modules:
                # ──── 更新现有模块 ────
                db_mod = existing_modules[module_name]
                module_id = db_mod["id"]
                updates = []
                params = []

                # product_id 修正
                if product_id and db_mod["product_id"] != product_id:
                    updates.append("product_id = %s")
                    params.append(product_id)
                    if db_mod["product_id"] != product_id:
                        stats["product_id_fixed"] += 1
                        print(f"  🔄 产品修正: {module_name}: {db_mod['product_id']}→{product_id}")

                # department_id 细化
                if primary_dept_id and db_mod["department_id"] != primary_dept_id:
                    updates.append("department_id = %s")
                    params.append(primary_dept_id)
                    stats["dept_id_updated"] += 1

                # description 补全
                if excel_data["desc"] and not db_mod["description"]:
                    updates.append("description = %s")
                    params.append(excel_data["desc"])
                    stats["desc_updated"] += 1

                # dev_owner 更新
                if excel_data["dev_owner"] and db_mod["dev_owner"] != excel_data["dev_owner"]:
                    updates.append("dev_owner = %s")
                    params.append(excel_data["dev_owner"])
                    stats["dev_owner_updated"] += 1

                # module_owner 更新
                if excel_data["module_owner"] and db_mod["module_owner"] != excel_data["module_owner"]:
                    updates.append("module_owner = %s")
                    params.append(excel_data["module_owner"])
                    stats["mod_owner_updated"] += 1

                # business_domain
                if excel_data["domain"] and db_mod["business_domain"] != excel_data["domain"]:
                    updates.append("business_domain = %s")
                    params.append(excel_data["domain"])

                if updates:
                    updates.append("updated_at = now()")
                    sql = f"UPDATE modules SET {', '.join(updates)} WHERE id = %s"
                    params.append(module_id)
                    cur.execute(sql, params)
                    stats["modules_updated"] += 1

                # module_menus
                all_menu_rows.extend(build_module_menus_rows(module_id, excel_data["depts"]))

            else:
                # ──── 插入新模块 ────
                print(f"  ➕ 新增模块: {module_name}")
                dir_name = None
                # 从 dept_mapping 的 SUBMODULE_TO_PATH 获取 dir_name
                try:
                    import sys
                    sys.path.insert(0, "/Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/projects/knowledge-base/src/server")
                    from repository.dept_mapping import SUBMODULE_TO_PATH
                    if module_name in SUBMODULE_TO_PATH:
                        dir_name = SUBMODULE_TO_PATH[module_name]
                except Exception:
                    pass

                cur.execute("""
                    INSERT INTO modules (name, department_id, product_id, description,
                                         dev_owner, module_owner, business_domain, dir_name,
                                         created_at, updated_at, is_deleted)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), now(), FALSE)
                    RETURNING id
                """, (
                    module_name,
                    primary_dept_id,
                    product_id,
                    excel_data["desc"] or None,
                    excel_data["dev_owner"] or None,
                    excel_data["module_owner"] or None,
                    excel_data["domain"] or "乐采业务",
                    dir_name,
                ))
                new_id = cur.fetchone()[0]
                stats["modules_inserted"] += 1

                all_menu_rows.extend(build_module_menus_rows(new_id, excel_data["depts"]))

        # ═══════════════════════════════════════
        # 5. 更新 module_menus
        # ═══════════════════════════════════════
        # 先删除乐采相关模块的旧 menus
        lecai_module_ids = []
        for module_name in excel_modules:
            if module_name in existing_modules:
                lecai_module_ids.append(existing_modules[module_name]["id"])

        if lecai_module_ids:
            # 使用子查询删除
            cur.execute("""
                DELETE FROM module_menus
                WHERE module_id = ANY(%s)
            """, (lecai_module_ids,))
            stats["menus_deleted"] = cur.rowcount

        # 插入新 menus
        if all_menu_rows:
            for row in all_menu_rows:
                cur.execute("""
                    INSERT INTO module_menus (module_id, level1, level2, level3)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, row)
            stats["menus_inserted"] = len(all_menu_rows)

        # ═══════════════════════════════════════
        # 6. 提交
        # ═══════════════════════════════════════
        conn.commit()
        print("\n✅ 事务已提交！")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 错误，已回滚: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

    # ═══════════════════════════════════════
    # 输出统计
    # ═══════════════════════════════════════
    print("\n" + "=" * 60)
    print("📊 更新统计")
    print("=" * 60)
    print(f"  模块更新: {stats['modules_updated']}")
    print(f"  模块新增: {stats['modules_inserted']}")
    print(f"  产品ID修正: {stats['product_id_fixed']}")
    print(f"  部门ID细化: {stats['dept_id_updated']}")
    print(f"  描述补全: {stats['desc_updated']}")
    print(f"  研发负责人更新: {stats['dev_owner_updated']}")
    print(f"  模块负责人更新: {stats['mod_owner_updated']}")
    print(f"  旧菜单删除: {stats['menus_deleted']}")
    print(f"  新菜单插入: {stats['menus_inserted']}")
    if stats["errors"]:
        print(f"\n⚠️  错误/警告 ({len(stats['errors'])}):")
        for err in stats["errors"]:
            print(f"    - {err}")


def verify_update():
    """更新后验证"""
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()

    print("\n" + "=" * 60)
    print("🔍 验证更新结果")
    print("=" * 60)

    # 1. 验证乐采模块 department_id 不再全部指向 L1
    print("\n1️⃣ 乐采模块 department_id 分布:")
    cur.execute("""
        SELECT d.name as dept_name, d.level, COUNT(*) as cnt
        FROM modules m
        JOIN departments d ON m.department_id = d.id
        WHERE m.is_deleted = FALSE
          AND m.business_domain = '乐采业务'
        GROUP BY d.name, d.level
        ORDER BY d.level, cnt DESC
    """)
    for row in cur.fetchall():
        print(f"  L{row[1]} {row[0]}: {row[2]} 个模块")

    # 2. 验证产品ID修正
    print("\n2️⃣ 乐采AI相关模块产品分布:")
    cur.execute("""
        SELECT p.name as prod_name, COUNT(*) as cnt
        FROM modules m
        JOIN products p ON m.product_id = p.id
        WHERE m.is_deleted = FALSE
          AND m.business_domain = '乐采业务'
          AND p.product_line_id = (SELECT id FROM product_lines WHERE name = '乐采AI')
        GROUP BY p.name
        ORDER BY cnt DESC
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[2]} 个模块" if len(row) > 2 else f"  {row[0]}: {row[1]} 个模块")

    # 3. 验证新模块
    print("\n3️⃣ 新增模块:")
    for name in ['政采云APP', '政采云军采版', '政采云商家版', '乐采对接']:
        cur.execute("SELECT id, name, department_id, product_id FROM modules WHERE name = %s AND is_deleted = FALSE", (name,))
        row = cur.fetchone()
        if row:
            print(f"  ✅ {name} (id={row[0]}, dept_id={row[2]}, prod_id={row[3]})")
        else:
            print(f"  ❌ {name} 未找到")

    # 4. 验证 module_menus
    print("\n4️⃣ module_menus 乐采数据:")
    cur.execute("""
        SELECT COUNT(*) FROM module_menus mm
        JOIN modules m ON mm.module_id = m.id
        WHERE m.business_domain = '乐采业务' AND m.is_deleted = FALSE
    """)
    count = cur.fetchone()[0]
    print(f"  总记录数: {count}")

    # 示例
    cur.execute("""
        SELECT m.name, mm.level1, mm.level2, mm.level3
        FROM module_menus mm
        JOIN modules m ON mm.module_id = m.id
        WHERE m.business_domain = '乐采业务' AND m.is_deleted = FALSE
        ORDER BY m.name, mm.level2, mm.level3
        LIMIT 15
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} → {row[2]} → {row[3]}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    print("🚀 乐采事业部模块关联数据更新")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Excel: {EXCEL_PATH}")
    print(f"   DB: {DB_URL}")
    print()

    run_update()
    verify_update()
