# Auth / Session

> **Layer 4 — Capability** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/4-capabilities/core/auth.md`](../../../docs-ita/4-capabilities/core/auth.md), limited to what is implemented (DOC-12). Phase 1 ships the full stateless-JWT auth: login/logout, refresh with rotation, the forced first password change and the normal change, the initial-admin bootstrap and the login rate limit.

## Purpose

Stateless JWT authentication with lightweight invalidation, two roles, admin-managed accounts. Sized for ≤5 users: no OAuth/SSO/MFA.

Refresh rotation is the delicate part: every refresh issues a new pair and invalidates the previous one; reusing an old refresh is treated as theft.

## Requirements

- **AUTH-R1** — `access_token` (15 min) is verified **without the DB** (signature + expiry + type); `refresh_token` (7 days) is verified **against the DB** only on refresh. Lifetimes are configurable from bootstrap.
- **AUTH-R2** — Token claims: `sub` (user id), `role`, `tv` (token_version), `jti` (refresh only), `mcp` (`must_change_password`, access only), `typ` (`"access"` | `"refresh"`), `exp`. Verification **rejects** a token with the wrong `typ` for the context. The `mcp` claim lets the per-request guard enforce AUTH-R7 **without a DB read**.
- **AUTH-R3** — HS256 signature with `WEA_SECRET_KEY` (≥256 bits of entropy, from `.env`).
- **AUTH-R4** — **Refresh rotation**: each refresh issues a new pair and persists the new `jti` in `users.refresh_jti`. A refresh is valid only if `jti == users.refresh_jti` **and** `tv == users.token_version`. Reusing an old refresh (jti mismatch) is treated as possible theft: `token_version += 1` (global logout) + a log warning.
- **AUTH-R5** — **Global invalidation** via `token_version += 1`: logout, password change, password reset, disable. Declared tolerance: an already-issued access token lives up to 15 min.
- **AUTH-R6** — Login with an in-memory **rate limit** per IP+username (5 attempts/min; 429 over the threshold) and bcrypt password hashing, minimum length 8.
- **AUTH-R7** — `must_change_password`: set on account creation and reset; while active, functional endpoints answer **403** with a dedicated code and the UI forces the change. **Exempt**: `change-password`, `logout` and **`GET /api/me`** (the last one feeds the SPA boot, which reads the user — including the flag — to route). The **forced first change** appears right after the first login and does **not** require the current password; the **normal change** (from Profile) always requires and verifies it.
- **AUTH-R8** — No self-registration; accounts are created/managed by the admin. Bootstrap: first boot with no users → initial admin from `.env` with a forced change.
- **AUTH-R10** — A **disabled / being-deleted** account: logging in with **correct credentials** returns a dedicated code (`account_disabled`); with wrong credentials, a generic error indistinguishable from a missing account (the account state is not enumerable).

## Flows

```
POST /api/auth/login {username, password}
  → verify hash, rate limit
  → hash ok but is_active=false / being deleted → 403 {code: "account_disabled"}
  → wrong hash → generic 401 (never reveal the account state)
  → access(typ=access, tv, mcp) + refresh(typ=refresh, tv, jti=new); users.refresh_jti = jti
  → users.last_login_at = now()
  → { access_token, refresh_token, expires_at }     # expires_at = ACCESS expiry

POST /api/auth/refresh {refresh_token}
  → verify signature, exp, typ=refresh, tv == users.token_version, jti == users.refresh_jti
  → jti mismatch → token_version += 1; 401 (suspected reuse)
  → ok → new pair, users.refresh_jti = new jti

POST /api/auth/logout (Bearer)            → token_version += 1 → 204
POST /api/auth/change-password (Bearer) {old_password?, new_password}
  → if must_change_password (forced change): ignore old_password
  → else (normal change): old_password required + verified, and ≠ new
  → set hash, must_change_password=false, token_version += 1 → 204
```

Per-request verification (middleware): decode the bearer, require `typ == "access"`, expose `UserCtx(sub, role)`; no DB read (AUTH-R1). `tv` is not checked here — an access token survives at most 15 min after a logout/disable.

## Roles and guards

| Guard | Behaviour |
|---|---|
| `require_user` | any authenticated user; rejects with 403 while `must_change_password` (the `mcp` claim) |
| `require_admin` | `role == "admin"` |

## `users` table (auth fields)

`username` (UNIQUE), `first_name`, `last_name`, `password_hash`, `role`, `is_active`, `locale`, `must_change_password`, `token_version`, `refresh_jti`, `last_login_at` — full schema in [database/schema.md](../database/schema.md).
