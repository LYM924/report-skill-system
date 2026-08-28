-- 知识库数据库 Schema
-- SQLite 数据库，存储结构化数据（模块、关键词、同义词、反馈、统计）
-- 文档内容（.md）保留在文件系统

-- 部门
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES departments(id),
    level INTEGER NOT NULL DEFAULT 1,
    code TEXT,
    dir_name TEXT
);

-- 产品线
CREATE TABLE IF NOT EXISTS product_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- 产品
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    product_line_id INTEGER REFERENCES product_lines(id)
);

-- 模块（替代 data/modules/*.md）
CREATE TABLE IF NOT EXISTS modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    product_id INTEGER REFERENCES products(id),
    dev_owner TEXT,
    module_owner TEXT,
    appendix TEXT,
    business_domain TEXT,
    description TEXT,
    path TEXT
);

-- 模块菜单映射
CREATE TABLE IF NOT EXISTS module_menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_id INTEGER REFERENCES modules(id),
    level1 TEXT,
    level2 TEXT,
    level3 TEXT
);

-- 关键词索引（替代 config/关键词索引.md）
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    module_id INTEGER REFERENCES modules(id),
    department TEXT,
    domain TEXT,
    kb_path TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_keywords_module ON keywords(module_id);

-- 同义词（替代 config/synonyms.json）
CREATE TABLE IF NOT EXISTS synonyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    synonym TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_synonyms_word ON synonyms(word);

-- 搜索反馈
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    result_id TEXT,
    result_path TEXT,
    type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_feedback_query ON feedback(query);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(type);

-- 搜索统计
CREATE TABLE IF NOT EXISTS search_counter (
    key TEXT PRIMARY KEY,
    value INTEGER DEFAULT 0
);

-- 部门数据由 import_departments.py 从组织架构文件导入，不再在此处硬编码默认值

-- 文档-部门关联表（多对多，支持多选部门、三级部门、后续扩展）
CREATE TABLE IF NOT EXISTS document_departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_path TEXT NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    is_primary INTEGER DEFAULT 0,
    source TEXT DEFAULT 'manual',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(document_path, department_id)
);
CREATE INDEX IF NOT EXISTS idx_doc_dept_path ON document_departments(document_path);
CREATE INDEX IF NOT EXISTS idx_doc_dept_dept ON document_departments(department_id);

-- 插入默认产品线
INSERT OR IGNORE INTO product_lines (name) VALUES
    ('浙里报'),
    ('徽报账'),
    ('免疫规划'),
    ('电子档案'),
    ('数字化支撑'),
    ('孵化业务'),
    ('直属');
-- 报表数据
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    week TEXT,
    year INTEGER,
    category TEXT DEFAULT '周报',
    content TEXT,
    path TEXT,
    dept_summary TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_reports_week ON reports(year, week);
CREATE INDEX IF NOT EXISTS idx_reports_category ON reports(category);

-- FAQ 分类表
CREATE TABLE IF NOT EXISTS faq_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER,
    dept TEXT,
    sub_module TEXT,
    level INTEGER DEFAULT 1
);

-- FAQ 知识库
CREATE TABLE IF NOT EXISTS faqs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faq_code TEXT NOT NULL UNIQUE,
    faq_title TEXT NOT NULL,
    faq_question TEXT NOT NULL,
    faq_answer TEXT NOT NULL,
    content TEXT,
    category_id INTEGER REFERENCES faq_categories(id),
    dept TEXT NOT NULL,
    sub_module TEXT DEFAULT '',
    module TEXT DEFAULT '',
    scene TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    status INTEGER DEFAULT 0,
    sort_num INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0,
    source_file_name TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    version_from TEXT DEFAULT '',
    related TEXT DEFAULT '[]',
    tickets TEXT DEFAULT '[]',
    create_user TEXT DEFAULT '',
    update_user TEXT DEFAULT '',
    create_time TEXT DEFAULT (datetime('now')),
    update_time TEXT DEFAULT (datetime('now')),
    is_deleted INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_faqs_code ON faqs(faq_code);
CREATE INDEX IF NOT EXISTS idx_faqs_dept ON faqs(dept, sub_module);
CREATE INDEX IF NOT EXISTS idx_faqs_status ON faqs(status, is_deleted);
CREATE INDEX IF NOT EXISTS idx_faqs_category ON faqs(category_id);
CREATE INDEX IF NOT EXISTS idx_faqs_tags ON faqs(tags);

-- ============================================================================
-- 关键词表 v2：关键词实体与映射分离
-- 旧 keywords 表保留（向后兼容），迁移后废弃
-- ============================================================================

-- 关键词实体表
CREATE TABLE IF NOT EXISTS keywords_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,
    created_at TEXT,
    updated_at TEXT,
    is_deleted INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_keywords_v2_kw ON keywords_v2(keyword);

-- 关键词→模块→部门 映射表
CREATE TABLE IF NOT EXISTS keyword_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords_v2(id),
    module_id INTEGER REFERENCES modules(id),
    department_id INTEGER REFERENCES departments(id),
    department TEXT,
    domain TEXT,
    kb_path TEXT,
    note TEXT,
    created_at TEXT,
    updated_at TEXT,
    is_deleted INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_kwm_keyword ON keyword_mappings(keyword_id);
CREATE INDEX IF NOT EXISTS idx_kwm_module ON keyword_mappings(module_id);
CREATE INDEX IF NOT EXISTS idx_kwm_dept ON keyword_mappings(department_id);
