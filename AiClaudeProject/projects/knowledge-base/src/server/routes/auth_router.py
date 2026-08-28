"""认证路由"""
from fastapi import APIRouter, Depends
from auth import create_token, verify_token

router = APIRouter(tags=["认证"])


@router.post("/auth/login")
async def login(username: str, password: str):
    """登录获取 Token（开发模式：任意用户名密码返回 token）"""
    # TODO: 接入真实用户认证
    token = create_token(username)
    return {"token": token, "token_type": "bearer"}


@router.get("/auth/me")
async def me(user: str = Depends(verify_token)):
    """当前用户信息"""
    return {"user": user or "anonymous"}
