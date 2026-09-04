-- ============================================================================
-- 迁移 008: 自动同步触发器（ID变更同步名称 + 实体改名级联）
-- 日期: 2026-09-03
-- 依赖: 007_module_mapping_tables.sql
-- 原则: ID 是权威来源，名称是 ID 的可读镜像，由触发器保证同步
-- 更新: v2 — 补全 INSERT 场景 + raw_documents/faq_categories/keyword_mappings.domain_id 同步
-- ============================================================================


-- ══════════════════════════════════════════════════════════════════════════
-- 第一组：ID 变更/插入时 → 自动更新对应名称列
-- 原理：当内容表的 _id 字段被 INSERT 或 UPDATE 时，自动从实体表反查最新名称填入
-- ══════════════════════════════════════════════════════════════════════════


-- ──── documents.dept_id 变更 → 自动同步 dept 名称 ────

CREATE OR REPLACE FUNCTION sync_documents_dept_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.dept_id IS DISTINCT FROM OLD.dept_id THEN
        IF NEW.dept_id IS NOT NULL THEN
            SELECT name INTO NEW.dept FROM departments WHERE id = NEW.dept_id;
        ELSE
            NEW.dept := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_documents_dept ON documents;
CREATE TRIGGER trg_sync_documents_dept
    BEFORE INSERT OR UPDATE OF dept_id ON documents
    FOR EACH ROW EXECUTE FUNCTION sync_documents_dept_name();

COMMENT ON FUNCTION sync_documents_dept_name IS 'ID同步触发器：documents.dept_id变更/插入时，自动更新dept名称';


-- ──── documents.module_id 变更 → 自动同步 module 名称 ────

CREATE OR REPLACE FUNCTION sync_documents_module_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.module_id IS DISTINCT FROM OLD.module_id THEN
        IF NEW.module_id IS NOT NULL THEN
            SELECT name INTO NEW.module FROM modules WHERE id = NEW.module_id;
        ELSE
            NEW.module := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_documents_module ON documents;
CREATE TRIGGER trg_sync_documents_module
    BEFORE INSERT OR UPDATE OF module_id ON documents
    FOR EACH ROW EXECUTE FUNCTION sync_documents_module_name();

COMMENT ON FUNCTION sync_documents_module_name IS 'ID同步触发器：documents.module_id变更/插入时，自动更新module名称';


-- ──── documents.product_id 变更 → 自动同步 product + product_line ────

CREATE OR REPLACE FUNCTION sync_documents_product_name()
RETURNS trigger AS $$
DECLARE
    v_product_line_id INTEGER;
    v_product_line_name TEXT;
BEGIN
    IF TG_OP = 'INSERT' OR NEW.product_id IS DISTINCT FROM OLD.product_id THEN
        IF NEW.product_id IS NOT NULL THEN
            SELECT p.name, pl.id, pl.name
              INTO NEW.product, v_product_line_id, v_product_line_name
              FROM products p
              LEFT JOIN product_lines pl ON p.product_line_id = pl.id
             WHERE p.id = NEW.product_id;
            -- 同步 product_line_id 和 product_line
            NEW.product_line_id := v_product_line_id;
            NEW.product_line := v_product_line_name;
        ELSE
            NEW.product := NULL;
            NEW.product_line_id := NULL;
            NEW.product_line := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_documents_product ON documents;
CREATE TRIGGER trg_sync_documents_product
    BEFORE INSERT OR UPDATE OF product_id ON documents
    FOR EACH ROW EXECUTE FUNCTION sync_documents_product_name();

COMMENT ON FUNCTION sync_documents_product_name IS 'ID同步触发器：documents.product_id变更/插入时，自动更新product+product_line';


-- ──── documents.product_line_id 独立变更 → 自动同步 product_line 名称 ────

CREATE OR REPLACE FUNCTION sync_documents_product_line_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.product_line_id IS DISTINCT FROM OLD.product_line_id THEN
        IF NEW.product_line_id IS NOT NULL THEN
            SELECT name INTO NEW.product_line FROM product_lines WHERE id = NEW.product_line_id;
        ELSE
            NEW.product_line := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_documents_product_line ON documents;
CREATE TRIGGER trg_sync_documents_product_line
    BEFORE INSERT OR UPDATE OF product_line_id ON documents
    FOR EACH ROW EXECUTE FUNCTION sync_documents_product_line_name();

COMMENT ON FUNCTION sync_documents_product_line_name IS 'ID同步触发器：documents.product_line_id变更/插入时，自动更新product_line名称';


-- ──── faqs.dept_id 变更 → 自动同步 dept 名称 ────

CREATE OR REPLACE FUNCTION sync_faqs_dept_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.dept_id IS DISTINCT FROM OLD.dept_id THEN
        IF NEW.dept_id IS NOT NULL THEN
            SELECT name INTO NEW.dept FROM departments WHERE id = NEW.dept_id;
        ELSE
            NEW.dept := '';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_faqs_dept ON faqs;
CREATE TRIGGER trg_sync_faqs_dept
    BEFORE INSERT OR UPDATE OF dept_id ON faqs
    FOR EACH ROW EXECUTE FUNCTION sync_faqs_dept_name();

COMMENT ON FUNCTION sync_faqs_dept_name IS 'ID同步触发器：faqs.dept_id变更/插入时，自动更新dept名称';


-- ──── faqs.module_id 变更 → 自动同步 module 名称 ────

CREATE OR REPLACE FUNCTION sync_faqs_module_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.module_id IS DISTINCT FROM OLD.module_id THEN
        IF NEW.module_id IS NOT NULL THEN
            SELECT name INTO NEW.module FROM modules WHERE id = NEW.module_id;
        ELSE
            NEW.module := '';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_faqs_module ON faqs;
CREATE TRIGGER trg_sync_faqs_module
    BEFORE INSERT OR UPDATE OF module_id ON faqs
    FOR EACH ROW EXECUTE FUNCTION sync_faqs_module_name();

COMMENT ON FUNCTION sync_faqs_module_name IS 'ID同步触发器：faqs.module_id变更/插入时，自动更新module名称';


-- ──── faqs.sub_module_id 变更 → 自动同步 sub_module 名称 ────

CREATE OR REPLACE FUNCTION sync_faqs_sub_module_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.sub_module_id IS DISTINCT FROM OLD.sub_module_id THEN
        IF NEW.sub_module_id IS NOT NULL THEN
            SELECT name INTO NEW.sub_module FROM modules WHERE id = NEW.sub_module_id;
        ELSE
            NEW.sub_module := '';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_faqs_sub_module ON faqs;
CREATE TRIGGER trg_sync_faqs_sub_module
    BEFORE INSERT OR UPDATE OF sub_module_id ON faqs
    FOR EACH ROW EXECUTE FUNCTION sync_faqs_sub_module_name();

COMMENT ON FUNCTION sync_faqs_sub_module_name IS 'ID同步触发器：faqs.sub_module_id变更/插入时，自动更新sub_module名称';


-- ──── keyword_mappings.department_id 变更 → 自动同步 department 名称 ────

CREATE OR REPLACE FUNCTION sync_keyword_mappings_dept_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.department_id IS DISTINCT FROM OLD.department_id THEN
        IF NEW.department_id IS NOT NULL THEN
            SELECT name INTO NEW.department FROM departments WHERE id = NEW.department_id;
        ELSE
            NEW.department := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_kwm_dept ON keyword_mappings;
CREATE TRIGGER trg_sync_kwm_dept
    BEFORE INSERT OR UPDATE OF department_id ON keyword_mappings
    FOR EACH ROW EXECUTE FUNCTION sync_keyword_mappings_dept_name();

COMMENT ON FUNCTION sync_keyword_mappings_dept_name IS 'ID同步触发器：keyword_mappings.department_id变更/插入时，自动更新department名称';


-- ──── keyword_mappings.domain_id 变更 → 自动同步 domain 名称 ────（新增）

CREATE OR REPLACE FUNCTION sync_keyword_mappings_domain_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.domain_id IS DISTINCT FROM OLD.domain_id THEN
        IF NEW.domain_id IS NOT NULL THEN
            SELECT name INTO NEW.domain FROM business_domains WHERE id = NEW.domain_id;
        ELSE
            NEW.domain := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_kwm_domain ON keyword_mappings;
CREATE TRIGGER trg_sync_kwm_domain
    BEFORE INSERT OR UPDATE OF domain_id ON keyword_mappings
    FOR EACH ROW EXECUTE FUNCTION sync_keyword_mappings_domain_name();

COMMENT ON FUNCTION sync_keyword_mappings_domain_name IS 'ID同步触发器：keyword_mappings.domain_id变更/插入时，自动更新domain名称';


-- ──── raw_documents.dept_id 变更 → 自动同步 dept 名称 ────（新增）

CREATE OR REPLACE FUNCTION sync_raw_documents_dept_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.dept_id IS DISTINCT FROM OLD.dept_id THEN
        IF NEW.dept_id IS NOT NULL THEN
            SELECT name INTO NEW.dept FROM departments WHERE id = NEW.dept_id;
        ELSE
            NEW.dept := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_raw_documents_dept ON raw_documents;
CREATE TRIGGER trg_sync_raw_documents_dept
    BEFORE INSERT OR UPDATE OF dept_id ON raw_documents
    FOR EACH ROW EXECUTE FUNCTION sync_raw_documents_dept_name();

COMMENT ON FUNCTION sync_raw_documents_dept_name IS 'ID同步触发器：raw_documents.dept_id变更/插入时，自动更新dept名称';


-- ──── raw_documents.module_id 变更 → 自动同步 module 名称 ────（新增）

CREATE OR REPLACE FUNCTION sync_raw_documents_module_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.module_id IS DISTINCT FROM OLD.module_id THEN
        IF NEW.module_id IS NOT NULL THEN
            SELECT name INTO NEW.module FROM modules WHERE id = NEW.module_id;
        ELSE
            NEW.module := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_raw_documents_module ON raw_documents;
CREATE TRIGGER trg_sync_raw_documents_module
    BEFORE INSERT OR UPDATE OF module_id ON raw_documents
    FOR EACH ROW EXECUTE FUNCTION sync_raw_documents_module_name();

COMMENT ON FUNCTION sync_raw_documents_module_name IS 'ID同步触发器：raw_documents.module_id变更/插入时，自动更新module名称';


-- ──── raw_documents.product_id 变更 → 自动同步 product 名称 ────（新增）

CREATE OR REPLACE FUNCTION sync_raw_documents_product_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.product_id IS DISTINCT FROM OLD.product_id THEN
        IF NEW.product_id IS NOT NULL THEN
            SELECT name INTO NEW.product FROM products WHERE id = NEW.product_id;
        ELSE
            NEW.product := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_raw_documents_product ON raw_documents;
CREATE TRIGGER trg_sync_raw_documents_product
    BEFORE INSERT OR UPDATE OF product_id ON raw_documents
    FOR EACH ROW EXECUTE FUNCTION sync_raw_documents_product_name();

COMMENT ON FUNCTION sync_raw_documents_product_name IS 'ID同步触发器：raw_documents.product_id变更/插入时，自动更新product名称';


-- ──── faq_categories.dept_id 变更 → 自动同步 dept 名称 ────（新增）

CREATE OR REPLACE FUNCTION sync_faq_categories_dept_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.dept_id IS DISTINCT FROM OLD.dept_id THEN
        IF NEW.dept_id IS NOT NULL THEN
            SELECT name INTO NEW.dept FROM departments WHERE id = NEW.dept_id;
        ELSE
            NEW.dept := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_faq_cat_dept ON faq_categories;
CREATE TRIGGER trg_sync_faq_cat_dept
    BEFORE INSERT OR UPDATE OF dept_id ON faq_categories
    FOR EACH ROW EXECUTE FUNCTION sync_faq_categories_dept_name();

COMMENT ON FUNCTION sync_faq_categories_dept_name IS 'ID同步触发器：faq_categories.dept_id变更/插入时，自动更新dept名称';


-- ──── faq_categories.sub_module_id 变更 → 自动同步 sub_module 名称 ────（新增）

CREATE OR REPLACE FUNCTION sync_faq_categories_sub_module_name()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.sub_module_id IS DISTINCT FROM OLD.sub_module_id THEN
        IF NEW.sub_module_id IS NOT NULL THEN
            SELECT name INTO NEW.sub_module FROM modules WHERE id = NEW.sub_module_id;
        ELSE
            NEW.sub_module := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_faq_cat_sub_module ON faq_categories;
CREATE TRIGGER trg_sync_faq_cat_sub_module
    BEFORE INSERT OR UPDATE OF sub_module_id ON faq_categories
    FOR EACH ROW EXECUTE FUNCTION sync_faq_categories_sub_module_name();

COMMENT ON FUNCTION sync_faq_categories_sub_module_name IS 'ID同步触发器：faq_categories.sub_module_id变更/插入时，自动更新sub_module名称';


-- ══════════════════════════════════════════════════════════════════════════
-- 第二组：实体改名时 → 自动级联到所有引用方
-- 原理：当部门/产品/产品线/模块的 name 被修改时，自动更新所有引用该名称的表
-- ══════════════════════════════════════════════════════════════════════════


-- ──── 部门改名 → 级联更新所有引用方 ────

CREATE OR REPLACE FUNCTION cascade_dept_rename()
RETURNS trigger AS $$
BEGIN
    IF NEW.name IS DISTINCT FROM OLD.name THEN
        -- documents
        UPDATE documents SET dept = NEW.name, updated_at = now()
         WHERE dept_id = NEW.id AND is_deleted = FALSE;
        -- faqs
        UPDATE faqs SET dept = NEW.name, update_time = now()
         WHERE dept_id = NEW.id AND is_deleted = FALSE;
        -- keyword_mappings
        UPDATE keyword_mappings SET department = NEW.name, updated_at = now()
         WHERE department_id = NEW.id AND is_deleted = FALSE;
        -- raw_documents
        UPDATE raw_documents SET dept = NEW.name
         WHERE dept_id = NEW.id AND is_deleted = FALSE;
        -- faq_categories
        UPDATE faq_categories SET dept = NEW.name
         WHERE dept_id = NEW.id;
        -- modules（更新 sub_dept 旧字段兼容）
        UPDATE modules SET sub_dept = NEW.name, updated_at = now()
         WHERE department_id = NEW.id AND sub_dept = OLD.name AND is_deleted = FALSE;
        -- modules.associated_dept（旧逗号分隔字段兼容：替换逗号分隔中的旧名）
        UPDATE modules SET associated_dept = REPLACE(associated_dept, OLD.name, NEW.name),
                           updated_at = now()
         WHERE associated_dept LIKE '%' || OLD.name || '%' AND is_deleted = FALSE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cascade_dept_rename ON departments;
CREATE TRIGGER trg_cascade_dept_rename
    AFTER UPDATE OF name ON departments
    FOR EACH ROW EXECUTE FUNCTION cascade_dept_rename();

COMMENT ON FUNCTION cascade_dept_rename IS '实体改名级联触发器：部门改名时自动更新所有引用方的dept名称';


-- ──── 产品改名 → 级联更新所有引用方 ────

CREATE OR REPLACE FUNCTION cascade_product_rename()
RETURNS trigger AS $$
BEGIN
    IF NEW.name IS DISTINCT FROM OLD.name THEN
        UPDATE documents SET product = NEW.name, updated_at = now()
         WHERE product_id = NEW.id AND is_deleted = FALSE;
        UPDATE raw_documents SET product = NEW.name
         WHERE product_id = NEW.id AND is_deleted = FALSE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cascade_product_rename ON products;
CREATE TRIGGER trg_cascade_product_rename
    AFTER UPDATE OF name ON products
    FOR EACH ROW EXECUTE FUNCTION cascade_product_rename();

COMMENT ON FUNCTION cascade_product_rename IS '实体改名级联触发器：产品改名时自动更新所有引用方的product名称';


-- ──── 产品线改名 → 级联更新所有引用方 ────

CREATE OR REPLACE FUNCTION cascade_product_line_rename()
RETURNS trigger AS $$
BEGIN
    IF NEW.name IS DISTINCT FROM OLD.name THEN
        UPDATE documents SET product_line = NEW.name, updated_at = now()
         WHERE product_line_id = NEW.id AND is_deleted = FALSE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cascade_product_line_rename ON product_lines;
CREATE TRIGGER trg_cascade_product_line_rename
    AFTER UPDATE OF name ON product_lines
    FOR EACH ROW EXECUTE FUNCTION cascade_product_line_rename();

COMMENT ON FUNCTION cascade_product_line_rename IS '实体改名级联触发器：产品线改名时自动更新所有引用方的product_line名称';


-- ──── 模块改名 → 级联更新所有引用方 ────

CREATE OR REPLACE FUNCTION cascade_module_rename()
RETURNS trigger AS $$
BEGIN
    IF NEW.name IS DISTINCT FROM OLD.name THEN
        -- documents
        UPDATE documents SET module = NEW.name, updated_at = now()
         WHERE module_id = NEW.id AND is_deleted = FALSE;
        -- faqs（module 字段）
        UPDATE faqs SET module = NEW.name, update_time = now()
         WHERE module_id = NEW.id AND is_deleted = FALSE;
        -- faqs（sub_module 字段）
        UPDATE faqs SET sub_module = NEW.name, update_time = now()
         WHERE sub_module_id = NEW.id AND is_deleted = FALSE;
        -- raw_documents
        UPDATE raw_documents SET module = NEW.name
         WHERE module_id = NEW.id AND is_deleted = FALSE;
        -- faq_categories（sub_module 字段）
        UPDATE faq_categories SET sub_module = NEW.name
         WHERE sub_module_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cascade_module_rename ON modules;
CREATE TRIGGER trg_cascade_module_rename
    AFTER UPDATE OF name ON modules
    FOR EACH ROW EXECUTE FUNCTION cascade_module_rename();

COMMENT ON FUNCTION cascade_module_rename IS '实体改名级联触发器：模块改名时自动更新所有引用方的module/sub_module名称';


-- ══════════════════════════════════════════════════════════════════════════
-- 第三组：业务域改名级联
-- ══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION cascade_domain_rename()
RETURNS trigger AS $$
BEGIN
    IF NEW.name IS DISTINCT FROM OLD.name THEN
        -- keyword_mappings.domain（旧字段兼容）
        UPDATE keyword_mappings SET domain = NEW.name, updated_at = now()
         WHERE domain_id = NEW.id AND is_deleted = FALSE;
        -- modules.business_domain（旧字段兼容，逗号分隔中可能包含旧名）
        UPDATE modules SET business_domain = REPLACE(business_domain, OLD.name, NEW.name),
                           updated_at = now()
         WHERE business_domain LIKE '%' || OLD.name || '%' AND is_deleted = FALSE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cascade_domain_rename ON business_domains;
CREATE TRIGGER trg_cascade_domain_rename
    AFTER UPDATE OF name ON business_domains
    FOR EACH ROW EXECUTE FUNCTION cascade_domain_rename();

COMMENT ON FUNCTION cascade_domain_rename IS '实体改名级联触发器：业务域改名时自动更新keyword_mappings.domain和modules.business_domain';
