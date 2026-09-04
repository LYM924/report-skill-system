-- ============================================================================
-- 迁移 007: 模块关联映射管理 — 新增关联表 + 补全缺失 FK + modules.status
-- 日期: 2026-09-03
-- 说明: v3 方案 Phase 1，只加不改，向后兼容
-- ============================================================================

-- ══════ 1. 模块-部门关联表（替代 modules.associated_dept_ids 逗号分隔） ══════

CREATE TABLE IF NOT EXISTS module_departments (
    id              SERIAL PRIMARY KEY,
    module_id       INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    department_id   INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    is_primary      BOOLEAN DEFAULT FALSE,      -- 是否主关联部门（取代 sub_dept）
    source          TEXT DEFAULT 'manual',       -- manual / auto
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(module_id, department_id)
);

CREATE INDEX IF NOT EXISTS idx_mod_dept_module ON module_departments(module_id);
CREATE INDEX IF NOT EXISTS idx_mod_dept_dept ON module_departments(department_id);

COMMENT ON TABLE module_departments IS '模块-部门关联表：替代 modules.associated_dept_ids 逗号分隔字段，多对多规范化';
COMMENT ON COLUMN module_departments.module_id IS '模块ID，引用 modules.id，级联删除';
COMMENT ON COLUMN module_departments.department_id IS '部门ID，引用 departments.id，级联删除';
COMMENT ON COLUMN module_departments.is_primary IS '是否主关联部门：true=主部门（取代旧 sub_dept 字段），false=次要关联';
COMMENT ON COLUMN module_departments.source IS '关联来源：manual=人工标注，auto=自动推导';


-- ══════ 2. 业务域字典表（替代 modules.business_domain 纯文本） ══════

CREATE TABLE IF NOT EXISTS business_domains (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    code        TEXT,                           -- 可选编码
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE business_domains IS '业务域字典表：替代 modules.business_domain 纯文本字段，规范定义业务域';
COMMENT ON COLUMN business_domains.name IS '业务域名称，如"乐采业务"、"研发业务"、"免疫规划组业务"';
COMMENT ON COLUMN business_domains.code IS '业务域编码，如 LECAI、R&D、YM';


-- ══════ 3. 模块-业务域关联表（替代 modules.business_domain 纯文本） ══════

CREATE TABLE IF NOT EXISTS module_domains (
    id              SERIAL PRIMARY KEY,
    module_id       INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    domain_id       INTEGER NOT NULL REFERENCES business_domains(id) ON DELETE CASCADE,
    is_primary      BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(module_id, domain_id)
);

CREATE INDEX IF NOT EXISTS idx_mod_dom_module ON module_domains(module_id);
CREATE INDEX IF NOT EXISTS idx_mod_dom_domain ON module_domains(domain_id);

COMMENT ON TABLE module_domains IS '模块-业务域关联表：替代 modules.business_domain 纯文本字段，多对多规范化';
COMMENT ON COLUMN module_domains.is_primary IS '是否主业务域：true=主要归属，false=次要关联';


-- ══════ 4. 变更审计日志表 ══════

CREATE TABLE IF NOT EXISTS mapping_change_logs (
    id              SERIAL PRIMARY KEY,
    change_type     TEXT NOT NULL,              -- 'module_dept_add', 'module_product_change', 'module_status_change', ...
    target_type     TEXT NOT NULL,              -- 'module', 'product_line', 'product', 'domain', 'department'
    target_id       INTEGER NOT NULL,           -- 变更对象的ID
    old_value       JSONB,                      -- 变更前的值（JSON，含ID+名称）
    new_value       JSONB,                      -- 变更后的值
    cascade_summary JSONB,                      -- 级联影响统计
    operator        TEXT NOT NULL,               -- 操作人
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mcl_type ON mapping_change_logs(change_type);
CREATE INDEX IF NOT EXISTS idx_mcl_target ON mapping_change_logs(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_mcl_time ON mapping_change_logs(created_at DESC);

COMMENT ON TABLE mapping_change_logs IS '模块关联映射变更审计日志';
COMMENT ON COLUMN mapping_change_logs.change_type IS '变更类型：module_dept_add/module_dept_remove/module_product_change/module_domain_change/module_status_change/module_rename等';
COMMENT ON COLUMN mapping_change_logs.old_value IS '变更前值（JSONB），如 {"product_id": 12, "product_name": "旧产品"}';
COMMENT ON COLUMN mapping_change_logs.new_value IS '变更后值（JSONB），如 {"product_id": 15, "product_name": "乐采AI平台"}';
COMMENT ON COLUMN mapping_change_logs.cascade_summary IS '级联影响统计（JSONB），如 {"documents_updated": 7, "faqs_updated": 3}';


-- ══════ 5. modules 新增 status 字段 ══════

ALTER TABLE modules ADD COLUMN IF NOT EXISTS status SMALLINT DEFAULT 1;
-- 0=草稿, 1=正常(active), 2=废弃(deprecated)

COMMENT ON COLUMN modules.status IS '模块状态：0=草稿，1=正常，2=废弃';


-- ══════ 6. faqs 补全 sub_module_id FK ══════

ALTER TABLE faqs ADD COLUMN IF NOT EXISTS sub_module_id INTEGER REFERENCES modules(id);

COMMENT ON COLUMN faqs.sub_module_id IS '子模块ID，引用 modules.id，替代 sub_module 纯文本字段';

CREATE INDEX IF NOT EXISTS idx_faqs_sub_module_id ON faqs(sub_module_id) WHERE sub_module_id IS NOT NULL;


-- ══════ 7. raw_documents 补全缺失 FK ══════

ALTER TABLE raw_documents ADD COLUMN IF NOT EXISTS module_id INTEGER REFERENCES modules(id);
ALTER TABLE raw_documents ADD COLUMN IF NOT EXISTS product_id INTEGER REFERENCES products(id);

COMMENT ON COLUMN raw_documents.module_id IS '模块ID，引用 modules.id';
COMMENT ON COLUMN raw_documents.product_id IS '产品ID，引用 products.id';

CREATE INDEX IF NOT EXISTS idx_raw_docs_module_id ON raw_documents(module_id) WHERE module_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_docs_product_id ON raw_documents(product_id) WHERE product_id IS NOT NULL;


-- ══════ 8. faq_categories 补全缺失 FK ══════

ALTER TABLE faq_categories ADD COLUMN IF NOT EXISTS dept_id INTEGER REFERENCES departments(id);
ALTER TABLE faq_categories ADD COLUMN IF NOT EXISTS sub_module_id INTEGER REFERENCES modules(id);

COMMENT ON COLUMN faq_categories.dept_id IS '部门ID，引用 departments.id，替代 dept 纯文本';
COMMENT ON COLUMN faq_categories.sub_module_id IS '子模块ID，引用 modules.id，替代 sub_module 纯文本';


-- ══════ 9. keyword_mappings 补全 domain_id FK ══════

ALTER TABLE keyword_mappings ADD COLUMN IF NOT EXISTS domain_id INTEGER REFERENCES business_domains(id);

COMMENT ON COLUMN keyword_mappings.domain_id IS '业务域ID，引用 business_domains.id，替代 domain 纯文本';

CREATE INDEX IF NOT EXISTS idx_kwm_domain_id ON keyword_mappings(domain_id) WHERE domain_id IS NOT NULL;
