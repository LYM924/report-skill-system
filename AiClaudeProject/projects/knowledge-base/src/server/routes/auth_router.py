"""认证路由"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import create_token, verify_token, check_credentials

router = APIRouter(tags=["认证"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(body: LoginBody):
    """登录：校验 ADMIN_USER/ADMIN_PASS（env 配置），签发 JWT"""
    if not check_credentials(body.username, body.password):
        return JSONResponse({"error": "用户名或密码错误"}, status_code=401)
    token = create_token(body.username)
    return {"token": token, "token_type": "bearer"}


@router.get("/auth/me")
async def me(user: str = Depends(verify_token)):
    """当前用户信息"""
    return {"user": user or "anonymous"}
