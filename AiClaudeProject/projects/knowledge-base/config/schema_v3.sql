-- ============================================================================
-- 智能知识库中台 · PostgreSQL 数据库完整 Schema v3.0
-- 日期: 2026-08-27
-- 适用: PostgreSQL 15+
--
-- 设计原则:
--   1. 每个 .md 文件对应一条数据库记录，content 保存完整 Markdown
--   2. JSON 数组拆为关联表，支持高效查询和索引
--   3. 所有 TEXT 外键改为真正的 FK 约束
--   4. PostgreSQL tsvector + GIN 索引支持全文搜索
--   5. 图片 URL 单独追踪，支持完整性校验
--   6. 软删除 + 时间戳，支持审计追溯
-- ============================================================================

-- 启用 pg_trgm 扩展（用于模糊匹配索引）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- 第1层：组织架构 (Organization)
-- 已存在且有数据，保留不变，仅优化索引
-- ============================================================================

-- 部门层级表（已有 188 行数据，来源于组织架构同步）
-- 注意：此表已有数据，不执行 DROP，仅添加缺失的索引

-- 字段注释（已有字段）

CREATE INDEX IF NOT EXISTS idx_dept_parent ON departments(parent_id);
CREATE INDEX IF NOT EXISTS idx_dept_level ON departments(level);
CREATE INDEX IF NOT EXISTS idx_dept_name_trgm ON departments USING gin (name gin_trgm_ops);

-- 产品线表（已有 41 行数据）


-- 产品表（已有数据）


CREATE INDEX IF NOT EXISTS idx_prod_line ON products(product_line_id);

-- ============================================================================
-- 第2层：业务模块 (Modules)
-- 迁移自 data/modules/*.md（71个模块定义文件）
-- ============================================================================

-- 删除旧表重建（旧表为空，安全）
DROP TABLE IF EXISTS module_menus CASCADE;
DROP TABLE IF EXISTS module_aliases CASCADE;
DROP TABLE IF EXISTS module_keywords CASCADE;
DROP TABLE IF EXISTS modules CASCADE;

-- 模块主表
CREATE TABLE modules (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,          -- 模块名称
    department_id   INTEGER REFERENCES departments(id),  -- 所属二级部门
    product_id      INTEGER REFERENCES products(id),     -- 所属产品
    dev_owner       TEXT,           -- 研发负责人
    module_owner    TEXT,           -- 模块负责人
    appendix        TEXT,           -- 附录编号（周报归属）
    business_domain TEXT,           -- 业务域，如"免疫规划组"
    associated_dept TEXT,           -- 关联部门（跨部门交叉模块）
    sub_dept        TEXT,           -- 子部门
    description     TEXT,           -- 模块描述/说明
    path            TEXT,           -- 相对于 knowledge-base/ 的 .md 文件路径
    dir_name        TEXT,           -- 文件所在目录名
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE
);
-- 表注释

-- 模块菜单映射表（一对多：一个模块可出现在多个菜单位置）

CREATE TABLE module_menus (
    id          SERIAL PRIMARY KEY,
    module_id   INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    level1      TEXT,               -- 一级菜单
    level2      TEXT,               -- 二级菜单
    level3      TEXT,               -- 三级菜单
    sort_order  INTEGER DEFAULT 0  -- 排序
);
COMMENT ON TABLE module_menus IS '模块菜单映射表：记录模块在系统菜单中的位置，一个模块可出现在多个菜单路径下';
COMMENT ON COLUMN module_menus.id IS '菜单映射唯一ID（自增主键）';
COMMENT ON COLUMN module_menus.module_id IS '所属模块ID，引用 modules.id，级联删除';
COMMENT ON COLUMN module_menus.level1 IS '一级菜单名称，如"便民服务"、"电子档案【新】"';
COMMENT ON COLUMN module_menus.level2 IS '二级菜单名称，如"接种异常反馈"、"档案保管"';
COMMENT ON COLUMN module_menus.level3 IS '三级菜单名称，如"资料采集/实体移交/移交记录"';
COMMENT ON COLUMN module_menus.sort_order IS '排序序号，数字越小越靠前';
-- 模块别名表（一对多：用于搜索时匹配不同叫法）

CREATE TABLE module_aliases (
    id          SERIAL PRIMARY KEY,
    module_id   INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    alias       TEXT NOT NULL
);
COMMENT ON TABLE module_aliases IS '模块别名表：同一个模块可能有多个称呼，如"浙里报"也称"zhelibao"';
COMMENT ON COLUMN module_aliases.id IS '别名唯一ID（自增主键）';
COMMENT ON COLUMN module_aliases.module_id IS '所属模块ID，引用 modules.id，级联删除';
COMMENT ON COLUMN module_aliases.alias IS '模块别名，如"浙里报"的别名"zhelibao"、"ZLB"';
-- 模块关键词关联表（多对多：模块↔关键词）

CREATE TABLE module_keywords (
    id          SERIAL PRIMARY KEY,
    module_id   INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    keyword     TEXT NOT NULL,
    UNIQUE(module_id, keyword)
);
COMMENT ON TABLE module_keywords IS '模块关键词关联表：记录每个模块的关键词，用于搜索匹配，多对多关系';
COMMENT ON COLUMN module_keywords.id IS '关键词关联唯一ID（自增主键）';
COMMENT ON COLUMN module_keywords.module_id IS '所属模块ID，引用 modules.id，级联删除';
COMMENT ON COLUMN module_keywords.keyword IS '关键词文本，如"预防接种"、"接种记录"、"免疫规划"';
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
-- 3a. 知识文档表 (knowledge/)
-- 迁移自 data/knowledge/*.md，73篇
-- ----------------------------
DROP TABLE IF EXISTS document_images CASCADE;
DROP TABLE IF EXISTS document_departments CASCADE;
DROP TABLE IF EXISTS documents CASCADE;

-- 文档主表

CREATE TABLE documents (
    id              SERIAL PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,       -- 文件路径（唯一标识）
    filename        TEXT NOT NULL,              -- 文件名
    title           TEXT NOT NULL,              -- 文档标题
    content         TEXT NOT NULL,              -- 完整 Markdown 内容（含图片）
    content_hash    TEXT,                       -- SHA256 哈希
    word_count      INTEGER DEFAULT 0,          -- 字数统计
    dept            TEXT,                       -- 部门名（冗余，便于查询）
    dept_id         INTEGER REFERENCES departments(id),
    module          TEXT,                       -- 模块名（冗余，便于查询）
    module_id       INTEGER REFERENCES modules(id),
    product         TEXT,                       -- 产品名（冗余，便于查询）
    product_id      INTEGER REFERENCES products(id),
    product_line    TEXT,                       -- 产品线名（冗余，便于查询）
    product_line_id INTEGER REFERENCES product_lines(id),
    date            TEXT,                       -- 版本日期
    appendix        TEXT,                       -- 附录
    keywords        TEXT[],                     -- PostgreSQL 数组
    related_modules TEXT[],                     -- 关联模块名数组
    imported_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE documents IS '知识文档表：存储产品知识库文档（knowledge/目录），每个.md文件对应一条记录，含完整Markdown内容';
COMMENT ON COLUMN documents.id IS '文档唯一ID（自增主键）';
COMMENT ON COLUMN documents.path IS '文件相对路径，唯一标识，如 data/knowledge/immunization/vaccination/预防接种-xxx.md';
COMMENT ON COLUMN documents.filename IS '文件名（不含路径），如 预防接种-20260101-预防接种-菜单路径.md';
COMMENT ON COLUMN documents.title IS '文档标题，从 frontmatter 的 title 字段提取';
COMMENT ON COLUMN documents.content IS '完整 Markdown 内容（含图片语法 ![](url)），保持原始格式';
COMMENT ON COLUMN documents.content_hash IS '内容 SHA256 哈希值，用于增量更新检测，避免重复处理';
COMMENT ON COLUMN documents.word_count IS '文档字数统计（不含 Markdown 标记和图片链接）';
COMMENT ON COLUMN documents.dept IS '所属部门名称，如"免疫规划组"、"数智财务组"（冗余字段，便于查询）';
COMMENT ON COLUMN documents.dept_id IS '所属部门ID，引用 departments.id';
COMMENT ON COLUMN documents.module IS '产品模块名称，如"预防接种"、"浙里报"（冗余字段，便于查询）';
COMMENT ON COLUMN documents.module_id IS '所属模块ID，引用 modules.id';
COMMENT ON COLUMN documents.product IS '产品名称，如"疫苗"、"数智财务"（冗余字段，便于查询）';
COMMENT ON COLUMN documents.product_id IS '所属产品ID，引用 products.id';
COMMENT ON COLUMN documents.product_line IS '产品线名称，如"免疫规划"、"数智财务"（冗余字段，便于查询）';
COMMENT ON COLUMN documents.product_line_id IS '所属产品线ID，引用 product_lines.id';
COMMENT ON COLUMN documents.date IS '文档版本日期，如 20250429、20260512';
COMMENT ON COLUMN documents.appendix IS '周报附录归属，如"附录1"、"附录2"';
COMMENT ON COLUMN documents.keywords IS '文档关键词数组（PostgreSQL text[]），如 {接种,预防接种,免疫规划}';
COMMENT ON COLUMN documents.related_modules IS '关联模块名数组，如 {政府投资,运营后台}';
COMMENT ON COLUMN documents.imported_at IS '文档首次导入时间';
COMMENT ON COLUMN documents.updated_at IS '文档最后更新时间';
COMMENT ON COLUMN documents.is_deleted IS '软删除标记：false=正常，true=已删除';
-- 文档-部门关联表（多对多：一文档可归属多个部门）

CREATE TABLE document_departments (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    department_id   INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    is_primary      BOOLEAN DEFAULT FALSE,
    source          TEXT DEFAULT 'auto',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, department_id)
);
COMMENT ON TABLE document_departments IS '文档-部门关联表：支持一个文档关联多个部门（多对多），如某文档同时属于免疫规划组和数字化支撑组';
COMMENT ON COLUMN document_departments.id IS '关联记录唯一ID（自增主键）';
COMMENT ON COLUMN document_departments.document_id IS '文档ID，引用 documents.id，级联删除';
COMMENT ON COLUMN document_departments.department_id IS '部门ID，引用 departments.id，级联删除';
COMMENT ON COLUMN document_departments.is_primary IS '是否主部门：true=主归属部门，false=次要关联部门';
COMMENT ON COLUMN document_departments.source IS '关联来源：auto=自动解析，manual=人工标注';
COMMENT ON COLUMN document_departments.created_at IS '关联创建时间';
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
COMMENT ON TABLE document_images IS '文档图片追踪表：记录文档中引用的所有图片URL，用于完整性校验和可访问性检测';
COMMENT ON COLUMN document_images.id IS '图片记录唯一ID（自增主键）';
COMMENT ON COLUMN document_images.document_id IS '所属文档ID，引用 documents.id，级联删除';
COMMENT ON COLUMN document_images.image_url IS '图片原始URL，如 https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/...';
COMMENT ON COLUMN document_images.alt_text IS '图片替代文本（Markdown 中 ![](url) 的 alt 部分）';
COMMENT ON COLUMN document_images.image_hash IS '图片内容 SHA256 哈希值（本地缓存后计算）';
COMMENT ON COLUMN document_images.file_size IS '图片文件大小（字节）';
COMMENT ON COLUMN document_images.is_accessible IS '图片是否可访问：NULL=未检测，true=可访问，false=不可访问';
COMMENT ON COLUMN document_images.last_checked IS '最后一次可访问性检测时间';
COMMENT ON COLUMN document_images.created_at IS '记录创建时间';
-- 全文搜索向量列 + 触发器
ALTER TABLE documents ADD COLUMN search_vector tsvector;
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
CREATE INDEX idx_doc_dept_doc ON document_departments(document_id);
CREATE INDEX idx_doc_dept_dept ON document_departments(department_id);
CREATE INDEX idx_doc_images_doc ON document_images(document_id);
CREATE INDEX idx_doc_images_url ON document_images(image_url);

-- ----------------------------
-- 3b. FAQ 知识库 (faq/)
-- 迁移自 data/faq/*.md，358篇
-- ----------------------------
DROP TABLE IF EXISTS faq_tags CASCADE;
DROP TABLE IF EXISTS faq_related CASCADE;
DROP TABLE IF EXISTS faq_tickets CASCADE;
DROP TABLE IF EXISTS faq_images CASCADE;
DROP TABLE IF EXISTS faqs CASCADE;
DROP TABLE IF EXISTS faq_categories CASCADE;

-- FAQ 分类表

CREATE TABLE faq_categories (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,                  -- 分类名称
    parent_id   INTEGER REFERENCES faq_categories(id),
    dept        TEXT,                           -- 所属部门
    sub_module  TEXT,                           -- 子模块
    level       INTEGER DEFAULT 1,              -- 层级
    sort_order  INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE faq_categories IS 'FAQ 分类表：FAQ 的层级分类目录，如"接种记录"、"数据同步"等';
COMMENT ON COLUMN faq_categories.id IS '分类唯一ID（自增主键）';
COMMENT ON COLUMN faq_categories.name IS '分类名称，如"接种记录"、"报销流程"';
COMMENT ON COLUMN faq_categories.parent_id IS '上级分类ID，顶级分类为NULL，引用 faq_categories.id';
COMMENT ON COLUMN faq_categories.dept IS '所属部门名称';
COMMENT ON COLUMN faq_categories.sub_module IS '所属子模块名称';
COMMENT ON COLUMN faq_categories.level IS '分类层级：1=一级，2=二级';
COMMENT ON COLUMN faq_categories.sort_order IS '排序序号，数字越小越靠前';
COMMENT ON COLUMN faq_categories.created_at IS '创建时间';
-- FAQ 主表

CREATE TABLE faqs (
    id              SERIAL PRIMARY KEY,
    faq_code        TEXT NOT NULL UNIQUE,       -- FAQ 编码
    faq_title       TEXT NOT NULL,              -- FAQ 标题
    faq_question    TEXT NOT NULL,              -- 问题描述
    faq_answer      TEXT NOT NULL,              -- 答案/解决方案
    content         TEXT,                       -- 完整 Markdown 原文
    category_id     INTEGER REFERENCES faq_categories(id),
    dept            TEXT NOT NULL,              -- 部门名
    dept_id         INTEGER REFERENCES departments(id),
    sub_module      TEXT DEFAULT '',            -- 子模块
    module          TEXT DEFAULT '',            -- 产品模块
    module_id       INTEGER REFERENCES modules(id),
    scene           TEXT DEFAULT '',            -- 业务场景
    tags            TEXT[] DEFAULT '{}',        -- 关键词标签数组
    status          SMALLINT DEFAULT 0,         -- 0草稿 1已发布 2归档 3禁用
    sort_num        INTEGER DEFAULT 0,
    view_count      INTEGER DEFAULT 0,
    source_file_name TEXT DEFAULT '',           -- 原始文件名
    file_path       TEXT DEFAULT '',            -- 文件路径
    version_from    TEXT DEFAULT '',            -- 版本来源
    create_user     TEXT DEFAULT '',
    update_user     TEXT DEFAULT '',
    create_time     TIMESTAMPTZ DEFAULT NOW(),
    update_time     TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE faqs IS 'FAQ 知识库主表：存储 FAQ 问答条目，每个 .md 文件对应一条记录，含完整问题描述和解决方案';
COMMENT ON COLUMN faqs.id IS 'FAQ 唯一ID（自增主键）';
COMMENT ON COLUMN faqs.faq_code IS 'FAQ 编码，唯一标识，如 FAQ-YM-YM-002（部门-子模块-序号）';
COMMENT ON COLUMN faqs.faq_title IS 'FAQ 标题，如"接种记录同步延迟"';
COMMENT ON COLUMN faqs.faq_question IS '问题描述（纯文本），用于搜索匹配和列表展示';
COMMENT ON COLUMN faqs.faq_answer IS '答案/解决方案（完整 Markdown），含排查步骤、关联知识等';
COMMENT ON COLUMN faqs.content IS '完整 Markdown 原文（含 frontmatter），保留原始格式备份';
COMMENT ON COLUMN faqs.category_id IS '所属分类ID，引用 faq_categories.id';
COMMENT ON COLUMN faqs.dept IS '所属部门名称，如"免疫规划组"、"数智财务组"';
COMMENT ON COLUMN faqs.dept_id IS '所属部门ID，引用 departments.id';
COMMENT ON COLUMN faqs.sub_module IS '子模块名称，如"免疫规划"、"浙里报"';
COMMENT ON COLUMN faqs.module IS '产品模块名称，如"预防接种"、"报销管理"';
COMMENT ON COLUMN faqs.module_id IS '所属模块ID，引用 modules.id';
COMMENT ON COLUMN faqs.scene IS '业务场景，如"预防接种"、"入学入托查验"、"报销审批"';
COMMENT ON COLUMN faqs.tags IS '关键词标签数组（PostgreSQL text[]），如 {接种,同步,延迟,省平台}';
COMMENT ON COLUMN faqs.status IS 'FAQ 状态：0=草稿，1=已发布，2=归档，3=禁用';
COMMENT ON COLUMN faqs.sort_num IS '排序序号，同分类下数字越小越靠前';
COMMENT ON COLUMN faqs.view_count IS '浏览次数，用于热门排序';
COMMENT ON COLUMN faqs.source_file_name IS '原始 .md 文件名，用于追溯';
COMMENT ON COLUMN faqs.file_path IS '文件相对路径，如 data/faq/immunization/immunization/接种记录同步延迟.md';
COMMENT ON COLUMN faqs.version_from IS '版本来源，如"2025-Q2"';
COMMENT ON COLUMN faqs.create_user IS '创建人';
COMMENT ON COLUMN faqs.update_user IS '最后更新人';
COMMENT ON COLUMN faqs.create_time IS '创建时间';
COMMENT ON COLUMN faqs.update_time IS '最后更新时间';
COMMENT ON COLUMN faqs.is_deleted IS '软删除标记：false=正常，true=已删除';
-- FAQ 标签关联表（与 tags[] 数组同步，用于精确查询）

CREATE TABLE faq_tags (
    id      SERIAL PRIMARY KEY,
    faq_id  INTEGER NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    UNIQUE(faq_id, tag)
);
COMMENT ON TABLE faq_tags IS 'FAQ 标签关联表：与 faqs.tags 数组同步，用于精确的标签查询和统计分析';
COMMENT ON COLUMN faq_tags.id IS '标签关联唯一ID（自增主键）';
COMMENT ON COLUMN faq_tags.faq_id IS 'FAQ ID，引用 faqs.id，级联删除';
COMMENT ON COLUMN faq_tags.tag IS '标签文本，如"接种"、"同步"、"延迟"';
-- FAQ 关联关系表（FAQ 之间的相互引用）

CREATE TABLE faq_related (
    id              SERIAL PRIMARY KEY,
    faq_id          INTEGER NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    related_faq_id  INTEGER NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    UNIQUE(faq_id, related_faq_id)
);
COMMENT ON TABLE faq_related IS 'FAQ 关联关系表：记录 FAQ 之间的相互引用关系，如"接种记录同步延迟"关联"接种记录无法保存"';
COMMENT ON COLUMN faq_related.id IS '关联记录唯一ID（自增主键）';
COMMENT ON COLUMN faq_related.faq_id IS '源 FAQ ID，引用 faqs.id，级联删除';
COMMENT ON COLUMN faq_related.related_faq_id IS '被关联的 FAQ ID，引用 faqs.id，级联删除';
-- FAQ 工单关联表

CREATE TABLE faq_tickets (
    id          SERIAL PRIMARY KEY,
    faq_id      INTEGER NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    ticket_id   TEXT NOT NULL,                  -- 工单号
    UNIQUE(faq_id, ticket_id)
);
COMMENT ON TABLE faq_tickets IS 'FAQ 工单关联表：记录 FAQ 关联的客服工单号，用于追溯问题来源';
COMMENT ON COLUMN faq_tickets.id IS '工单关联唯一ID（自增主键）';
COMMENT ON COLUMN faq_tickets.faq_id IS 'FAQ ID，引用 faqs.id，级联删除';
COMMENT ON COLUMN faq_tickets.ticket_id IS '工单号，如"202608201104285945903"';
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
COMMENT ON TABLE faq_images IS 'FAQ 图片追踪表：记录 FAQ 文档中引用的图片URL，用于完整性校验';
COMMENT ON COLUMN faq_images.id IS '图片记录唯一ID（自增主键）';
COMMENT ON COLUMN faq_images.faq_id IS 'FAQ ID，引用 faqs.id，级联删除';
COMMENT ON COLUMN faq_images.image_url IS '图片原始URL';
COMMENT ON COLUMN faq_images.alt_text IS '图片替代文本';
COMMENT ON COLUMN faq_images.is_accessible IS '图片是否可访问：NULL=未检测，true=可访问，false=不可访问';
COMMENT ON COLUMN faq_images.last_checked IS '最后检测时间';
COMMENT ON COLUMN faq_images.created_at IS '记录创建时间';
-- 全文搜索
ALTER TABLE faqs ADD COLUMN search_vector tsvector;
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
CREATE INDEX idx_faqs_cat_parent ON faq_categories(parent_id);
CREATE INDEX idx_faq_tags_faq ON faq_tags(faq_id);
CREATE INDEX idx_faq_tags_tag ON faq_tags(tag);
CREATE INDEX idx_faq_related_faq ON faq_related(faq_id);
CREATE INDEX idx_faq_tickets_faq ON faq_tickets(faq_id);
CREATE INDEX idx_faq_tickets_ticket ON faq_tickets(ticket_id);
CREATE INDEX idx_faq_images_faq ON faq_images(faq_id);

-- ----------------------------
-- 3c. 报表表 (reports/)
-- 迁移自 data/reports/*.md，12篇
-- ----------------------------
DROP TABLE IF EXISTS reports CASCADE;


CREATE TABLE reports (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,              -- 报表标题
    week            TEXT,                       -- 周次
    year            INTEGER,                    -- 年份
    category        TEXT DEFAULT '周报',        -- 周报 | 月报 | 年报
    content         TEXT NOT NULL,              -- 完整 Markdown 内容
    content_hash    TEXT,                       -- SHA256
    path            TEXT,                       -- 文件路径
    dept_summary    JSONB DEFAULT '{}',         -- 各部门摘要
    metrics         JSONB DEFAULT '{}',         -- 报表指标
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE reports IS '报表表：存储周报/月报/年报，每个 .md 文件对应一条记录，含完整内容和指标数据';
COMMENT ON COLUMN reports.id IS '报表唯一ID（自增主键）';
COMMENT ON COLUMN reports.title IS '报表标题，如"2026-W21 技术支持周报"';
COMMENT ON COLUMN reports.week IS '周次标识，如"2026-W21"、"W21"';
COMMENT ON COLUMN reports.year IS '年份，如 2026';
COMMENT ON COLUMN reports.category IS '报表类别：周报、月报、年报';
COMMENT ON COLUMN reports.content IS '完整 Markdown 内容，含所有表格和格式化文本';
COMMENT ON COLUMN reports.content_hash IS '内容 SHA256 哈希值，用于增量更新检测';
COMMENT ON COLUMN reports.path IS '文件相对路径，如 data/reports/weekly/2026-w21-技术支持周报.md';
COMMENT ON COLUMN reports.dept_summary IS '各部门摘要（JSONB），如 {"免疫规划组": "工单4个...", "数智财务组": "..."}';
COMMENT ON COLUMN reports.metrics IS '报表指标数据（JSONB），如 {"total_tickets": 136, "p1_count": 0, "two_hour_rate": "100%"}';
COMMENT ON COLUMN reports.created_at IS '创建时间';
COMMENT ON COLUMN reports.updated_at IS '最后更新时间';
COMMENT ON COLUMN reports.is_deleted IS '软删除标记：false=正常，true=已删除';
ALTER TABLE reports ADD COLUMN search_vector tsvector;
CREATE INDEX idx_reports_search ON reports USING gin(search_vector);
CREATE INDEX idx_reports_week ON reports(year, week);
CREATE INDEX idx_reports_category ON reports(category);
CREATE INDEX idx_reports_created ON reports(created_at);
CREATE INDEX idx_reports_not_deleted ON reports(is_deleted) WHERE is_deleted = FALSE;

-- ----------------------------
-- 3d. 原始文档表 (raw-docs/)
-- 迁移自 data/raw-docs/*.md，70篇
-- ----------------------------
DROP TABLE IF EXISTS raw_document_images CASCADE;
DROP TABLE IF EXISTS raw_documents CASCADE;


CREATE TABLE raw_documents (
    id              SERIAL PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,       -- 文件路径
    filename        TEXT NOT NULL,              -- 文件名
    title           TEXT NOT NULL,              -- 文档标题
    content         TEXT NOT NULL,              -- 完整 Markdown
    content_hash    TEXT,                       -- SHA256
    dept            TEXT,                       -- 部门
    dept_id         INTEGER REFERENCES departments(id),
    module          TEXT,                       -- 模块
    product         TEXT,                       -- 产品
    date            TEXT,                       -- 日期
    image_count     INTEGER DEFAULT 0,          -- 图片数量
    imported_at     TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE raw_documents IS '原始文档表：存储原始产品文档（raw-docs/目录），保留产品需求的原始版本记录';
COMMENT ON COLUMN raw_documents.id IS '原始文档唯一ID（自增主键）';
COMMENT ON COLUMN raw_documents.path IS '文件相对路径，唯一标识';
COMMENT ON COLUMN raw_documents.filename IS '文件名（不含路径）';
COMMENT ON COLUMN raw_documents.title IS '文档标题，从 Markdown 第一个 # 标题提取';
COMMENT ON COLUMN raw_documents.content IS '完整 Markdown 内容';
COMMENT ON COLUMN raw_documents.content_hash IS '内容 SHA256 哈希值';
COMMENT ON COLUMN raw_documents.dept IS '部门名称（从文件路径推断）';
COMMENT ON COLUMN raw_documents.dept_id IS '部门ID，引用 departments.id';
COMMENT ON COLUMN raw_documents.module IS '模块名称（从文件路径推断）';
COMMENT ON COLUMN raw_documents.product IS '产品名称（从文件路径推断）';
COMMENT ON COLUMN raw_documents.date IS '文档日期';
COMMENT ON COLUMN raw_documents.image_count IS '文档中引用的图片数量';
COMMENT ON COLUMN raw_documents.imported_at IS '导入时间';
COMMENT ON COLUMN raw_documents.is_deleted IS '软删除标记：false=正常，true=已删除';
-- 原始文档图片追踪表

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
COMMENT ON TABLE raw_document_images IS '原始文档图片追踪表：记录原始文档中引用的图片URL';
COMMENT ON COLUMN raw_document_images.id IS '图片记录唯一ID（自增主键）';
COMMENT ON COLUMN raw_document_images.document_id IS '原始文档ID，引用 raw_documents.id，级联删除';
COMMENT ON COLUMN raw_document_images.image_url IS '图片原始URL';
COMMENT ON COLUMN raw_document_images.alt_text IS '图片替代文本';
COMMENT ON COLUMN raw_document_images.is_accessible IS '图片是否可访问：NULL=未检测，true=可访问，false=不可访问';
COMMENT ON COLUMN raw_document_images.last_checked IS '最后检测时间';
COMMENT ON COLUMN raw_document_images.created_at IS '记录创建时间';
ALTER TABLE raw_documents ADD COLUMN search_vector tsvector;
CREATE INDEX idx_raw_docs_search ON raw_documents USING gin(search_vector);
CREATE INDEX idx_raw_docs_path ON raw_documents(path);
CREATE INDEX idx_raw_docs_dept ON raw_documents(dept);
CREATE INDEX idx_raw_docs_date ON raw_documents(date);
CREATE INDEX idx_raw_docs_not_deleted ON raw_documents(is_deleted) WHERE is_deleted = FALSE;
CREATE INDEX idx_raw_doc_images_doc ON raw_document_images(document_id);

-- ============================================================================
-- 第4层：搜索与反馈 (Search & Feedback)
-- 已存在且有数据，仅优化
-- ============================================================================

-- 全局关键词索引表（已有 3404 行数据，保留并优化）

ALTER TABLE keywords ADD COLUMN IF NOT EXISTS department_id INTEGER REFERENCES departments(id);
CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_keywords_module ON keywords(module_id);
CREATE INDEX IF NOT EXISTS idx_keywords_dept_id ON keywords(department_id);
CREATE INDEX IF NOT EXISTS idx_keywords_kw_trgm ON keywords USING gin (keyword gin_trgm_ops);

-- 同义词表（已有 153 行数据，保留）

CREATE INDEX IF NOT EXISTS idx_synonyms_word ON synonyms(word);
CREATE INDEX IF NOT EXISTS idx_synonyms_syn ON synonyms(synonym);

-- 搜索反馈表（已有 4 行数据，保留）

CREATE INDEX IF NOT EXISTS idx_feedback_query ON feedback(query);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(type);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at);

-- 搜索统计表（已有数据，保留）

-- 搜索日志表（新增）

DROP TABLE IF EXISTS search_logs CASCADE;
CREATE TABLE search_logs (
    id              SERIAL PRIMARY KEY,
    query           TEXT NOT NULL,              -- 搜索词
    normalized_q    TEXT,                       -- 纠错后查询
    result_count    INTEGER DEFAULT 0,          -- 结果数
    has_answer      BOOLEAN DEFAULT FALSE,      -- 是否有 AI 答案
    search_time_ms  INTEGER,                    -- 搜索耗时
    source          TEXT DEFAULT 'web',         -- web | api | claude
    user_agent      TEXT,                       -- UA
    ip_hash         TEXT,                       -- IP 哈希
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE search_logs IS '搜索日志表：记录每次搜索请求的详细信息，用于搜索趋势分析和效果评估';
COMMENT ON COLUMN search_logs.id IS '日志记录唯一ID（自增主键）';
COMMENT ON COLUMN search_logs.query IS '用户原始搜索词';
COMMENT ON COLUMN search_logs.normalized_q IS '纠错后的标准化查询词';
COMMENT ON COLUMN search_logs.result_count IS '返回结果数量';
COMMENT ON COLUMN search_logs.has_answer IS '是否有 AI 生成答案';
COMMENT ON COLUMN search_logs.search_time_ms IS '搜索耗时（毫秒）';
COMMENT ON COLUMN search_logs.source IS '搜索来源：web=网页搜索，api=接口调用，claude=AI助手';
COMMENT ON COLUMN search_logs.user_agent IS '客户端 User-Agent';
COMMENT ON COLUMN search_logs.ip_hash IS '客户端 IP 哈希值（隐私保护）';
COMMENT ON COLUMN search_logs.created_at IS '搜索时间';
CREATE INDEX idx_search_logs_created ON search_logs(created_at);
CREATE INDEX idx_search_logs_source ON search_logs(source);

-- ============================================================================
-- 触发器：自动更新 search_vector（全文搜索索引）
-- ============================================================================

-- 文档表
CREATE OR REPLACE FUNCTION documents_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.content, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_search ON documents;
CREATE TRIGGER trg_documents_search
    BEFORE INSERT OR UPDATE OF title, content ON documents
    FOR EACH ROW EXECUTE FUNCTION documents_search_update();

-- FAQ 表
CREATE OR REPLACE FUNCTION faqs_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.faq_title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.faq_question, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(NEW.faq_answer, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_faqs_search ON faqs;
CREATE TRIGGER trg_faqs_search
    BEFORE INSERT OR UPDATE OF faq_title, faq_question, faq_answer ON faqs
    FOR EACH ROW EXECUTE FUNCTION faqs_search_update();

-- 报表表
CREATE OR REPLACE FUNCTION reports_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.content, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reports_search ON reports;
CREATE TRIGGER trg_reports_search
    BEFORE INSERT OR UPDATE OF title, content ON reports
    FOR EACH ROW EXECUTE FUNCTION reports_search_update();

-- 原始文档表
CREATE OR REPLACE FUNCTION raw_documents_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.content, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_raw_documents_search ON raw_documents;
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

DROP TRIGGER IF EXISTS trg_modules_updated ON modules;
CREATE TRIGGER trg_modules_updated
    BEFORE UPDATE ON modules
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

DROP TRIGGER IF EXISTS trg_documents_updated ON documents;
CREATE TRIGGER trg_documents_updated
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

DROP TRIGGER IF EXISTS trg_faqs_updated ON faqs;
CREATE TRIGGER trg_faqs_updated
    BEFORE UPDATE ON faqs
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

DROP TRIGGER IF EXISTS trg_reports_updated ON reports;
CREATE TRIGGER trg_reports_updated
    BEFORE UPDATE ON reports
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ============================================================================
-- 视图：统一搜索（跨文档/FAQ/报表/原始文档）
-- ============================================================================


CREATE OR REPLACE VIEW unified_search AS
SELECT
    'document' AS source_type,
    id,
    title,
    content,
    dept,
    module,
    search_vector,
    updated_at
FROM documents
WHERE is_deleted = FALSE

UNION ALL

SELECT
    'faq' AS source_type,
    id,
    faq_title AS title,
    COALESCE(faq_question, '') || ' ' || COALESCE(faq_answer, '') AS content,
    dept,
    module,
    search_vector,
    update_time AS updated_at
FROM faqs
WHERE is_deleted = FALSE AND status = 1

UNION ALL

SELECT
    'report' AS source_type,
    id,
    title,
    content,
    '' AS dept,
    '' AS module,
    search_vector,
    updated_at
FROM reports
WHERE is_deleted = FALSE

UNION ALL

SELECT
    'raw_doc' AS source_type,
    id,
    title,
    content,
    dept,
    module,
    search_vector,
    imported_at AS updated_at
FROM raw_documents
WHERE is_deleted = FALSE;
COMMENT ON VIEW unified_search IS '统一搜索视图：联合 documents、faqs、reports、raw_documents 四张表，支持跨类型全文搜索';

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
COMMENT ON VIEW dashboard_stats IS '知识库仪表盘统计视图：一行汇总所有核心数据量，用于首页仪表盘展示';
COMMENT ON TABLE departments IS '部门层级表：存储公司组织架构树，支持多级部门';
COMMENT ON COLUMN departments.id IS '部门唯一ID（自增主键）';
COMMENT ON COLUMN departments.name IS '部门名称，如"免疫规划组"、"数智财务组"';
COMMENT ON COLUMN departments.parent_id IS '上级部门ID，顶级部门为NULL，引用 departments.id';
COMMENT ON COLUMN departments.level IS '部门层级：1=一级部门，2=二级部门，3=三级部门';
COMMENT ON COLUMN departments.code IS '部门编码/缩写，如 RLXZB=人力行政部';
COMMENT ON COLUMN departments.dir_name IS '部门拼音目录名，如 mian_yi_gui_hua_zu';
COMMENT ON TABLE product_lines IS '产品线表：业务产品线的顶层分类，如"免疫规划"、"数智财务"、"浙里报"';
COMMENT ON COLUMN product_lines.id IS '产品线唯一ID（自增主键）';
COMMENT ON COLUMN product_lines.name IS '产品线名称，如"免疫规划"、"浙里报"、"电子档案"';
COMMENT ON TABLE products IS '产品表：产品线下的具体产品，如"疫苗"属于"免疫规划"产品线';
COMMENT ON COLUMN products.id IS '产品唯一ID（自增主键）';
COMMENT ON COLUMN products.name IS '产品名称，如"疫苗"、"数智财务"、"电子档案"';
COMMENT ON COLUMN products.product_line_id IS '所属产品线ID，引用 product_lines.id';
COMMENT ON TABLE modules IS '业务模块表：产品的功能模块定义，如"预防接种"、"浙里报"、"电子档案"等，共71个模块';
COMMENT ON COLUMN modules.id IS '模块唯一ID（自增主键）';
COMMENT ON COLUMN modules.name IS '模块名称，如"预防接种"、"浙里报"、"便民服务"、"电子档案"';
COMMENT ON COLUMN modules.department_id IS '所属二级部门ID，引用 departments.id，如 免疫规划组';
COMMENT ON COLUMN modules.product_id IS '所属产品ID，引用 products.id，如 疫苗';
COMMENT ON COLUMN modules.dev_owner IS '研发负责人姓名/花名，如"泠墨"';
COMMENT ON COLUMN modules.module_owner IS '模块负责人姓名/花名，如"守正"、"毛豆"';
COMMENT ON COLUMN modules.appendix IS '周报附录编号，如"附录1"、"附录2"，用于周报归组';
COMMENT ON COLUMN modules.business_domain IS '业务域名称，与所属部门通常一致，用于业务分类';
COMMENT ON COLUMN modules.associated_dept IS '关联部门名称，当模块跨多个部门时记录';
COMMENT ON COLUMN modules.sub_dept IS '子部门/下级部门名称';
COMMENT ON COLUMN modules.description IS '模块描述/说明文字';
COMMENT ON COLUMN modules.path IS '源 .md 文件相对路径，如 data/modules/immunization/预防接种.md';
COMMENT ON COLUMN modules.dir_name IS '文件所在目录名，用于快速定位';
COMMENT ON COLUMN modules.created_at IS '记录创建时间';
COMMENT ON COLUMN modules.updated_at IS '记录最后更新时间';
COMMENT ON COLUMN modules.is_deleted IS '软删除标记：false=正常，true=已删除';
COMMENT ON TABLE keywords IS '全局关键词索引表：关键词到模块的映射，用于搜索时关键词→模块→文档的快速路由，共3404条';
COMMENT ON COLUMN keywords.id IS '关键词记录唯一ID（自增主键）';
COMMENT ON COLUMN keywords.keyword IS '关键词文本，如"预算"、"项目库"、"预算申报"';
COMMENT ON COLUMN keywords.module_id IS '关联模块ID，引用 modules.id';
COMMENT ON COLUMN keywords.department IS '部门名称（冗余字段，便于查询）';
COMMENT ON COLUMN keywords.department_id IS '部门ID，引用 departments.id（新增，替代 TEXT 外键）';
COMMENT ON COLUMN keywords.domain IS '业务域名称';
COMMENT ON COLUMN keywords.kb_path IS '知识库路径，指向具体文档';
COMMENT ON COLUMN keywords.note IS '备注说明';
COMMENT ON TABLE synonyms IS '同义词表：用于搜索时的查询扩展，如"浙里报"的同义词"zhelibao"、"ZLB"';
COMMENT ON COLUMN synonyms.id IS '同义词记录唯一ID（自增主键）';
COMMENT ON COLUMN synonyms.word IS '主词/标准词，如"浙里报"、"报销单"';
COMMENT ON COLUMN synonyms.synonym IS '同义词/别名，如"zhelibao"、"ZLB"、"差旅报销单"';
COMMENT ON TABLE feedback IS '搜索反馈表：记录用户对搜索结果的评价（有用/无用），用于优化搜索排序';
COMMENT ON COLUMN feedback.id IS '反馈记录唯一ID（自增主键）';
COMMENT ON COLUMN feedback.query IS '用户的搜索关键词';
COMMENT ON COLUMN feedback.result_id IS '被评价的搜索结果ID';
COMMENT ON COLUMN feedback.result_path IS '被评价的搜索结果文档路径';
COMMENT ON COLUMN feedback.type IS '反馈类型：useful=有用，not_useful=无用';
COMMENT ON COLUMN feedback.created_at IS '反馈时间';
COMMENT ON TABLE search_counter IS '搜索统计计数器表：key-value 结构，记录各类搜索统计数据';
COMMENT ON COLUMN search_counter.key IS '统计项名称，如 total、today、week、faq_hits';
COMMENT ON COLUMN search_counter.value IS '统计数值';

-- ============================================================================
-- 第5层：自学习闭环 (Self-Learning)
-- ============================================================================

-- 学习候选池：AI 回答 / 用户反馈中有价值的知识，经管理员审核后沉淀为 FAQ
CREATE TABLE IF NOT EXISTS learning_candidates (
    id              SERIAL PRIMARY KEY,
    source          VARCHAR(20) DEFAULT 'ai_answer',   -- ai_answer | ai_extract | user_feedback | manual
    query           TEXT NOT NULL,                      -- 原始用户问题
    answer          TEXT NOT NULL,                      -- AI 回答 / 用户补充的答案
    summary         TEXT DEFAULT '',                     -- AI 提炼的知识摘要（精简版）
    dept            VARCHAR(100) DEFAULT '',             -- 归属部门（AI 推断 + 人工修正）
    module          VARCHAR(200) DEFAULT '',             -- 归属模块
    keywords        TEXT DEFAULT '[]',                   -- 提取的关键词 JSON
    status          INTEGER DEFAULT 0,                  -- 0待审核 / 1已通过 / 2已拒绝 / 3已过期
    review_note     TEXT DEFAULT '',                     -- 审核备注
    reviewed_by     VARCHAR(100) DEFAULT '',
    reviewed_at     VARCHAR(30) DEFAULT '',
    feedback_id     INTEGER DEFAULT 0,                  -- 关联 feedback 表 ID
    session_id      VARCHAR(50) DEFAULT '',              -- 关联会话 ID
    faq_code        VARCHAR(50) DEFAULT '',              -- 通过后生成的 FAQ 编号
    created_by      VARCHAR(100) DEFAULT '',
    create_time     VARCHAR(30) DEFAULT '',
    update_time     VARCHAR(30) DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_lc_status ON learning_candidates(status);
CREATE INDEX IF NOT EXISTS idx_lc_dept ON learning_candidates(dept);
CREATE INDEX IF NOT EXISTS idx_lc_created ON learning_candidates(create_time);

COMMENT ON TABLE learning_candidates IS '学习候选池：AI 回答 / 用户反馈中有价值的知识，经管理员审核后沉淀为 FAQ，实现知识库自学习闭环';
COMMENT ON COLUMN learning_candidates.source IS '知识来源：ai_answer=AI回答，ai_extract=AI自动提取，user_feedback=用户👍反馈，manual=手动提交';
COMMENT ON COLUMN learning_candidates.query IS '原始用户问题';
COMMENT ON COLUMN learning_candidates.answer IS 'AI 回答原文 / 用户补充的答案';
COMMENT ON COLUMN learning_candidates.summary IS 'AI 提炼的知识摘要（去除对话套话，保留核心事实和步骤）';
COMMENT ON COLUMN learning_candidates.dept IS '归属部门（AI 推断 + 人工修正），如"数智财务组"';
COMMENT ON COLUMN learning_candidates.module IS '归属业务模块，如"浙里报"';
COMMENT ON COLUMN learning_candidates.keywords IS '提取的关键词，JSON 数组格式，便于检索';
COMMENT ON COLUMN learning_candidates.status IS '审核状态：0=待审核，1=已通过（已沉淀为FAQ），2=已拒绝，3=已过期';
COMMENT ON COLUMN learning_candidates.review_note IS '审核备注/拒绝原因';
COMMENT ON COLUMN learning_candidates.reviewed_by IS '审核人';
COMMENT ON COLUMN learning_candidates.faq_code IS '审核通过后自动生成的 FAQ 编号，如 FAQ-SZ-ZLB-001';
COMMENT ON COLUMN learning_candidates.feedback_id IS '关联的 feedback 表 ID（来源为用户反馈时）';