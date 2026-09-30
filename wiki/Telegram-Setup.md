# Telegram alerts — step by step

**English** · [Português (Brasil)](Configuracao-Telegram.md)

This tutorial configures the `telegram` alert channel: create the bot, discover the `chat_id`, set
the token as an environment variable (never in the YAML) and test the delivery.

> The Telegram channel is optional and independent from the other channels: if it fails, sound,
> popup and log keep working, and the monitoring loop never breaks.

## What you need

- A Telegram account (mobile or desktop app).
- `screen-watch` installed (or `python -m screen_watch` from the source).
- A configured selection and `config.yaml` (see [Configuration](Configuration.md)); `init-config`
  creates a default one.

## 1. Create the bot and get the token

1. In Telegram, search for **@BotFather** and open the chat.
2. Send `/newbot`.
3. Choose a **display name** (anything) and a **username** ending in `bot` (e.g.
   `my_panel_watcher_bot`).
4. BotFather replies with the **HTTP API token**, like `123456789:AAE...`. **This token is a
   secret** — never commit it or put it in the YAML.
   - If the token leaks, send `/revoke` to BotFather to generate a new one.

## 2. Start a chat with your bot

Bots cannot message you first:

1. Open your new bot's chat (link `https://t.me/<bot_username>`).
2. Press **Start** (or send `/start`).

For a **group**: add the bot to the group and send a message (if `getUpdates` does not show it,
send `/start@<bot_username>` or mention the bot).

## 3. Discover the `chat_id`

**Option A — via `getUpdates` (works for private chats and groups):**

1. Send a message to the bot (private) or in the group.
2. In a browser, open:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. In the JSON, find the message you sent and read `"chat": {"id": ...}`:
   - private chat: positive number (e.g. `123456789`);
   - group: negative number (e.g. `-1001234567890`).

**Option B — helper bots:** message **@userinfobot** (or add it to the group) and copy the id it
shows.

> The `chat_id` in the YAML must be the id **of the conversation where the bot may post** (your
> chat with the bot, or a group the bot belongs to).

## 4. Set the token as an environment variable

Never put the token in `config.yaml`. The default variable name is `TELEGRAM_BOT_TOKEN`
(configurable with `bot_token_env`).

**Windows (permanent, user-level):**

```powershell
setx TELEGRAM_BOT_TOKEN "123456789:AAE..."
# new terminals and applications see it from now on; restart the app/GUI
```

**Windows (current terminal only, for a quick test):**

```powershell
$env:TELEGRAM_BOT_TOKEN = "123456789:AAE..."
```

**Linux/macOS (permanent):**

```bash
echo 'export TELEGRAM_BOT_TOKEN="123456789:AAE..."' >> ~/.profile
# log out and back in (or `source ~/.profile` for the current shell)
```

> If the app launched from the menu does not see the variable, create
> `~/.config/environment.d/telegram.conf` with `TELEGRAM_BOT_TOKEN=123456789:AAE...` and log out
> and back in.

Check that the variable is visible:

```powershell
echo $env:TELEGRAM_BOT_TOKEN     # Windows PowerShell
```

```bash
printenv TELEGRAM_BOT_TOKEN      # Linux/macOS
```

> The value is read when an alert fires; if you change it, restart the app (processes inherit the
> environment at start).

## 5. Configure the alert in `config.yaml`

Open the config (`python -m screen_watch show-paths` shows where it is) and add the `telegram`
entry to the profile's `alerts:` list:

```yaml
version: 2
profile: default
profiles:
  default:
    alerts:
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30 }
      - { type: "telegram", enabled: true, severity_min: 2, cooldown_s: 60,
          bot_token_env: "TELEGRAM_BOT_TOKEN", chat_id: "123456789", attach_roi: true }
```

The `config.yaml` created by `init-config` already contains a Telegram example with
`chat_id: "123456789"` — replace it with your id (or keep `enabled: false` until you configure it).

| Field | Default | Meaning |
|---|---|---|
| `enabled` | `true` | turns the channel on/off |
| `severity_min` | `1` | minimum severity (0–3) to send; `2` avoids noisy warnings |
| `cooldown_s` | `30` | minimum interval between sends of this channel |
| `bot_token_env` | `TELEGRAM_BOT_TOKEN` | name of the environment variable holding the token |
| `chat_id` | — (required) | destination chat/group id |
| `attach_roi` | `true` | attaches the ROI screenshot to the message (best for validating false positives) |

## 6. Test

```powershell
screen-watch test-alert --selection painel     # from source: python -m screen_watch test-alert --selection painel
```

This fires a **synthetic alert with severity 3** using the current ROI, bypassing the comparison.
Expected output:

```text
target='painel' handle=12345 roi=(120, 340, 400, 80)
outcome: fired
jsonl: C:\Users\...\AppData\Roaming\screen_watch\logs\alerts.jsonl
```

You should receive a message with the ROI image (when `attach_roi: true`); the caption shows the
strategy, score and severity that triggered the alert. Exit code `0` means the chain fired; `1`
means nothing fired (check the messages below).

## Troubleshooting

- **`variable TELEGRAM_BOT_TOKEN missing, Telegram disabled` (warning)** — the process did not see
  the environment variable. Set it and open a **new** terminal / restart the app.
- **`notifier telegram failed: ...` (error)** — the HTTP call failed. Most common causes:
  - `401 Unauthorized`: wrong token (or revoked).
  - `400 Bad Request` / `chat not found`: wrong `chat_id`; for groups use the negative id.
  - `403 Forbidden`: the bot was blocked, or you never sent `/start` to it.
- **`outcome: fired` but no message** — another channel (sound/popup) may have fired while Telegram
  failed; `fired` does not mean *every* channel succeeded. Look for the lines above in the console.
- **The message stopped after the first one** — `cooldown_s` suppresses repeats; the pending change
  alerts again when the cooldown expires.
- **No warning and no message** — confirm `enabled: true`, `severity_min` <= 3 (the synthetic alert
  is severity 3) and that the bot can post in that conversation.

## Related

- [Alerts](Alerts.md) — channels, severity, cooldown and re-arm
- [Configuration](Configuration.md) — where `alerts:` lives in the YAML
- [doc/00 §11.2](../doc/00-Architecture_and_Specification.md) — design of the Telegram notifier
