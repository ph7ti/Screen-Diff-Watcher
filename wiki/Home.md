# Screen Diff Watcher — Wiki

**English** · [Português (Brasil)](Home-pt-BR.md)

Watches a **rectangular region (ROI) of a window** and notifies you when it changes — sound, popup,
Telegram, webhook/HTTP POST, syslog, log, ntfy, e-mail (SMTP) or MQTT — on **Windows, Linux and
macOS (arm64, unsigned build)**, without touching the watched application.

This wiki gathers the **usage and feature details**. The overview (what it does and does not do,
platforms, prerequisites, quick start and build) is in the [README](../README.md).

## Pages

| Page | What it covers |
|---|---|
| [Installation](Installation.md) | binaries (Inno Setup / `.deb`), source code, automatic Tesseract, autostart, app-data, `features` diagnostics |
| [Usage (CLI)](CLI-Usage.md) | command reference, ROI selection, masks, calibration, profiles, robustness, selection lifecycle (create→edit→validate→run) |
| [GUI and tray](GUI-and-Tray.md) | the window, the buttons, arming, hover help, prints, tray, snooze/mute/escalation, multiple ROIs |
| [Configuration](Configuration.md) | `config.yaml` v2 (profiles, overrides), `state.json`, v1→v2 migration |
| [Pseudo-human actions](Pseudo-Human-Actions.md) | steps, triggers, arming/rehearsal, limits, GUI editor, recorder, audit |
| [Alerts](Alerts.md) | sound/popup/Telegram/log + webhook/HTTP POST/syslog/ntfy/SMTP/MQTT, snooze/mute + escalation, severity, cooldown, re-arm, `test-alert --list/--only` |
| [Telegram setup](Telegram-Setup.md) | step by step: create the bot, get the chat id, set the token, edit the YAML and test |
| [Evidence](Evidence.md) | baseline/change prints, retention, folders, toggle |
| [Languages (i18n)](Languages.md) | catalogs, precedence, how to add a language |
| [DPI and limitations](DPI-and-Limitations.md) | screen scaling, Wayland, occluded window, robustness |
| [Development, tests and CI](Development-Tests-and-CI.md) | unit/integration tests, CI, release |

## Minimal step-by-step

With the binaries installed, use `screen-watch`; from the source code, `python -m screen_watch`.

```powershell
screen-watch list-windows                                    # see the target window handle
screen-watch select --handle 12345 --name painel             # draw the ROI on the overlay
screen-watch test-alert --selection painel                   # check the alert
screen-watch run --selection painel                          # monitor
screen-watch gui                                             # ...or use the GUI with tray
```

The GUI is the shortest path: **New Target (overlay)** → draw the ROI → **Start**.

The full selection lifecycle is also available headless: `list-windows` → `select-manual` →
`edit-selection NAME` → `validate-config --selections` → `run --selection NAME`.

## Points to note

- An **occluded window** cannot be captured: capture reads pixels from the screen (an API limitation, not a bug).
- **Wayland** is not supported on Linux; run on X11.
- **Actions** are opt-in, disarmed by default and require the `input` extra (`pynput`).
- **Snooze/Mute** silence the alerts for every session and persist in `state.json`; with escalation
  enabled, an alert repeats until **Acknowledge**.
- The GUI can monitor **multiple ROIs** at once (checkboxes in the selection list, up to
  `ui.max_sessions`, default 4); the CLI `run` stays single-selection.
- The **CLI and the log** are in fixed English; only the GUI goes through the language catalog (pt-BR/en-US).

## Repository documents

- [README](../README.md) — overview, platforms, requirements, build.
- [doc/00 — Architecture and specification](../doc/00-Architecture_and_Specification.md) —
  the single source of truth for the design.
- [doc/01 — Build and release](../doc/01-Build_and_Release.md) — installers pipeline.
- [CHANGELOG](../CHANGELOG.md) — changes per version.

> **Publishing to the GitHub Wiki**: the pages in this folder (`wiki/`) follow the GitHub Wiki format.
> To publish, clone `https://github.com/ph7ti/Screen-Diff-Watcher.wiki.git` and copy the contents of
> `wiki/` there (the `../doc/...` and `../README.md` links must be adjusted to repository URLs,
> or keep the pages only in the repository).
