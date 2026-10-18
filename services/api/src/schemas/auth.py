"""Authentication schemas."""

from typing import Literal

from pydantic import BaseModel


class LoginRequest(BaseModel):
    role: Literal["owner", "staff"]
    secret: str


class LoginResponse(BaseModel):
    status: Literal["ok"]
    role: Literal["owner", "staff"]


class MeResponse(BaseModel):
    role: Literal["owner", "staff"]


class LogoutResponse(BaseModel):
    status: Literal["ok"]


class AuthConfigResponse(BaseModel):
    demo_mode: bool


class DemoLoginRequest(BaseModel):
    role: Literal["owner", "staff"]


class DemoInfoResponse(BaseModel):
    guest_url: str
    owner_url: str
    kitchen_url: str
    qr_token: str | None = None
    table_label: str | None = None
