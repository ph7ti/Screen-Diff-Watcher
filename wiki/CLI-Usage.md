# Usage (CLI)

**English** · [Português (Brasil)](Uso-CLI.md)

If you installed from the binaries, the command is **`screen-watch`**; from the source code, use
**`python -m screen_watch`**. Both have the same command surface.

```powershell
python -m screen_watch --help
python -m screen_watch <command> --help
```

**Global flags**:

| Flag | Effect |
|---|---|
| `--language TAG` | GUI language (`auto`, `pt-BR`, `en-US` or a discovered tag); does not affect the CLI, which is fixed English |
| `--verbose` | DEBUG-level diagnostic logging |

## Command reference

### Configuration

| Command | What it does |
|---|---|
| `init-config [--path PATH] [--force]` | creates the default `config.yaml` v2 in app-data (or at the given path); without `--force`, it does not overwrite |
| `validate-config [--config PATH] [--selections]` | validates the YAML (and, with `--selections`, the overrides of each selection) |
| `show-paths` | shows app-data, config, selections, state, logs and the effective prints folder (`captures:`) |

```powershell
python -m screen_watch init-config
python -m screen_watch validate-config --selections
python -m screen_watch show-paths
```

### ROI selection

| Command | What it does |
|---|---|
| `list-windows` | lists the windows: `handle`, state (`ok`/`minimized`), position/size and title |
| `select --handle H [--name NAME] [--mode light|default|advanced]` | opens the **overlay**: drag with the left button; right button cancels. Writes the JSON to app-data |
| `select-manual --handle H --roi X Y W H [--name NAME] [--title T] [--mode ...]` | writes the selection by coordinates, without the overlay |
| `list-selections` | lists the selections (app name, region, mode; marks the last used one) |
| `migrate-config [--path PATH] [--dry-run]` | converts a v1 YAML (`targets:`) into `selections/*.json` + v2 YAML |

```powershell
python -m screen_watch list-windows
python -m screen_watch select --handle 12345 --name painel
python -m screen_watch select-manual --handle 12345 --roi 120 340 400 80 --name painel
python -m screen_watch list-selections
```

- The default mode of selections is `advanced`; you can change it later in the GUI selector or through the
  JSON `overrides`.
- The minimum accepted area is 10×10 logical pixels.

### Execution

| Command | What it does |
|---|---|
| `run [--config C] [--profile P] [--selection S] [--actions a,b|all|none]` | starts monitoring the selection |
| `gui [--config C] [--profile P]` | opens the GUI with tray (see [GUI and tray](GUI-and-Tray.md)) |

The `--target` alias still works as **deprecated** in `run`/`test-*`/`list-actions`/`record-actions`
(use `--selection`).

**How `run` resolves the selection**: `--selection NAME` looks for `selections/NAME.json` in app-data;
it also accepts a **path** to a `.json`. Without `--selection`, it uses `state.json.last_selection`; if
there is none, it lists the available ones and exits with an error.

**How `run` builds the target**: selection JSON + YAML profile; the selection `overrides`
**replace** the profile values (they do not add up). Without a YAML (or with a v1 YAML without a matching
target), it uses the default alerts: **sound + popup + log** (Telegram requires `chat_id`, so it does not
enter the default).

```powershell
python -m screen_watch run --selection painel
python -m screen_watch run --selection "%APPDATA%\screen_watch\selections\painel.json"
python -m screen_watch run --profile trabalho --selection painel
python -m screen_watch run --selection painel --actions reprocessar,confirmar   # subset for this session only
python -m screen_watch run --selection painel --actions none                    # only monitors
```

During execution, each trigger prints a line `[action] rehearsal|armed <name> -> ok|failed
(reason)`. Ctrl+C ends with `shutting down...`. On Wayland, `run` warns and exits (code 2).

### Tests and diagnostics

| Command | What it does |
|---|---|
| `test-alert --selection S` | fires a **synthetic** alert (severity 3) with the current ROI, to check sound/popup/Telegram/log |
| `test-evidence --selection S` | writes an example baseline+change pair and prints the paths |
| `test-action --selection S [--armed] [--dry-run] [--actions ...] [--no-countdown]` | rehearses (default) or runs the actions; `--armed` shows the 3 s countdown |
| `list-actions --selection S` | lists the resolved actions and the saved subset, without starting a session |
| `record-actions --selection S [--name NAME] [--out FILE] [--no-countdown]` | records clicks/keys and generates an `actions:` snippet (`input` extra; `F10` ends it) |
| `compare-modes --selection S [--delay 5] [--repeat 1] [--modes light,default,advanced]` | measures `changed`/`score`/`threshold`/`severity`/time of each mode (calibration) |
| `probe-dpi` | prints the monitor matrix (physical mss × logical Qt × scale) and the rect of a window |
| `features [--json]` | environment diagnostics (version/origin, Tesseract, input, sound, tray, monitors) |
| `validate-i18n` | validates the language catalogs (keys, `error.*`, `help.*`, `_meta`) |

```powershell
python -m screen_watch test-alert --selection painel
python -m screen_watch test-action --selection painel            # rehearsal
python -m screen_watch test-action --selection painel --armed    # actually executes
python -m screen_watch compare-modes --selection painel --delay 5
python -m screen_watch features --json
```

## Masks of volatile regions

Masks are `[x, y, w, h]` rectangles **relative to the ROI**, painted black before comparison —
useful for spinners/clocks that change on their own. The overlay does not draw masks yet; edit the
`masks` field in the YAML (profile) or in the selection JSON (which overrides the profile).

## Calibration (Step D)

`compare-modes` captures the ROI, waits `--delay` seconds (change the panel during that interval) and measures
`changed`/`score`/`threshold`/`severity` and the `compare` time of each mode; for `advanced`,
it also prints the texts recognized by OCR. Use this to adjust `similarity_threshold`,
`upscale`, `psm` and the `severity_min` of the alerts/actions. Record each adjustment with the context in
which it was made (doc/00 §18, item 8).

## Re-arm (edge-triggered)

With `rearm: true` (default), a sustained change alarms **once**; a new change re-arms. If
an alert fails (e.g.: Telegram down), it is retried respecting `cooldown_s` (backoff),
without hammering on every tick. Manual re-arm is in the tray, in the window's **Re-arm** button and in the
`rearm` hotkey.

## Robustness (loop events)

- `target_unavailable` — window closed, minimized or ROI out of bounds; the loop keeps retrying.
- `capture_clipped` — the ROI was clipped against the virtual desktop (monitor off/off-screen).
- `roi_off_screen` — the ROI is 100% off-screen: the tick is skipped, without breaking the loop.
- Consecutive identical failures are reported once (not on every tick).

## Related

- [Configuration](Configuration.md) — `config.yaml`, overrides, migration
- [Pseudo-human actions](Pseudo-Human-Actions.md) — `actions:` format and arming flow
- [Alerts](Alerts.md) — channels, severity and cooldown
