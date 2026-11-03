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


def set_auth_cookie(response: Response, user_id: uuid.UUID) -> None:
    """Set 8-hour httpOnly signed authentication cookie carrying the signed-in user's id."""
    exp_ts = int(time.time()) + 8 * 3600
    val = f"{user_id}:{exp_ts}"
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
