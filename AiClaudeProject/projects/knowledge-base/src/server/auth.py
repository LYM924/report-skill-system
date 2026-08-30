"""JWT 认证"""
import logging
import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from config import settings

security = HTTPBearer(auto_error=False)

logger = logging.getLogger("auth")


def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def get_admin_credentials() -> tuple[str, str]:
    """管理员账号（env 优先，未配置时使用默认并告警）"""
    user = os.getenv("ADMIN_USER", "").strip()
    password = os.getenv("ADMIN_PASS", "").strip()
    if not user or not password:
        logger.warning("ADMIN_USER/ADMIN_PASS 未配置，使用默认账号 admin/admin123，请尽快修改")
        return "admin", "admin123"
    return user, password


def check_credentials(username: str, password: str) -> bool:
    u, p = get_admin_credentials()
    return username == u and password == p


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证 JWT Token（全部接口强制鉴权，/api/auth/login 除外）"""
    if settings.KB_API_KEY:
        # API Key 模式（兼容外部程序调用）
        if credentials and credentials.credentials == settings.KB_API_KEY:
            return "api_key_user"
        raise HTTPException(status_code=401, detail="未提供有效的 API Key")
    if not credentials:
        raise HTTPException(status_code=401, detail="未提供认证凭证")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="认证凭证无效或已过期")
