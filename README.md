# Screen Diff Watcher

**English** · [Português (Brasil)](README.pt-BR.md)

Watches a **rectangular region (ROI) of a window** and alerts you when it changes — sound, popup,
Telegram or log — so you don't have to keep an eye on the screen.

Runs on **Windows and Linux**, capturing pixels only (it never touches the watched application).

[Wiki — usage guide](wiki/Home.md) ·
[Architecture and specification](doc/00-Architecture_and_Specification.md) ·
[Build and release](doc/01-Build_and_Release.md) ·
[Changelog](CHANGELOG.md)

## What it does

- **Watches a ROI of a window**: you draw the rectangle and the app captures only that area every N
  seconds. The ROI is anchored to the window — if the window moves, the ROI follows (Model B,
  doc §3.3).
- **Detects visual changes** in three modes: `light` (mean color), `default` (perceptual hash) and
  `advanced` (OCR + text diff; requires Tesseract).
- **Alerts** through sound, popup, Telegram and/or a JSONL log, with per-channel minimum severity
  and cooldown.
- **Masks** to ignore areas that change on their own (clock, spinner, cursor).
- **Evidence**: prints of the baseline and of each change — opt-in.
- **Pseudo-human actions** (click, keys, text) when armed — rehearsal by default, audited in
  `logs/actions.jsonl`.
- **GUI with tray + full CLI**, with **profiles**, a scheduler (suspends actions outside the time
  window) and global hotkeys.
- **Multilingual UI**: pt-BR/en-US; the CLI and the technical log stay in English.

## What it doesn't do

- **It does not record the screen or video** — it only watches a region and compares.
- **It is not a document OCR**: OCR is used only to notice text changes.
- **It cannot capture occluded windows**: capture reads **screen pixels**; if another window covers
  the ROI, the overlapping content becomes part of the comparison. It is an API limitation, not a
  bug (doc §7.5).
- **It does not work on Wayland**: on Linux, run it on X11 — the app detects and warns.
- **No installers for macOS or ARM** (builds target Windows x64 and Linux amd64).
- **Installers are not code-signed** — SmartScreen will warn (signing is out of scope).
- **It does not bypass DRM/anti-cheat** or elevation (UAC).
- **It does not click on its own by default**: actions require the `input` extra and must be armed.

## How it works (overview)

1. You pick the **target window** and **draw the ROI** (`select` overlay, or coordinates via
   `select-manual`).
2. Every `poll_interval_s`, the app captures the ROI. The **first frame is the baseline** — not a
   change.
3. Each tick: capture → **masks** → **comparison** with the baseline in the chosen mode.
4. Change confirmed → the **alert chain** fires (severity + cooldown) and, if actions are armed, the
   configured sequence runs.
5. Config and state live in **app-data**: `config.yaml`, `selections/`, `state.json` and `logs/`.

```text
target window ──► ROI ──► capture ──► mask ──► compare (light/default/advanced)
                                                     │ changed?
                                                     ▼
                                   alerts (sound/popup/Telegram/log) + actions (if armed)
```

## What problems it solves

- Watching a **panel/indicator** (ERP, dashboard, status screen) without staring at it.
- Knowing that **something changed** (queue, order, ticket, balance, job state) even when the system
  offers no notification.
- Being alerted when a **text** changes — `advanced` mode.
- Watching a **long-running process** (build, import, bot) and reacting when it finishes or fails.
- Responding to a change with a **simple action** (click/shortcut/text) — opt-in, like a mini-RPA.

## Supported platforms

| Platform | How to run | Status |
|---|---|---|
| **Windows (x64)** | `.exe` installer (Inno Setup) or from source | supported; the installer downloads Tesseract automatically (optional) |
| **Linux Debian/Ubuntu (amd64, X11)** | `.deb` package or from source | supported; Wayland is not supported for capture |
| **macOS** | from source only | **not validated** and no installer (outside the build scope) |

Per-platform details: [wiki/Installation.md](wiki/Installation.md).

## How to use (step by step)

If you installed from the binaries, the command is `screen-watch`; from source, use
`python -m screen_watch`.

```powershell
python -m screen_watch list-windows                           # 1. pick the window (note the handle)
python -m screen_watch select --handle 12345 --name panel     # 2. draw the ROI in the overlay
python -m screen_watch test-alert --selection panel           # 3. check the alert
python -m screen_watch run --selection panel                  # 4. monitor
python -m screen_watch gui                                    # ...or use the GUI with tray
```

The shortest path is the GUI: **New Target (overlay)** → draw the ROI → **Start**. The selection is
saved in app-data (`selections/panel.json`) and can be reused by `run`.

**Quick command reference** (details in [wiki/CLI-Usage.md](wiki/CLI-Usage.md)):

```powershell
python -m screen_watch init-config            # create the v2 config.yaml in app-data
python -m screen_watch validate-config --selections
python -m screen_watch list-windows           # handle/title/rect
python -m screen_watch probe-dpi              # DPI matrix (mss physical × Qt logical)
python -m screen_watch select --handle 12345 --name panel     # overlay: drag on screen
python -m screen_watch select-manual --handle 12345 --roi 120 340 400 80 --name panel
python -m screen_watch list-selections
python -m screen_watch migrate-config --dry-run               # convert v1 YAML -> v2
python -m screen_watch test-alert --selection panel           # synthetic alert
python -m screen_watch test-evidence --selection panel        # sample prints
python -m screen_watch test-action --selection panel          # actions rehearsal (--armed executes)
python -m screen_watch list-actions --selection panel
python -m screen_watch record-actions --selection panel --out snippet.yaml
python -m screen_watch compare-modes --selection panel --delay 5   # calibration
python -m screen_watch show-paths
python -m screen_watch run --selection panel                  # monitor
python -m screen_watch gui                                    # GUI + tray
python -m screen_watch features                               # environment diagnostics
python -m screen_watch validate-i18n                          # validate the language catalogs
```

The global flags `--language TAG` (GUI language) and `--verbose` come **before** the subcommand, for
example: `python -m screen_watch --language en-US gui`.

- Full CLI guide: [wiki/CLI-Usage.md](wiki/CLI-Usage.md)
- Window and tray: [wiki/GUI-and-Tray.md](wiki/GUI-and-Tray.md)
- Configuration (profiles, overrides, migration): [wiki/Configuration.md](wiki/Configuration.md)

## Prerequisites

**To use the installers (Windows/Linux):**

- None for `light`/`default` modes.
- **Tesseract** on the system (`por` + `eng` traineddata) for `advanced` mode — on Windows the
  installer downloads it on demand; in the `.deb` it comes as a dependency.
- **Telegram** (optional): token via the `TELEGRAM_BOT_TOKEN` environment variable (never in the
  YAML).
- **Actions and global hotkeys** (optional): the `input` extra (`pynput`).
- **Sound** (optional): `winsound` on Windows; on Linux, a player (`paplay`/`aplay`/`ffplay`).
- **Linux**: an **X11** session — Wayland is not supported.

**To run from source:** Python **3.11+** and the extras you need:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"     # core + tests (ruff/pytest)
python -m pip install -e ".[input]"   # optional: actions/hotkeys (pynput)
python -m pip install -e ".[sound]"   # optional: sound via simpleaudio
```

## Installation

### Option 1 — binaries (recommended)

Download from [GitHub Releases](https://github.com/ph7ti/Screen-Diff-Watcher/releases):

- **Windows**: `screen-diff-watcher_<version>_windows_x64_setup.exe` (Inno Setup, per-machine,
  requires admin). Creates Start Menu shortcuts and, optionally, a Desktop shortcut and Windows
  startup. SmartScreen will warn (the `.exe` is unsigned): use "More info" → "Run anyway"; your
  antivirus may do the same.
- **Linux (Debian/Ubuntu amd64)**: `screen-watch_<version>_amd64.deb`
  (`sudo apt install ./screen-watch_<version>_amd64.deb`). The package declares `tesseract-ocr` +
  `tesseract-ocr-por` and the Qt6/X11 libs.

### Option 2 — from source

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m screen_watch --help
```

Detailed installation (automatic Tesseract, Linux autostart, uninstall, app-data, `features`
diagnostics): [wiki/Installation.md](wiki/Installation.md).

## Building the installers

The installers are built **on the target OS** (no cross-build) by `scripts/build_release.py`.
Full guide: [`doc/01-Build_and_Release.md`](doc/01-Build_and_Release.md).

```powershell
python -m pip install -e ".[dev,build,input]"
python scripts/build_release.py --windows   # on Windows (requires Inno Setup 6 / ISCC.exe)
python scripts/build_release.py --linux     # on Linux (requires dpkg-deb)
```

The script reads the version from `screen_watch.__version__` (single source; `pyproject.toml` is
dynamic), runs PyInstaller and writes the artifacts + `build-info.json` to `dist/installers/`. To
publish, create the tag `vX.Y.Z` (equal to `__version__`) and push: the
`.github/workflows/release.yml` workflow builds both installers, generates `SHA256SUMS.txt` and
creates the GitHub Release. `workflow_dispatch` generates artifacts only (no release).

## Current status

**Implemented:** capture and anchoring (Model B), comparison modes (`light`/`default`/`advanced`)
with pipeline and short-circuit, alerts with cooldown/re-arm, evidence, pseudo-human actions (with
GUI editor and recorder), scheduler, profiles, full CLI, GUI + tray with i18n (pt-BR/en-US),
packaging (Inno Setup and `.deb`) and tag-driven CI/release.

**Manual validation pending:** GUI/tray/overlay at 100/125/150% (doc §5.1, §9.5) and bundle details
on a clean machine (icon, `StartupWMClass`, package size, SmartScreen warning) — checklist in
[`doc/01`](doc/01-Build_and_Release.md) §9.

**Radar:** a fully CLI-driven selection flow (no overlay) is not defined yet — revisit when there
is demand.

## Known limitations (summary)

- **Wayland** cannot capture; **occluded windows** compare whatever is in front; **ARM** and
  **macOS** are not part of the build.
- **Tray on GNOME** may not appear without a tray extension (the window keeps working).
- **Sound on Linux** depends on an external player; without one it stays silent (the alert never
  breaks).
- A minimized or missing window emits `target_unavailable` and the loop keeps trying (it never
  breaks).

Full list, display scaling (DPI) and robustness notes:
[wiki/DPI-and-Limitations.md](wiki/DPI-and-Limitations.md).

## Development

```powershell
ruff check .
python -m pytest -q -m "not integration"
```

Integration tests are opt-in (`TEST_REAL_CAPTURE`, `TEST_REAL_TELEGRAM`) — details, script ladder
and CI in [wiki/Development-Tests-and-CI.md](wiki/Development-Tests-and-CI.md).

## Documentation

| Where | What it has |
|---|---|
| [**Wiki**](wiki/Home.md) | usage and feature details: CLI, GUI, config, actions, alerts, evidence, languages, DPI, build |
| [`doc/00-Architecture_and_Specification.md`](doc/00-Architecture_and_Specification.md) | architecture and specification — **single source of truth for the design** |
| [`doc/01-Build_and_Release.md`](doc/01-Build_and_Release.md) | installer build and release pipeline |
| [`CHANGELOG.md`](CHANGELOG.md) | changes per version (semantic) |
| [`README.pt-BR.md`](README.pt-BR.md) | este guia em português |

> **Design note**: `doc/00` decides the design; the Wiki describes usage and features. Never record
> a design decision here without it being (or having to be) in `doc/00`.
