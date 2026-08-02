# Notifier plugin (generic contract)

> **Layer 3 — Feature plugin** · Audience: architects, plugin developers · English mirror of the
> Italian reference [`docs-ita/3-features/plugins/notifier-plugin.md`](../../../docs-ita/3-features/plugins/notifier-plugin.md),
> limited to what is implemented (DOC-12, phase 7). Contract: [config-field](../../4-capabilities/contracts/config-field.md) ·
> Payload: [alert-event](../../4-capabilities/contracts/alert-event.md) · Concrete channel: [email](../../implemented-plugins/notifiers/email.md).

A notifier is the translator between the notification content (the core decides **what** and
**when**) and a delivery channel (the plugin decides **how to format** and **where to send**).

## Responsibilities: core vs plugin

| Responsibility | Core | Plugin |
|---|---|---|
| Decide when to send (after each scrape) | ✅ | — |
| Build the content (the digest) | ✅ | — |
| Write the in-app history (always) | ✅ | — |
| Iterate the user's active channels | ✅ | — |
| Merge admin+user config (keys filtered per side) | ✅ | — |
| Pass the user's locale | ✅ | — |
| Record the per-channel outcome | ✅ | — |
| Declare the config schema (admin + user) | — | ✅ |
| Format the message for the channel | — | ✅ |
| Send on the channel | — | ✅ |
| Short retries on transient errors | — | ✅ |

## The contract (implemented in phase 7)

```python
class NotifierPlugin(BasePlugin):
    display_name: str
    def get_admin_config_schema(self) -> list[ConfigField]: ...   # system infrastructure
    def get_user_config_schema(self)  -> list[ConfigField]: ...   # personal target
    def send(self, notification, config: dict, locale: str) -> None: ...   # AlertEvent (digest)
    def send_test(self, config: dict, locale: str) -> None: ...            # test, no persistence
```

- **NOT-R2 — Two-level config.** `admin` (channel infrastructure, e.g. server + credentials) and
  `user` (personal target + on/off), both from a declarative schema ([config-field](../../4-capabilities/contracts/config-field.md)).
  Without the admin part the channel is "not available" to everyone.
- **NOT-R5 — Errors.** The plugin does a few short retries with backoff on transient errors, then
  raises `NotifierDeliveryError` with a readable reason. The core records the final per-channel
  outcome (`delivered`/`failed`/`skipped`); a failed channel blocks neither the others nor the history.
- **NOT-R6 — Test.** Every notifier sends a **test** with the current merged config. **Admin-only
  since 10.X4**: the probe answers *"does the system config work"*, which is a question for whoever
  can fix it, and its target is the admin's own account rather than an address typed in a field. No
  persistence.
- **NOT-R9 — A channel proves itself before it is switched on** (10.B28). The test of NOT-R6 is
  that proof: `POST /api/admin/notifiers/{id}/validate` sends a real message and, **if the server
  accepts it**, records the settings as validated. Until then the kill-switch refuses to go on
  (`422 not_validated`) and the channel is not available to anybody. Three consequences worth
  stating:
  - **What is claimed is narrow, on purpose.** The server took the message. Whether it then
    delivers it, files it as spam or bounces it is between that server and the recipient — an
    installation that claimed more would have to become a mail monitor.
  - **The proof is about a configuration, not a channel.** What is stored is a fingerprint of the
    settings that worked, so editing one invalidates the proof by arithmetic rather than by
    somebody remembering to clear a flag — and a channel whose settings change is switched off.
  - **A failure records nothing**, so a channel never drifts into "validated" by having been tried.
  In-app is exempt: it has no server to accept anything and no config to get wrong.
- **NOT-R7 — Content survives formatting.** Whatever the channel format, the decision-carrying data
  must survive: event tags, before/after prices, **provenance**, links, cart totals and threshold.

## Delivery (asynchronous, decoupled from the scrape)

The alert engine always writes the digest to `alert_log`. Then the core records one `alert_delivery`
row per active channel. The **in-app** channel is local → marked `delivered` inline. Network channels
start `pending`; a **separate periodic worker step** drains them (send + the plugin's retry, then
`delivered`/`failed`). Best-effort: a `failed` row is not re-drained — the next digest carries the
new state. See [notification-architecture](../../2-architecture/notification-architecture.md).

## The in-app channel

`in_app` is a first-class notifier used to unify dispatch: no config, **always active for the user**
(cannot be user-disabled), delivered inline (the history record is the delivery). Only the admin
kill-switch can disable it globally.

## Channel state for a user

A channel delivers only when **all** hold — each level has its owner:

| Condition | Owner |
|---|---|
| Plugin enabled in the manifest (deploy) | manifest |
| Admin kill-switch on (PCFG-R8) | admin |
| System config complete | admin |
| Personal config valid | user |
| Channel activated | user (in-app: always on) |
