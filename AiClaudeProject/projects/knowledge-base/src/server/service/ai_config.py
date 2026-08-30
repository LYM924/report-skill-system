"""多用户账号与 AI 配置服务

- 密码：PBKDF2 哈希（格式 "salt$hex"）
- AppKey：以 JWT_SECRET_KEY 做 XOR + base64 混淆存储（防直接库泄漏明文）
- 配置解析优先级：用户自己保存的配置 → 服务器 .env/环境变量回退
"""
import base64
import hashlib
import os
import secrets

from config import settings
from repository import DBRepository


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
    repo = DBRepository()
    row = repo._execute_one(
        "SELECT id, username, password_hash, role FROM users WHERE username = ? AND is_deleted = FALSE",
        (username,))
    return row


def create_user(username: str, password: str, role: str = "user") -> dict:
    repo = DBRepository()
    try:
        repo._execute_write(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, hash_password(password), role))
        return {"ok": True}
    except Exception:
        return {"error": "用户名已存在"}


def list_users() -> list:
    repo = DBRepository()
    rows = repo._execute(
        "SELECT id, username, role, created_at FROM users WHERE is_deleted = FALSE ORDER BY id")
    return [{"id": r["id"], "username": r["username"], "role": r["role"],
             "created_at": str(r["created_at"]) if r["created_at"] else ""} for r in rows]


def update_user_password(username: str, new_password: str) -> bool:
    repo = DBRepository()
    exists = repo._execute_one("SELECT id FROM users WHERE username = ? AND is_deleted = FALSE", (username,))
    if not exists:
        return False
    repo._execute_write("UPDATE users SET password_hash = ?, updated_at = NOW() WHERE username = ?",
                        (hash_password(new_password), username))
    return True


def delete_user(username: str) -> bool:
    repo = DBRepository()
    exists = repo._execute_one("SELECT id FROM users WHERE username = ? AND is_deleted = FALSE", (username,))
    if not exists:
        return False
    repo._execute_write("UPDATE users SET is_deleted = TRUE, updated_at = NOW() WHERE username = ?", (username,))
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


# ══════ AI 配置 ══════

def get_ai_config(username: str) -> dict:
    """返回该用户的 AI 配置（api_key 解密后的完整值）"""
    repo = DBRepository()
    row = repo._execute_one(
        "SELECT model, base_url, api_key_enc, max_tokens FROM ai_configs WHERE username = ?",
        (username,))
    if row:
        return {
            "model": row["model"],
            "base_url": row["base_url"],
            "api_key": decrypt_key(row["api_key_enc"]),
            "max_tokens": row["max_tokens"],
            "source": "user",
        }
    return {"model": "", "base_url": "", "api_key": "", "max_tokens": 4096, "source": "none"}


def get_ai_config_masked(username: str) -> dict:
    """返回给前端展示的配置（api_key 脱敏：前4后4）"""
    cfg = get_ai_config(username)
    key = cfg.get("api_key", "")
    cfg["api_key_masked"] = (key[:4] + "****" + key[-4:]) if len(key) >= 8 else ("****" if key else "")
    cfg["has_key"] = bool(key)
    cfg.pop("api_key", None)
    return cfg


def save_ai_config(username: str, model: str, base_url: str, api_key: str, max_tokens: int) -> dict:
    """保存配置。api_key 传空 = 保留已有密钥（前端脱敏回显后重新保存的场景）"""
    repo = DBRepository()
    if api_key:
        enc = encrypt_key(api_key)
    else:
        existing = repo._execute_one("SELECT api_key_enc FROM ai_configs WHERE username = ?", (username,))
        enc = existing["api_key_enc"] if existing else ""
    try:
        repo._execute_write(
            "INSERT INTO ai_configs (username, model, base_url, api_key_enc, max_tokens) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (username) DO UPDATE SET "
            "model = EXCLUDED.model, base_url = EXCLUDED.base_url, "
            "api_key_enc = EXCLUDED.api_key_enc, max_tokens = EXCLUDED.max_tokens, updated_at = NOW()",
            (username, model or "deepseek-v4-pro", base_url or "", enc, int(max_tokens or 4096)))
        return {"ok": True}
    except Exception as e:
        return {"error": f"保存失败: {e}"}


def resolve_ai_config(username: str) -> dict:
    """AI 调用时的最终配置解析：用户配置优先 → 服务器环境回退 → None（不可用）"""
    cfg = get_ai_config(username)
    if cfg.get("api_key"):
        return {**cfg, "source": "user"}
    # 环境回退
    env_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if env_key:
        from service import claude_stream
        return {
            "model": claude_stream.default_model(),
            "base_url": os.environ.get("ANTHROPIC_BASE_URL", ""),
            "api_key": env_key,
            "max_tokens": 4096,
            "source": "env",
        }
    return None


def test_ai_config(model: str, base_url: str, api_key: str) -> dict:
    """测试连通性：用给定配置发一条最小请求（Bearer 优先，失败回退 x-api-key）"""
    if not api_key:
        return {"ok": False, "error": "缺少 AppKey"}
    try:
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
        except Exception:
            resp = _ping({**base_kwargs, "api_key": api_key})
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return {"ok": True, "message": f"连接成功（模型响应: {text[:50] or 'ok'}）"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
