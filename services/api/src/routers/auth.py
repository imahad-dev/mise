"""Authentication routes for owner and staff."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.access import get_current_user
from src.auth import clear_auth_cookie, set_auth_cookie
from src.config import settings
from src.database import get_db
from src.models.user import User
from src.passwords import hash_password, verify_password
from src.redis_client import redis_client
from src.request_limits import client_ip, enforce_ip_limit
from src.schemas.auth import (
    AuthConfigResponse,
    DemoLoginRequest,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Verified against when the email is unknown so timing does not reveal which emails exist.
_DUMMY_HASH = hash_password("dummy")


async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email.strip().lower())
    return (await db.execute(stmt)).scalar_one_or_none()


@router.get(
    "/config",
    response_model=AuthConfigResponse,
    status_code=status.HTTP_200_OK,
)
async def get_auth_config() -> AuthConfigResponse:
    """Return public authentication and environment config (e.g. demo_mode)."""
    return AuthConfigResponse(demo_mode=settings.demo_mode)


@router.post(
    "/demo-login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "Demo mode disabled or demo user not seeded"},
        429: {"description": "Rate limit exceeded (max 20 per minute per IP)"},
    },
)
async def demo_login(
    payload: DemoLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Sign in as the seeded demo owner or a venue's demo staff user in DEMO_MODE.

    Rate limited to 20 per minute per client IP. Returns 404 if DEMO_MODE is false.
    """
    if not settings.demo_mode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo mode is disabled",
        )

    await enforce_ip_limit(
        request,
        "demo_login",
        limit=20,
        window_s=60,
        detail="Too many demo login requests: rate limit is 20 per minute",
    )

    if payload.venue is not None and payload.venue not in settings.demo_restaurant_slugs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo user not found")
    if payload.role == "owner":
        email = settings.demo_owner_email
    else:
        venue = payload.venue or settings.demo_restaurant_slugs[0]
        email = f"demo-staff+{venue}@mise.demo"
    user = await _user_by_email(db, email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo user not found")

    set_auth_cookie(response, user.id)
    return LoginResponse(status="ok", name=user.name, email=user.email)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Invalid credentials"},
        429: {"description": "Too many failed login attempts"},
    },
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate a user by email and password and set httpOnly signed cookie.

    Rate limited via Redis to 5 failures per 5 minutes per client IP.
    """
    rl_key = f"rate_limit:login:{client_ip(request)}"

    # 1. Check rate limit in Redis
    try:
        failures = await redis_client.get(rl_key)
        if failures and int(failures) >= 5:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Redis error reading rate limit: %s", e)

    # 2. Verify password; an unknown email still costs one hash verification
    user = await _user_by_email(db, payload.email)
    if user is None:
        await run_in_threadpool(verify_password, payload.password, _DUMMY_HASH)
        is_valid = False
    else:
        is_valid = await run_in_threadpool(verify_password, payload.password, user.password_hash)

    if not is_valid or user is None:
        # Increment failure count
        try:
            count = await redis_client.incr(rl_key)
            if count == 1:
                await redis_client.expire(rl_key, 300)
            if count >= 5:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed login attempts",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Redis error setting rate limit: %s", e)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # 3. Successful authentication: clear failure count and set cookie
    try:
        await redis_client.delete(rl_key)
    except Exception as e:
        logger.warning("Redis error clearing rate limit: %s", e)

    set_auth_cookie(response, user.id)
    return LoginResponse(status="ok", name=user.name, email=user.email)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
)
async def logout(response: Response) -> LogoutResponse:
    """Clear authentication cookie."""
    clear_auth_cookie(response)
    return LogoutResponse(status="ok")


@router.get(
    "/me",
    response_model=MeResponse,
    status_code=status.HTTP_200_OK,
    responses={401: {"description": "Unauthenticated"}},
)
async def get_me(user: User = Depends(get_current_user)) -> MeResponse:
    """Return the signed-in user's name and email."""
    return MeResponse(name=user.name, email=user.email)
