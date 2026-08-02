# Profile

> **Layer 3 — User feature** · Audience: architects, developers.
>
> English translation of the Italian reference [`docs-ita/3-features/user/profile-and-notifiers.md`](../../../docs-ita/3-features/user/profile-and-notifiers.md), limited to what is implemented (DOC-12). Phase 1 shipped the **account** slice (identity, language, theme, password); **phase 7** adds the **notification channels** section (below). The alert cadence is gone (alerts are event-driven), the periodic report and the self-service data export remain spec-ahead (phases 10/11).

## Purpose

The Profile page gathers what concerns the account itself: identity, interface language, theme and password. In later phases it also becomes the home of notification delivery (personal notifier channels, alert cadence, periodic report) — those parts are not documented here.

## Requirements

### Account

- **PROF-R1** — **Password change** (old + new, with a minimum length): the change **invalidates all active sessions** (the user is signed out and must sign in again — AUTH-R5). The normal change always requires the current password; the **forced** change at first login (`must_change_password`) omits it. Endpoint: `POST /api/auth/change-password`.
- **PROF-R2** — **Interface language**, persisted on the profile (`PATCH /api/me {locale}`): used by the UI at every login and, later, by the core to generate notification text. **V1 is English-only**: `locale` is fixed to `en`, the selector is not exposed, but the plumbing (field, keys, per-user resolution) stays in place for future multilingual support.
- **PROF-R3** — The **theme** (light/dark) is a **browser** preference (not an account one), remembered locally; the default is dark. Stated choice: the theme is device aesthetics, the language is user identity.

## The profile page (implemented)

| Section | Content |
|---|---|
| Account | username, role, **first and last name** (read-only, set by the admin — USR-R15), interface language (fixed `English`) |
| Settings | theme toggle (light/dark), a browser-local preference |
| Change password | current + new + confirmation (min length enforced); on success the session is invalidated and the user returns to login |

## Notification channels (phase 7)

A **Notification channels** section lists every notifier the admin has made available. For each
channel the user sees its **composite state** and, where applicable, a personal config form (rendered
from the plugin's [`ConfigField`](../../4-capabilities/contracts/config-field.md) schema), an **on/off**
toggle and a **Test** button (outcome shown as a toast). See [notifier-plugin](../plugins/notifier-plugin.md).

- **PROF-R6/R7** — A channel delivers only when it is admin-enabled **and** its system config is
  complete **and** the user's required fields are valid **and** the user has activated it. The
  composite state is shown plainly (available / needs your details / active). A channel the admin has
  globally disabled is **not listed**.
- **PROF-R8** — Each configurable channel has a **Test** button: sends a test with the current merged
  config; no persistence.
- **PROF-R9** — Secret fields are masked and write-only (never returned); a stored value is shown as
  "saved" without revealing it.
- **PROF-R10** — Deactivating a channel keeps its config (re-activate without re-typing).
- **PROF-R12** (10.F17) — The **notification address** is the account itself. Since 10.B23 the username *is* an email address, so the profile **shows** it and offers nothing to edit: changing where your mail goes would mean changing who you sign in as, which is an administrator's operation. The **bootstrap admin** is the single exception — it signs in with a name rather than an address, so it sets its own `contact_email` (`PATCH /api/me {contact_email}`, validated and stored lowercase); every other account gets `403 address_not_editable`. Consequence for the email channel: it declares **no user fields** any more (10.B25), so what is left of it in the profile is the on/off switch, which a new account already has on.
- **In-app channel.** The in-app history is itself a channel, shown here as **always on** — the user
  cannot disable it (only the admin can, globally). So the dashboard banner no longer means "you get
  nothing"; it only nudges a user with **no external channel** active (e.g. email) to add one.

## Deferred (spec-ahead)

The **periodic report** (PROF-R5) and the self-service **data export** (PROF-R11) arrive in later
phases. The alert cadence (former PROF-R4) was removed — alerts are event-driven. See the Italian
reference for the full specification.
