-- ============================================================================
-- 001_schema_fixes.sql — 修复 schema_v3 与运行时代码的契约断裂（幂等，可重复执行）
-- 日期: 2026-08-30 ｜ 依据: 知识库系统前端接口数据库映射报告_2026-08-30.md
-- 执行: psql -U zcy1 knowledge_base -f config/migrations/001_schema_fixes.sql
-- ============================================================================

BEGIN;

-- D1: faqs 补 SQLite 遗留列（代码 db_repo.save_faq/_row_to_faq 仍写读 related/tickets）
-- 先对齐列结构恢复 PG 写库能力；拆分表(faq_related/faq_tickets)改造另立专项
ALTER TABLE faqs ADD COLUMN IF NOT EXISTS related TEXT DEFAULT '[]';
ALTER TABLE faqs ADD COLUMN IF NOT EXISTS tickets TEXT DEFAULT '[]';

-- D2: document_departments 去重（同 document_path+department_id 保留最新 id 行）
-- 线上存在 document_path/document_id 双轨，运行时以 document_path 为规范
DELETE FROM document_departments a
USING document_departments b
WHERE a.document_path = b.document_path
  AND a.department_id = b.department_id
  AND a.id < b.id;
CREATE UNIQUE INDEX IF NOT EXISTS uq_dd_path_dept
  ON document_departments(document_path, department_id);

-- D3: keyword_mappings 去重（同 keyword_id+module_id：软删行让位存活行；同状态保留最新）
-- 注意：module_id 大量为 NULL，必须用 IS NOT DISTINCT FROM 做 NULL 安全比较
DELETE FROM keyword_mappings a
USING keyword_mappings b
WHERE a.keyword_id IS NOT DISTINCT FROM b.keyword_id
  AND a.module_id IS NOT DISTINCT FROM b.module_id
  AND ( (a.is_deleted AND NOT b.is_deleted)
     OR (a.is_deleted = b.is_deleted AND a.id < b.id) );
-- 部分唯一索引：仅约束存活映射，允许历史软删行共存。
-- PG 限制：NULL module_id 之间不冲突（NULL 视为互异），NULL 模块映射的防重依赖上面的
-- 一次性去重 + add_keyword 的复活式 upsert（Phase 1 配套修改 db_repo.add_keyword）
CREATE UNIQUE INDEX IF NOT EXISTS uq_km_kw_mod_active
  ON keyword_mappings(keyword_id, module_id) WHERE is_deleted = FALSE;

COMMIT;

-- ============================================================================
-- 校验输出
-- ============================================================================
SELECT 'faqs_columns' AS check_item,
       COUNT(*) AS cnt
  FROM information_schema.columns
 WHERE table_name = 'faqs'
   AND column_name IN ('related', 'tickets');

SELECT 'km_active_dupes_should_be_0' AS check_item, COUNT(*) AS cnt FROM (
  SELECT keyword_id, module_id
    FROM keyword_mappings
   WHERE is_deleted = FALSE
   GROUP BY 1, 2
  HAVING COUNT(*) > 1
) t;

SELECT 'dd_path_dept_dupes_should_be_0' AS check_item, COUNT(*) AS cnt FROM (
  SELECT document_path, department_id
    FROM document_departments
   GROUP BY 1, 2
  HAVING COUNT(*) > 1
) t;
