# Configuration

**English** · [Português (Brasil)](Configuracao.md)

## Where everything lives (app-data)

| Path | What it is |
|---|---|
| `config.yaml` | global config: profiles (defaults/alerts/actions), `ui`, `schedule`, `evidence` |
| `selections/<name>.json` | ROI selections (one per target), with optional `overrides` |
| `state.json` | lightweight state: `last_selection`, `profile`, `language`, `action_selection`, `evidence_enabled` |
| `logs/` | `alerts.jsonl` (alerts) and `actions.jsonl` (actions audit) |

Base: `%APPDATA%\screen_watch` (Windows), `~/.config/screen_watch` (Linux),
`~/Library/Application Support/screen_watch` (macOS) — or the `SCREEN_WATCH_HOME` override.
See the effective paths with `python -m screen_watch show-paths`.

## `config.yaml` v2

The YAML is **global**: it defines an active profile, one or more named profiles, and the `ui`,
`schedule` and `evidence` sections. Targets live in `selections/*.json` (no longer in the YAML).

```yaml
version: 2
profile: default                 # active profile; switchable with --profile / GUI selector
profiles:
  default:
    defaults:
      mode: "advanced"           # "light" | "default" | "advanced"
      poll_interval_s: 2.0       # minimum 1.0
      rearm: true
      humanize:                  # pseudo-human noise of the actions
        mouse_steps: 24
        key_interval_ms: 60
        jitter_px: 3
        wait_jitter_ms: 150
        seed: null               # for deterministic tests only
      compare_options:
        light:    { threshold: 12.0 }
        default:  { hash_size: 8, threshold: 6 }
        advanced: { similarity_threshold: 0.92, psm: 6, lang: "por+eng", upscale: 2,
                    tesseract_cmd: null }
    alerts:
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.mp3" }
      - { type: "popup",    enabled: true, severity_min: 1, cooldown_s: 30 }
      - { type: "telegram", enabled: true, severity_min: 2, cooldown_s: 60,
          bot_token_env: "TELEGRAM_BOT_TOKEN", chat_id: "123456789", attach_roi: true }
      - { type: "log",      enabled: true, severity_min: 1, cooldown_s: 0 }   # optional
    actions: []                  # see wiki/Pseudo-Human-Actions.md
  trabalho:
    defaults: { mode: "default", poll_interval_s: 1.0 }
ui:
  hotkeys: { arm: "<ctrl>+<alt>+a", disarm: "<ctrl>+<alt>+d", toggle: "<ctrl>+<alt>+<space>",
             rearm: "<ctrl>+<alt>+r", abort: "<esc>" }
  arm_durations_min: [1, 5, 15, 30]
  language: auto                 # auto | pt-BR | en-US | tag discovered in i18n/*.json
schedule: { enabled: false, days: [mon, tue, wed, thu, fri], windows: ["08:00-12:00"] }
evidence: { enabled: false, dir: null, keep_per_target: 50, max_total_mb: 200,
            on_baseline: true, on_change: true, per_step: false }
```

**Rules**:

- **Secrets never in the YAML** — only the name of the environment variable (`bot_token_env`).
- `version` accepts **1 or 2**; any other value is an error. v2 **requires** `profiles`.
- A nonexistent `profile` is a validation error.
- A missing `version` with `targets:` is treated as **legacy v1** (with a warning) and converted by
  `migrate-config`.
- An unknown `ui.language` generates a warning and falls back to `auto` (it is not an error).
- The app rewrites the YAML **without preserving comments**; the write is atomic (temp + `os.replace`)
  and leaves a `config.yaml.bak` backup.

## Alert channels

Each item of `alerts:` accepts `type`, `enabled`, `severity_min`, `cooldown_s` and an optional **`id`**
(default `type`; `type#n` when repeated). The `id` is the **cooldown key** and the selection name for the
send test. The four original types (`sound`/`popup`/`telegram`/`log`) use **flat fields**; the new ones
use a nested **`options:`** block:

```yaml
alerts:
  - type: webhook
    id: teams
    severity_min: 2
    cooldown_s: 60
    options:
      url_env: TEAMS_WEBHOOK             # or url: "https://..."
      method: POST                       # POST | PUT | PATCH
      headers: { Content-Type: "application/json" }
      payload: { text: "Change on ${target}: ${strategy} sev=${severity}" }   # or payload_raw: "..."
      timeout_s: 5
      verify_tls: true
  - type: http_post
    id: erp-api
    options: { scheme: http, host: 10.0.0.20, port: 8080, path: /alerta }
  - type: syslog
    id: siem
    options: { host: 10.0.0.9, port: 514, protocol: udp, facility: local0 }
```

Rules (validated with a stable `config.alert_*` code):

- `webhook`/`http_post` require `url` or `url_env`; the URL must start with `http://`/`https://`.
- `payload` and `payload_raw` are mutually exclusive; unknown `${...}` placeholders are an error.
- `port` must be 1..65535; `protocol` is `udp`/`tcp`; `facility` must be a known syslog facility;
  `method` is `POST`/`PUT`/`PATCH`.
- An unknown `type` is an error (a "mute" channel no longer goes unnoticed).
- Details and the full placeholder list: [Alerts](Alerts.md).

## Profiles

Named profiles (`profiles.<name>.defaults` + `.alerts` + `.actions`) let you switch sets of
parameters. The switch (GUI selector, tray submenu or `--profile`) applies **on the next start** — the
active loop does not change — and is written to `state.json.profile`.

`defaults` covers `mode`, `poll_interval_s`, `rearm`, `compare_options` and `humanize` (below).

### Humanization (`defaults.humanize`)

Used by the pseudo-human actions:

| Key | Default | Effect |
|---|---|---|
| `mouse_steps` | 24 | intermediate points in the mouse movement (>= 1) |
| `key_interval_ms` | 60 | default typing interval (`type`, when the step does not define `interval_ms`) |
| `jitter_px` | 3 | pixel noise in the movement |
| `wait_jitter_ms` | 150 | noise in the pauses (`wait`/`settle_s`) |
| `seed` | `null` | fixed seed for deterministic tests |

There is no UI for humanization: edit the YAML.

### Text watch (`defaults.compare_options.advanced.text_watch`)

Alerts only when a text **appears** or **disappears** in the ROI — **`advanced` mode only**. It can
live in the profile (parity for CLI-only users) or in the selection `overrides` (the GUI row
**Watch text** writes there; the **override takes precedence**):

```yaml
compare_options:
  advanced:
    text_watch: { text: "CONCLUÍDO", expect: "appears",
                  case_sensitive: false, ignore_accents: true }
```

```json
"overrides": { "text_watch": { "text": "CONCLUÍDO", "expect": "appears",
                               "case_sensitive": false, "ignore_accents": true } }
```

- `expect`: `appears` (default) or `disappears`; `text` is required (non-empty).
- Substring match; `case_sensitive: false` and `ignore_accents: true` by default (NFKD + diacritics
  removal on both sides — robust for pt-BR OCR).
- **Only in `advanced`**: anywhere else it is a validation error
  (`config.text_watch_needs_advanced`); the GUI clears the override when the mode changes.
- With a watch configured the **phash gate is bypassed** (the OCR runs on every tick and the watch
  verdict is authoritative) and the **actions also run only on the transition** — details in the
  [v0.6.0 release notes](../doc/releases/v0.6.0.md).

## Selection JSON v2 and overrides

Each selection can carry `overrides` that **replace** (do not add to) the profile values for that
target: `mode`, `poll_interval_s`, `rearm`, `masks`, `alerts`, `actions` and `text_watch`.

```json
{
  "version": 2,
  "window_handle": 123456,
  "window_title_hint": "ERP - Estoque",
  "app_name": "ERP",
  "name": "verificando download",
  "origin_at_selection": [100, 200],
  "roi_relative": [120, 340, 400, 80],
  "mode": "advanced",
  "masks": [],
  "overrides": { "poll_interval_s": 1.5, "rearm": false,
                 "text_watch": { "text": "CONCLUÍDO", "expect": "appears" } }
}
```

- **Mode precedence**: explicit mode (GUI selector) > `overrides.mode` > `selection.mode`.
- `actions` overrides are validated with the resolved mode (`text_*` filters require `advanced`);
  `text_watch` **requires `advanced`** (`config.text_watch_needs_advanced`).
- `version: 1` selections keep loading (without overrides/`app_name`/`name`).
- `window_handle` is the lookup key; `roi_relative` is the ROI source of truth on every tick.
- `name` (optional) is the **display name** edited in the GUI (prefix in the label and in `run`).
  Renaming writes `name` and moves the file to the **slug** of the name
  (`verificando download` → `verificando-download.json`), never overwriting another selection;
  `--selection <name>` then uses the **new file name**. The region re-edit (double-click) preserves
  `name`/`mode`/`overrides` and **clears the masks** (relative to the old ROI).

## Migration from a v1 YAML (`targets:`)

```powershell
python -m screen_watch migrate-config --dry-run   # prints the plan
python -m screen_watch migrate-config             # writes selections/*.json + config.yaml v2 (.bak)
python -m screen_watch list-selections            # lists the selections (marks the last used one)
```

The migration aborts if a selection with the same name as one of the targets already exists (remove/rename
it first). Duplicate names in v1 also abort.

## `state.json`

| Key | What for |
|---|---|
| `last_selection` | selection used last (default of `--selection`) |
| `profile` | chosen profile (applies on the next start) |
| `language` | language chosen in the GUI selector |
| `action_selection` | per-selection subset of actions (missing key = all; empty list = none) |
| `evidence_enabled` | toggle of the "Record captures" checkbox (takes precedence over the YAML) |

`state.json` is written atomically and without backup; it is disposable state (deleting it does not break).

## Scheduler

```yaml
schedule:
  enabled: true
  days: [mon, tue, wed, thu, fri]
  windows: ["08:00-12:00", "13:30-18:00"]   # windows crossing midnight are accepted
```

Outside the time window, monitoring and alerts continue normally, but **actions** are
suspended (recorded as `suspended_schedule` in the audit). Scheduler enabled without `days`/`windows`
does not restrict anything.

## Evidence

Configured in the `evidence:` section of the YAML **or** through the GUI checkbox (which takes precedence). Details
in [Evidence](Evidence.md).

## Related

- [Pseudo-human actions](Pseudo-Human-Actions.md) — the `actions:` format
- [Alerts](Alerts.md) — the `alerts:` format
- [Usage (CLI)](CLI-Usage.md) — `validate-config`, `migrate-config`, `--profile`
- [doc/00 §12](../doc/00-Architecture_and_Specification.md) — schema and design decisions
