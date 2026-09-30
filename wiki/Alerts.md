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
| `webhook` | POST/PUT/PATCH JSON to a webhook URL (Teams **Workflows**, Slack, Discord, Mattermost) | `options:` (`url`/`url_env`, `method`, `headers`, `payload`/`payload_raw`, `timeout_s`, `verify_tls`) |
| `http_post` | POST JSON to a host/IP + port (or a full URL) | `options:` (`url`/`url_env`, `scheme`, `host`, `port`, `path`, `method`, `headers`, `payload`/`payload_raw`, `verify_tls`) |
| `syslog` | informational syslog message (host/port, `udp`/`tcp`) — no image | `options:` (`host`, `port`, `protocol`, `facility`, `app_name`, `payload_raw`, `severity_map`, `timeout_s`) |

The four first types keep **flat fields**; the new ones use a nested **`options:`** block. All accept
`enabled`, `severity_min`, `cooldown_s` and the optional **`id`** (default `type`; `type#n` when repeated
in the same profile). The `id` is the **cooldown key**, so two webhooks no longer share the cooldown.
Profile example:

```yaml
profiles:
  default:
    alerts:
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.wav" }
      - { type: "popup",    enabled: true, severity_min: 1, cooldown_s: 30 }
      - { type: "telegram", enabled: true, severity_min: 2, cooldown_s: 60,
          bot_token_env: "TELEGRAM_BOT_TOKEN", chat_id: "123456789", attach_roi: true }
      - { type: "log",      enabled: true, severity_min: 1, cooldown_s: 0 }   # optional
      - type: webhook                   # Teams Workflows / Slack / Discord / Mattermost…
        id: teams
        severity_min: 2
        cooldown_s: 60
        options:
          url_env: TEAMS_WEBHOOK        # secret stays out of the YAML
          payload: { text: "Change on ${target}: ${strategy} sev=${severity}" }
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
- **Full step-by-step**: [Telegram setup](Telegram-Setup.md) — create the bot, get the chat id,
  set the token, edit the YAML and test.

### Log

- One JSON line per firing in `app-data/logs/alerts.jsonl` (or in the configured `path`).

### Webhook / HTTP POST

- **No image/ROI**: the attached print stays exclusive to Telegram.
- URL: literal (`url`) **or** from the environment (`url_env: VAR`). `headers`/`payload` strings accept
  `${env:VAR}`; the resolved URL and the variable values **never** appear in errors/logs.
- `method` is `POST` (default), `PUT` or `PATCH`; redirects are **not** followed; the default
  `Content-Type` is `application/json` (overridable in `headers`).
- Success = HTTP **2xx**; a non-2xx raises `alert.http_status` (redacted URL) and a network failure
  raises `alert.http_unreachable`.
- **Payload template**: `payload:` (mapping) substitutes `${campo}` **only in string values**;
  `payload_raw:` (string) sends a non-object body. Using both is a config error. Placeholders:
  `message`, `strategy`, `score`, `threshold`, `severity`, `target`, `timestamp`, `window_handle`,
  `changed`, `roi`, and `env:VAR`. `$$` escapes `$`; `{`/`}` are literal, so the body can be JSON.
- `http_post` uses `scheme` (default `http`), `host`, `port`, `path`, or a full `url`.
- `verify_tls: true` (default); with `false` (self-signed/internal endpoints) a warning is logged **on
  every send**.
- **Teams**: the legacy *Incoming Webhooks* are being retired (deadline **2026-03-31**, shutdown
  **2026-05**) — use the **Workflows** webhook URL.

### Syslog

- **Informational by default**: the real severity goes in the text via `${severity}`; use
  `severity_map` (`{0: "debug", 3: "error"}`) to set the syslog level per severity (0..3).
- `protocol` is `udp` (default) or `tcp`; `port` default `514`; `facility` default `local0`;
  `app_name` becomes the syslog **tag** (`ident`).
- **UDP does not confirm delivery** (fire-and-forget) — prefer `tcp` when delivery must be confirmed.


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
python -m screen_watch test-alert --selection painel            # all channels (respects enabled)
python -m screen_watch test-alert --selection painel --list     # list id/type/state/destination
python -m screen_watch test-alert --selection painel --only siem # a single destination (text mode)
```

`test-alert` fires a **synthetic** alert (severity 3) with the current ROI, to check each channel without
waiting for a real change. Without flags it keeps the previous behavior (respects `enabled`); `--list`
prints the alerts and `--only ID` sends to a single destination, **ignoring `enabled`** and warning when
the alert is off (`--only` sends in text mode, without capturing the ROI). In the GUI, the **Test
alert…** button opens the same list and sends on a worker thread. To avoid duplicating records, the extra
line in `alerts.jsonl` is only written when the configuration does not have a `log` notifier.

## Related

- [Configuration](Configuration.md) — where the alerts live in the YAML and in the selection overrides
- [Evidence](Evidence.md) — prints recorded along with the alerts (optional)
- [doc/00 §11](../doc/00-Architecture_and_Specification.md) — design decisions
