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
