-- ============================================================================
-- 005_ai_config_providers.sql — AI 配置支持多模型提供商（协议字段）
-- provider: deepseek/openai/qwen/glm/kimi/doubao/claude/ollama/custom
-- protocol: anthropic（Anthropic SDK 调用，如 api.deepseek.com/anthropic、
--           api.anthropic.com）| openai（OpenAI 兼容协议，如 OpenAI/通义/GLM/Kimi/豆包/Ollama）
-- 执行: psql -U zcy1 knowledge_base -f config/migrations/005_ai_config_providers.sql
-- 幂等，可重复执行
-- ============================================================================

ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'deepseek';
ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS protocol TEXT NOT NULL DEFAULT 'anthropic';
