"""Profile endpoints (endpoints.md: GET/PATCH /api/me)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.core.alert_cadence import get_schedule, upsert_schedule
from src.core.alert_engine import delete_all_snapshots, seed_all_snapshots
from src.core.errors import APIError
from src.core.models import AlertSchedule, User
from src.web.adjust import make_adjuster_provider
from src.web.deps import ClaimsDep, SessionDep, UserDep
from src.web.schemas import AlertScheduleOut, AlertSchedulePut, MePatch, MeResponse

router = APIRouter(tags=["Me"])

# Default cadence for a user who has never set one (endpoints.md GET): off, 09:00.
_DEFAULT_TIME = "09:00:00"


def _schedule_out(
    row: AlertSchedule | None, baseline_effect: str | None = None
) -> AlertScheduleOut:
    if row is None:
        return AlertScheduleOut(scheduled_time=_DEFAULT_TIME, weekdays=[], baseline_effect=None)
    return AlertScheduleOut(
        scheduled_time=row.scheduled_time,
        weekdays=list(row.weekdays),
        baseline_effect=baseline_effect,
    )


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


@router.get("/me/alert-schedule", response_model=AlertScheduleOut, summary="Get the alert cadence.")
def get_alert_schedule(user: UserDep, db: SessionDep) -> AlertScheduleOut:
    return _schedule_out(get_schedule(db, user.sub))


@router.put(
    "/me/alert-schedule",
    response_model=AlertScheduleOut,
    summary="Set the alert cadence (weekdays + time); [] weekdays = off.",
)
def put_alert_schedule(
    body: AlertSchedulePut, user: UserDep, db: SessionDep, request: Request
) -> AlertScheduleOut:
    """Set the per-account cadence (ALERT-R1). Turning it **off** ([] weekdays) deletes the
    user's baselines; turning it **on** re-seeds them from the current state (ALERT-R3) —
    the response declares which happened so the UI can warn that monitoring restarts now."""
    prev = get_schedule(db, user.sub)
    was_off = prev is None or not prev.weekdays

    try:
        row = upsert_schedule(db, user.sub, body.scheduled_time, body.weekdays)
    except ValueError as exc:
        raise APIError(422, "invalid_schedule", str(exc)) from exc
    now_off = not row.weekdays
    db.commit()

    effect: str | None = None
    if was_off and not now_off:  # off → on: re-seed baselines from now
        seed_all_snapshots(db, user.sub, make_adjuster_provider(request))
        effect = "reseeded"
    elif now_off and not was_off:  # on → off: drop baselines (no backlog on re-enable)
        delete_all_snapshots(db, user.sub)
        db.commit()
        effect = "cleared"
    return _schedule_out(row, effect)
