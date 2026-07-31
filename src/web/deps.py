"""Auth dependencies and guards (auth.md: require_user / require_admin).

`current_claims` validates the access token only (used by logout and
change-password, which must work while a password change is pending).
`require_user`/`require_admin` add the AUTH-R7 must-change-password gate and the
role check. No DB read on access verification (AUTH-R1) — the `mcp` claim carries
the must_change_password flag.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.core.config import Settings, get_settings
from src.core.db import get_session
from src.core.errors import APIError
from src.core.security import TokenClaims, TokenError, decode_token

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]

# Bearer scheme: makes Swagger show the "Authorize" button (paste just the token).
# auto_error=False so we return the project's {detail, code} envelope, not the default.
_bearer = HTTPBearer(auto_error=False, description="Paste the access_token (no 'Bearer ' prefix).")


def current_claims(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> TokenClaims:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise APIError(401, "not_authenticated", "missing bearer token")
    try:
        return decode_token(
            settings.core.secret_key, credentials.credentials, expected_typ="access"
        )
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


# Three levels, not two (9.B8). A super-user is a normal user with their own carts who is also
# trusted with the tools that send unplanned traffic to a site — the manual scrape above all,
# which is the quickest way to make requests a Crawl-delay never asked for. The direction is
# that manual scraping goes away; this phase narrows it to a role rather than removing it.
_SUPER_ROLES = frozenset({"admin", "super_user"})


def require_super_user(claims: UserDep) -> TokenClaims:
    """Admin or super-user. A plain user gets 403 — from the API, not from a hidden button."""
    if claims.role not in _SUPER_ROLES:
        raise APIError(403, "forbidden", "super-user role required")
    return claims


SuperUserDep = Annotated[TokenClaims, Depends(require_super_user)]
