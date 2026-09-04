-- ============================================================================
-- 智能知识库中台 · PostgreSQL 完整建表脚本
-- 日期: 2026-09-03
-- 适用: PostgreSQL 15+（全新空库执行）
-- 用法: psql -U <用户> -d <数据库名> -f knowledge_base_init.sql
--
-- 包含：全部表、索引、触发器、视图、注释
-- 不含：数据导入（业务数据由应用系统运行时写入）
-- ============================================================================

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- 第1层：组织架构 (Organization)
-- ============================================================================

-- 部门层级表
CREATE TABLE departments (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_id   INTEGER REFERENCES departments(id),
    level       INTEGER NOT NULL DEFAULT 1,
    code        TEXT,
    dir_name    TEXT
);
COMMENT ON TABLE departments IS '部门层级表：存储公司组织架构树，支持多级部门';
COMMENT ON COLUMN departments.id IS '部门唯一ID（自增主键）';
COMMENT ON COLUMN departments.name IS '部门名称，如"免疫规划组"、"数智财务组"';
COMMENT ON COLUMN departments.parent_id IS '上级部门ID，顶级部门为NULL';
COMMENT ON COLUMN departments.level IS '部门层级：1=一级，2=二级，3=三级';
COMMENT ON COLUMN departments.code IS '部门编码/缩写';
COMMENT ON COLUMN departments.dir_name IS '部门拼音目录名';

-- 产品线表
CREATE TABLE product_lines (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
COMMENT ON TABLE product_lines IS '产品线表：业务产品线的顶层分类';
COMMENT ON COLUMN product_lines.name IS '产品线名称，如"免疫规划"、"浙里报"、"电子档案"';

-- 产品表
CREATE TABLE products (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    product_line_id INTEGER REFERENCES product_lines(id)
);
COMMENT ON TABLE products IS '产品表：产品线下的具体产品';
COMMENT ON COLUMN products.name IS '产品名称';
COMMENT ON COLUMN products.product_line_id IS '所属产品线ID';

-- 索引
CREATE INDEX idx_dept_parent ON departments(parent_id);
CREATE INDEX idx_dept_level ON departments(level);
CREATE INDEX idx_dept_name_trgm ON departments USING gin (name gin_trgm_ops);
CREATE INDEX idx_prod_line ON products(product_line_id);

-- ============================================================================
-- 第2层：业务模块 (Modules)
-- ============================================================================

-- 模块主表
CREATE TABLE modules (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    department_id   INTEGER REFERENCES departments(id),
    product_id      INTEGER REFERENCES products(id),
    dev_owner       TEXT,
    module_owner    TEXT,
    appendix        TEXT,
    business_domain TEXT,
    associated_dept TEXT,
    sub_dept        TEXT,
    description     TEXT,
    path            TEXT,
    dir_name        TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE modules IS '业务模块表：产品的功能模块定义';

-- 模块菜单映射表
CREATE TABLE module_menus (
    id          SERIAL PRIMARY KEY,
    module_id   INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    level1      TEXT,
    level2      TEXT,
    level3      TEXT,
    sort_order  INTEGER DEFAULT 0
);
COMMENT ON TABLE module_menus IS '模块菜单映射表：记录模块在系统菜单中的位置';

-- 模块别名表
CREATE TABLE module_aliases (
    id          SERIAL PRIMARY KEY,
    module_id   INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    alias       TEXT NOT NULL
);
COMMENT ON TABLE module_aliases IS '模块别名表：同一模块的多个称呼';

-- 模块关键词关联表
CREATE TABLE module_keywords (
    id          SERIAL PRIMARY KEY,
    module_id   INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    keyword     TEXT NOT NULL,
    UNIQUE(module_id, keyword)
);
COMMENT ON TABLE module_keywords IS '模块关键词关联表：记录每个模块的关键词';

-- 索引
CREATE INDEX idx_modules_dept ON modules(department_id);
CREATE INDEX idx_modules_product ON modules(product_id);
CREATE INDEX idx_modules_name ON modules(name);
CREATE INDEX idx_modules_appendix ON modules(appendix);
CREATE INDEX idx_modules_not_deleted ON modules(is_deleted) WHERE is_deleted = FALSE;
CREATE INDEX idx_module_menus_mod ON module_menus(module_id);
CREATE INDEX idx_module_menus_level1 ON module_menus(level1);
CREATE INDEX idx_module_aliases_mod ON module_aliases(module_id);
CREATE INDEX idx_module_aliases_alias ON module_aliases(alias);
CREATE INDEX idx_module_keywords_mod ON module_keywords(module_id);
CREATE INDEX idx_module_keywords_kw ON module_keywords(keyword);

-- ============================================================================
-- 第3层：内容资产 (Content) — 文档 / FAQ / 报表 / 原始文档
-- ============================================================================

-- ----------------------------
-- 3a. 知识文档表
-- ----------------------------
CREATE TABLE documents (
    id              SERIAL PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,
    filename        TEXT NOT NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    content_hash    TEXT,
    word_count      INTEGER DEFAULT 0,
    dept            TEXT,
    dept_id         INTEGER REFERENCES departments(id),
    dept3           TEXT,                        -- 三级部门名（兼容旧字段）
    module          TEXT,
    module_id       INTEGER REFERENCES modules(id),
    product         TEXT,
    product_id      INTEGER REFERENCES products(id),
    product_line    TEXT,
    product_line_id INTEGER REFERENCES product_lines(id),
    date            TEXT,
    appendix        TEXT,
    keywords        TEXT[],
    related_modules TEXT[],
    imported_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE,
    search_vector   tsvector
);
COMMENT ON TABLE documents IS '知识文档表：存储产品知识库文档';

-- 文档-部门关联表
CREATE TABLE document_departments (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    document_path   TEXT,                        -- 兼容旧数据：path 关联
    department_id   INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    is_primary      BOOLEAN DEFAULT FALSE,
    source          TEXT DEFAULT 'auto',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, department_id)
);
COMMENT ON TABLE document_departments IS '文档-部门关联表：多对多';

-- 文档图片追踪表
CREATE TABLE document_images (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    image_url       TEXT NOT NULL,
    alt_text        TEXT,
    image_hash      TEXT,
    file_size       BIGINT,
    is_accessible   BOOLEAN,
    last_checked    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, image_url)
);
COMMENT ON TABLE document_images IS '文档图片追踪表';

-- 文档索引
CREATE INDEX idx_documents_search ON documents USING gin(search_vector);
CREATE INDEX idx_documents_path ON documents(path);
CREATE INDEX idx_documents_dept ON documents(dept);
CREATE INDEX idx_documents_module ON documents(module);
CREATE INDEX idx_documents_dept_id ON documents(dept_id);
CREATE INDEX idx_documents_module_id ON documents(module_id);
CREATE INDEX idx_documents_product_id ON documents(product_id);
CREATE INDEX idx_documents_date ON documents(date);
CREATE INDEX idx_documents_keywords ON documents USING gin(keywords);
CREATE INDEX idx_documents_not_deleted ON documents(is_deleted) WHERE is_deleted = FALSE;
CREATE INDEX idx_documents_updated_at ON documents(updated_at DESC NULLS LAST) WHERE is_deleted = FALSE;
CREATE INDEX idx_doc_dept_doc ON document_departments(document_id);
CREATE INDEX idx_doc_dept_dept ON document_departments(department_id);
CREATE INDEX idx_doc_dept_path ON document_departments(document_path);
CREATE UNIQUE INDEX uq_dd_path_dept ON document_departments(document_path, department_id);
CREATE INDEX idx_doc_images_doc ON document_images(document_id);
CREATE INDEX idx_doc_images_url ON document_images(image_url);

-- ----------------------------
-- 3b. FAQ 知识库
-- ----------------------------
CREATE TABLE faq_categories (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_id   INTEGER REFERENCES faq_categories(id),
    dept        TEXT,
    sub_module  TEXT,
    level       INTEGER DEFAULT 1,
    sort_order  INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE faq_categories IS 'FAQ 分类表';

CREATE TABLE faqs (
    id              SERIAL PRIMARY KEY,
    faq_code        TEXT NOT NULL UNIQUE,
    faq_title       TEXT NOT NULL,
    faq_question    TEXT NOT NULL,
    faq_answer      TEXT NOT NULL,
    content         TEXT,
    category_id     INTEGER REFERENCES faq_categories(id),
    dept            TEXT NOT NULL,
    dept_id         INTEGER REFERENCES departments(id),
    sub_module      TEXT DEFAULT '',
    module          TEXT DEFAULT '',
    module_id       INTEGER REFERENCES modules(id),
    scene           TEXT DEFAULT '',
    tags            TEXT[] DEFAULT '{}',
    status          SMALLINT DEFAULT 0,
    sort_num        INTEGER DEFAULT 0,
    view_count      INTEGER DEFAULT 0,
    source_file_name TEXT DEFAULT '',
    file_path       TEXT DEFAULT '',
    version_from    TEXT DEFAULT '',
    related         TEXT DEFAULT '[]',
    tickets         TEXT DEFAULT '[]',
    create_user     TEXT DEFAULT '',
    update_user     TEXT DEFAULT '',
    create_time     TIMESTAMPTZ DEFAULT NOW(),
    update_time     TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE,
    search_vector   tsvector
);
COMMENT ON TABLE faqs IS 'FAQ 知识库主表';

-- FAQ 标签关联表
CREATE TABLE faq_tags (
    id      SERIAL PRIMARY KEY,
    faq_id  INTEGER NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    UNIQUE(faq_id, tag)
);
COMMENT ON TABLE faq_tags IS 'FAQ 标签关联表';

-- FAQ 关联关系表
CREATE TABLE faq_related (
    id              SERIAL PRIMARY KEY,
    faq_id          INTEGER NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    related_faq_id  INTEGER NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    UNIQUE(faq_id, related_faq_id)
);
COMMENT ON TABLE faq_related IS 'FAQ 关联关系表';

-- FAQ 工单关联表
CREATE TABLE faq_tickets (
    id          SERIAL PRIMARY KEY,
    faq_id      INTEGER NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    ticket_id   TEXT NOT NULL,
    UNIQUE(faq_id, ticket_id)
);
COMMENT ON TABLE faq_tickets IS 'FAQ 工单关联表';

-- FAQ 图片追踪表
CREATE TABLE faq_images (
    id              SERIAL PRIMARY KEY,
    faq_id          INTEGER NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    image_url       TEXT NOT NULL,
    alt_text        TEXT,
    is_accessible   BOOLEAN,
    last_checked    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(faq_id, image_url)
);
COMMENT ON TABLE faq_images IS 'FAQ 图片追踪表';

-- FAQ 索引
CREATE INDEX idx_faqs_search ON faqs USING gin(search_vector);
CREATE INDEX idx_faqs_code ON faqs(faq_code);
CREATE INDEX idx_faqs_dept ON faqs(dept);
CREATE INDEX idx_faqs_dept_id ON faqs(dept_id);
CREATE INDEX idx_faqs_module ON faqs(module);
CREATE INDEX idx_faqs_module_id ON faqs(module_id);
CREATE INDEX idx_faqs_scene ON faqs(scene);
CREATE INDEX idx_faqs_status ON faqs(status, is_deleted) WHERE is_deleted = FALSE;
CREATE INDEX idx_faqs_category ON faqs(category_id);
CREATE INDEX idx_faqs_tags ON faqs USING gin(tags);
CREATE INDEX idx_faqs_created ON faqs(create_time);
CREATE INDEX idx_faqs_view ON faqs(view_count DESC);
CREATE INDEX idx_faqs_update_time ON faqs(update_time DESC NULLS LAST) WHERE is_deleted = FALSE;
CREATE INDEX idx_faqs_cat_parent ON faq_categories(parent_id);
CREATE INDEX idx_faq_tags_faq ON faq_tags(faq_id);
CREATE INDEX idx_faq_tags_tag ON faq_tags(tag);
CREATE INDEX idx_faq_related_faq ON faq_related(faq_id);
CREATE INDEX idx_faq_tickets_faq ON faq_tickets(faq_id);
CREATE INDEX idx_faq_tickets_ticket ON faq_tickets(ticket_id);
CREATE INDEX idx_faq_images_faq ON faq_images(faq_id);

-- ----------------------------
-- 3c. 报表表
-- ----------------------------
CREATE TABLE reports (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    week            TEXT,
    year            INTEGER,
    category        TEXT DEFAULT '周报',
    content         TEXT NOT NULL,
    content_hash    TEXT,
    path            TEXT,
    dept_summary    JSONB DEFAULT '{}',
    metrics         JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE,
    search_vector   tsvector
);
COMMENT ON TABLE reports IS '报表表：存储周报/月报/年报';

CREATE INDEX idx_reports_search ON reports USING gin(search_vector);
CREATE INDEX idx_reports_week ON reports(year, week);
CREATE INDEX idx_reports_category ON reports(category);
CREATE INDEX idx_reports_created ON reports(created_at);
CREATE INDEX idx_reports_not_deleted ON reports(is_deleted) WHERE is_deleted = FALSE;

-- ----------------------------
-- 3d. 原始文档表
-- ----------------------------
CREATE TABLE raw_documents (
    id              SERIAL PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,
    filename        TEXT NOT NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    content_hash    TEXT,
    dept            TEXT,
    dept_id         INTEGER REFERENCES departments(id),
    module          TEXT,
    product         TEXT,
    date            TEXT,
    image_count     INTEGER DEFAULT 0,
    imported_at     TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE,
    search_vector   tsvector
);
COMMENT ON TABLE raw_documents IS '原始文档表：存储原始产品文档';

CREATE TABLE raw_document_images (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES raw_documents(id) ON DELETE CASCADE,
    image_url       TEXT NOT NULL,
    alt_text        TEXT,
    is_accessible   BOOLEAN,
    last_checked    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, image_url)
);
COMMENT ON TABLE raw_document_images IS '原始文档图片追踪表';

CREATE INDEX idx_raw_docs_search ON raw_documents USING gin(search_vector);
CREATE INDEX idx_raw_docs_path ON raw_documents(path);
CREATE INDEX idx_raw_docs_dept ON raw_documents(dept);
CREATE INDEX idx_raw_docs_date ON raw_documents(date);
CREATE INDEX idx_raw_docs_not_deleted ON raw_documents(is_deleted) WHERE is_deleted = FALSE;
CREATE INDEX idx_raw_doc_images_doc ON raw_document_images(document_id);

-- ============================================================================
-- 第4层：搜索与反馈 (Search & Feedback)
-- ============================================================================

-- 关键词索引表（旧版，向后兼容）
CREATE TABLE keywords (
    id              SERIAL PRIMARY KEY,
    keyword         TEXT NOT NULL,
    module_id       INTEGER REFERENCES modules(id),
    department      TEXT,
    department_id   INTEGER REFERENCES departments(id),
    domain          TEXT,
    kb_path         TEXT,
    note            TEXT
);
COMMENT ON TABLE keywords IS '全局关键词索引表（旧版，保留兼容）';

-- 关键词实体表 v2
CREATE TABLE keywords_v2 (
    id          SERIAL PRIMARY KEY,
    keyword     TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ,
    is_deleted  BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE keywords_v2 IS '关键词实体表（v2）';

-- 关键词→模块→部门映射表
CREATE TABLE keyword_mappings (
    id              SERIAL PRIMARY KEY,
    keyword_id      INTEGER NOT NULL REFERENCES keywords_v2(id),
    module_id       INTEGER REFERENCES modules(id),
    department_id   INTEGER REFERENCES departments(id),
    department      TEXT,
    domain          TEXT,
    kb_path         TEXT,
    note            TEXT,
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    is_deleted      BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE keyword_mappings IS '关键词映射表（v2）：关键词→模块→部门';

-- 同义词表
CREATE TABLE synonyms (
    id      SERIAL PRIMARY KEY,
    word    TEXT NOT NULL,
    synonym TEXT NOT NULL
);
COMMENT ON TABLE synonyms IS '同义词表：搜索时查询扩展';

-- 搜索反馈表
CREATE TABLE feedback (
    id          SERIAL PRIMARY KEY,
    query       TEXT NOT NULL,
    result_id   TEXT,
    result_path TEXT,
    type        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE feedback IS '搜索反馈表：用户对搜索结果的评价';

-- 搜索统计计数器
CREATE TABLE search_counter (
    key   TEXT PRIMARY KEY,
    value INTEGER DEFAULT 0
);
COMMENT ON TABLE search_counter IS '搜索统计计数器（key-value）';

-- 搜索日志表
CREATE TABLE search_logs (
    id              SERIAL PRIMARY KEY,
    query           TEXT NOT NULL,
    normalized_q    TEXT,
    result_count    INTEGER DEFAULT 0,
    has_answer      BOOLEAN DEFAULT FALSE,
    search_time_ms  INTEGER,
    source          TEXT DEFAULT 'web',
    user_agent      TEXT,
    ip_hash         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE search_logs IS '搜索日志表';

-- 索引
CREATE INDEX idx_keywords_keyword ON keywords(keyword);
CREATE INDEX idx_keywords_module ON keywords(module_id);
CREATE INDEX idx_keywords_dept_id ON keywords(department_id);
CREATE INDEX idx_keywords_kw_trgm ON keywords USING gin (keyword gin_trgm_ops);
CREATE INDEX idx_keywords_v2_kw ON keywords_v2(keyword) WHERE is_deleted = FALSE;
CREATE INDEX idx_kwm_keyword ON keyword_mappings(keyword_id);
CREATE INDEX idx_kwm_module ON keyword_mappings(module_id);
CREATE INDEX idx_kwm_dept ON keyword_mappings(department_id);
CREATE INDEX idx_kwm_not_deleted ON keyword_mappings(keyword_id) WHERE is_deleted = FALSE;
CREATE UNIQUE INDEX uq_km_kw_mod_active ON keyword_mappings(keyword_id, module_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_synonyms_word ON synonyms(word);
CREATE INDEX idx_synonyms_syn ON synonyms(synonym);
CREATE INDEX idx_feedback_query ON feedback(query);
CREATE INDEX idx_feedback_type ON feedback(type);
CREATE INDEX idx_feedback_created ON feedback(created_at);
CREATE INDEX idx_search_logs_created ON search_logs(created_at);
CREATE INDEX idx_search_logs_source ON search_logs(source);

-- ============================================================================
-- 第5层：用户与配置 (Users & Config)
-- ============================================================================

-- 用户表
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE users IS '用户表';

-- 每用户 AI 配置表
CREATE TABLE ai_configs (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    model           TEXT NOT NULL DEFAULT 'deepseek-v4-pro',
    base_url        TEXT NOT NULL DEFAULT '',
    api_key_enc     TEXT NOT NULL DEFAULT '',
    provider        TEXT NOT NULL DEFAULT 'deepseek',
    protocol        TEXT NOT NULL DEFAULT 'anthropic',
    max_tokens      INTEGER NOT NULL DEFAULT 4096,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE ai_configs IS '每用户 AI 模型配置表';

-- 审计日志表
CREATE TABLE audit_logs (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(100) NOT NULL,
    action      VARCHAR(50) NOT NULL,
    target      VARCHAR(200),
    detail      TEXT,
    ip          VARCHAR(50),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE audit_logs IS '审计日志表：管理操作追踪';

-- 系统配置表
CREATE TABLE system_settings (
    key         VARCHAR(100) PRIMARY KEY,
    value       TEXT NOT NULL,
    description VARCHAR(500),
    category    VARCHAR(50) DEFAULT 'general',
    updated_by  VARCHAR(100),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE system_settings IS '系统配置表：运行时可配置项';

-- 索引
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_ai_configs_username ON ai_configs(username);
CREATE INDEX idx_audit_time ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_user ON audit_logs(username);

-- ============================================================================
-- 触发器：自动更新 search_vector（全文搜索索引）
-- ============================================================================

CREATE OR REPLACE FUNCTION documents_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.content, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_documents_search
    BEFORE INSERT OR UPDATE OF title, content ON documents
    FOR EACH ROW EXECUTE FUNCTION documents_search_update();

CREATE OR REPLACE FUNCTION faqs_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.faq_title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.faq_question, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(NEW.faq_answer, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_faqs_search
    BEFORE INSERT OR UPDATE OF faq_title, faq_question, faq_answer ON faqs
    FOR EACH ROW EXECUTE FUNCTION faqs_search_update();

CREATE OR REPLACE FUNCTION reports_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.content, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_reports_search
    BEFORE INSERT OR UPDATE OF title, content ON reports
    FOR EACH ROW EXECUTE FUNCTION reports_search_update();

CREATE OR REPLACE FUNCTION raw_documents_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.content, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_raw_documents_search
    BEFORE INSERT OR UPDATE OF title, content ON raw_documents
    FOR EACH ROW EXECUTE FUNCTION raw_documents_search_update();

-- ============================================================================
-- 触发器：自动更新 updated_at 时间戳
-- ============================================================================

CREATE OR REPLACE FUNCTION update_timestamp() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_modules_updated
    BEFORE UPDATE ON modules
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trg_documents_updated
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trg_faqs_updated
    BEFORE UPDATE ON faqs
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trg_reports_updated
    BEFORE UPDATE ON reports
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ============================================================================
-- 视图：统一搜索（跨文档/FAQ/报表/原始文档）
-- ============================================================================

CREATE OR REPLACE VIEW unified_search AS
SELECT
    'document' AS source_type,
    id, title, content, dept, module, search_vector, updated_at
FROM documents WHERE is_deleted = FALSE
UNION ALL
SELECT
    'faq' AS source_type,
    id, faq_title AS title,
    COALESCE(faq_question, '') || ' ' || COALESCE(faq_answer, '') AS content,
    dept, module, search_vector, update_time AS updated_at
FROM faqs WHERE is_deleted = FALSE AND status = 1
UNION ALL
SELECT
    'report' AS source_type,
    id, title, content, '' AS dept, '' AS module, search_vector, updated_at
FROM reports WHERE is_deleted = FALSE
UNION ALL
SELECT
    'raw_doc' AS source_type,
    id, title, content, dept, module, search_vector, imported_at AS updated_at
FROM raw_documents WHERE is_deleted = FALSE;
COMMENT ON VIEW unified_search IS '统一搜索视图：跨四张表全文搜索';

-- ============================================================================
-- 视图：知识库仪表盘统计
-- ============================================================================

CREATE OR REPLACE VIEW dashboard_stats AS
SELECT
    (SELECT COUNT(*) FROM documents WHERE is_deleted = FALSE) AS doc_count,
    (SELECT COUNT(*) FROM faqs WHERE is_deleted = FALSE AND status = 1) AS faq_count,
    (SELECT COUNT(*) FROM reports WHERE is_deleted = FALSE) AS report_count,
    (SELECT COUNT(*) FROM raw_documents WHERE is_deleted = FALSE) AS raw_doc_count,
    (SELECT COUNT(*) FROM modules WHERE is_deleted = FALSE) AS module_count,
    (SELECT COUNT(*) FROM keywords) AS keyword_count,
    (SELECT COUNT(*) FROM synonyms) AS synonym_count,
    (SELECT COUNT(*) FROM document_images) AS image_count;
COMMENT ON VIEW dashboard_stats IS '仪表盘统计视图';

-- ============================================================================
-- 初始数据：默认产品线
-- ============================================================================

INSERT INTO product_lines (name) VALUES
    ('浙里报'), ('徽报账'), ('免疫规划'), ('电子档案'),
    ('数字化支撑'), ('孵化业务'), ('直属')
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- 完成
-- ============================================================================

-- 校验：统计各表数量
SELECT 'tables' AS item, COUNT(*) AS cnt FROM information_schema.tables
 WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
