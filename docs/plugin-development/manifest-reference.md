# Manifest — Riferimento completo

> Audience: plugin developer.

Il `manifest.json` è il contratto dichiarativo del plugin: tutto ciò che il sistema sa di te senza eseguirti. Validato al load dal [Plugin Registry](../4-capabilities/core/plugin-registry.md): un campo invalido = plugin rifiutato con errore esplicito (il resto del sistema procede).

## Campi

| Campo | Tipo | Obbl. | Regole |
|---|---|---|---|
| `name` | string | ✅ | **È il `plugin_id`** in tutto il sistema. Snake_case, univoco. Deve coincidere con `plugin_id` dichiarato dalla tua classe (validato). Usato nel naming delle tabelle (`plugin_<name>_*`). |
| `display_name` | string | ✅ | Nome leggibile (sidebar, provenienza, hover). |
| `type` | `"scraper"` \| `"notifier"` | ✅ | Deve combaciare con la cartella (`scrapers/` ↔ `scraper`): mismatch = rifiutato. |
| `version` | string semver | ✅ | Versione del plugin (informativa). |
| `api_version` | int | ✅ | Versione del **contratto plugin** supportata. Se diversa da quella del core = rifiutato. Attuale: `1`. |
| `enabled` | bool | ✅ | **Unica source of truth** dell'attivazione. `false` = ignorato del tutto (nessun import). Cambiarlo richiede rebuild + restart. |
| `icon` | path | consigliato | Relativo alla cartella del plugin. SVG (o PNG ≥48px) quadrata; resa a 24×24 nelle celle di provenienza. Assente = icona neutra. |
| `backend.entry` | path | ✅ | **Relativo alla cartella del plugin** (es. `backend/__init__.py`). Deve esportare l'istanza del plugin. |
| `backend.locales` | path | notifier | Cartella dei file lingua backend (testi delle notifiche). |
| `frontend.entry` | path | ✅* | Relativo; esporta `default { component }`. *Omissibile solo per plugin senza UI propria (raro). |
| `frontend.route_base` | string | ✅* | Base delle route del plugin (es. `/plugins/nome-plugin`, kebab-case). **Unica fonte della route**: l'entry frontend non la ridichiara. |
| `frontend.locales` | path | ✅* | Cartella traduzioni UI (namespace dedicato al plugin). |

## Esempio completo

```json
{
  "name": "esempio_store",
  "display_name": "Esempio Store",
  "type": "scraper",
  "version": "1.2.0",
  "api_version": 1,
  "enabled": true,
  "icon": "frontend/assets/icon.svg",
  "backend":  { "entry": "backend/__init__.py" },
  "frontend": { "entry": "frontend/index.ts",
                "route_base": "/plugins/esempio-store",
                "locales": "frontend/locales" }
}
```

## Errori di validazione comuni

| Sintomo nel log | Causa |
|---|---|
| `type/cartella non combaciano` | plugin scraper messo in `notifiers/` (o viceversa) |
| `api_version incompatibile` | contratto del core evoluto: adegua il plugin e aggiorna il campo |
| `name duplicato` | un altro plugin usa lo stesso `name` |
| `plugin_id != manifest.name` | la classe dichiara un id diverso dal manifest |
| `entry non importabile` | path sbagliato (ricorda: **relativo alla cartella del plugin**) o errore di import nel modulo |

## Convenzioni di naming

- `name`: `snake_case` (finisce negli identificatori SQL).
- `route_base`: `kebab-case` (finisce negli URL).
- La coppia è correlata ma distinta (`esempio_store` ↔ `/plugins/esempio-store`).
