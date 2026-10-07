# Installation

**English** · [Português (Brasil)](Instalacao.md)

Screen Diff Watcher runs on **Windows (x64)** and **Linux Debian/Ubuntu (amd64, X11)** and, from
v0.11.0, on **macOS (arm64)** as an unsigned `.app`. There are two ways to install: via the
**binaries** (installers) or via the **source code**.

| Platform | Format | Notes |
|---|---|---|
| Windows x64 | `screen-diff-watcher_<version>_windows_x64_setup.exe` (Inno Setup) | requires admin (per-machine); offers the optional Tesseract download (asks first; silent only via `/TESSERACT=yes`) |
| Linux Debian/Ubuntu amd64 | `screen-watch_<version>_amd64.deb` | requires X11; Wayland does not capture |
| macOS arm64 | `screen-diff-watcher_<version>_macos_arm64.zip` | unsigned `.app` (no notarization); **not yet validated on hardware**; needs Screen Recording + Accessibility permissions |

## Option 1 — binaries

The installers are published on
[GitHub Releases](https://github.com/ph7ti/Screen-Diff-Watcher/releases).

### Windows

1. Download and run `screen-diff-watcher_<version>_windows_x64_setup.exe`.
2. The installer is **per-machine** (installs to `Program Files`) and **requires admin** — because of the
   machine-wide Tesseract install. It creates a Start Menu shortcut and, optionally (unchecked),
   a Desktop shortcut and **automatic start with Windows**.
3. **SmartScreen**: since the `.exe` is not signed, Windows will warn — use "More info" →
   "Run anyway". The antivirus may do the same. Code signing is out of scope.
4. **Optional Tesseract**: the installer asks before downloading (Yes/No). If Tesseract is not
   installed and you accept, it downloads the pinned UB-Mannheim release, **verifies the SHA256**,
   installs it silently and ensures the `por.traineddata` (the package already ships `eng`). It needs
   network and admin; if you decline, the download/verification fails or you are offline, it
   **warns and continues** — the `light`/`default` modes work and `advanced` reports the absence
   with a clear message. Silent installs (`/SILENT` or `/VERYSILENT`) skip it unless `/TESSERACT=yes`
   is passed.
   - **Offline**: install Tesseract manually
     (https://github.com/UB-Mannheim/tesseract/wiki) with the `por` and `eng` traineddata; the installer
     detects the binary and does not download anything.
5. Uninstalling removes only the app and **preserves** Tesseract and the user data.

### Linux (Debian/Ubuntu amd64)

```bash
sudo apt install ./screen-watch_<version>_amd64.deb
```

- Requires **X11** (Wayland is not supported for capture).
- The `.deb` declares `tesseract-ocr` + `tesseract-ocr-por` and the Qt6/X11 libs as dependencies;
  `pulseaudio-utils`/`alsa-utils` come as `Recommends` (legacy fallback players).
- Installed commands: `screen-watch` (CLI) and `screen-diff-watcher-gui` (GUI, also in the
  menu shortcut).
- **Autostart**: the `.deb` does not configure it. To start with the session, create
  `~/.config/autostart/screen-diff-watcher.desktop`:

  ```ini
  [Desktop Entry]
  Type=Application
  Exec=screen-diff-watcher-gui
  X-GNOME-Autostart-enabled=true
  ```

- Uninstalling preserves Tesseract and the app-data.

## Option 2 — source code

Requires **Python 3.11+**.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"     # core + test tools (ruff/pytest)
```

Optional extras:

| Extra | What for |
|---|---|
| `pip install -e ".[input]"` | pseudo-human actions and global hotkeys (`pynput`) |
| `pip install -e ".[sound]"` | sound via `simpleaudio` (no reliable wheel on Python 3.13; optional) |
| `pip install -e ".[ocr-preproc]"` | OCR preprocessing experiments (`opencv-python`) |
| `pip install -e ".[mqtt]"` | MQTT alert channel (`paho-mqtt`; not bundled in the installers) |
| `pip install -e ".[macosx]"` | popups on **macOS** (`pyobjus`; required by the plyer backend) |
| `pip install -e ".[build]"` | build installers (`pyinstaller`) |

The **ntfy** and **SMTP** alert channels need no extra (the core `httpx` and the stdlib `smtplib`);
only **MQTT** requires the `mqtt` extra. Credentials for every channel (Telegram, ntfy, SMTP, MQTT)
come from **environment variables**, never from the YAML.

Then:

```powershell
python -m screen_watch --help
python -m screen_watch init-config    # creates config.yaml v2 in app-data
```

## Where config, selections and logs live (app-data)

Everything lives in `%APPDATA%\screen_watch` on Windows (`config.yaml`, `selections/`, `state.json`,
`logs/`). To point to another directory, set `SCREEN_WATCH_HOME`. See the effective paths:

```powershell
python -m screen_watch show-paths
```

**Microsoft Store Python (MSIX)**: Windows redirects `%APPDATA%` into the package, and the
file becomes invisible to Explorer/editors. In that case the app switches to the real path
(`...\AppData\Local\Packages\<package>\LocalCache\Roaming\screen_watch`).

## Diagnostics: `features`

```powershell
screen-watch features           # version/origin, app-data, number of selections, Tesseract, input, sound, tray, monitors
screen-watch features --json    # JSON output (used in the CI smoke)
```

It degrades without a display (does not break) and reports whether the binary is `bundle` or `source`. It is the
first command to diagnose an environment (e.g.: missing Tesseract, `pynput` unavailable).

## Installer limitations

- **Wayland**: capture via `mss` does not work; run on X11. The app warns and ends the `run`.
- **Tray on GNOME**: may not appear without a tray extension; the window keeps working.
- **Sound on Linux**: the CLI/`run` uses the bundled `miniaudio` (WAV/MP3/OGG/FLAC); the GUI depends
  on the GStreamer plugins, and **M4A/AAC** in the CLI needs an external player (`ffplay`), otherwise
  it falls back to `beep`.
- **Architecture**: only `amd64`/`x86_64`. ARM out of scope.
