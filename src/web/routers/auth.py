"""Auth endpoints (auth.md, endpoints.md). JWT with refresh rotation.

login → access + refresh (rotating jti). refresh → verify tv + jti against the
DB, rotate; a reused (stale-jti) refresh bumps token_version (global logout) and
401s. logout / change-password bump token_version (AUTH-R5).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from src.core.errors import APIError
from src.core.models import User
from src.core.rate_limit import RateLimiter
from src.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    new_jti,
    verify_password,
)
from src.web.deps import ClaimsDep, SessionDep, SettingsDep
from src.web.schemas import ChangePasswordRequest, LoginRequest, RefreshRequest, TokenPair

log = logging.getLogger(__name__)
router = APIRouter(tags=["Auth"])

# Per-process limiter (AUTH-R6): 5 attempts / minute per IP+username.
_login_limiter = RateLimiter(max_attempts=5, window_seconds=60.0)


def _issue_pair(settings: SettingsDep, user: User) -> TokenPair:
    """Mint a fresh access+refresh pair and rotate the user's refresh jti."""
    jti = new_jti()
    user.refresh_jti = jti
    access, access_exp = create_access_token(
        settings.core.secret_key,
        sub=user.id,
        role=user.role,
        tv=user.token_version,
        ttl_min=settings.core.access_token_ttl_min,
        mcp=user.must_change_password,
    )
    refresh, _ = create_refresh_token(
        settings.core.secret_key,
        sub=user.id,
        role=user.role,
        tv=user.token_version,
        ttl_days=settings.core.refresh_token_ttl_days,
        jti=jti,
    )
    return TokenPair(access_token=access, refresh_token=refresh, expires_at=access_exp)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Authenticate and return an access + refresh token pair (public).",
)
def login(body: LoginRequest, request: Request, settings: SettingsDep, db: SessionDep) -> TokenPair:
    client_ip = request.client.host if request.client else "unknown"
    rl_key = f"{client_ip}:{body.username.lower()}"
    if not _login_limiter.allow(rl_key):
        raise APIError(429, "rate_limited", "too many login attempts, try again shortly")

    user = db.scalar(select(User).where(User.username == body.username))
    # Wrong credentials must stay indistinguishable from a missing account (AUTH-R10).
    if user is None or not verify_password(body.password, user.password_hash):
        raise APIError(401, "invalid_credentials", "invalid username or password")
    # Correct credentials but disabled / being deleted → dedicated code (AUTH-R10).
    if not user.is_active or user.deletion_marked_at is not None:
        raise APIError(403, "account_disabled", "this account can no longer sign in")

    _login_limiter.reset(rl_key)
    user.last_login_at = datetime.now(tz=UTC)
    pair = _issue_pair(settings, user)
    db.commit()
    return pair


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Exchange a valid refresh token for a new token pair, rotating the jti (public).",
)
def refresh(body: RefreshRequest, settings: SettingsDep, db: SessionDep) -> TokenPair:
    try:
        claims = decode_token(settings.core.secret_key, body.refresh_token, expected_typ="refresh")
    except TokenError as exc:
        raise APIError(401, "invalid_token", "invalid or expired refresh token") from exc

    user = db.get(User, claims.sub)
    if user is None or not user.is_active or user.deletion_marked_at is not None:
        raise APIError(401, "invalid_token", "refresh not accepted")
    if claims.tv != user.token_version:
        raise APIError(401, "invalid_token", "stale refresh token")
    if claims.jti is None or claims.jti != user.refresh_jti:
        # Reuse of an old refresh → treat as theft: global logout (AUTH-R4).
        user.token_version += 1
        user.refresh_jti = None
        db.commit()
        log.warning(
            "refresh reuse detected for user_id=%s; bumped token_version (global logout)", user.id
        )
        raise APIError(401, "refresh_reuse", "refresh token reuse detected; please log in again")

    pair = _issue_pair(settings, user)  # rotates refresh_jti
    db.commit()
    return pair


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out everywhere: invalidate all of the current user's tokens.",
)
def logout(claims: ClaimsDep, db: SessionDep) -> Response:
    user = db.get(User, claims.sub)
    if user is not None:
        user.token_version += 1  # AUTH-R5: global logout
        user.refresh_jti = None
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the current user's password (the forced first change omits the old password).",
)
def change_password(body: ChangePasswordRequest, claims: ClaimsDep, db: SessionDep) -> Response:
    user = db.get(User, claims.sub)
    if user is None:
        raise APIError(401, "invalid_token", "unknown user")
    # The forced first change (must_change_password) appears immediately after
    # login and does NOT require the current password; a normal change always
    # does (auth.md, AUTH-R7).
    if not user.must_change_password:
        if not body.old_password:
            raise APIError(400, "old_password_required", "the current password is required")
        if not verify_password(body.old_password, user.password_hash):
            raise APIError(400, "invalid_old_password", "the current password is not correct")
        if body.new_password == body.old_password:
            raise APIError(
                400, "password_unchanged", "the new password must differ from the old one"
            )

    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(tz=UTC)  # 10.X1: the age `password_expiry` measures
    user.must_change_password = False
    user.token_version += 1  # AUTH-R5: invalidate all tokens; client logs in again
    user.refresh_jti = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
