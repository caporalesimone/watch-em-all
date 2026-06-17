from __future__ import annotations

import pytest

from src.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    new_jti,
    verify_password,
)

SECRET = "u" * 64


def test_password_hash_roundtrip() -> None:
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)


def test_verify_password_tolerates_garbage_hash() -> None:
    assert not verify_password("x", "not-a-bcrypt-hash")


def test_access_token_roundtrip_carries_mcp() -> None:
    token, _exp = create_access_token(SECRET, sub=7, role="admin", tv=3, ttl_min=15, mcp=True)
    claims = decode_token(SECRET, token, expected_typ="access")
    assert claims.sub == 7
    assert claims.role == "admin"
    assert claims.tv == 3
    assert claims.mcp is True
    assert claims.jti is None


def test_refresh_token_carries_jti() -> None:
    jti = new_jti()
    token, _exp = create_refresh_token(SECRET, sub=1, role="user", tv=0, ttl_days=7, jti=jti)
    claims = decode_token(SECRET, token, expected_typ="refresh")
    assert claims.jti == jti


def test_wrong_token_type_is_rejected() -> None:
    access, _ = create_access_token(SECRET, sub=1, role="user", tv=0, ttl_min=15, mcp=False)
    with pytest.raises(TokenError):
        decode_token(SECRET, access, expected_typ="refresh")


def test_bad_signature_is_rejected() -> None:
    access, _ = create_access_token(SECRET, sub=1, role="user", tv=0, ttl_min=15, mcp=False)
    with pytest.raises(TokenError):
        decode_token("other-secret-other-secret-other!", access, expected_typ="access")
