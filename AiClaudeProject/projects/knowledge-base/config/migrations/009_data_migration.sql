-- ============================================================================
-- 迁移 009: 数据迁移 — 逗号分隔字段→关联表 + 纯文本→业务域 + 补全FK
-- 日期: 2026-09-03
-- 依赖: 007_module_mapping_tables.sql, 008_auto_sync_triggers.sql
-- 注意: 幂等执行，可重复运行
-- ============================================================================


-- ══════ 1. modules.associated_dept_ids（逗号分隔）→ module_departments ══════

-- 确保 associated_dept_ids 列存在（由 update_lecai_dept_mapping_20260901.sql 添加，此为安全兜底）
ALTER TABLE modules ADD COLUMN IF NOT EXISTS associated_dept_ids TEXT;

-- 清空旧数据（幂等）
DELETE FROM module_departments WHERE source = 'migration';

-- 从逗号分隔的 associated_dept_ids 迁移到 module_departments
-- PostgreSQL UNNEST + STRING_TO_ARRAY 拆分逗号分隔值
INSERT INTO module_departments (module_id, department_id, is_primary, source)
SELECT
    m.id,
    trim(trim_ids.dt_id)::integer,
    -- 第一个ID标记为主部门（兼容 sub_dept 语义）
    CASE WHEN trim_ids.ordinal = 1 THEN TRUE ELSE FALSE END,
    'migration'
FROM modules m
CROSS JOIN LATERAL unnest(
    string_to_array(m.associated_dept_ids, ',')
) WITH ORDINALITY AS trim_ids(dt_id, ordinal)
WHERE m.associated_dept_ids IS NOT NULL
  AND m.associated_dept_ids != ''
  AND trim_ids.dt_id IS NOT NULL
  AND trim(trim_ids.dt_id) ~ '^\d+$'    -- 确保是数字
ON CONFLICT (module_id, department_id) DO NOTHING;


-- ══════ 2. modules.business_domain（纯文本）→ business_domains + module_domains ══════

-- 2a. 提取去重的 business_domain 值，写入 business_domains 字典表
INSERT INTO business_domains (name)
SELECT DISTINCT trim(business_domain)
FROM modules
WHERE business_domain IS NOT NULL
  AND trim(business_domain) != ''
ON CONFLICT (name) DO NOTHING;

-- 2b. 建立 module_domains 关联
INSERT INTO module_domains (module_id, domain_id, is_primary)
SELECT m.id, bd.id, TRUE
FROM modules m
JOIN business_domains bd ON trim(m.business_domain) = bd.name
WHERE m.business_domain IS NOT NULL
  AND trim(m.business_domain) != ''
ON CONFLICT (module_id, domain_id) DO NOTHING;


-- ══════ 3. faqs.sub_module（纯文本）→ faqs.sub_module_id FK ══════

-- 按 sub_module 文本名匹配 modules.id
-- 优先精确匹配，跳过空值
UPDATE faqs f
SET sub_module_id = m.id
FROM modules m
WHERE f.sub_module = m.name
  AND f.sub_module IS NOT NULL
  AND f.sub_module != ''
  AND f.sub_module_id IS NULL
  AND f.is_deleted = FALSE;


-- ══════ 4. faq_categories 补全 dept_id / sub_module_id ══════

-- dept 文本名 → departments.id
UPDATE faq_categories fc
SET dept_id = d.id
FROM departments d
WHERE fc.dept = d.name
  AND fc.dept IS NOT NULL
  AND fc.dept != ''
  AND fc.dept_id IS NULL;

-- sub_module 文本名 → modules.id
UPDATE faq_categories fc
SET sub_module_id = m.id
FROM modules m
WHERE fc.sub_module = m.name
  AND fc.sub_module IS NOT NULL
  AND fc.sub_module != ''
  AND fc.sub_module_id IS NULL;


-- ══════ 5. raw_documents 补全 module_id / product_id ══════

-- module 文本名 → modules.id
UPDATE raw_documents rd
SET module_id = m.id
FROM modules m
WHERE rd.module = m.name
  AND rd.module IS NOT NULL
  AND rd.module != ''
  AND rd.module_id IS NULL
  AND rd.is_deleted = FALSE;

-- product 文本名 → products.id
UPDATE raw_documents rd
SET product_id = p.id
FROM products p
WHERE rd.product = p.name
  AND rd.product IS NOT NULL
  AND rd.product != ''
  AND rd.product_id IS NULL
  AND rd.is_deleted = FALSE;


-- ══════ 6. keyword_mappings 补全 domain_id ══════

UPDATE keyword_mappings km
SET domain_id = bd.id
FROM business_domains bd
WHERE km.domain = bd.name
  AND km.domain IS NOT NULL
  AND km.domain != ''
  AND km.domain_id IS NULL
  AND km.is_deleted = FALSE;


-- ══════ 7. 初始化 modules.status ══════

-- 现有模块全部标记为正常（status=1），默认值已是1，此处显式确认
UPDATE modules SET status = 1 WHERE status IS NULL;


-- ══════ 8. 验证迁移结果 ══════

-- 统计关联表行数（输出到日志）
DO $$
DECLARE
    v_mod_dept_count integer;
    v_domain_count integer;
    v_mod_domain_count integer;
    v_faq_sub_mod_count integer;
BEGIN
    SELECT COUNT(*) INTO v_mod_dept_count FROM module_departments;
    SELECT COUNT(*) INTO v_domain_count FROM business_domains;
    SELECT COUNT(*) INTO v_mod_domain_count FROM module_domains;
    SELECT COUNT(*) INTO v_faq_sub_mod_count FROM faqs WHERE sub_module_id IS NOT NULL;

    RAISE NOTICE '迁移完成统计:';
    RAISE NOTICE '  module_departments: % 条关联', v_mod_dept_count;
    RAISE NOTICE '  business_domains: % 个业务域', v_domain_count;
    RAISE NOTICE '  module_domains: % 条关联', v_mod_domain_count;
    RAISE NOTICE '  faqs.sub_module_id: % 条已补全', v_faq_sub_mod_count;
END;
$$;
