"""Email notifier (email.md, notifier-development-guide.md). Phase 7 (7.B5–7.B7).

Delivers the alert digest by email over SMTP with STARTTLS, using only the standard library
(``smtplib`` / ``email``). Two-level config: the admin sets the shared server (host/port/creds/
from); each user supplies their delivery address. The digest is rendered as HTML (inline CSS for
client compatibility) with a plain-text fallback; strings live behind i18n keys in
``backend/i18n`` (V1: ``en`` only). Transient errors are retried a few times with backoff, then a
:class:`~src.core.plugins.base.NotifierDeliveryError` with a readable reason is raised; a
permanently refused recipient / auth failure fails immediately (no retry).
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import time
from decimal import Decimal
from email.message import EmailMessage
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any

from src.core.alert_engine import (
    AlertEvent,
    CartAlertPayload,
    NotificationEvent,
    TextMessageEvent,
)
from src.core.contracts import ACCOUNT_EMAIL_KEY, ConfigField
from src.core.plugins.base import NotifierDeliveryError, NotifierPlugin
from src.core.plugins.context import MarkdownHelper, PluginContext

_I18N_DIR = Path(__file__).resolve().parent / "i18n"

_CURRENCY_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF "}

# Dev-only convenience (set ONLY in compose-dev.yml, never in production): pre-fill the config
# form with Mailpit-friendly defaults so a developer can configure the channel in one click. The
# channel still shows as "not configured" until the admin saves — defaults are form hints, not
# stored values. In production the flag is unset and the schema keeps sensible SMTP defaults.
_DEV_MAILPIT = os.environ.get("WEA_DEV_MAILPIT_DEFAULTS", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


@lru_cache(maxsize=8)
def _strings(locale: str) -> dict[str, str]:
    """Merged translations: ``en`` (mandatory, always complete) overlaid with ``locale`` if the
    file exists (NOT-R4). V1 ships only ``en`` — the fallback is the whole dictionary."""
    base: dict[str, str] = json.loads((_I18N_DIR / "en.json").read_text(encoding="utf-8"))
    path = _I18N_DIR / f"{locale}.json"
    if locale != "en" and path.is_file():
        base.update(json.loads(path.read_text(encoding="utf-8")))
    return base


def _money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "—"
    sym = _CURRENCY_SYMBOL.get(currency.upper(), currency + " ")
    return f"{sym}{value:.2f}"


# The Difference rule itself is **not** here any more (C19): it lives in the core and arrives
# already rendered in the payload, so this notifier and the in-app history cannot say different
# numbers about the same digest. A notifier's job is presentation.


class EmailNotifierPlugin(NotifierPlugin):
    plugin_id = "email"
    display_name = "Email"

    # Retry policy (NOT-R5): a few transient attempts with growing backoff. Class attributes so
    # tests can shrink the backoff; production keeps the readable defaults.
    retries = 3
    backoff_base_s = 1.0

    # Handed over at load time; see `initialize`. None until then, which `_render` treats as one
    # more reason to degrade rather than to fail.
    _markdown: MarkdownHelper | None = None

    def get_admin_config_schema(self) -> list[ConfigField]:
        # Dev pre-fill (Mailpit) vs production defaults; see _DEV_MAILPIT above.
        host_default = "mailpit" if _DEV_MAILPIT else None
        port_default = 1025 if _DEV_MAILPIT else 587
        tls_default = not _DEV_MAILPIT  # Mailpit: TLS off; production: on
        from_default = "watch@mailpit.local" if _DEV_MAILPIT else None
        # Three rows instead of six (10.F26). The widths say what belongs together: an SMTP
        # server is one thought — where it is, on which port, with or without TLS — and reading
        # it down a column of six made the admin assemble it themselves. Credentials are the
        # second pair; the sender address stands alone because it is not part of the server.
        return [
            ConfigField(
                key="smtp_host",
                label_key="email.cfg.host",
                type="text",
                required=True,
                default=host_default,
                width="half",
            ),
            ConfigField(
                key="smtp_port",
                label_key="email.cfg.port",
                type="number",
                default=port_default,
                width="quarter",
            ),
            ConfigField(
                key="use_tls",
                label_key="email.cfg.tls",
                type="bool",
                default=tls_default,
                width="quarter",
            ),
            ConfigField(key="smtp_user", label_key="email.cfg.user", type="text", width="half"),
            ConfigField(
                key="smtp_password", label_key="email.cfg.pass", type="password", width="half"
            ),
            ConfigField(
                key="from_address",
                label_key="email.cfg.from",
                type="email",
                required=True,
                default=from_default,
            ),
        ]

    def get_user_config_schema(self) -> list[ConfigField]:
        """Nothing (10.B25). The channel used to ask each person for a delivery address; since
        10.B23 the account *is* an address, so the core injects it (``ACCOUNT_EMAIL_KEY``) and
        there is no second field left to disagree with the first. What remains for the user is
        the on/off switch, which is not config — it lives on the row, not in the schema."""
        return []

    # -------------------------------------------------------------- send

    def initialize(self, context: PluginContext) -> None:
        # Kept for the Markdown helpers (AEV-R7): `send` does not receive the context, and the
        # rendering must come from the core rather than from a parser of this plugin's own.
        self._markdown = context.markdown

    def send(self, notification: NotificationEvent, config: dict[str, Any], locale: str) -> None:
        if isinstance(notification, AlertEvent):
            subject, html, text = self._format(notification, _strings(locale))
        else:
            subject, html, text = self._format_message(notification, _strings(locale))
        self._deliver(config, subject, html, text)

    def _format_message(self, event: TextMessageEvent, s: dict[str, str]) -> tuple[str, str, str]:
        """A text message as an email: the title is the subject, the body is the message.

        No digest furniture around it — an announcement that arrived wrapped in "here are your
        price alerts" would be lying about what it is.
        """
        body_html, body_text = self._render(event.body)
        html = _HTML_SHELL.format(
            heading=escape(event.title), body=body_html, footer=escape(s["footer"])
        )
        return event.title, html, f"{event.title}\n\n{body_text}\n"

    def _render(self, body: str) -> tuple[str, str]:
        """Markdown → (sanitised HTML, plain text), degrading rather than failing (NOT-R8).

        If the helper is missing or throws, the message still goes out with its body escaped and
        its line breaks kept. A formatting problem must never be the reason somebody does not
        hear about scheduled maintenance — which is exactly the kind of message this carries.
        """
        try:
            if self._markdown is None:
                raise RuntimeError("markdown helper unavailable")
            return self._markdown.to_html(body), self._markdown.strip(body)
        except Exception:
            return f"<p>{escape(body).replace(chr(10), '<br>')}</p>", body

    def send_test(self, config: dict[str, Any], locale: str, username: str = "") -> None:
        subject, html, text = self._format_test(username, _strings(locale))
        self._deliver(config, subject, html, text)

    def _format_test(self, username: str, s: dict[str, str]) -> tuple[str, str, str]:
        """A dedicated, simple test email (not a fake digest): the eyes, the title, and a one-line
        message naming the account the test was run for."""
        body = s["test.body"].format(username=username or "—")
        html = _TEST_SHELL.format(
            title=escape(s["test.title"]), body=escape(body), note=escape(s["test.note"])
        )
        text = f"👀 {s['test.title']}\n\n{body}\n"
        return s["subject.test"], html, text

    # -------------------------------------------------------------- formatting

    def _format(self, event: AlertEvent, s: dict[str, str]) -> tuple[str, str, str]:
        n = len(event.cart_alerts)
        subject = s["subject.digest.one"] if n == 1 else s["subject.digest.many"].format(count=n)

        html_parts: list[str] = []
        text_parts: list[str] = []
        for cart in event.cart_alerts:
            html_parts.append(self._cart_html(cart, s))
            text_parts.append(self._cart_text(cart, s))

        html = _HTML_SHELL.format(
            heading=escape(s["heading"]), body="".join(html_parts), footer=escape(s["footer"])
        )
        text = f"{s['heading']}\n\n" + "\n\n".join(text_parts) + f"\n\n{s['footer']}\n"
        return subject, html, text

    def _cart_html(self, cart: CartAlertPayload, s: dict[str, str]) -> str:
        badges = "".join(
            f'<span style="{_BADGE}">{escape(s.get(f"event.{e}", e))}</span>'
            for e in cart.cart_events
        )
        rows: list[str] = []
        for p in cart.products:
            tags = " ".join(escape(s.get(f"tag.{t}", str(t))) for t in p.tags)
            name_cell = f'{escape(p.name)}<br><small style="color:#6b7280">{tags}</small>'
            rows.append(
                "<tr>"
                f'<td style="{_TD}">{name_cell}</td>'
                f'<td style="{_TD}">{escape(p.plugin_id)}</td>'
                f'<td style="{_TD}">{escape(_money(p.price_previous, p.currency))}</td>'
                f'<td style="{_TD}"><b>{escape(_money(p.price_current, p.currency))}</b></td>'
                # Rendered, not computed: the rule lives in the core and travels in the payload
                # (C19), so this table and the in-app history cannot drift apart.
                f"{_difference_td(p.difference)}"
                f'<td style="{_TD}"><a href="{escape(p.url)}">{escape(s["open"])}</a></td>'
                "</tr>"
            )
        table = (
            f'<table style="{_TABLE}"><thead><tr>'
            f'<th style="{_TH}">{escape(s["product"])}</th>'
            f'<th style="{_TH}">{escape(s["source"])}</th>'
            f'<th style="{_TH}">{escape(s["was"])}</th>'
            f'<th style="{_TH}">{escape(s["now"])}</th>'
            f'<th style="{_TH}">{escape(s["difference"])}</th>'
            f'<th style="{_TH}"></th>'
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
            if cart.products
            else ""
        )
        return (
            f'<h2 style="font-size:16px;margin:24px 0 8px">{escape(s["cart"])}: '
            f"{escape(cart.cart_name)}</h2>{badges}{table}{self._totals_html(cart, s)}"
        )

    def _totals_html(self, cart: CartAlertPayload, s: dict[str, str]) -> str:
        cur = cart.products[0].currency if cart.products else "EUR"
        final = escape(_money(cart.totals.final, cur))
        out = f'<p style="margin:8px 0"><b>{escape(s["total"])}:</b> {final}'
        if cart.threshold is not None:
            mark = " ✅" if cart.threshold.reached else ""
            out += (
                f" &nbsp;|&nbsp; {escape(s['threshold'])}: "
                f"{escape(_money(cart.threshold.target, cur))}{mark}"
            )
        return out + "</p>"

    def _cart_text(self, cart: CartAlertPayload, s: dict[str, str]) -> str:
        cur = cart.products[0].currency if cart.products else "EUR"
        lines = [f"{s['cart']}: {cart.cart_name}"]
        for e in cart.cart_events:
            lines.append(f"  * {s.get(f'event.{e}', e)}")
        for p in cart.products:
            tags = ", ".join(s.get(f"tag.{t}", str(t)) for t in p.tags)
            diff = p.difference
            lines.append(
                f"  - {p.name} [{p.plugin_id}] "
                f"{_money(p.price_previous, p.currency)} -> {_money(p.price_current, p.currency)} "
                f"({diff or '—'}) {tags} {p.url}"
            )
        lines.append(f"  {s['total']}: {_money(cart.totals.final, cur)}")
        return "\n".join(lines)

    # -------------------------------------------------------------- delivery

    def _deliver(self, config: dict[str, Any], subject: str, html: str, text: str) -> None:
        host = str(config.get("smtp_host") or "").strip()
        from_addr = str(config.get("from_address") or "").strip()
        # The recipient comes from the account, not from this channel's config (10.B25).
        to_addr = str(config.get(ACCOUNT_EMAIL_KEY) or "").strip()
        if not host or not from_addr or not to_addr:
            raise NotifierDeliveryError("email: incomplete configuration (host/from/to)")
        try:
            port = int(config.get("smtp_port") or 587)
        except (TypeError, ValueError):
            port = 587
        user = config.get("smtp_user") or None
        password = config.get("smtp_password") or ""
        use_tls = bool(config.get("use_tls", True))

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")

        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                with smtplib.SMTP(host, port, timeout=15) as smtp:
                    if use_tls:
                        smtp.starttls(context=ssl.create_default_context())
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(msg)
                return
            except smtplib.SMTPRecipientsRefused as exc:  # permanent: no retry
                raise NotifierDeliveryError(f"email: recipient refused ({to_addr})") from exc
            except smtplib.SMTPAuthenticationError as exc:  # permanent: no retry
                raise NotifierDeliveryError("email: authentication failed") from exc
            except Exception as exc:  # transient: retry with backoff
                last_exc = exc
                if attempt < self.retries - 1:
                    time.sleep(self.backoff_base_s * (2**attempt))
        raise NotifierDeliveryError(f"email: channel unreachable ({last_exc})")


# Inline styles kept as short constants (email clients need inline CSS, no <style>).
_TABLE = "border-collapse:collapse;width:100%;font-size:14px"
_TH = "text-align:left;border-bottom:2px solid #e5e7eb;padding:6px 8px;color:#374151"
_TD = "border-bottom:1px solid #f3f4f6;padding:6px 8px"
# Direction colour for the Difference cell, keyed by the sign the text carries: a rise is
# against the buyer (red), a drop in their favour (green); an unchanged price stays neutral.
_DIFF_COLOR = {"+": ";color:#b91c1c", "-": ";color:#047857"}


def _difference_td(text: str | None) -> str:
    """One Difference cell: the signed percentage, coloured by direction; an em dash when
    there is no previous price to compare against."""
    if text is None:
        return f'<td style="{_TD}">—</td>'
    return f'<td style="{_TD}{_DIFF_COLOR.get(text[0], "")}">{escape(text)}</td>'


_BADGE = (
    "display:inline-block;background:#eef2ff;color:#3730a3;border-radius:6px;"
    "padding:2px 8px;margin:0 4px 4px 0;font-size:12px"
)
_SHELL_DIV = "font-family:Arial,Helvetica,sans-serif;color:#111827;max-width:640px;margin:0 auto"
_HTML_SHELL = (
    f'<div style="{_SHELL_DIV}">'
    '<h1 style="font-size:20px">{heading}</h1>{body}'
    '<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">'
    '<p style="color:#6b7280;font-size:12px">{footer}</p></div>'
)

# The test email: a small centred card with the eyes, the title and a one-line message.
_TEST_CARD = (
    "font-family:Arial,Helvetica,sans-serif;color:#111827;max-width:480px;margin:0 auto;"
    "text-align:center;padding:32px 24px;border:1px solid #e5e7eb;border-radius:14px"
)
_TEST_SHELL = (
    f'<div style="{_TEST_CARD}">'
    '<div style="font-size:56px;line-height:1">👀</div>'
    '<h1 style="font-size:24px;margin:12px 0 6px">{title}</h1>'
    '<p style="font-size:15px;color:#374151;margin:0">{body}</p>'
    '<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">'
    '<p style="color:#9ca3af;font-size:12px;margin:0">{note}</p></div>'
)

plugin = EmailNotifierPlugin()
