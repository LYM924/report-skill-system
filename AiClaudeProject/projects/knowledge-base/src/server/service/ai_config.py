"""多用户账号与 AI 配置服务

- 密码：PBKDF2 哈希（格式 "salt$hex"）
- AppKey：以 JWT_SECRET_KEY 做 XOR + base64 混淆存储（防直接库泄漏明文）
- 配置解析优先级：用户自己保存的配置 → 服务器 .env/环境变量回退
"""
import base64
import hashlib
import json
import os
import secrets

from config import settings
from repository import get_repo


# ══════ 密码 ══════

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return secrets.compare_digest(digest.hex(), expected)
    except Exception:
        return False


# ══════ AppKey 混淆（XOR + base64，密钥来自 JWT_SECRET_KEY）══════

def _xor_key() -> bytes:
    return settings.JWT_SECRET_KEY.encode("utf-8")


def encrypt_key(api_key: str) -> str:
    if not api_key:
        return ""
    key = _xor_key()
    data = api_key.encode("utf-8")
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(out).decode("ascii")


def decrypt_key(enc: str) -> str:
    if not enc:
        return ""
    try:
        key = _xor_key()
        data = base64.urlsafe_b64decode(enc.encode("ascii"))
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).decode("utf-8")
    except Exception:
        return ""


# ══════ 用户与配置读写 ══════

def get_user(username: str) -> dict:
    repo = get_repo()
    row = repo._execute_one(
        "SELECT id, username, password_hash, role FROM users WHERE username = ? AND is_deleted = FALSE",
        (username,))
    return row


def create_user(username: str, password: str, role: str = "user") -> dict:
    repo = get_repo()
    try:
        repo._execute_write(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, hash_password(password), role))
        return {"ok": True}
    except Exception:
        return {"error": "用户名已存在"}


def list_users() -> list:
    repo = get_repo()
    rows = repo._execute(
        "SELECT id, username, role, created_at FROM users WHERE is_deleted = FALSE ORDER BY id")
    return [{"id": r["id"], "username": r["username"], "role": r["role"],
             "created_at": str(r["created_at"]) if r["created_at"] else ""} for r in rows]


def update_user_password(username: str, new_password: str) -> bool:
    repo = get_repo()
    exists = repo._execute_one("SELECT id FROM users WHERE username = ? AND is_deleted = FALSE", (username,))
    if not exists:
        return False
    repo._execute_write("UPDATE users SET password_hash = ?, updated_at = NOW() WHERE username = ?",
                        (hash_password(new_password), username))
    return True


def delete_user(username: str) -> bool:
    repo = get_repo()
    exists = repo._execute_one("SELECT id FROM users WHERE username = ? AND is_deleted = FALSE", (username,))
    if not exists:
        return False
    repo._execute_write("UPDATE users SET is_deleted = TRUE, updated_at = NOW() WHERE username = ?", (username,))
    return True


def update_user_role(username: str, new_role: str) -> bool:
    repo = get_repo()
    exists = repo._execute_one("SELECT id FROM users WHERE username = ? AND is_deleted = FALSE", (username,))
    if not exists:
        return False
    repo._execute_write("UPDATE users SET role = ?, updated_at = NOW() WHERE username = ?", (new_role, username))
    return True


def is_admin(username: str) -> bool:
    if not username:
        return False
    row = get_user(username)
    if row and row["role"] == "admin":
        return True
    # 环境管理员账号兜底
    admin_user = os.getenv("ADMIN_USER", "").strip()
    return bool(admin_user) and username == admin_user


# ══════ AI 配置（多提供商：Anthropic 协议 / OpenAI 兼容协议）══════

# 主流提供商预设（前端下拉选择，自动带出 base_url/协议/推荐模型）
PROVIDER_PRESETS = [
    {"provider": "deepseek", "name": "DeepSeek（深度求索）", "protocol": "anthropic",
     "base_url": "https://api.deepseek.com/anthropic",
     "models": ["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"],
     "needs_key": True, "note": "Anthropic 兼容端点（已实测可用）"},
    {"provider": "deepseek-openai", "name": "DeepSeek（OpenAI 格式）", "protocol": "openai",
     "base_url": "https://api.deepseek.com/v1",
     "models": ["deepseek-chat", "deepseek-reasoner"],
     "needs_key": True, "note": "官方 OpenAI 兼容端点"},
    {"provider": "openai", "name": "OpenAI", "protocol": "openai",
     "base_url": "https://api.openai.com/v1",
     "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1"],
     "needs_key": True, "note": "OpenAI 官方"},
    {"provider": "qwen", "name": "通义千问（阿里）", "protocol": "openai",
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
     "needs_key": True, "note": "阿里云百炼，OpenAI 兼容模式"},
    {"provider": "glm", "name": "智谱 GLM", "protocol": "openai",
     "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "models": ["glm-4.6", "glm-4-flash", "glm-4.5"],
     "needs_key": True, "note": "智谱 AI 开放平台"},
    {"provider": "kimi", "name": "Kimi（月之暗面）", "protocol": "openai",
     "base_url": "https://api.moonshot.cn/v1",
     "models": ["kimi-k2.5", "moonshot-v1-32k"],
     "needs_key": True, "note": "Moonshot 官方"},
    {"provider": "doubao", "name": "豆包（火山方舟）", "protocol": "openai",
     "base_url": "https://ark.cn-beijing.volces.com/api/v3",
     "models": ["doubao-1-5-pro-32k-250115", "doubao-seed-1-6-250615"],
     "needs_key": True, "note": "需在火山方舟创建推理接入点，模型名为端点ID"},
    {"provider": "claude", "name": "Claude（Anthropic）", "protocol": "anthropic",
     "base_url": "https://api.anthropic.com",
     "models": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"],
     "needs_key": True, "note": "Anthropic 官方"},
    {"provider": "cai-gateway", "name": "公司AI网关（灵龙TokenPlan）", "protocol": "anthropic",
     "base_url": "https://ai-gateway.prod.cai-inc.com/api/biz-ai/ai-llm/anthropic",
     "models": ["Bailian-GLM5.2", "Bailian-GLM5.1", "DeepSeek-deepseek-v4-flash", "Bailian-Qwen3.6-Flash"],
     "needs_key": True, "note": "灵龙申领AppKey（linglong.cai-inc.com）。模型名须带供应商前缀且与可用列表完全一致否则403；仅限公司内网/VPN"},

    {"provider": "ollama", "name": "Ollama（本地模型）", "protocol": "openai",
     "base_url": "http://localhost:11434/v1",
     "models": ["qwen2.5:14b", "llama3.1:8b"],
     "needs_key": False, "note": "本地部署，无需 AppKey"},
]


def get_provider_presets() -> list:
    return PROVIDER_PRESETS
# ══════ 全机联动：管理员保存配置 → 同步共享 AI 环境文件 ══════

def _shared_env_path() -> str:
    """共享 AI 环境文件路径（终端 Claude Code 等工具统一 source 此文件）"""
    return os.path.expanduser(os.getenv("SHARED_AI_ENV_FILE", "~/.ai_gateway.env"))


def _claude_settings_path() -> str:
    """Claude Code settings.json 路径（通义灵码等 IDE 内 Claude Code 读此文件获取配置）"""
    return os.path.expanduser("~/.claude/settings.json")


def _sync_claude_settings(model: str, base_url: str, api_key: str) -> None:
    """同步 AI 配置到 Claude Code settings.json（合并 env，保留其他已有字段）"""
    path = _claude_settings_path()
    new_env = {
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "CLAUDE_CODE_SUBAGENT_MODEL": model,
        "CLAUDE_MODEL": model,
        "API_TIMEOUT_MS": "3000000",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CODE_EFFORT_LEVEL": "max",
    }
    try:
        # 读取已有配置，保留非 env 字段
        existing = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        # 合并 env：新值覆盖旧值，保留非 AI 相关的 env 条目
        old_env = existing.get("env", {})
        old_env.update(new_env)
        existing["env"] = old_env
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(path, 0o600)
        print(f"[ai_config] 已同步 Claude Code settings.json: {path}")
    except Exception as e:
        print(f"[ai_config] 同步 Claude Code settings.json 失败: {e}")


def sync_shared_env(username: str, model: str, base_url: str, api_key: str, protocol: str) -> None:
    """管理员保存 AI 配置后，将配置写入共享环境文件，实现全机联动。

    - 仅管理员保存时触发（其他用户的配置只影响知识库内本人 AI 功能）；
    - 仅同步 anthropic 协议（Claude Code 只认 Anthropic 协议，openai 协议的
      key 无法给终端使用，跳过并保留原文件）；
    - 同步失败只告警不阻断保存。
    - 同时同步到 ~/.claude/settings.json（供通义灵码等 IDE 内 Claude Code 读取）。
    """
    if not is_admin(username) or protocol != "anthropic":
        return
    # 1) 写 ~/.ai_gateway.env（终端 source 用）
    path = _shared_env_path()
    content = (
        "# 本机统一 AI 大模型配置（唯一来源：知识库配置中心「管理员保存」时由后端同步写入）\n"
        "# 供终端 Claude Code 与所有读取 ANTHROPIC_* 环境变量的工具共用，请勿手改\n"
        f'export ANTHROPIC_BASE_URL="{base_url}"\n'
        f'export ANTHROPIC_AUTH_TOKEN="{api_key}"\n'
        f'export ANTHROPIC_MODEL="{model}"\n'
        f'export ANTHROPIC_DEFAULT_OPUS_MODEL="{model}"\n'
        f'export ANTHROPIC_DEFAULT_SONNET_MODEL="{model}"\n'
        f'export ANTHROPIC_DEFAULT_HAIKU_MODEL="{model}"\n'
        f'export CLAUDE_CODE_SUBAGENT_MODEL="{model}"\n'
        f'export CLAUDE_MODEL="{model}"\n'
        'export API_TIMEOUT_MS="3000000"\n'
        'export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"\n'
    )
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(path, 0o600)
        print(f"[ai_config] 已同步共享AI环境文件: {path}")
    except Exception as e:
        print(f"[ai_config] 同步共享AI环境文件失败: {e}")
    # 2) 写 ~/.claude/settings.json（通义灵码等 IDE 内 Claude Code 用）
    _sync_claude_settings(model, base_url or "", api_key or "")



def get_ai_config(username: str) -> dict:
    """返回该用户的 AI 配置（api_key 解密后的完整值）"""
    repo = get_repo()
    row = repo._execute_one(
        "SELECT model, base_url, api_key_enc, max_tokens, provider, protocol FROM ai_configs WHERE username = ?",
        (username,))
    if row:
        return {
            "model": row["model"],
            "base_url": row["base_url"],
            "api_key": decrypt_key(row["api_key_enc"]),
            "max_tokens": row["max_tokens"],
            "provider": row["provider"] or "custom",
            "protocol": row["protocol"] or "anthropic",
            "source": "user",
        }
    return {"model": "", "base_url": "", "api_key": "", "max_tokens": 4096,
            "provider": "custom", "protocol": "anthropic", "source": "none"}


def get_ai_config_masked(username: str) -> dict:
    """返回给前端展示的配置（api_key 脱敏：前4后4）"""
    cfg = get_ai_config(username)
    key = cfg.get("api_key", "")
    cfg["api_key_masked"] = (key[:4] + "****" + key[-4:]) if len(key) >= 8 else ("****" if key else "")
    cfg["has_key"] = bool(key)
    cfg.pop("api_key", None)
    return cfg


def save_ai_config(username: str, model: str, base_url: str, api_key: str, max_tokens: int,
                   provider: str = "custom", protocol: str = "anthropic") -> dict:
    """保存配置。api_key 传空 = 保留已有密钥（前端脱敏回显后重新保存的场景）"""
    repo = get_repo()
    model_final = model or "deepseek-v4-pro"
    if api_key:
        enc = encrypt_key(api_key)
    else:
        existing = repo._execute_one("SELECT api_key_enc FROM ai_configs WHERE username = ?", (username,))
        enc = existing["api_key_enc"] if existing else ""
    try:
        repo._execute_write(
            "INSERT INTO ai_configs (username, model, base_url, api_key_enc, max_tokens, provider, protocol) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (username) DO UPDATE SET "
            "model = EXCLUDED.model, base_url = EXCLUDED.base_url, "
            "api_key_enc = EXCLUDED.api_key_enc, max_tokens = EXCLUDED.max_tokens, "
            "provider = EXCLUDED.provider, protocol = EXCLUDED.protocol, updated_at = NOW()",
            (username, model_final, base_url or "", enc, int(max_tokens or 4096),
             provider or "custom", protocol or "anthropic"))
    except Exception as e:
        return {"error": f"保存失败: {e}"}
    # 管理员保存 = 全机联动：同步写入共享AI环境文件（终端 Claude Code 等统一读取）
    sync_shared_env(username, model_final, base_url or "",
                    api_key or decrypt_key(enc), protocol or "anthropic")
    # 审计日志
    from service.audit import log_action
    log_action(username, "config.ai_save", detail=json.dumps({"model": model_final, "provider": provider, "protocol": protocol}, ensure_ascii=False))
    return {"ok": True}


def resolve_ai_config(username: str) -> dict:
    """AI 调用时的最终配置解析：用户配置优先 → 服务器环境回退 → None（不可用）

    环境回退受 system_settings.ai_env_fallback 控制：
    - "1"（默认）: 未配置 AI 的用户可使用服务器共享密钥
    - "0": 未配置 AI 的用户不可使用 AI 功能（必须自行配置密钥）
    """
    cfg = get_ai_config(username)
    if cfg.get("api_key"):
        return {**cfg, "source": "user"}
    # 环境回退（受开关控制）
    from routes.settings_router import get_system_setting
    allow_fallback = get_system_setting("ai_env_fallback", "1") == "1"
    if not allow_fallback:
        return None
    env_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if env_key:
        from service import claude_stream
        return {
            "model": claude_stream.default_model(),
            "base_url": os.environ.get("ANTHROPIC_BASE_URL", ""),
            "api_key": env_key,
            "max_tokens": 4096,
            "provider": "env",
            "protocol": "anthropic",
            "source": "env",
        }
    return None


def test_ai_config(model: str, base_url: str, api_key: str, protocol: str = "anthropic") -> dict:
    """测试连通性：按协议发一条最小请求（anthropic: Bearer 优先回退 x-api-key；openai: api_key）"""
    if not api_key:
        return {"ok": False, "error": "缺少 AppKey"}
    try:
        if protocol == "openai":
            import openai
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            client = openai.OpenAI(**kwargs)
            resp = client.chat.completions.create(
                model=model or "gpt-4o-mini", max_tokens=16,
                messages=[{"role": "user", "content": "ping"}])
            text = (resp.choices[0].message.content or "").strip()
            return {"ok": True, "message": f"连接成功（模型响应: {text[:50] or 'ok'}）"}
        # anthropic 协议
        import anthropic
        base_kwargs = {}
        if base_url:
            base_kwargs["base_url"] = base_url

        def _ping(kwargs):
            client = anthropic.Anthropic(**kwargs)
            return client.messages.create(
                model=model or "deepseek-v4-pro",
                max_tokens=16,
                messages=[{"role": "user", "content": "ping"}],
            )

        try:
            resp = _ping({**base_kwargs, "auth_token": api_key})
        except anthropic.AuthenticationError:
            # 部分网关只接受 x-api-key 头，仅鉴权失败时才回退（避免掩盖模型/网络等真实错误）
            try:
                resp = _ping({**base_kwargs, "api_key": api_key})
            except Exception as e:
                return {"ok": False, "error": str(e)[:300]}
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return {"ok": True, "message": f"连接成功（模型响应: {text[:50] or 'ok'}）"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
