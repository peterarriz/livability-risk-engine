"""
backend/app/auth.py
task: data-045
lane: data

JWT + password utilities for user account authentication.

Provides:
  hash_password(password)       → bcrypt hash string
  verify_password(pw, hash)     → bool
  create_token(account_id, ...) → signed JWT string (HS256, 30-day expiry)
  decode_token(token)           → payload dict
  get_current_user(auth_header) → FastAPI dependency, raises 401 if invalid
  get_current_user_optional(…)  → same but returns None instead of raising

Environment variables:
  JWT_SECRET   — HS256 signing key (required in production; random fallback for dev)
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Header, HTTPException, status

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_JWT_SECRET: str = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_DAYS = 30

if not os.environ.get("JWT_SECRET"):
    log.warning(
        "JWT_SECRET not set — using an ephemeral random key. "
        "All tokens will be invalidated on every server restart. "
        "Set JWT_SECRET in your Railway / .env config before going to production."
    )


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password* suitable for DB storage."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if *password* matches *password_hash*."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_token(account_id: int, email: str, display_name: Optional[str] = None) -> str:
    """
    Create a signed JWT for *account_id*.

    Payload shape:
        sub   — str(account_id)
        email — user's email address
        name  — display_name or email-local-part
        iat   — issued-at (UTC)
        exp   — expires-at (UTC, +30 days)
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(account_id),
        "email": email,
        "name": display_name or email.split("@")[0],
        "iat": now,
        "exp": now + timedelta(days=_JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT.  Raises jwt.InvalidTokenError subtypes on failure.
    """
    return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def get_current_user(authorization: str = Header(default=None)) -> dict:
    """
    FastAPI dependency that extracts and verifies the Bearer JWT from the
    Authorization header.  Raises HTTP 401 if missing, expired, or invalid.

    Usage:
        @app.get("/protected")
        def protected(user: dict = Depends(get_current_user)):
            return {"account_id": user["sub"], "email": user["email"]}
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:]  # strip "Bearer "
    try:
        return decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired — please sign in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_optional(authorization: str = Header(default=None)) -> Optional[dict]:
    """
    Like get_current_user but returns None for unauthenticated requests instead
    of raising HTTP 401.  Use on endpoints that behave differently for logged-in
    users but are also accessible anonymously.
    """
    if not authorization:
        return None
    try:
        return get_current_user(authorization)
    except HTTPException:
        return None
