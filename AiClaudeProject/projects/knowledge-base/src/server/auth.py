"""JWT 认证"""
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings

security = HTTPBearer(auto_error=False)


def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证 JWT Token，未配置 API Key 时跳过（开发模式）"""
    # 开发模式
    if settings.JWT_SECRET_KEY == "dev-secret-key":
        return None
    # API Key 模式（兼容旧版）
    if settings.KB_API_KEY:
        if credentials and credentials.credentials == settings.KB_API_KEY:
            return "api_key_user"
        raise HTTPException(status_code=401, detail="未提供有效的 API Key")
    # JWT 模式
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
        raise HTTPException(status_code=401, detail="认证凭证无效")