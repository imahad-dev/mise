"""Authentication routes for owner and staff."""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.auth import (
    Role,
    clear_auth_cookie,
    get_current_role,
    set_auth_cookie,
)
from src.config import settings
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
        404: {"description": "Demo mode disabled"},
        429: {"description": "Rate limit exceeded (max 20 per minute per IP)"},
    },
)
async def demo_login(
    payload: DemoLoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    """Issue signed auth cookie for owner or staff in DEMO_MODE without credentials.

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

    set_auth_cookie(response, payload.role)
    return LoginResponse(status="ok", role=payload.role)


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
) -> LoginResponse:
    """Authenticate staff or owner and set httpOnly signed cookie.

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

    # 2. Verify secret using constant-time byte comparison
    secret_bytes = payload.secret.encode("utf-8")
    if payload.role == "owner":
        is_valid = secrets.compare_digest(secret_bytes, settings.owner_api_key.encode("utf-8"))
    elif payload.role == "staff":
        is_valid = secrets.compare_digest(secret_bytes, settings.staff_pin.encode("utf-8"))
    else:
        is_valid = False

    if not is_valid:
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

    set_auth_cookie(response, payload.role)
    return LoginResponse(status="ok", role=payload.role)


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
async def get_me(role: Role = Depends(get_current_role)) -> MeResponse:
    """Return current authenticated role."""
    return MeResponse(role=role)
