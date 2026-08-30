-- ============================================================================
-- 003_fix_faqs_trigger.sql — 修复 faqs 表上的坏触发器
-- 问题：schema_v3.sql 将 update_timestamp()（设 NEW.updated_at）触发器挂到 faqs 表，
--       但 faqs 表的时间列是 update_time（无 updated_at 列）→
--       任何 UPDATE faqs 都报"记录new没有字段updated_at"，导致：
--       - 软删除（is_deleted=TRUE）失败
--       - view_count 自增失败
-- 修复：faqs 的时间戳由代码显式维护（update_time），移除坏触发器。
-- 执行: psql -U zcy1 knowledge_base -f config/migrations/003_fix_faqs_trigger.sql
-- 幂等，可重复执行
-- ============================================================================

DROP TRIGGER IF EXISTS trg_faqs_updated ON faqs;

-- 校验：faqs 上不应再有 update_timestamp 类触发器（search_vector 触发器保留）
SELECT tgname FROM pg_trigger WHERE tgrelid = 'faqs'::regclass AND NOT tgisinternal;
