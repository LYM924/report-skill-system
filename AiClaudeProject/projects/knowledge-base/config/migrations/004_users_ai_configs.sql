-- ============================================================================
-- 004_users_ai_configs.sql — 多用户账号 + 每用户 AI 模型配置
-- 场景：系统部署在服务器后，不同人登录自己的账号，各自配置自己的 AI 模型
--       API 地址 / AppKey，互不影响；服务器 .env 仅作回退默认值。
-- 执行: psql -U zcy1 knowledge_base -f config/migrations/004_users_ai_configs.sql
-- 幂等，可重复执行
-- ============================================================================

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,             -- "salt$pbkdf2_hex"
    role            TEXT NOT NULL DEFAULT 'user',  -- admin | user
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- 每用户 AI 配置表（一行一用户）
CREATE TABLE IF NOT EXISTS ai_configs (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    model           TEXT NOT NULL DEFAULT 'deepseek-v4-pro',
    base_url        TEXT NOT NULL DEFAULT '',
    api_key_enc     TEXT NOT NULL DEFAULT '',  -- XOR(JWT_SECRET_KEY) + base64
    max_tokens      INTEGER NOT NULL DEFAULT 4096,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_configs_username ON ai_configs(username);
