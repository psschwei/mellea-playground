"""Security utilities for password hashing and JWT tokens."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from mellea_api.core.config import get_settings
from mellea_api.models.user import UserRole

# Password hasher using Argon2 (recommended modern algorithm)
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    try:
        _password_hasher.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False


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

    now = datetime.now(UTC)
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


def create_impersonation_token(
    target_user_id: str,
    target_email: str,
    target_name: str,
    target_role: UserRole,
    impersonator_id: str,
    impersonator_email: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    """Create a JWT token for user impersonation.

    This creates a special token that allows an admin to act as another user
    while maintaining a record of who is actually performing the actions.

    Args:
        target_user_id: ID of the user being impersonated
        target_email: Email of the user being impersonated
        target_name: Display name of the user being impersonated
        target_role: Role of the user being impersonated
        impersonator_id: ID of the admin performing impersonation
        impersonator_email: Email of the admin performing impersonation
        expires_delta: Optional custom expiration time (defaults to 1 hour)

    Returns:
        Tuple of (token string, expiration datetime)
    """
    settings = get_settings()

    # Impersonation tokens have a shorter lifetime for security
    if expires_delta is None:
        expires_delta = timedelta(hours=1)

    now = datetime.now(UTC)
    expire = now + expires_delta

    payload: dict[str, Any] = {
        "sub": target_user_id,
        "email": target_email,
        "name": target_name,
        "role": target_role.value,
        "iat": now,
        "exp": expire,
        # Impersonation metadata
        "impersonator_id": impersonator_id,
        "impersonator_email": impersonator_email,
        "is_impersonation": True,
    }

    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    return token, expire
