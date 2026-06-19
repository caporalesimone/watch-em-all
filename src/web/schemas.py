"""Pydantic request/response models for the web API (BE-5, BE-19).

JSON is snake_case throughout (api/README). These models make the OpenAPI schema
complete by construction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: datetime  # expiry of the ACCESS token (AUTH-R)


class ChangePasswordRequest(BaseModel):
    # old_password is required for a normal change; omitted for the forced first
    # change (must_change_password), which appears right after login (auth.md).
    old_password: str | None = None
    new_password: str = Field(min_length=8)  # AUTH-R6


class MeResponse(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    role: str
    locale: str
    must_change_password: bool


class MePatch(BaseModel):
    locale: str | None = None


class HealthResponse(BaseModel):
    status: str
    db: str
    version: str
    worker_heartbeat_age_s: float | None = None


class UserCreate(BaseModel):
    # Admin-created account (USR-R1/R15): username + first/last name (both required)
    # + role + a temporary password the user must change at first login (USR-R2).
    username: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1, max_length=64)
    last_name: str = Field(min_length=1, max_length=64)
    role: Literal["admin", "user"]
    temp_password: str = Field(min_length=8)  # AUTH-R6


class AdminUserSummary(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
