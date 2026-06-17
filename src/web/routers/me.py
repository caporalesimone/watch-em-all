"""Profile endpoints (endpoints.md: GET/PATCH /api/me)."""

from __future__ import annotations

from fastapi import APIRouter

from src.core.errors import APIError
from src.core.models import User
from src.web.deps import SessionDep, UserDep
from src.web.schemas import MePatch, MeResponse

router = APIRouter(tags=["Me"])


def _to_response(user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        locale=user.locale,
        must_change_password=user.must_change_password,
    )


@router.get("/me", response_model=MeResponse)
def get_me(claims: UserDep, db: SessionDep) -> MeResponse:
    user = db.get(User, claims.sub)
    if user is None:
        raise APIError(401, "invalid_token", "unknown user")
    return _to_response(user)


@router.patch("/me", response_model=MeResponse)
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
