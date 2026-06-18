"""Profile endpoints (endpoints.md: GET/PATCH /api/me)."""

from __future__ import annotations

from fastapi import APIRouter

from src.core.errors import APIError
from src.core.models import User
from src.web.deps import ClaimsDep, SessionDep, UserDep
from src.web.schemas import MePatch, MeResponse

router = APIRouter(tags=["Me"])


def _to_response(user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        locale=user.locale,
        must_change_password=user.must_change_password,
    )


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Current user's profile (exempt from the must-change-password gate, for the SPA boot).",
)
def get_me(claims: ClaimsDep, db: SessionDep) -> MeResponse:
    # Exempt from the must-change-password gate (auth.md): the SPA boot reads /me
    # to learn the user (and the must_change_password flag) and route accordingly.
    user = db.get(User, claims.sub)
    if user is None:
        raise APIError(401, "invalid_token", "unknown user")
    return _to_response(user)


@router.patch(
    "/me",
    response_model=MeResponse,
    summary="Update the current user's profile (locale).",
)
def patch_me(body: MePatch, claims: UserDep, db: SessionDep) -> MeResponse:
    user = db.get(User, claims.sub)
    if user is None:
        raise APIError(401, "invalid_token", "unknown user")
    if body.locale is not None:
        # V1 is English-only: 'en' is the sole accepted value (endpoints.md).
        if body.locale != "en":
            raise APIError(400, "unsupported_locale", "only 'en' is supported in V1")
        user.locale = body.locale
    db.commit()
    return _to_response(user)
