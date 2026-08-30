"""认证路由"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import create_token, verify_token, check_credentials
from service import ai_config

router = APIRouter(tags=["认证"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(body: LoginBody):
    """登录：优先校验用户表（多用户各自账号），回退环境 ADMIN_USER/ADMIN_PASS"""
    username = body.username.strip()
    if not username or not body.password:
        return JSONResponse({"error": "用户名和密码不能为空"}, status_code=401)
    # 1. 用户表校验
    row = ai_config.get_user(username)
    if row and ai_config.verify_password(body.password, row["password_hash"]):
        token = create_token(username)
        return {"token": token, "token_type": "bearer", "role": row["role"]}
    # 2. 环境管理员账号回退
    if check_credentials(username, body.password):
        token = create_token(username)
        return {"token": token, "token_type": "bearer", "role": "admin"}
    return JSONResponse({"error": "用户名或密码错误"}, status_code=401)


@router.get("/auth/me")
async def me(user: str = Depends(verify_token)):
    """当前用户信息（含角色，前端用于菜单显隐）"""
    role = "admin" if ai_config.is_admin(user) else "user"
    return {"user": user or "anonymous", "role": role}
