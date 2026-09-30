# Alerts

**English** · [Português (Brasil)](Alertas.md)

An alert fires when the comparison confirms a **change** (`changed: true`) and the
**severity** of the change reaches the channel's `severity_min`, respecting each one's `cooldown_s`.

## Channels

| Type (`type`) | What it does | Specific fields |
|---|---|---|
| `sound` | plays a local sound | `file` (WAV; default `alert.wav`) |
| `popup` | local notification (`plyer`) | — |
| `telegram` | sends a message (and the ROI image) via bot | `bot_token_env`, `chat_id`, `attach_roi` |
| `log` | writes a JSON line to `logs/alerts.jsonl` | `path` (optional; empty = default) |

All accept `enabled`, `severity_min` and `cooldown_s`. Profile example:

```yaml
profiles:
  default:
    alerts:
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.wav" }
      - { type: "popup",    enabled: true, severity_min: 1, cooldown_s: 30 }
      - { type: "telegram", enabled: true, severity_min: 2, cooldown_s: 60,
          bot_token_env: "TELEGRAM_BOT_TOKEN", chat_id: "123456789", attach_roi: true }
      - { type: "log",      enabled: true, severity_min: 1, cooldown_s: 0 }   # optional
```

**Without a YAML** (or a v1 YAML without a matching target), the app uses the default alerts: **sound + popup +
log** (Telegram requires `chat_id`, so it does not enter the default).

## How each channel works

### Sound

- All playback goes through the `platform/audio.py` boundary; `alerts/` does not know `sys.platform`.
- Windows: `winsound` (stdlib); without `alert.wav`, it uses `MessageBeep()`.
- Linux/macOS: external player in order of preference — `paplay`, `aplay -q`,
  `ffplay -nodisp -autoexit -loglevel quiet`; on macOS, `afplay`.
- The `simpleaudio` extra (`pip install -e ".[sound]"`) is optional and does **not** enter the installers
  (no reliable wheel for Python 3.13). Without any player, the sound is **silent** — the alert
  never breaks.

### Popup

- `plyer.notification` (depends on each OS's native backend).

### Telegram

- Token **never** in the YAML: read from the environment variable indicated in `bot_token_env`
  (`TELEGRAM_BOT_TOKEN` by default).
- `attach_roi: true` (default) sends the **ROI screenshot** along with it (`sendPhoto`), which is essential
  to validate false positives; with `false`, it sends text only (`sendMessage`).
- Short timeout (**5 s**) so as not to block the loop.

### Log

- One JSON line per firing in `app-data/logs/alerts.jsonl` (or in the configured `path`).

## Severity

The severity (0..3) comes from the comparison pipeline: when the strategy does not define one, the pipeline
computes `compute_severity(score, threshold)` — ratio `score/threshold`: `>= 3.0` → 3; `>= 2.0` → 2;
`>= 1.0` → 1; otherwise 0. Use the `severity_min` values to separate "warning" from "critical" (e.g.: Telegram only at
severity 2+).

## Cooldown, failures and re-arm

- The `cooldown_s` is **per notifier**: even with the ROI changing on every tick, each channel fires at
  most once per cooldown window.
- A failure in one notifier does **not** prevent the others (each has its own `try`). The attempt is
  recorded to provide **backoff** — a Telegram that is down is not hammered on every tick.
- With `rearm: true` (default), the baseline advances after an effective (or ineffective) alert — a sustained
  change alarms once. In cooldown or failure, the baseline is kept: the pending change alarms
  when the cooldown expires.
- Manual re-arm: tray, the window's **Re-arm** button or the `rearm` hotkey (`<ctrl>+<alt>+r`).

## Test

```powershell
python -m screen_watch test-alert --selection painel
```

Fires a **synthetic** alert (severity 3) with the current ROI, to check each channel without waiting
for a real change. If the selection has no alerts configured, the command fails with a clear message.
To avoid duplicating records, the extra line in `alerts.jsonl` is only written when the configuration does not
have a `log` notifier.

## Related

- [Configuration](Configuration.md) — where the alerts live in the YAML and in the selection overrides
- [Evidence](Evidence.md) — prints recorded along with the alerts (optional)
- [doc/00 §11](../doc/00-Architecture_and_Specification.md) — design decisions
