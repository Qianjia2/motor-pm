"""JWT token handling and password hashing."""
import hashlib
import secrets
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend_v2.config import settings
from backend_v2.database import get_db

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """SHA256 + salt — compatible with v1 hashes, production should migrate to bcrypt."""
    salt = secrets.token_hex(8)
    return salt + ":" + hashlib.sha256((salt + password).encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify SHA256+salt hash (compatible with v1)."""
    try:
        salt, h = hashed.split(":")
        return h == hashlib.sha256((salt + plain).encode()).hexdigest()
    except (ValueError, AttributeError):
        return False


def create_access_token(username: str, user_id: int, role: str, member_id: int = None) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "user_id": user_id,
        "role": role,
        "type": "access",
        "exp": expire,
    }
    if member_id is not None:
        payload["member_id"] = member_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(username: str, user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": username,
        "user_id": user_id,
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的认证令牌")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Dependency: extract current user from JWT access token."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="需要登录")
    payload = verify_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="请使用 access_token")

    from backend_v2.models import UserAuth  # noqa
    result = db.execute(
        select(UserAuth).where(
            UserAuth.username == payload["sub"],
            UserAuth.is_active == True,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Dependency: like get_current_user but returns None when unauthenticated."""
    if credentials is None:
        return None
    try:
        payload = verify_token(credentials.credentials)
    except HTTPException:
        return None
    if payload.get("type") != "access":
        return None

    from backend_v2.models import UserAuth
    user = db.execute(
        select(UserAuth).where(
            UserAuth.username == payload["sub"],
            UserAuth.is_active == True,
        )
    ).scalar_one_or_none()
    return user


def require_admin(
    current_user=Depends(get_current_user),
):
    """Dependency: ensure current user has admin role."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user
