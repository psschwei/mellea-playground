"""Security utilities for password hashing and JWT tokens."""

from datetime import datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from mellea_api.core.config import get_settings
from mellea_api.models.user import UserRole

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    user_id: str,
    email: str,
    name: str,
    role: UserRole,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    """Create a JWT access token.

    Args:
        user_id: User's unique identifier
        email: User's email address
        name: User's display name
        role: User's role
        expires_delta: Optional custom expiration time

    Returns:
        Tuple of (token string, expiration datetime)
    """
    settings = get_settings()

    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)

    now = datetime.utcnow()
    expire = now + expires_delta

    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "name": name,
        "role": role.value,
        "iat": now,
        "exp": expire,
    }

    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    return token, expire


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT access token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload if valid, None if invalid or expired
    """
    settings = get_settings()

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
