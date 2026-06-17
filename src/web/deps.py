"""Auth dependencies and guards (auth.md: require_user / require_admin).

`current_claims` validates the access token only (used by logout and
change-password, which must work while a password change is pending).
`require_user`/`require_admin` add the AUTH-R7 must-change-password gate and the
role check. No DB read on access verification (AUTH-R1) — the `mcp` claim carries
the must_change_password flag.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from src.core.config import Settings, get_settings
from src.core.db import get_session
from src.core.errors import APIError
from src.core.security import TokenClaims, TokenError, decode_token

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]


def current_claims(
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenClaims:
    if not authorization or not authorization.startswith("Bearer "):
        raise APIError(401, "not_authenticated", "missing bearer token")
    token = authorization[len("Bearer ") :].strip()
    try:
        return decode_token(settings.core.secret_key, token, expected_typ="access")
    except TokenError as exc:
        raise APIError(401, "invalid_token", "invalid or expired token") from exc


ClaimsDep = Annotated[TokenClaims, Depends(current_claims)]


def require_user(claims: ClaimsDep) -> TokenClaims:
    if claims.mcp:
        raise APIError(403, "must_change_password", "password change required")
    return claims


UserDep = Annotated[TokenClaims, Depends(require_user)]


def require_admin(claims: UserDep) -> TokenClaims:
    if claims.role != "admin":
        raise APIError(403, "forbidden", "admin role required")
    return claims


AdminDep = Annotated[TokenClaims, Depends(require_admin)]
