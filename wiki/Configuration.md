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
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.wav" }
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
schedule: { enabled: false, days: [mon, tue, wed, thu, fri], windows: ["08:00-12:00"], timezone: local }
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

## Selection JSON v2 and overrides

Each selection can carry `overrides` that **replace** (do not add to) the profile values for that
target: `mode`, `poll_interval_s`, `rearm`, `masks`, `alerts` and `actions`.

```json
{
  "version": 2,
  "window_handle": 123456,
  "window_title_hint": "ERP - Estoque",
  "app_name": "ERP",
  "origin_at_selection": [100, 200],
  "roi_relative": [120, 340, 400, 80],
  "mode": "advanced",
  "masks": [],
  "overrides": { "poll_interval_s": 1.5, "rearm": false }
}
```

- **Mode precedence**: explicit mode (GUI selector) > `overrides.mode` > `selection.mode`.
- `actions` overrides are validated with the resolved mode (`text_*` filters require `advanced`).
- `version: 1` selections keep loading (without overrides/`app_name`).
- `window_handle` is the lookup key; `roi_relative` is the ROI source of truth on every tick.

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
  timezone: local
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
