-- ============================================================================
-- 002_sync_sequences.sql — 同步所有 SERIAL 序列（SQLite→PG 迁移遗留）
-- 问题：SQLite 数据迁入 PG 后，自增序列仍从 1 开始，新 INSERT 会撞已有主键
--       （例：feedback 表已有 id=1..4，nextval 返回 1 → UniqueViolation）
-- 执行: psql -U zcy1 knowledge_base -f config/migrations/002_sync_sequences.sql
-- 幂等，可重复执行
-- ============================================================================

DO $$
DECLARE
    t text;
    has_rows boolean;
    max_id bigint;
BEGIN
    FOR t IN
        SELECT table_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND column_name = 'id'
           AND data_type = 'integer'
           AND column_default LIKE 'nextval%'
    LOOP
        EXECUTE format('SELECT EXISTS(SELECT 1 FROM public.%I)', t) INTO has_rows;
        IF has_rows THEN
            EXECUTE format('SELECT MAX(id) FROM public.%I', t) INTO max_id;
            EXECUTE format('SELECT setval(pg_get_serial_sequence(''public.%I'', ''id''), %s, true)', t, COALESCE(max_id, 0));
        ELSE
            EXECUTE format('SELECT setval(pg_get_serial_sequence(''public.%I'', ''id''), 1, false)', t);
        END IF;
    END LOOP;
END $$;

-- 校验输出：各序列当前值（应等于对应表当前最大 id）
SELECT sequencename, last_value
  FROM pg_sequences
 WHERE sequencename LIKE '%_id_seq'
 ORDER BY sequencename;
