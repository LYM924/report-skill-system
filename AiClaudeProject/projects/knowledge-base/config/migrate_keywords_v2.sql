-- 关键词 v2 迁移脚本（PostgreSQL）
CREATE TABLE IF NOT EXISTS keywords_v2 (
    id SERIAL PRIMARY KEY,
    keyword TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_keywords_v2_kw ON keywords_v2(keyword);

CREATE TABLE IF NOT EXISTS keyword_mappings (
    id SERIAL PRIMARY KEY,
    keyword_id INTEGER NOT NULL REFERENCES keywords_v2(id),
    module_id INTEGER REFERENCES modules(id),
    department_id INTEGER REFERENCES departments(id),
    department TEXT,
    domain TEXT,
    kb_path TEXT,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_kwm_keyword ON keyword_mappings(keyword_id);
CREATE INDEX IF NOT EXISTS idx_kwm_module ON keyword_mappings(module_id);
CREATE INDEX IF NOT EXISTS idx_kwm_dept ON keyword_mappings(department_id);

-- 迁移数据
INSERT INTO keywords_v2 (keyword, created_at, updated_at)
SELECT DISTINCT keyword, NOW(), NOW()
FROM keywords WHERE keyword IS NOT NULL
ON CONFLICT (keyword) DO NOTHING;

INSERT INTO keyword_mappings (keyword_id, module_id, department, domain, kb_path, note, created_at, updated_at)
SELECT kv2.id, k.module_id, k.department, k.domain, k.kb_path, k.note, NOW(), NOW()
FROM keywords k
JOIN keywords_v2 kv2 ON k.keyword = kv2.keyword
WHERE NOT EXISTS (
    SELECT 1 FROM keyword_mappings km
    WHERE km.keyword_id = kv2.id AND km.module_id = k.module_id
);

SELECT 'keywords_v2' as tbl, COUNT(*) FROM keywords_v2
UNION ALL
SELECT 'keyword_mappings', COUNT(*) FROM keyword_mappings;