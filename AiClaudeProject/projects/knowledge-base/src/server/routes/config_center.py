"""系统管理路由：AI 配置中心 + 用户管理

- AI 配置：每个登录用户保存自己的模型/API地址/AppKey（GET 返回脱敏密钥）
- 用户管理：仅管理员可创建/重置/删除用户
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from auth import verify_token
from service import ai_config

router = APIRouter(tags=["系统管理"])


# ══════ AI 配置中心（每个用户自己的配置）══════

class AIConfigBody(BaseModel):
    model: str = "deepseek-v4-pro"
    base_url: str = ""
    api_key: str = ""          # 空 = 保留已有密钥
    max_tokens: int = 4096


class AIConfigTestBody(BaseModel):
    model: str = "deepseek-v4-pro"
    base_url: str = ""
    api_key: str = ""          # 空 = 用已保存的密钥测试


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
        "source": cfg.get("source", "none"),
    }


@router.put("/config/ai")
async def save_ai_config(body: AIConfigBody, user: str = Depends(verify_token)):
    """保存当前用户的 AI 配置"""
    if not body.model.strip():
        return JSONResponse({"error": "模型名必填"}, status_code=422)
    result = ai_config.save_ai_config(user, body.model.strip(), body.base_url.strip(),
                                      body.api_key.strip(), body.max_tokens)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return {"ok": True}


@router.post("/config/ai/test")
async def test_ai_config(body: AIConfigTestBody, user: str = Depends(verify_token)):
    """测试连通性：api_key 传空时使用已保存的密钥"""
    api_key = body.api_key.strip()
    if not api_key:
        cfg = ai_config.get_ai_config(user)
        api_key = cfg.get("api_key", "")
    return ai_config.test_ai_config(body.model.strip(), body.base_url.strip(), api_key)


# ══════ 用户管理（仅管理员）══════

def _require_admin(user: str):
    if not ai_config.is_admin(user):
        return JSONResponse({"error": "仅管理员可操作"}, status_code=403)
    return None


class UserCreateBody(BaseModel):
    username: str
    password: str
    role: str = "user"


class PasswordBody(BaseModel):
    password: str


@router.get("/users")
async def list_users(user: str = Depends(verify_token)):
    resp = _require_admin(user)
    if resp:
        return resp
    return {"users": ai_config.list_users()}


@router.post("/users")
async def create_user(body: UserCreateBody, user: str = Depends(verify_token)):
    resp = _require_admin(user)
    if resp:
        return resp
    username = body.username.strip()
    if not username or not body.password:
        return JSONResponse({"error": "用户名和密码必填"}, status_code=422)
    if body.role not in ("admin", "user"):
        return JSONResponse({"error": "角色必须是 admin 或 user"}, status_code=422)
    result = ai_config.create_user(username, body.password, body.role)
    if "error" in result:
        return JSONResponse(result, status_code=409)
    return {"ok": True, "username": username}


@router.put("/users/{username}/password")
async def reset_password(username: str, body: PasswordBody, user: str = Depends(verify_token)):
    resp = _require_admin(user)
    if resp:
        return resp
    if not body.password:
        return JSONResponse({"error": "密码不能为空"}, status_code=422)
    if not ai_config.update_user_password(username, body.password):
        return JSONResponse({"error": "用户不存在"}, status_code=404)
    return {"ok": True}


@router.delete("/users/{username}")
async def delete_user(username: str, user: str = Depends(verify_token)):
    resp = _require_admin(user)
    if resp:
        return resp
    if username == user:
        return JSONResponse({"error": "不能删除自己"}, status_code=400)
    if not ai_config.delete_user(username):
        return JSONResponse({"error": "用户不存在"}, status_code=404)
    return {"ok": True}
