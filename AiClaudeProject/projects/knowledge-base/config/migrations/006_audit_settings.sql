-- 006: 审计日志表 + 系统配置表
-- 用于管理操作审计追踪和运行时可配置系统设置

-- 审计日志表
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,      -- 操作类型: auth.login, user.create, doc.upload, faq.save, system.rebuild 等
    target VARCHAR(200),              -- 操作对象（用户名/文档路径/FAQ code 等）
    detail TEXT,                      -- 变更详情（JSON 或纯文本）
    ip VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(username);

-- 系统配置表
CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    description VARCHAR(500),
    category VARCHAR(50) DEFAULT 'general',  -- sso, general, search, security
    updated_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT NOW()
);
