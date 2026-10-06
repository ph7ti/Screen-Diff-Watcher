# Alerts

**English** · [Português (Brasil)](Alertas.md)

An alert fires when the comparison confirms a **change** (`changed: true`) and the
**severity** of the change reaches the channel's `severity_min`, respecting each one's `cooldown_s`.

## Channels

| Type (`type`) | What it does | Specific fields |
|---|---|---|
| `sound` | plays a local sound | `file` (WAV/MP3/M4A/AAC/OGG/FLAC…; default `alert.mp3`, bundled) |
| `popup` | local notification (`plyer`) | — |
| `telegram` | sends a message (and the ROI image) via bot | `bot_token_env`, `chat_id`, `attach_roi` |
| `log` | writes a JSON line to `logs/alerts.jsonl` | `path` (optional; empty = default) |
| `webhook` | POST/PUT/PATCH JSON to a webhook URL (Teams **Workflows**, Slack, Discord, Mattermost) | `options:` (`url`/`url_env`, `method`, `headers`, `payload`/`payload_raw`, `timeout_s`, `verify_tls`) |
| `http_post` | POST JSON to a host/IP + port (or a full URL) | `options:` (`url`/`url_env`, `scheme`, `host`, `port`, `path`, `method`, `headers`, `payload`/`payload_raw`, `verify_tls`) |
| `syslog` | informational syslog message (host/port, `udp`/`tcp`) — no image | `options:` (`host`, `port`, `protocol`, `facility`, `app_name`, `payload_raw`, `severity_map`, `timeout_s`) |
| `ntfy` | phone push (HTTP) | `options:` (`server`, `topic`, `token_env`, `title`/`message`, `priority_map`, `tags`, `attach_roi`, `timeout_s`) |
| `smtp` | sends an e-mail (stdlib `smtplib`) | `options:` (`host`, `port`, `security`, `from_addr`, `to`, `subject`/`message`, `username_env`/`password_env`, `attach_roi`, `timeout_s`) |
| `mqtt` | publishes a JSON payload to an MQTT broker (optional extra `mqtt`) — no image | `options:` (`host`, `topic`, `port`, `qos`, `retain`, `client_id`, `username_env`/`password_env`, `tls`, `payload`/`payload_raw`, `timeout_s`) |

The four first types keep **flat fields**; the new ones use a nested **`options:`** block. All accept
`enabled`, `severity_min`, `cooldown_s` and the optional **`id`** (default `type`; `type#n` when repeated
in the same profile). The `id` is the **cooldown key**, so two webhooks no longer share the cooldown.
Profile example:

```yaml
profiles:
  default:
    alerts:
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.mp3" }
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

- All playback goes through the `platform/audio.py` boundary; `alerts/` does not know `sys.platform`,
  Qt or miniaudio.
- **GUI**: `QMediaPlayer` (QtMultimedia) created on the GUI thread — WAV/MP3/M4A/AAC/FLAC/WMA via
  Media Foundation (Windows), GStreamer (Linux, depends on the installed plugins) or AVFoundation
  (macOS). Playing again interrupts the previous sound.
- **CLI/`run`** (no Qt application): **miniaudio** (core dependency) plays WAV/MP3/OGG/FLAC on a
  **daemon thread** (it never blocks the loop). **No AAC/M4A** — it falls back to an external player
  when present, otherwise `beep`.
- **Legacy fallback**: `winsound` (stdlib; WAV only) on Windows; on Linux/macOS an external player in
  order of preference — `paplay`, `aplay -q`, `ffplay -nodisp -autoexit -loglevel quiet`; on macOS,
  `afplay`.
- `file` may be **absolute** or **relative**: relative is looked up in **`app-data/sounds/`** first,
  then in the **bundled sounds** (`screen_watch/assets/sounds`, where the default `alert.mp3` lives)
  and finally in the CWD. A missing file — or a format with no decoder — falls back to `beep()` with a
  log warning (never silence nor an exception).
- The `simpleaudio` extra (`pip install -e ".[sound]"`) remains optional and does **not** enter the
  installers (no reliable wheel for Python 3.13); it is only tried for `.wav`.
- **GUI selector (v0.8.0)**: the **Alert sound** row previews any file with **Play** and, after
  **Choose…**, asks for confirmation and **writes** `file:` into the `type: "sound"` alert of the
  active profile in `config.yaml` (atomic write, `config.yaml.bak` backup; comments are not
  preserved). The dialog keeps **Copy path and open YAML** / **Open YAML only** / **Close** as
  secondary actions. A v1 config is refused with a message to run `migrate-config`; when the selected
  selection has `overrides.alerts` (which replace the profile alerts) the dialog warns that the sound
  will not apply to it.
- Full format matrix per context: [v0.6.0 release notes](../doc/releases/v0.6.0.md).

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
- The record has no channel/target/evidence path (`ts`, `strategy`, `changed`, `score`, `threshold`,
  `severity`, `window_handle`, `absolute_rect`, `sequence`, `detail`).
- **Alert history (v0.8.0)**: the GUI **History…** button opens a table over this file with filters
  (date from/to, minimum severity, strategy), tolerant to invalid lines. **Open print** finds the
  nearest `*_change.png` within ±2 s of the alert (best effort; otherwise it reports that no print was
  found) and **Open prints folder** opens the effective captures folder.

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

### ntfy

- Plain-text `POST` to `{server}/{topic}` with the `Title`, `Priority` and `Tags` headers;
  `attach_roi: true` switches to a PNG `PUT` (`Filename: roi.png`, the rendered text goes in the
  `Message` header).
- `server` defaults to `https://ntfy.sh`; `topic` is **required**.
- `token_env` is **optional** and empty by default (anonymous topic); when set to a variable that is
  missing, the notifier logs and skips. The token **never** appears in the YAML.
- `priority_map` maps severity 1..3 to the ntfy priority 1..5 (default 3/4/5); `title`/`message`
  accept the same `${...}` templates as the other channels.
- Errors (`alert.ntfy_unavailable`, `alert.ntfy_status`) carry only the redacted server
  (`scheme://host/…`).

```yaml
- type: ntfy
  id: celular
  severity_min: 1
  cooldown_s: 60
  options:
    server: "https://ntfy.sh"          # default
    topic: "meu-topico"                # required
    token_env: NTFY_TOKEN              # optional; empty = anonymous
    priority_map: { 1: 3, 2: 4, 3: 5 } # default
    tags: ["warning"]                  # optional
    attach_roi: false                  # true = PUT the ROI PNG
    timeout_s: 5
```

### SMTP

- Stdlib `smtplib` + `EmailMessage`; `security` is `starttls` (default), `ssl` or `none`.
- `host` and `from_addr` are **required**; `to` is a **non-empty list**; `port` defaults to `587`.
- `subject`/`message` are templates with the same `${...}` rules.
- `username_env`/`password_env` (defaults `SMTP_USERNAME`/`SMTP_PASSWORD`) log in **only when the
  user variable is set**; secrets never appear in errors/logs.
- `attach_roi: true` (default) attaches the ROI PNG (`image/png`).
- Errors: `alert.smtp_unavailable` (connect/TLS), `alert.smtp_auth_failed` (login),
  `alert.smtp_send_failed` (message rejected).

```yaml
- type: smtp
  id: email
  severity_min: 2
  cooldown_s: 300
  options:
    host: "smtp.example.com"        # required
    port: 587                       # default
    security: starttls              # starttls | ssl | none
    from_addr: "watch@example.com"  # required
    to: ["oncall@example.com"]      # non-empty list
    subject: "[screen-diff-watcher] ${target} sev=${severity}"
    username_env: SMTP_USERNAME     # login only if the variable is set
    password_env: SMTP_PASSWORD
    attach_roi: true                # attach the ROI PNG
    timeout_s: 10
```

### MQTT

- Optional extra: `python -m pip install -e ".[mqtt]"` (`paho-mqtt`, lazy import; the installers do
  not bundle it). A configured channel without the extra raises the visible
  `alert.mqtt_missing_extra` — never a silent skip. `features --json` reports whether the extra is
  installed.
- `host`/`topic` are **required**; `port` defaults to `1883` (`8883` with `tls: true`); `qos` is
  `0`/`1`/`2`; `retain`, `client_id` (`screen-diff-watcher` by default) and
  `username_env`/`password_env` (defaults `MQTT_USERNAME`/`MQTT_PASSWORD`) follow the broker setup.
- The payload is a template mapping (default `text`/`target`/`severity`/`strategy`/`score`/
  `threshold`/`timestamp`) or `payload_raw`; using both is a config error.
- **No image/ROI**.
- Errors: `alert.mqtt_unavailable` (connect), `alert.mqtt_publish_failed` (publish rejected).

```yaml
- type: mqtt
  id: barramento
  severity_min: 1
  cooldown_s: 60
  options:
    host: "10.0.0.30"              # required
    topic: "screen-watch/default"  # required
    port: 1883                     # default; 8883 with tls
    qos: 1                         # 0 | 1 | 2
    retain: false
    client_id: "screen-diff-watcher"
    tls: false
    username_env: MQTT_USERNAME
    password_env: MQTT_PASSWORD
    # payload: { text: "${message}", severity: "${severity}" }   # or payload_raw: "..."
    timeout_s: 5
```

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
- Manual re-arm: tray, the window's **Re-arm baseline** button or the `rearm` hotkey (`<ctrl>+<alt>+r`).

## Snooze, mute and escalation

- **Snooze…** silences the alerts for the chosen duration; the menu offers `ui.snooze_minutes`
  (default `[5, 15, 30, 60]`). **Mute/Unmute** silences until unmuted, and **Acknowledge** stops an
  escalation — all in the Detection and alerts group and in the tray; `acknowledge` also has the
  optional `ui.hotkeys.acknowledge`.
- The gate is shared by every session and persisted in `state.json` (`alerts_snooze_until`,
  `alerts_muted`), so a later `run` inherits it until the snooze expires (an expired timestamp is
  ignored on start). An explicit `test-alert` ignores the gate.
- While suppressed, `dispatch` returns `SUPPRESSED_MANUAL` before trying any channel and the
  baseline is kept: the pending change alarms when the snooze expires or the mute is lifted. Risk:
  if the ROI returns to the baseline before the snooze ends, the pending change is dropped.
- **Escalation** (`defaults.escalation`, or `overrides.escalation` per selection): `enabled` (default
  `false`) and `severity_min` (default `2`). With it enabled and a `FIRED` outcome at
  `severity >= severity_min`, the baseline does not advance and the alert **repeats at each
  channel's own `cooldown_s` until Acknowledge**, which re-arms the baseline (manual re-arm does the
  same). The status shows "awaiting acknowledgement".
- **Change evidence follows the delivery attempts**: prints are written only on `FIRED`/`FAILED`
  (plus each escalation firing), instead of once per tick while the change is pending.

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
