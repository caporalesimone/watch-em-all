# Profile

> **Layer 3 — User feature** · Audience: architects, developers.
>
> English translation of the Italian reference [`docs-ita/3-features/user/profile-and-notifiers.md`](../../../docs-ita/3-features/user/profile-and-notifiers.md), limited to what is implemented (DOC-12). Phase 1 ships the **account** slice of the Profile page: read-only identity, interface language (V1 English-only), theme, and password change. Everything about **notification delivery** — the notifier channels, the alert cadence, the periodic report, the self-service data export — is spec-ahead (phases 6/7/11) and stays in the Italian reference.

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

## Deferred (spec-ahead)

The notification-delivery half of the page — the alert cadence (PROF-R4), the periodic report (PROF-R5), the self-service **data export** (PROF-R11), and the personal **notifier channels** with their composite state and the "no notifier configured" dashboard banner (PROF-R6..R10) — arrives with the alerts, notifier and reporting features in later phases. See the Italian reference for the full specification.
