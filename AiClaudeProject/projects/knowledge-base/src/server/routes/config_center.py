"""系统管理路由：AI 配置中心 + 用户管理

- AI 配置：每个登录用户保存自己的模型/API地址/AppKey（GET 返回脱敏密钥）
- 用户管理：仅管理员可创建/重置/删除用户
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from auth import verify_token, require_admin
from service import ai_config
from service.audit import log_action

router = APIRouter(tags=["系统管理"])


# ══════ AI 配置中心（每个用户自己的配置）══════

class AIConfigBody(BaseModel):
    model: str = "deepseek-v4-pro"
    base_url: str = ""
    api_key: str = ""          # 空 = 保留已有密钥
    max_tokens: int = 4096
    provider: str = "custom"   # 提供商标识（预设列表见 /config/ai/presets）
    protocol: str = "anthropic"  # anthropic | openai


class AIConfigTestBody(BaseModel):
    model: str = "deepseek-v4-pro"
    base_url: str = ""
    api_key: str = ""          # 空 = 用已保存的密钥测试
    protocol: str = "anthropic"


@router.get("/config/ai/presets")
async def ai_presets(user: str = Depends(verify_token)):
    """主流大模型提供商预设（名称/协议/默认地址/推荐模型）"""
    return {"presets": ai_config.get_provider_presets()}


@router.get("/config/ai")
async def get_ai_config(user: str = Depends(verify_token)):
    """当前用户的 AI 配置（AppKey 脱敏）"""
    cfg = ai_config.get_ai_config_masked(user)
    return {
        "model": cfg["model"] or "deepseek-v4-pro",
        "base_url": cfg["base_url"],
        "api_key_masked": cfg.get("api_key_masked", ""),
        "has_key": cfg.get("has_key", False),
        "max_tokens": cfg["max_tokens"],
        "provider": cfg.get("provider", "custom"),
        "protocol": cfg.get("protocol", "anthropic"),
        "source": cfg.get("source", "none"),
    }


@router.put("/config/ai")
async def save_ai_config(body: AIConfigBody, user: str = Depends(verify_token)):
    """保存当前用户的 AI 配置"""
    if not body.model.strip():
        return JSONResponse({"error": "模型名必填"}, status_code=422)
    if body.protocol not in ("anthropic", "openai"):
        return JSONResponse({"error": "protocol 必须是 anthropic 或 openai"}, status_code=422)
    result = ai_config.save_ai_config(user, body.model.strip(), body.base_url.strip(),
                                      body.api_key.strip(), body.max_tokens,
                                      body.provider, body.protocol)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return {"ok": True}


@router.post("/config/ai/test")
async def test_ai_config(body: AIConfigTestBody, user: str = Depends(verify_token)):
    """测试连通性：api_key 传空时使用已保存的密钥"""
    api_key = body.api_key.strip()
    protocol = body.protocol
    if not api_key:
        cfg = ai_config.get_ai_config(user)
        api_key = cfg.get("api_key", "")
        protocol = protocol or cfg.get("protocol", "anthropic")
    return ai_config.test_ai_config(body.model.strip(), body.base_url.strip(), api_key, protocol)


# ══════ 用户管理（仅管理员）══════


class UserCreateBody(BaseModel):
    username: str
    password: str
    role: str = "user"


class PasswordBody(BaseModel):
    password: str


class RoleBody(BaseModel):
    role: str


@router.get("/users")
async def list_users(user: str = Depends(require_admin)):
    return {"users": ai_config.list_users()}


@router.post("/users")
async def create_user(body: UserCreateBody, user: str = Depends(require_admin)):
    username = body.username.strip()
    if not username or not body.password:
        return JSONResponse({"error": "用户名和密码必填"}, status_code=422)
    if body.role not in ("admin", "user"):
        return JSONResponse({"error": "角色必须是 admin 或 user"}, status_code=422)
    result = ai_config.create_user(username, body.password, body.role)
    if "error" in result:
        return JSONResponse(result, status_code=409)
    log_action(user, "user.create", target=username, detail=f"role={body.role}")
    return {"ok": True, "username": username}


@router.put("/users/{username}/password")
async def reset_password(username: str, body: PasswordBody, user: str = Depends(require_admin)):
    if not body.password:
        return JSONResponse({"error": "密码不能为空"}, status_code=422)
    if not ai_config.update_user_password(username, body.password):
        return JSONResponse({"error": "用户不存在"}, status_code=404)
    log_action(user, "user.reset_password", target=username)
    return {"ok": True}


@router.delete("/users/{username}")
async def delete_user(username: str, user: str = Depends(require_admin)):
    if username == user:
        return JSONResponse({"error": "不能删除自己"}, status_code=400)
    if not ai_config.delete_user(username):
        return JSONResponse({"error": "用户不存在"}, status_code=404)
    log_action(user, "user.delete", target=username)
    return {"ok": True}


@router.put("/users/{username}/role")
async def update_user_role(username: str, body: RoleBody, user: str = Depends(require_admin)):
    if body.role not in ("admin", "user"):
        return JSONResponse({"error": "角色必须是 admin 或 user"}, status_code=422)
    if not ai_config.update_user_role(username, body.role):
        return JSONResponse({"error": "用户不存在"}, status_code=404)
    log_action(user, "user.update_role", target=username, detail=f"new_role={body.role}")
    return {"ok": True}
