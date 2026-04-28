"""JWT authentication module."""
from __future__ import annotations

import os
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from dotenv import load_dotenv, set_key

# Constants
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Lazy-initialized secret key
_jwt_secret: str | None = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
router = APIRouter()


def _get_jwt_secret() -> str:
    """Get or generate JWT secret key."""
    global _jwt_secret
    if _jwt_secret:
        return _jwt_secret

    secret = os.getenv("JWT_SECRET_KEY", "")
    if not secret:
        secret = secrets.token_urlsafe(32)
        _jwt_secret = secret
        # Persist to .env
        try:
            set_key(".env", "JWT_SECRET_KEY", secret)
        except Exception:
            pass
    else:
        _jwt_secret = secret
    return _jwt_secret


def _write_env(key: str, value: str) -> None:
    """Write a key=value pair to .env without quoting."""
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _get_admin_credentials() -> tuple[str, str]:
    """Get admin credentials, auto-generate password if not set."""
    username = os.getenv("ADMIN_USERNAME", "")
    password = os.getenv("ADMIN_PASSWORD", "")

    if not username:
        username = "admin"
        _write_env("ADMIN_USERNAME", username)
        os.environ["ADMIN_USERNAME"] = username

    if not password:
        from loguru import logger
        password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
        _write_env("ADMIN_PASSWORD", password)
        os.environ["ADMIN_PASSWORD"] = password
        logger.warning(f"已自动生成管理员密码: {password} (请妥善保存)")

    return username, password


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(subject: str, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, _get_jwt_secret(), algorithm=ALGORITHM)


def create_access_token(username: str) -> str:
    return _create_token(username, timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))


def create_refresh_token(username: str) -> str:
    return _create_token(username, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises JWTError on invalid/expired."""
    return jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """FastAPI dependency: validate Bearer token and return user info."""
    try:
        payload = decode_token(credentials.credentials)
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权访问")
        return {"username": username}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权访问")


# ─── Request / Response Models ───

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Routes ───

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate and return JWT tokens."""
    admin_user, admin_pass = _get_admin_credentials()

    if body.username != admin_user or body.password != admin_pass:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    return TokenResponse(
        access_token=create_access_token(body.username),
        refresh_token=create_refresh_token(body.username),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest):
    """Refresh access token using a valid refresh token."""
    try:
        payload = decode_token(body.refresh_token)
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token已过期，请重新登录")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token已过期，请重新登录")

    return TokenResponse(
        access_token=create_access_token(username),
        refresh_token=create_refresh_token(username),
    )
