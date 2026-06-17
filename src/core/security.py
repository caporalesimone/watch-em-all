"""Password hashing (bcrypt) and JWT encode/decode (AUTH-R1..R5).

Tokens are HS256-signed (AUTH-R3). Claims: `sub` (user id), `role`, `tv`
(token_version), `typ` ("access"|"refresh"), `exp`, plus `jti` on refresh and
`mcp` (must_change_password) on access — `mcp` lets the per-request guard
enforce AUTH-R7 without a DB read (AUTH-R1).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # malformed stored hash → treat as a non-match, never raise to the caller
        return False


def new_jti() -> str:
    return secrets.token_hex(16)


@dataclass(frozen=True)
class TokenClaims:
    sub: int
    role: str
    tv: int
    typ: TokenType
    exp: datetime
    jti: str | None = None
    mcp: bool = False


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired or of the wrong type."""


def _encode(
    secret_key: str,
    *,
    sub: int,
    role: str,
    tv: int,
    typ: TokenType,
    ttl: timedelta,
    jti: str | None = None,
    mcp: bool = False,
) -> tuple[str, datetime]:
    now = datetime.now(tz=UTC)
    exp = now + ttl
    payload: dict[str, Any] = {
        "sub": str(sub),
        "role": role,
        "tv": tv,
        "typ": typ,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if jti is not None:
        payload["jti"] = jti
    if typ == "access":
        payload["mcp"] = mcp
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM), exp


def create_access_token(
    secret_key: str, *, sub: int, role: str, tv: int, ttl_min: int, mcp: bool
) -> tuple[str, datetime]:
    return _encode(
        secret_key,
        sub=sub,
        role=role,
        tv=tv,
        typ="access",
        ttl=timedelta(minutes=ttl_min),
        mcp=mcp,
    )


def create_refresh_token(
    secret_key: str, *, sub: int, role: str, tv: int, ttl_days: int, jti: str
) -> tuple[str, datetime]:
    return _encode(
        secret_key,
        sub=sub,
        role=role,
        tv=tv,
        typ="refresh",
        ttl=timedelta(days=ttl_days),
        jti=jti,
    )


def decode_token(secret_key: str, token: str, *, expected_typ: TokenType) -> TokenClaims:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("typ") != expected_typ:
        raise TokenError(f"expected a {expected_typ} token")

    try:
        return TokenClaims(
            sub=int(payload["sub"]),
            role=str(payload["role"]),
            tv=int(payload["tv"]),
            typ=expected_typ,
            exp=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
            jti=payload.get("jti"),
            mcp=bool(payload.get("mcp", False)),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenError("malformed token claims") from exc
