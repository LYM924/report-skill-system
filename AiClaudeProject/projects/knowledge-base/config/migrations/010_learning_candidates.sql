-- ============================================================================
-- 迁移 010: 学习候选池 — AI 回答/用户反馈中有价值的知识，经审核后沉淀为 FAQ
-- 日期: 2026-09-04
-- 说明: 自学习闭环核心表，配合 learning_service.py + learning_router.py
-- ============================================================================

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
