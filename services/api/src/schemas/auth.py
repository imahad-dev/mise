"""Authentication schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    status: Literal["ok"]
    name: str
    email: str


class MeResponse(BaseModel):
    name: str
    email: str


class LogoutResponse(BaseModel):
    status: Literal["ok"]


class AuthConfigResponse(BaseModel):
    demo_mode: bool


class DemoLoginRequest(BaseModel):
    role: Literal["owner", "staff"]
    venue: str | None = None


class DemoVenueInfo(BaseModel):
    slug: str
    name: str
    city: str | None
    guest_url: str
    qr_token: str
    table_label: str


class DemoInfoResponse(BaseModel):
    owner_url: str
    kitchen_url: str
    venues: list[DemoVenueInfo]
