# Manifest — reference

> Audience: plugin developer.
>
> Phase 2 ships the manifest and its load-time validation; the configuration fields (admin/user schemas) arrive with the config infrastructure in later phases.

The `manifest.json` is the plugin's declarative contract: everything the system knows about it without executing it. It is validated at load by the [plugin registry](../4-capabilities/core/plugin-registry.md); an invalid field means the plugin is rejected with an explicit error, while the rest of the system carries on.

## Fields

| Field | Type | Req. | Rules |
|---|---|---|---|
| `name` | string | ✅ | **The `plugin_id`** across the system. snake_case, unique. Must equal the `plugin_id` declared by your class (validated). Used in table names (`plugin_<name>_*`). |
| `display_name` | string | ✅ | Human-readable (sidebar, provenance). |
| `type` | `"scraper"` \| `"notifier"` | ✅ | Must match the folder (`scrapers/` ↔ `scraper`): mismatch = rejected. |
| `version` | string (semver) | ✅ | The plugin's own version (informative). |
| `api_version` | int | ✅ | The supported **plugin-contract** version. Different from the core's = rejected. Current: `1`. |
| `enabled` | bool | ✅ | **The only source of truth** for activation. `false` = ignored entirely (no import). Changing it needs a rebuild + restart. |
| `icon` | path | optional | Explicit override (relative to the plugin folder). **If omitted**, the core auto-detects `frontend/assets/plugin-icon.{ico,svg}` (prefers `.ico`), resolved **once at load**. Square, rendered at 24×24 in the provenance cells. No file = neutral icon. |
| `backend.entry` | path | ✅ | **Relative to the plugin folder** (e.g. `backend/__init__.py`). Must export the plugin instance as `plugin`. |
| `backend.i18n` | path | notifier | Backend language folder (notification texts). `en.json` is the fallback. |
| `frontend.entry` | path | ✅\* | Relative; exports `default { component }`. *Omitted only by plugins without their own UI (notifiers).* |
| `frontend.route_base` | string | ✅\* | The plugin's route base, e.g. `/plugins/my-store` (kebab-case under `/plugins/`). **The only source of the route**: the frontend entry never re-declares it. The backend mounts the plugin's API at `/api` + `route_base`. |
| `frontend.i18n` | path | ✅\* | UI translations folder. Default export `{ <locale>: messages }`; the core registers it. |

## Example (scraper)

```json
{
  "name": "my_store",
  "display_name": "My Store",
  "type": "scraper",
  "version": "1.0.0",
  "api_version": 1,
  "enabled": true,
  "backend":  { "entry": "backend/__init__.py" },
  "frontend": { "entry": "frontend/index.ts",
                "route_base": "/plugins/my-store",
                "i18n": "frontend/i18n" }
}
```

A notifier omits the whole `frontend` block (it has no page of its own).

## Common validation errors

| Symptom in the log | Cause |
|---|---|
| `type ... does not match its folder` | a scraper placed in `notifiers/` (or vice versa) |
| `api_version ... incompatible` | the core contract evolved: adjust the plugin and the field |
| `duplicate plugin name` | another plugin uses the same `name` |
| `plugin_id ... does not match manifest name` | the class declares a different id than the manifest |
| `backend entry not found` / import error | wrong path (**relative to the plugin folder**) or an error in the module |

## Naming conventions

- `name`: `snake_case` (ends up in SQL identifiers).
- `route_base`: a `kebab-case` slug under `/plugins/` (ends up in URLs).
- The pair is related but distinct (`my_store` ↔ `/plugins/my-store`).
