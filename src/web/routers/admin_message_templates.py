"""Admin API for the system-message catalog (admin-notifications.md, ADMSG-R7..R9). 10.B17.

Three verbs over one resource, and the shape of the resource is the whole design: **the list is
the catalog, not the table**. `GET` returns every key the core declares, each carrying its
default *and* its override if one exists, so a message added to the core shows up here the
moment it is written — nothing to seed, nothing to migrate (ADMSG-R9). `DELETE` removes the
override, which is how a template goes back to the default rather than being "reset" to a copy
of it.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import Response

from src.core import system_messages as sysmsg
from src.core.errors import APIError
from src.core.models import SystemMessageTemplate
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import MessageTemplateOut, MessageTemplatePut

router = APIRouter(prefix="/admin/message-templates", tags=["Admin: message templates"])


def _out(db: SessionDep, key: str) -> MessageTemplateOut:
    entry = sysmsg.entry(key)
    row = sysmsg.override(db, key)
    title, body = (row.title, row.body) if row else (entry.title, entry.body)
    unknown, _missing = sysmsg.validate_override(key, title, body)
    return MessageTemplateOut(
        key=key,
        title=title,
        body=body,
        default_title=entry.title,
        default_body=entry.body,
        placeholders=list(entry.placeholders),
        required=list(entry.required),
        is_override=row is not None,
        # Reported on read as well as on write: an override saved before a placeholder was
        # renamed in the core is still stored, still delivered, and still worth a warning the
        # next time somebody opens the page.
        unknown_placeholders=unknown,
    )


@router.get(
    "",
    response_model=list[MessageTemplateOut],
    summary="Every system message with its default, its override if any, and its placeholders.",
)
def list_templates(_admin: AdminDep, db: SessionDep) -> list[MessageTemplateOut]:
    return [_out(db, key) for key in sysmsg.all_keys(db)]


@router.put(
    "/{key}",
    response_model=MessageTemplateOut,
    summary="Rewrite one system message (admin only).",
)
def put_template(
    key: str, body: MessageTemplatePut, _admin: AdminDep, db: SessionDep
) -> MessageTemplateOut:
    if key not in sysmsg.CATALOG:
        raise APIError(404, "unknown_template", f"no system message {key!r}")
    _unknown, missing = sysmsg.validate_override(key, body.title, body.body)
    if missing:
        # The only refusal in this endpoint, and only two templates can trigger it. An unknown
        # placeholder is a warning because it degrades to literal text; a *missing required* one
        # means the message would go out without the thing it exists to carry — a credential
        # mail with no credential in it (Simone's rule, 2026-08-02).
        raise APIError(
            422,
            "missing_placeholder",
            f"this message must contain {', '.join('{' + m + '}' for m in missing)}",
        )
    row = sysmsg.override(db, key)
    if row is None:
        db.add(SystemMessageTemplate(key=key, title=body.title, body=body.body))
    else:
        row.title, row.body = body.title, body.body
    db.commit()
    return _out(db, key)


@router.delete(
    "/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Drop the override so the message goes back to the core's default (admin only).",
)
def delete_template(key: str, _admin: AdminDep, db: SessionDep) -> Response:
    row = sysmsg.override(db, key)
    if row is not None:
        db.delete(row)
        db.commit()
    # Idempotent: deleting an override that is not there leaves the key on its default, which
    # is exactly the state the caller asked for.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
