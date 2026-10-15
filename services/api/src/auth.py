"""Authentication and cookie security utilities for Mise API."""

import hashlib
import hmac
import secrets
import time
import uuid
from typing import Literal

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models.session import GuestSession

AUTH_COOKIE_NAME = "mise_auth"
GUEST_COOKIE_NAME = "mise_guest"

Role = Literal["owner", "staff"]


def sign_value(val: str, secret: str = settings.api_secret_key) -> str:
    """Sign a string value using HMAC-SHA256."""
    sig = hmac.new(secret.encode("utf-8"), val.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{val}.{sig}"


def unsign_value(signed: str, secret: str = settings.api_secret_key) -> str | None:
    """Verify HMAC-SHA256 signature and return original string, or None if invalid."""
    if "." not in signed:
        return None
    val, sig = signed.rsplit(".", 1)
    expected_sig = hmac.new(secret.encode("utf-8"), val.encode("utf-8"), hashlib.sha256).hexdigest()
    if secrets.compare_digest(sig, expected_sig):
        return val
    return None


def set_auth_cookie(response: Response, role: Role) -> None:
    """Set 8-hour httpOnly signed authentication cookie for owner or staff."""
    exp_ts = int(time.time()) + 8 * 3600
    val = f"{role}:{exp_ts}"
    signed = sign_value(val)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=signed,
        max_age=8 * 3600,
        httponly=True,
        samesite="lax",
        secure=(settings.app_env != "dev"),
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Clear authentication cookie."""
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=(settings.app_env != "dev"),
        path="/",
    )


def set_guest_cookie(response: Response, session_id: uuid.UUID) -> None:
    """Set 4-hour httpOnly signed session cookie for guests."""
    signed = sign_value(str(session_id))
    response.set_cookie(
        key=GUEST_COOKIE_NAME,
        value=signed,
        max_age=4 * 3600,
        httponly=True,
        samesite="lax",
        secure=(settings.app_env != "dev"),
        path="/",
    )


async def get_current_role(request: Request) -> Role:
    """Extract and validate owner/staff role from signed httpOnly cookie."""
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    if not cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    val = unsign_value(cookie)
    if not val or ":" not in val:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication cookie",
        )

    role_str, exp_str = val.split(":", 1)
    try:
        exp_ts = int(exp_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed authentication cookie",
        ) from None

    if time.time() > exp_ts:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication cookie expired",
        )

    if role_str not in ("owner", "staff"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid role in authentication cookie",
        )

    return role_str  # type: ignore[return-value]


async def require_staff_or_owner(role: Role = Depends(get_current_role)) -> Role:
    """Allow either staff or owner (owner is allowed everywhere staff is)."""
    if role in ("owner", "staff"):
        return role
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Staff or owner privileges required",
    )


async def require_owner(role: Role = Depends(get_current_role)) -> Role:
    """Require owner privileges; staff receives 403 Forbidden."""
    if role == "owner":
        return role
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Owner privileges required",
    )


async def get_current_guest_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GuestSession:
    """Extract and validate guest session from signed httpOnly cookie.

    Every lookup filters expires_at > now() and returns 401 if expired.
    """
    cookie = request.cookies.get(GUEST_COOKIE_NAME)
    if not cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Guest session required",
        )

    session_id_str = unsign_value(cookie)
    if not session_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid guest session cookie",
        )

    try:
        session_id = uuid.UUID(session_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed guest session ID",
        ) from None

    stmt = select(GuestSession).where(
        GuestSession.id == session_id,
        GuestSession.expires_at > func.now(),
    )
    res = await db.execute(stmt)
    guest_session = res.scalar_one_or_none()

    if guest_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Guest session not found or expired",
        )

    return guest_session
