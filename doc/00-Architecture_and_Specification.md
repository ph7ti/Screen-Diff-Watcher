# Screen Diff Watcher — Architecture and Specification Document

**English** · [Português (Brasil)](00-Documento_de_Arquitetura_e_Especificação.md)

> **Purpose of this document**: to serve as the **single source of truth for the design** so that
> another AI (or developer) can continue the project without having to reconstruct decisions, and to
> record **what is implemented** (reference: v0.10.1). Every decision recorded here was made
> deliberately; where there are alternatives, they are listed as "rejected" with the reason.
>
> **Maintenance rule**: do not replace a recorded decision with a "more modern" alternative
> without explicit justification. If the code diverges from the document, **update the document by
> recording the reason for the change and the history** — never change the document silently to
> hide the divergence.

Related guides:

- Usage and features (wiki): [`../wiki/Home.md`](../wiki/Home.md)
- Build and release: [`01-Build_and_Release.md`](01-Build_and_Release.md)
- Overview in the README: [`../README.md`](../README.md)

---

## 1. Overview

### 1.1 What the project is

A **cross-platform Python desktop application** that:

1. Lets the user **select a window** and, inside it, a **rectangular region (ROI)**.
2. **Monitors that ROI periodically** (configurable interval, minimum 1 s).
3. Detects **visual changes** according to a comparison mode (Light / Default / Advanced).
4. **Emits alerts** when the change is confirmed: local sound, local popup, JSONL log and/or remote
   channels (Telegram, ntfy push, e-mail/SMTP, MQTT, generic webhook/HTTP POST, syslog), with
   snooze/mute and optional escalation until acknowledged (§11).
5. Optionally, **executes pseudo-human actions** (click/keys/text) when **armed** — by default in
   rehearsal (dry-run), with auditing in `logs/actions.jsonl` (§11.4).
6. Offers a **GUI with tray** (PyQt6 + pystray) and a **full CLI**, with profiles, scheduler and i18n
   (pt-BR/en-US in the GUI; CLI and log in fixed English).

**Build target platforms**: Windows (x64) and Linux Debian/Ubuntu (amd64, X11). macOS has code
paths (audio/paths), but is **not a build or validation target** (§15).

### 1.2 What the project is NOT

- It is not a screen recorder.
- It is not document OCR (OCR only serves to detect text change).
- It does not capture occluded windows (fundamental limitation of the capture API — see §7.5).
- It does not bypass DRM, anti-cheat or protected windows.
- It does not depend on any proprietary cloud service: every remote channel (Telegram, ntfy, SMTP,
  MQTT, webhook) is optional and user-configured, with credentials in environment variables.
- It does not support **Wayland** (§3.2) or **ARM**; it does not digitally sign the installers.
- It is not a generic RPA: the actions are an opt-in and deliberate subsystem (§11.4).

### 1.3 Canonical use case

Monitor a panel/indicator inside a desktop application (e.g., the inventory panel of an ERP) and
alert the user when that panel undergoes a visual change, without requiring the user to keep
looking at the screen. Natural extension: react to the change with a simple action (e.g., click
"Refresh") when that is explicitly armed.

### 1.4 Implementation status (v0.10.1)

Implemented and covered by tests: platform boundary, capture/anchoring (Model B), the three
comparison modes, pipeline with short-circuit (`advanced` gated by phash and bypassed by
`text_watch`), alerts (sound/popup/Telegram/log plus `webhook`/`http_post`/`syslog`, with payload
template, stable `id` and cooldown) with re-arm, **selectable sound (Qt Multimedia in the GUI,
`miniaudio` in the CLI, legacy fallback)** and the **`text_watch`** presence filter
(appears/disappears, advanced only, per-selection override), send test per channel (`test-alert
--list/--only` and the GUI button), evidence, pseudo-human
actions (arming, rehearsal, limits, auditing, GUI editor, recorder), scheduler (suspends actions
only), profiles + v1→v2 migration, selection JSON v2 with overrides and the **selection
`name`/rename** (`selections/<slug>.json`), CLI (`init-config` … `validate-i18n`), GUI + tray with
i18n and hover help — including **"Highlight"** (transient ROI outline that never paints inside the
ROI), **double-click to re-edit the region / Enter to start-stop**, the **2×2 grid window layout**
(Selections and Session actions on the left; Monitoring and Detection and alerts on the right;
Status+Log footer with the buttons on the right), the **bundled default sound `alert.mp3`** (resolver
order `app_home()/sounds` → `assets/sounds` → CWD) and the **sound-choice popup** that points to the
YAML — packaging (PyInstaller; Inno Setup on Windows; `.deb` on Linux) and tag-based release pipeline.

**v0.8.0 additions**: visual **mask editor** (draw/remove masks in the overlay, atomic selection JSON
write, `overrides.masks` precedence, blocked while running), **sound picker writes `file:` into the
active profile's YAML** (atomic + `.bak`, config v1 refused), **frame preview** (baseline + latest,
downsampled thumbnails), **alert history** over `logs/alerts.jsonl` (date/severity/strategy filters,
best-effort evidence print) and **live calibration** (score vs threshold, CSV export); CI now runs
Python 3.11/3.12/3.13 with a coverage artifact and the wiki has a manual publication runbook.

**v0.9.0 additions**: three alert channels (**ntfy**, **SMTP** via stdlib, **MQTT** via the optional
`mqtt` extra) following the `options:` schema and stable error codes; **snooze/mute** via the shared
thread-safe `AlertGate` persisted in `state.json` (GUI/tray, `SUPPRESSED_MANUAL` outcome) and
**escalation** (repeat until acknowledged, `acknowledge()` + per-alert cooldown pacing, change
evidence tied to delivery attempts); the **selection lifecycle in the CLI** (`remove-selection`,
`rename-selection`, `edit-selection`, `list-selections --json`) completing the headless flow (the
README "Radar" item); and **multiple simultaneous ROIs** in the GUI (`SessionManager` running N
`MonitorLoop`s with per-session preview/calibration, checkbox set, `ui.max_sessions`, aggregated
status/tray, per-selection tray start/stop).

**v0.9.1 fix**: `SessionManager.escalating` is a **method**; the GUI gate-status/acknowledge code
calls it (`main_window._update_gate_status`/`_acknowledge`). The leftover property access raised
`TypeError` inside the `QTimer` slot and PyQt6 aborts the process on an unhandled slot exception —
the GUI died on the first drain tick (`0xC0000409`) without a visible traceback. Regression tests in
`tests/test_gui_main_window.py` drive the real methods with Qt-free stubs (and a lazy
`main_window` import, so the tests that simulate Qt being absent keep working).

**v0.10.0 additions**: per-action **time triggers** (`when.trigger: change|at|every|after`, §11.4):
the pure evaluator `actions/triggers.py` (injectable wall/monotonic clocks; 60 s tolerance recorded
as `skipped -> missed`; no catch-up or replay), `ArmingController.armed_since` phases,
`ActionDispatcher.on_tick` evaluated on every post-baseline frame plus `next_deadline_delay()`
capping the `MonitorLoop` wait (§3.5), strict validation (change-only fields, `rebaseline` refused,
`cooldown_s >= every_s`), `trigger` in the audit/live payloads, GUI editor trigger selector,
`list-actions` summary, one-off notice (`trigger ... ignored (explicit run)`) and the recorder
commented hint; i18n in both catalogs and fake-clock tests.

**v0.10.1 fix**: the GUI mouse locator and the ROI highlight now convert between Qt logical and
physical space anchored on the monitor origin (§9.5); before, actions created with the locator
clicked at **logical** coordinates on scaled monitors (`ref: roi`/`window`/`screen`; e.g., ~192×120 px
off at the center of a 1920×1200 @ 125% screen). Capture, recorder and hand-typed coordinates were
already physical and unchanged.

Pending **manual validation** items (not automatable in CI):

- GUI/tray/overlay at 100/125/150% scales (§5.1, §9).
- Bundle on a clean machine: window/tray icon, `StartupWMClass` of the `.desktop`, package size,
  SmartScreen warning (signing out of scope). Checklist in [`doc/01`](01-Build_and_Release.md) §9.

---

## 2. Non-negotiable architectural principles

These principles guide all the decisions below. If an implementation detail conflicts
with any of them, the principle wins.

1. **Capture and comparison are decoupled by a data contract (`Frame`).** Comparison never
   accesses the screen, never knows about windows, never sleeps.
2. **Every OS dependency stays behind an explicit boundary.** No `if sys.platform == ...`
   scattered through business code.
3. **DPI awareness is fixed at process start, before any backend.** See §5.1.
4. **The capture loop is immediately cancellable** and its cadence is stable under load.
5. **The first frame is baseline, not change.** The initial state of the comparison is explicit, never
   implicit.
6. **Capture failures do not break the loop.** They emit an event and the next tick tries again.
7. **Configuration is declarative and persisted.** No hardcoded session state.
8. **Actions are opt-in, disarmed by default and audited.** The arming state lives only in
   memory (§11.4); never in the YAML.
9. **Errors have a stable code (`AppError.code`)** and an English message; the GUI translates by code
   (`render_error`), the CLI/log show English (§12.7).
10. **The GUI is translatable (JSON catalogs in the package); CLI and logging are in fixed English** (§12.6).

---

## 3. Architecture decisions (condensed ADR)

Each item below is a closed decision. Format: **Decision → Reason → Rejected alternatives**.

### 3.1 Language and runtime

- **Decision**: Python 3.11+.
- **Reason**: `Protocol`, `dataclass(frozen=True)`, modern `tomllib`/`typing`, mature `asyncio`;
  wide availability of bindings for capture, GUI and OCR. PyInstaller only gained
  Python 3.13 support starting with 6.11.1 (pin in the `build` extra).
- **Rejected**: Python 3.9/3.10 (missing typing features used in the design); Rust/Go (integration
  cost with `mss`, `pywinctl`, Tesseract does not pay off for the scope).

### 3.2 Screen capture

- **Decision**: **`mss`** as the only backend in the prototype. `pyautogui` is not used.
- **Reason**: `mss` is faster, returns `numpy`-compatible data directly, has a stable API across
  platforms, and keeps a reusable instance.
- **Implementation details**:
  - The backend lives behind the `capture/backend.py` contract; `MssCaptureBackend` creates the
    instance **once** and reuses it (never per tick). `mss` **is not thread-safe**: `MonitorLoop`
    creates the backend **inside its own thread** and closes it in the worker's `finally`.
  - `MssCaptureBackend.bounds()` returns the virtual desktop rectangle (including negative
    coordinates), used by the ROI clipping (§7.6).
  - The BGRA→RGB conversion is done in the backend (`np.asarray(...)[:, :, [2, 1, 0]]`).
- **Rejected alternatives**:
  - `pyautogui` — slower, limited screenshot API; it would only be worth it as a fallback we have
    no need to use.
  - `dxcam` / `d3dshot` — Windows-specific with GPU; they break the cross-platform promise.
  - `Pillow.ImageGrab` — covers fewer cases than `mss` and brings no advantage.
- **Known and accepted limitation**: `mss` **does not work on Wayland**. The project detects it
  (`XDG_SESSION_TYPE=wayland`) and shuts down the `run` command with a clear warning (`is_wayland()`
  in `platform/dpi.py`). **Do not implement a Wayland backend in the prototype** — it is out of scope.

### 3.3 Window location and anchoring

- **Decision**: **`pywinctl`**, anchoring by **Model B (relative to the window origin)**.
- **Reason**: `pywinctl` is maintained and cross-platform. Model B follows the window when it moves,
  without requiring access to the client area (which is per-OS plumbing).
- **Implementation details**: the `platform/window.py` wrapper exposes `WindowInfo`
  (`handle`, `title`, `rect`, `is_minimized`, `exists`), `find_window_by_handle`, `list_windows`,
  `activate_window` and `is_window_active`. The `resolver` uses the identity converter by default
  (`identity_converter`) — see §5.1.
- **Rejected alternatives**:
  - `pygetwindow` — abandoned, Windows/macOS only with gaps.
  - Model A (frozen absolute coordinates) — breaks when the window moves.
  - Model C (relative to the client area, excluding chrome) — semantically more robust, but requires
    per-OS plumbing that is unnecessary for the scope.

### 3.4 Comparison

- **Decision**: three pluggable strategies:
  1. **Light** — `MeanColorStrategy` (mean RGB color + Euclidean distance).
  2. **Default** — `PerceptualHashStrategy` (`imagehash.phash`, `hash_size=8`).
  3. **Advanced** — `OCRTextDiffStrategy` (`pytesseract` + `difflib.SequenceMatcher`).
- **Reason**: each mode covers a cost/sensitivity trade-off; the cheap strategy vetoes the expensive
  ones when composed in the pipeline (§10.5).
- **Implementation details**: `light`/`default` map to **one stage**; `advanced` maps to
  **two** (`default` → `advanced`), so the phash acts as a **pixel gate** before the OCR: if the
  pixels did not change, the pipeline short-circuits and OCR does not run/score. This avoids OCR
  noise on nearly-identical frames producing a "change" every tick (updated §10.5).
- **Rejected alternatives**:
  - phash only — does not distinguish semantic change from structural noise in some cases.
  - OCR only — too expensive per tick, unfeasible at 1 Hz.
  - SSIM — more expensive than phash with no clear gain for the use case.

### 3.5 Scheduling

- **Decision**: `threading.Thread` + `threading.Event.wait(timeout)` as the main loop.
- **Reason**: immediate cancellation, no extra dependency, simple to reason about. `wait` subtracts
  the work time from the interval, guaranteeing a stable cadence.
- **Multiple sessions (v0.9.0)**: the GUI runs **N `MonitorLoop`s** — one thread, one `mss` backend
  and one `MonitorSession` per target — coordinated by `gui/session_manager.SessionManager`. The
  per-thread isolation of `mss` (§3.2, §14.16) is what makes it safe; each session keeps its own
  preview/calibration buffers and the snooze/mute `AlertGate` is shared. `ui.max_sessions` (default
  4, range 1..16) bounds the GUI set; OCR in `advanced` multiplies CPU per session (documented).
  The CLI `run` intentionally stays single-selection (multi-ROI headless is out of scope for now).
- **Action-trigger deadlines (v0.10.0)**: the same `Event.wait` is capped by the next armed
  time-trigger deadline (`ActionDispatcher.next_deadline_delay()` forwarded by `build_loop`), so a
  punctual `at` and an `every_s` shorter than the poll can fire on time; the floor is 0.05 s and the
  cadence stays the poll interval when there is no deadline (§11.4).
- **Rejected alternatives**:
  - `asyncio` — unnecessary overhead; `mss`/`pywinctl` are synchronous and blocking.
  - `APScheduler` — over-engineering for a single loop.
  - One process per session — duplicated config/state/alert gate and heavier packaging, no benefit
    for the scope.

### 3.6 Alerts

- **Decision**: chain of notifiers (**Chain of Responsibility**), each with `enabled`,
  `severity_min` and `cooldown_s`. Implemented in the prototype:
  - **Local sound** — behind the `platform/audio.py` boundary: Qt Multimedia in the GUI
    (`QMediaPlayer`, WAV/MP3/M4A/AAC/…), `miniaudio` in the CLI/`run` (core dependency;
    WAV/MP3/OGG/FLAC on a daemon thread) and the legacy fallback (`winsound` on Windows;
    `paplay`/`aplay`/`ffplay` on Linux; `afplay` on macOS). The `simpleaudio` extra remains optional.
  - **Local popup** (`plyer.notification`).
  - **Telegram Bot webhook** (`httpx`, `sendPhoto`/`sendMessage`, 5 s timeout; token via
    environment variable).
  - **ntfy** (`httpx`; plain-text POST to `server/topic`, optional PNG PUT with `attach_roi`,
    `Title`/`Priority`/`Tags` headers; token via environment variable, anonymous when unset).
  - **E-mail (SMTP)** (stdlib `smtplib`; STARTTLS/SSL/none, credentials via environment variables,
    optional PNG attachment).
  - **MQTT** (optional extra `paho-mqtt`; JSON payload publish with QoS/retain/TLS, credentials via
    environment variables, no image).
  - **JSONL log** (`app-data/logs/alerts.jsonl`).
- **Reason**: Telegram is free, reliable, allows attaching an image of the ROI in the alert (essential
  to validate false positives), and requires no server setup. ntfy covers phone push without a bot;
  SMTP covers corporate e-mail; MQTT covers user-owned automation buses. All three keep the
  credentials in environment variables and follow the same chain/cooldown contract. The JSONL log
  gives local auditing; the popup/sound cover offline use.
- **Rejected alternatives**:
  - Pushover — paid.
  - FCM — disproportionate setup complexity.
  - `simpleaudio` as the only sound route — no reliable wheel for Python 3.13; it became an optional
    extra (`pip install -e ".[sound]"`), with fallback to an external player.
  - Qt Multimedia as the **only** sound route — it requires a `QCoreApplication`, so the CLI/`run`
    cannot use it (hence `miniaudio` in the core).

### 3.7 GUI and selection overlay

- **Decision**: **PyQt6** for the GUI and overlay.
- **Reason**: native multi-monitor (`QGuiApplication.screens()`), real transparency, high DPI
  correctly resolved, `CompositionMode_Clear` available for the selection "hole".
- **Implementation details**:
  - **Layout**: the window follows the `UI.txt` mockup (upper panel in a **2×2 grid**: on the left the
    **Selections** group — New Target/Remove/Reload/**Highlight selection**/**Edit masks…** button row,
    legend, list and
    the **Selection name** field (`name` + Rename) — and the **Session actions** group — checklist,
    counter and the New action…/Edit…/Remove Action/Run action row; on the right **Monitoring** — a
    two-column grid Start/Language, Stop/Re-arm baseline, Mode/Profile, Arm actions/Disarm actions,
    Arm for…/Minimize to tray, plus **Record captures (evidence)** and the arming status — and
    **Detection and alerts** — the text watch first and then the sound, with **Choose…/Play/Copy path**;
    in the footer, in a `QSplitter`, the **Status** group with Status/Last/**Log** and the right column
    with **Captures/Test alert…/Open YAML**). Step editing with
    Move Up/Move Down/drag&drop/Edit/Duplicate.
  - **Sound picker (v0.8.0)**: after choosing a sound, the GUI **asks for confirmation and writes**
    `file:` into the active profile's `sound` alert in `config.yaml` (atomic + `.bak`, §11.2/§12.1);
    the dialog keeps **Copy path and open YAML**/**Open YAML only**/**Close** as secondary actions,
    warns when the selection overrides `alerts`, and shows a migrate message for config v1 instead of
    writing.
  - **Selection interactions**: **double-click re-edits the region** (overlay again, same window,
    preserving `name`/`mode`/`overrides` and clearing `masks`); **Enter starts/stops** the session
    (`QShortcut` with `WidgetShortcut`; `itemActivated` is not used because it also fires on the
    double-click). Renaming writes the display name and moves the file (slug; never overwrites).
  - **Highlight ("Ver local")**: one frameless, *top-most* window per monitor, transparent to
    clicks/focus (`WindowTransparentForInput` + `WA_TransparentForMouseEvents`, no grabs, no modal),
    dimming **only outside** the ROI (`overlay_geometry.dim_rects`) with a 2 px border drawn just
    outside the hole; auto-closes after 2 s. Because the ROI pixels are never painted, it can run
    while the session monitors (`gui/highlight.py`).
  - **Mask editor ("Edit masks…", v0.8.0)**: modal per-monitor overlay (same visual pattern as the
    selection overlay) that shows the ROI border and the effective masks; left-drag adds a mask,
    right-click removes the mask under the cursor, Enter saves and Esc cancels. It is blocked while a
    session runs and writes the selection JSON atomically (§8.3, §12.3).
  - **Preview, history and calibration (v0.8.0)**: the Monitoring area shows a **Preview** with the
    latest captured frame and the baseline; only downsampled thumbnails cross the thread boundary —
    the controller keeps two bounded arrays under a lock and the GUI builds/copies the `QImage` on
    the GUI thread (the loop thread never hands its `numpy` array to a widget). An **Alert history**
    table reads `logs/alerts.jsonl` (tolerant to invalid lines) with date/severity/strategy filters
    and a best-effort "open print" (nearest `*_change.png` within ±2 s, else the captures folder).
    A **Calibration** widget plots `score` vs `threshold` from a bounded per-session ring buffer fed
    by **every** comparison (not only changed frames) with CSV export; no extra dependency (custom
    `QPainter`).
   - **Tray**: `pystray` (`gui/tray.py`) with show/hide, start/stop, arm/disarm, profile,
     **Snooze/Mute/Unmute/Acknowledge** (v0.9.0) and quit. The GUI receives events through a
     **queue** consumed by `QTimer` (`gui/session_manager.py`); tray/hotkey callbacks never call Qt from
     inside the listener thread.
   - **Snooze/mute/escalation controls (v0.9.0)**: the Detection and alerts group has **Snooze…**
     (durations from `ui.snooze_minutes`), **Mute/Unmute** and **Acknowledge** (enabled while a
     session escalates), plus a label with the remaining snooze/mute time; the same actions are in
     the tray. Snooze/mute persist in `state.json` and apply to every session sharing the gate
     (§11.3).
   - **Multiple ROIs (v0.9.0)**: the selection list has **checkboxes**; Start starts every checked
     selection (none checked = the highlighted one) through `SessionManager`, up to
     `ui.max_sessions`. Rows of running sessions are prefixed with `▶`, the status line aggregates
     the count (`status.monitoring_multi`), the log/result lines are prefixed with `[selection]`
     when 2+ run, and preview/calibration/actions follow the **highlighted** running row (else the
     first running one). Stop stops every session; Remove stops the affected ones first; the tray
     menu has aggregated start/stop plus a per-selection start/stop submenu. (`MonitorController`
     was replaced by `gui/session_manager.SessionManager`; §3.5.)
  - **Languages**: the GUI goes through i18n (JSON catalog in the package); CLI/log stay in English (§12.6).
  - **Help**: 2 s hover shows the purpose + example of each control (`gui/help.py` +
    `gui/hover_help.py`).
  - **Arming from the window**: `Arm actions`/`Disarm`/`Arm for…` buttons wired to the same path as
    the tray/hotkey (§11.4).
- **Rejected alternatives**:
  - `tkinter` — transparency and multi-monitor require hacks; `overrideredirect` breaks on
    some Linux WMs.
  - No GUI (manual config only) — the use case requires visual selection.

### 3.8 Packaging

- **Decision**: **PyInstaller**, per-platform build, with native installers:
  **Inno Setup** (Windows) and **`.deb`** (Linux).
- **Reason**: more mature, extensive documentation, works on the target OSes; native installers give
  shortcuts, uninstallation and declared dependencies.
- **Implementation details**: **onedir** bundle with two executables (`screen-watch` console and
  `screen-watch-gui` windowless) that share `PYZ`/`COLLECT`; the script
  `scripts/build_release.py` runs **on the target OS** (no cross-build), reads the version from
  `screen_watch.__version__` and writes `dist/installers/`. Full guide: [`doc/01`](01-Build_and_Release.md).
- **Rejected alternatives**:
  - Nuitka — faster, but more fragile builds and longer compilation time.
  - Briefcase — promising, but a smaller ecosystem for the chosen stack.

### 3.9 Configuration

- **Decision**: **YAML** (`PyYAML`) for user config; **JSON** for the ROI selection dump.
- **Reason**: YAML is readable for manual editing; JSON is generated by the GUI and does not need comments.
- **Implementation details**: the YAML is **global and versioned** (`version` 1 or 2). v2 brings
  `profiles` (defaults/alerts/actions), `ui`, `schedule` and `evidence`; targets become JSON
  selection files in app-data (§12). Secrets never in the YAML (§12.1).
- **Rejected alternatives**: TOML (good, but `tomllib` is read-only in older versions); INI
  (limited for nested structures).

---

## 4. Directory structure (implemented)

```
ScreenDiffWatcher/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE
├── doc/
│   ├── 00-Architecture_and_Specification.md            # this document (SSoT)
│   ├── 00-Documento_de_Arquitetura_e_Especificação.md  # PT mirror
│   ├── 01-Build_and_Release.md                         # build/release pipeline
│   ├── 01-Build_e_Release.md                           # PT mirror
│   └── releases/                                       # per-version notes (EN + .pt-BR.md)
├── wiki/                          # GitHub Wiki pages (usage and features)
├── src/
│   └── screen_watch/
│       ├── __init__.py            # __version__ (single source)
│       ├── __main__.py            # entry point: python -m screen_watch (main() only)
│       ├── cli/                   # CLI: 22 subcommands (commands.py) + parser (parser.py)
│       ├── app.py                 # orchestration: pipeline + chain + session + evidence
│       ├── errors.py              # AppError/ConfigError + ERROR_CODES + render_error
│       ├── naming.py              # slugify for selection file names (pure)
│       ├── gui_main.py            # entry point of the windowless executable (GUI)
│       ├── resources.py           # package resources (icons etc.)
│       │
│       ├── platform/              # OS boundary (no sys.platform outside of here)
│       │   ├── dpi.py             # set_dpi_awareness, is_wayland
│       │   ├── window.py          # pywinctl wrapper; activate_window/is_window_active
│       │   ├── paths.py           # app-data, state.json (atomic), MSIX
│       │   ├── display.py         # per-monitor scale (mss × Qt matrix)
│       │   ├── tesseract.py       # binary location (PATH + common directories)
│       │   ├── audio.py           # winsound / paplay / aplay / ffplay / afplay
│       │   ├── input.py           # pynput (lazy), interpolation/jitter (humanization)
│       │   └── shell.py           # open_path (os.startfile / open / xdg-open)
│       │
│       ├── capture/
│       │   ├── frame.py           # Frame dataclass
│       │   ├── backend.py         # Protocol ScreenCaptureBackend (bounds/capture/close)
│       │   ├── mss_backend.py     # mss implementation (BGRA->RGB, per-thread instance)
│       │   ├── resolver.py        # window + roi_relative -> absolute ROI (Model B)
│       │   ├── roi.py             # shared window+ROI resolution (capture and Highlight)
│       │   ├── geometry.py        # intersect_rect (clip against the virtual desktop)
│       │   └── mask.py            # apply_mask
│       │
│       ├── compare/
│       │   ├── protocol.py        # CompareStrategy, ComparisonResult, compute_severity
│       │   ├── light.py           # MeanColorStrategy
│       │   ├── default.py         # PerceptualHashStrategy
│       │   ├── advanced.py        # OCRTextDiffStrategy
│       │   └── pipeline.py        # MODE_STAGES + ComparePipeline (short-circuit)
│       │
│       ├── alerts/
│       │   ├── protocol.py        # Notifier
│       │   ├── sound.py           # SoundNotifier (platform/audio.py boundary)
│       │   ├── popup.py           # PopupNotifier (plyer)
│       │   ├── telegram.py        # TelegramNotifier (httpx; token via env)
│       │   ├── ntfy.py            # NtfyNotifier (httpx; optional token via env; PNG PUT)
│       │   ├── smtp.py            # SmtpNotifier (stdlib smtplib; credentials via env)
│       │   ├── mqtt.py            # MqttNotifier (optional extra paho-mqtt; JSON payload)
│       │   ├── log.py             # JsonlNotifier (logs/alerts.jsonl)
│       │   ├── template.py        # ${field}/${env:VAR} template (string.Template)
│       │   ├── http.py            # WebhookNotifier + HttpPostNotifier (httpx; payload template)
│       │   ├── syslog.py          # SyslogNotifier (SysLogHandler; udp/tcp; severity_map)
│       │   ├── test_send.py       # list_alert_targets + send_test (CLI/GUI send test)
│       │   ├── gate.py            # AlertGate (thread-safe snooze/mute; state.json)
│       │   └── chain.py           # AlertChain + DispatchOutcome (cooldown key = uid; gate)
│       │
│       ├── actions/               # pseudo-human actions (opt-in)
│       │   ├── protocol.py        # ActionSpec/ActionStep (pure)
│       │   ├── plan.py            # parse/validation (click requires activate; text_* requires advanced)
│       │   ├── dispatch.py        # ActionDispatcher (on_tick/deadline; rehearsal/armed/scheduler/limits)
│       │   ├── triggers.py        # pure time-trigger evaluator (at/every/after; injectable clocks)
│       │   ├── runner.py          # synchronous execution + focus + humanization + limits
│       │   ├── arming.py          # ArmingController (disarmed/armed/timed; memory only)
│       │   ├── audit.py           # ActionAudit (logs/actions.jsonl)
│       │   ├── selection.py       # per-session subset (state.json)
│       │   ├── summary.py         # human-readable action description
│       │   ├── once.py            # one-off execution (test-action / GUI button)
│       │   └── recorder.py        # click/key recorder -> YAML snippet
│       │
│       ├── evidence/
│       │   └── recorder.py        # EvidenceRecorder (prints; retention; effective folder)
│       │
│       ├── scheduler/
│       │   ├── loop.py            # MonitorLoop (threading + Event; deduplicated events)
│       │   └── schedule.py        # is_open/gate (pure function with injectable clock)
│       │
│       ├── config/
│       │   ├── schema.py          # dataclasses (AppConfig/ProfileOptions/TargetConfig/…)
│       │   └── loader.py          # YAML <-> dataclasses; defaults; v1->v2 migration
│       │
│       ├── persistence/
│       │   └── selection.py       # selection JSON v1/v2 + build_target (overrides) +
│       │                          #   CLI edit helpers + name/rename
│       │
│       ├── i18n/
│       │   ├── __init__.py        # JSON catalog, language resolution, tr()
│       │   ├── pt-BR.json         # fallback
│       │   └── en-US.json
│       │
│       ├── gui/
│       │   ├── main_window.py     # window (UI layout; checkbox set; aggregated status)
│       │   ├── session_manager.py # SessionManager: N sessions + events + preview/calibration
│       │   ├── tray.py            # pystray (start/stop, snooze/mute/ack, per-selection)
│       │   ├── overlay.py         # SelectionOverlay (one window per monitor)
│       │   ├── overlay_geometry.py# logical<->physical conversions (pure, no Qt)
│       │   ├── mask_overlay.py    # mask editor overlay
│       │   ├── mask_editor_geometry.py  # mask editor geometry (pure)
│       │   ├── preview_widget.py  # baseline/latest preview panel
│       │   ├── preview_geometry.py# downsample/thumbnail (pure)
│       │   ├── history_dialog.py  # alert history (logs/alerts.jsonl)
│       │   ├── calibration_widget.py    # live calibration chart
│       │   ├── calibration.py     # calibration helpers (pure)
│       │   ├── countdown.py       # 3 s countdown (focusless overlay)
│       │   ├── locator.py         # mouse position locator
│       │   ├── action_editor.py   # selection action editor
│       │   ├── alert_dialog.py    # "Test alert…" dialog + send worker
│       │   ├── hotkeys.py         # global hotkeys (pynput, lazy)
│       │   ├── help.py            # help texts (pure)
│       │   ├── hover_help.py      # 2 s tooltip
│       │   ├── labels.py          # catalog labels
│       │   ├── highlight.py       # transient ROI highlight ("Ver local"; never paints the ROI)
│       │   └── qt_app.py          # ensure_app (single QApplication)
│       │
│       └── assets/icons/          # icons (used in the bundle)
│
├── tests/                         # unit tests (default) + integration marker (opt-in)
├── scripts/
│   ├── step1_absolute_roi.py      # validation ladder (capture)
│   ├── step2_anchored_roi.py      # validation ladder (anchoring)
│   ├── step3_selection_overlay.py # validation ladder (overlay)
│   ├── probe_dpi.py               # DPI matrix
│   └── build_release.py           # installer build (target OS)
├── packaging/
│   ├── screen-watch.spec          # PyInstaller (2 EXEs, onedir)
│   ├── make_ico.py                # generates the .ico from the PNGs
│   ├── windows/                   # .iss (Inno Setup), install-tesseract.ps1, tesseract.json
│   └── linux/                     # control.template, launcher.template, .desktop, postinst
└── .github/workflows/             # ci.yml (matrix) and release.yml (tag -> Release)
```

---

## 5. Platform boundary (`platform/`)

### 5.1 DPI awareness — mandatory and first

**Rule**: `set_dpi_awareness()` must be called **before** instantiating any capture backend,
any Qt window, any call to `pywinctl`. In the implementation, it is the first executable
line of `main()` in `__main__.py` (and of the GUI entry point).

```python
# platform/dpi.py
import ctypes, sys, os

def set_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()

def is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
```

**Reason**: without this, `pywinctl` (logical) and `mss` (physical) disagree at scales != 100%, and
the ROI "slips" silently. It is the most expensive bug to debug if discovered late.

**Result measured in the implementation**: with `set_dpi_awareness()` at the start, `pywinctl` and
`mss` stay in the **same physical space** (`pywinctl == GetWindowRect` in 15/15 windows measured).
That is why the `resolver` uses the identity converter and there is **no drift** in the monitoring
path, even on a scaled monitor (e.g., 125%). Qt's `device_pixel_ratio` (`1.25` on the primary) belongs
to Qt's logical space — used only at the Qt boundaries: the select overlay, the mouse locator and the
ROI highlight (§9.5).

When starting `run`, the app checks each monitor, marks the suitable ones (`OK`, 100%) and warns if
the target window is on a scaled monitor. `probe-dpi` and `scripts/probe_dpi.py` print the matrix.

**Wayland**: if `is_wayland()` returns `True`, `run` displays a clear message and exits (code 2).
Do not attempt to capture.

### 5.2 Window wrapper (`platform/window.py`)

Encapsulate `pywinctl` so that the rest of the code never imports `pywinctl` directly.

Implemented interface:

```python
@dataclass(frozen=True)
class WindowInfo:
    handle: int
    title: str
    rect: tuple[int, int, int, int]   # (x, y, w, h) in logical space
    is_minimized: bool
    exists: bool

def find_window_by_handle(handle: int) -> WindowInfo | None: ...
def list_windows() -> list[WindowInfo]: ...
def activate_window(handle: int) -> bool: ...   # used by the actions (activate)
def is_window_active(handle: int) -> bool: ...  # action focus confirmation
```

**Rules**:
- Always identify by `handle`. Title is only a `title_hint` for display, never a lookup key
  (it changes in browsers, IDEs).
- If `is_minimized` is `True`, the `rect` is garbage — the resolver returns `None` and the loop emits
  `target_unavailable` (§7.2).
- In the GUI, `list_windows()` filters out windows that are not from active applications (invisible,
  hidden by DWM, tool windows, child/auxiliary, untitled) and displays the **application name** in Task
  Manager style (`FileDescription`/`ProductName`, with fallback to the `.exe` name).

### 5.3 Other OS ports (implemented)

| Module | Responsibility |
|---|---|
| `platform/paths.py` | `app_home()`, `config_path()`, `selections_dir()`, `logs_dir()`, `state_path()`; `SCREEN_WATCH_HOME` override; Python MSIX/Store detection (uses the package's real path, visible outside it); `load_state`/`update_state` (atomic, no backup). |
| `platform/display.py` | per-monitor scale: `mss` (physical) × Qt (logical) × DPR matrix, used by the monitor warning and by `probe-dpi`. |
| `platform/tesseract.py` | `resolve_tesseract_cmd(configured)`: explicit path > `PATH` > common OS directories (never a hardcoded machine path). |
| `platform/audio.py` | single port for playing sound: `winsound` on Windows (with `MessageBeep()` when there is no WAV), external players on Linux/macOS (`paplay`/`aplay`/`ffplay`/`afplay`); `probe` for `features`. |
| `platform/input.py` | `pynput` **imported on demand** (`input` extra); pure helpers `interpolate_points`/`make_rng` (testable without a display) for action humanization. |
| `platform/shell.py` | `open_path()`: `os.startfile` on Windows, `open`/`xdg-open` on the others; returns `False` with `log.warning` when there is no association (the GUI shows "open manually: <path>"). |

**Rule**: no other package may import `pynput`, `winsound`, `mss` or `pywinctl` directly.

---

## 6. `Frame` contract

Canonical definition. Any comparison strategy consumes only this.

```python
# capture/frame.py
from dataclasses import dataclass
import numpy as np

Rect = tuple[int, int, int, int]          # (x, y, w, h) in physical space

@dataclass(frozen=True)
class Frame:
    rgb: np.ndarray                     # (H, W, 3) uint8, RGB order
    timestamp: float                    # time.time()
    absolute_rect: Rect                 # physical space (for mss/debug)
    window_rect: Rect                   # logical space (for debug and ref=window)
    window_handle: int
    sequence: int                       # increments on every successful tick
```

**Invariants**:
- `rgb.shape[2] == 3` and `dtype == np.uint8` (the backend already delivers RGB; the loop normalizes and
  ensures contiguity).
- `rgb` is already masked (see §8).
- `sequence` is monotonic per monitoring session; used to discard stale frames if the
  consumer falls behind.

---

## 7. Capture chain — detailed operation

### 7.1 Selection phase (once, per ROI)

Exact order of steps:

1. The user chooses the **target window** (`list_windows()` in the CLI, or the GUI/"New Target" list).
2. The overlay is displayed (see §9); overlay-free alternative: `select-manual` with `--roi X Y W H`.
3. The user drags the rectangle (or passes the coordinates).
4. On release, the overlay emits a `QRect` in **global logical coordinates**.
5. **Immediately** query `window.getRect()` → `origin_at_selection`.
6. Convert the global logical rect → rect relative to the window: `roi_relative = global_rect − origin_at_selection`.
7. Persist JSON v2 (§7.3), with `app_name` (friendly executable name) and, when present,
   `overrides`.

**Critical rule**: step 5 must happen before any I/O, log, or processing. The window
can move between `mouseRelease` and persistence.

### 7.2 Tick phase (loop)

```
┌─────────────────────────────────────────────────────────┐
│ 1. Resolve window (handle → WindowInfo)                 │
│    - if it does not exist: emit target_unavailable      │
│      (reason: not_found), wait                          │
│    - if minimized: emit target_unavailable              │
│      (reason: minimized), wait                          │
│    - if ROI out of bounds: target_unavailable           │
│      (reason: roi_out_of_bounds), wait                  │
├─────────────────────────────────────────────────────────┤
│ 2. Resolve absolute ROI                                 │
│    abs = roi_relative + window_rect.topLeft()           │
│    - logical→physical conversion (identity by default)  │
├─────────────────────────────────────────────────────────┤
│ 3. Clip against the backend's virtual desktop           │
│    - clipped: capture_clipped (event)                   │
│    - 100% outside: roi_off_screen (event); skip tick    │
├─────────────────────────────────────────────────────────┤
│ 4. Capture (mss, instance created in the loop thread)   │
├─────────────────────────────────────────────────────────┤
│ 5. Normalize (shape (H, W, 3), uint8, contiguous)       │
├─────────────────────────────────────────────────────────┤
│ 6. Apply mask                                           │
├─────────────────────────────────────────────────────────┤
│ 7. Emit Frame to the sink (sequence++)                  │
└─────────────────────────────────────────────────────────┘
```

**`_tick` contract**: returns `Frame | None`. `None` means "nothing to process on this tick", and the
`sink` **is not called**.

**Loop events** (emitted by `on_event`, deduplicated by consecutive name):
`target_unavailable` (with `reason`), `capture_clipped` and `roi_off_screen` (§7.6).

### 7.3 Selection JSON schema

Current version (**v2**):

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
  "overrides": { "poll_interval_s": 1.5, "rearm": false }
}
```

Required fields: `version`, `window_handle`, `origin_at_selection`, `roi_relative`.
`app_name`, `name`, `mode`, `masks` and `overrides` are optional with defaults. `version: 1`
selections still load without `overrides`/`app_name`/`name` (§12.3). `window_title_hint` is only a
human hint; the lookup uses `window_handle`. `roi_relative` is the source of truth for reconstructing
the ROI on each tick. `name` is the display name (shown as a prefix in the GUI label and in `run`);
the **file name** is the slug of the name (`naming.slugify`), which is what `--selection` uses.

**Headless lifecycle (v0.9.0)**: the whole selection lifecycle is CLI-driven, with no overlay:
`list-windows` → `select-manual --handle H --roi X Y W H [--name N]` → `edit-selection N ...`
(mode/ROI/masks/overrides) → `validate-config --selections` → `run --selection N`. `list-selections`
lists the files and `--json` emits the scriptable form; `rename-selection OLD NAME` reuses
`plan_rename`/`rename_selection`; `remove-selection NAME...` deletes and clears `state.json` when
`last_selection` pointed to a removed file. `edit-selection` writes atomically (`dump_selection`) and
follows the same rules as the GUI: `--mode` updates `overrides.mode` when it exists, else `mode`;
`--roi` re-anchors `origin_at_selection` and clears **both** mask fields (relative to the old ROI);
`--mask` uses the effective-location rule (`set_masks`); `--clear-masks` empties both fields;
`--poll-interval-s`/`--rearm` write into `overrides`; `--clear-override KEY` removes one of the five
override keys. Errors are English, exit code 1 (2 for a missing edit option), and the file is left
untouched on failure.

### 7.4 Capture loop — implemented skeleton

```python
def _run(self) -> None:
    backend = self.backend or self.backend_factory()   # mss is NOT thread-safe: create it in the thread
    try:
        while not self._stop.is_set():
            t0 = time.perf_counter()
            frame = None
            try:
                frame = self._tick(backend)
            except Exception as exc:
                self._error(exc)                        # deduplicates identical consecutive errors
            if frame is not None:
                try:
                    self.sink(frame)                    # sink OUTSIDE the capture try
                except Exception as exc:
                    self._error(exc)
            elapsed = time.perf_counter() - t0
            self._stop.wait(max(0.0, self.interval_s - elapsed))
    finally:
        backend.close()
```

**Built-in decisions** (do not change without justification):
- `_stop.wait` is the only sleep. Never `time.sleep` inside the loop.
- The work time is subtracted from the interval.
- Exceptions in `_tick` **and in the sink** do not break the loop (there is a separate `try` for each).
- The `sink` (comparison) is outside the capture `try` — capture and comparison are separate
  responsibilities.
- The backend is created and closed **in the loop thread** (`mss` is not thread-safe).
- Identical consecutive failures (same message) are reported **once**; they reappear if they change.

### 7.5 Occluded window limitation

`mss` captures **screen pixels**, not the window surface. If another window covers the ROI, the
captured frame will contain the content of the overlapping window. **This is not a bug to be
fixed** — it is a fundamental limitation of the available APIs. Documented in the README and the Wiki.

### 7.6 Loop robustness (Stage H)

- **Negative/off-screen coordinates**: the ROI is clipped against the virtual desktop
  (`mss.monitors[0]`, via `bounds()` + `intersect_rect`). When clipping occurs, the loop emits
  `capture_clipped`; when the ROI falls 100% outside, it emits `roi_off_screen` and **skips the
  tick** — without breaking the loop.
- **Repeated failures**: deduplicated by message (e.g., Tesseract missing, token missing).
- **Stop**: `stop()` signals the event and performs `join`; `backend.close()` runs in the
  worker's `finally`.
- **DPI**: `probe-dpi`/`scripts/probe_dpi.py` print the matrix (physical mss × logical Qt × scale).

---

## 8. Mask

### 8.1 Format

List of rectangles `[x, y, w, h]` **relative to the ROI** (not absolute, not relative to the window).
They survive moving the window. They come from `selection.masks` or `overrides.masks` (§12.3).

### 8.2 Application

```python
def apply_mask(rgb: np.ndarray, masks: list[tuple[int, int, int, int]]) -> np.ndarray:
    out = rgb.copy()
    for (x, y, w, h) in masks:
        out[y:y+h, x:x+w] = 0
    return out
```

- Paints **black (0,0,0)**.
- **Reason**: phash and mean color treat black neutrally. For OCR, black is acceptable in the
  prototype (it does not generate ghost text).
- **Application point**: stage 6 of the capture chain, **before** the `Frame` is emitted. The
  strategies never see the mask.

### 8.3 Typically masked regions

Cursor, loading spinner, clock, network indicator, anything that blinks.

**Visual mask editor (v0.8.0)**: the GUI has an **Edit masks…** button (Selections group) that opens a
transparent overlay per monitor over the target window. Drag with the left button **adds** a mask;
right-click over an existing mask **removes** it; **Enter confirms** (writes the selection JSON) and
**Esc cancels** (no write). Masks stay ROI-relative physical pixels, so they survive moving the
window. The editor is **blocked while a session is running** (same rule as rename) because the ROI is
being measured; unlike Highlight (pitfall 23), this overlay is modal and may paint over the ROI
precisely because monitoring is stopped. It writes where the effective masks currently live (§12.3)
and the write is atomic (§12.4). The geometry (ROI in screen-local logical space, drag → mask, clamp,
hit-test) lives in the pure module `gui/mask_editor_geometry.py`; the Qt overlay is
`gui/mask_overlay.py::run_mask_editor`.

---

## 9. Selection overlay (PyQt6)

### 9.1 Multi-monitor strategy

**Decision**: **one window per monitor**, not a single window covering `virtualGeometry`.

**Reason**: with mixed DPI between monitors, a single window forces Qt to map a single framebuffer
to distinct scales — behavior varies per platform. One window per screen simplifies the calculation
(each one operates in the space of its own `screen`).

```python
overlays = []
for screen in QGuiApplication.screens():
    ov = SelectionOverlay(screen)
    ov.setGeometry(screen.geometry())
    ov.show()
    overlays.append(ov)
```

At the end of the drag on an overlay, the rect is converted to global by adding `screen.geometry().topLeft()`.
The pure conversions live in `gui/overlay_geometry.py` (no Qt, testable).

### 9.2 Flags and attributes

```python
self.setWindowFlags(
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
)
self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
self.setCursor(Qt.CursorShape.CrossCursor)
```

### 9.3 Drawing the selection "hole"

Use `QPainter.CompositionMode.CompositionMode_Clear` to remove the dark mask in the
selected area. **Do not use `setMask`** — it is slow and problematic with DPI.

```python
painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
if self._origin and self._current:
    r = QRect(self._origin, self._current).normalized()
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.fillRect(r, Qt.GlobalColor.transparent)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.setPen(QPen(QColor("#0052d6"), 2))
    painter.drawRect(r)
```

### 9.4 High DPI in Qt

Before creating `QApplication`:

```python
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)
```

**Reason**: prevents factors such as 1.25 from being rounded to 1.0, which misaligns the overlay with
`mss`.

### 9.5 Logical → physical conversion

The Qt `QRect` is in **logical** space. `mss` consumes **physical** space.

```python
def to_physical(rect: QRect, screen) -> tuple[int, int, int, int]:
    dpr = screen.devicePixelRatio()
    offset = screen.geometry().topLeft()
    x = int((rect.x() - offset.x()) * dpr + offset.x() * dpr)
    y = int((rect.y() - offset.y()) * dpr + offset.y() * dpr)
    return (x, y, int(rect.width() * dpr), int(rect.height() * dpr))
```

**Note**: with `SetProcessDpiAwareness(2)` + `PassThrough`, in many cases `dpr == 1.0` and the conversion
is the identity. **Do not assume that** — test at 125%, 150%, 200%.

The same anchoring applies to **points** and to the **reverse direction** (pure helpers in
`gui/overlay_geometry.py`, tested without display): `point_to_physical` (mouse locator —
`QCursor.pos()` is logical, the runner/`pynput` is physical; anchored on the monitor under the cursor
via `screenAt`), `point_to_logical` and `rect_to_logical` (ROI highlight "Ver local" — the rect comes
from the physical path and Qt paints logical). **Rule**: every Qt ↔ physical boundary converts
**exactly once**, anchored on the monitor origin; the select overlay, the mouse locator and the
highlight are the only Qt boundaries (v0.10.1).

### 9.6 Post-drag validation

Before persisting:

1. **Minimum area**: reject rectangles smaller than 10×10 logical pixels (`MIN_ROI_SIDE = 10`).
2. **Inside the target window**: convert to relative and check with `fits_in_window`. If it
   extrapolates (x/y < 0 or x+w/y+h beyond the window), **reject** with `runtime.roi_outside_window`
   and do not persist — a ROI outside the window would make the tick capture a region unrelated to
   the target (e.g., another monitor), producing prints/alerts that do not match the window.
   *(Changed from "allow but log a warning" — the old behavior silently produced wrong prints.)*
3. **Origin captured before I/O**: see §7.1.

---

## 10. Comparison — interface and strategies

### 10.1 Protocol

```python
from typing import Protocol, Any
from dataclasses import dataclass

@dataclass(frozen=True)
class ComparisonResult:
    changed: bool
    score: float
    threshold: float
    strategy: str
    severity: int = 0                 # 0..3; computed at the end of the pipeline when it is 0
    detail: dict[str, Any] | None = None

def compute_severity(score: float, threshold: float) -> int:
    """score/threshold >= 3.0 -> 3; >= 2.0 -> 2; >= 1.0 -> 1; otherwise 0."""

class CompareStrategy(Protocol):
    name: str
    def initialize(self, baseline: Frame) -> None: ...
    def compare(self, current: Frame) -> ComparisonResult: ...
```

**Rules**:
- `compare` is a **pure function** over the `Frame` (it may read internal state, but no I/O, no sleep,
  no capture).
- `initialize` is called once per session with the first frame (baseline); it is also re-called on
  re-arm (§11.3) and on manual re-baseline.
- `changed` always in the same sense (True = change detected). For OCR, which naturally produces
  similarity, normalize before exposing.
- `severity` (0..3) feeds the `severity_min` of alerts and actions; when a stage does not define it,
  the pipeline computes `compute_severity(score, threshold)` in the final verdict.

### 10.2 Light strategy — `MeanColorStrategy`

```python
class MeanColorStrategy:
    name = "light"
    def __init__(self, threshold: float = 12.0):
        self.threshold = threshold
        self._baseline_mean = None

    def initialize(self, baseline: Frame) -> None:
        self._baseline_mean = baseline.rgb.mean(axis=(0, 1))

    def compare(self, current: Frame) -> ComparisonResult:
        current_mean = current.rgb.mean(axis=(0, 1))
        delta = float(np.linalg.norm(current_mean - self._baseline_mean))
        return ComparisonResult(
            changed=delta > self.threshold,
            score=delta, threshold=self.threshold, strategy=self.name,
        )
```

- `threshold=12.0` is an empirical starting point (0–255 scale).
- If there is JPEG compression in the pipeline, raise it to 20–25.
- **Do not use** for textual or fine structural content.

### 10.3 Default strategy — `PerceptualHashStrategy`

```python
class PerceptualHashStrategy:
    name = "default"
    def __init__(self, hash_size: int = 8, threshold: int = 6):
        self.hash_size = hash_size
        self.threshold = threshold
        self._baseline_hash = None

    def initialize(self, baseline: Frame) -> None:
        img = Image.fromarray(baseline.rgb)
        self._baseline_hash = imagehash.phash(img, hash_size=self.hash_size)

    def compare(self, current: Frame) -> ComparisonResult:
        img = Image.fromarray(current.rgb)
        h = imagehash.phash(img, hash_size=self.hash_size)
        dist = int(self._baseline_hash - h)
        return ComparisonResult(
            changed=dist > self.threshold,
            score=float(dist), threshold=float(self.threshold),
            strategy=self.name,
        )
```

- `hash_size=8` (64 bits) is the default.
- Typical `threshold`: 4–10. Start with 6.
- **Small ROIs (< 100×100)**: phash becomes unstable. Consider `hash_size=6` or switching to Light.
- **`hash_size=16`**: more sensitive, more expensive, jumpier with anti-aliasing. Do not use it as
  the default.

### 10.4 Advanced strategy — `OCRTextDiffStrategy`

```python
class OCRTextDiffStrategy:
    name = "advanced"
    def __init__(self, similarity_threshold: float = 0.92,
                 psm: int = 6, lang: str = "por+eng", upscale: int = 2,
                 tesseract_cmd: str | None = None):
        ...
        self._tesseract_cmd = resolve_tesseract_cmd(tesseract_cmd)  # platform/tesseract.py
        self._baseline_text = ""

    def _extract(self, rgb: np.ndarray) -> str:
        # without the binary: AppError(code="runtime.tesseract_missing") with a clear message
        # upscale > 1: nearest-neighbor (np.repeat), without depending on cv2
        # sets/restores pytesseract.pytesseract.tesseract_cmd (does not leak between instances)
        ...

    def compare(self, current: Frame) -> ComparisonResult:
        ratio = difflib.SequenceMatcher(None, self._baseline_text, current_text).ratio()
        score = 1.0 - ratio          # normalized: high = changed
        threshold = 1.0 - self.similarity_threshold
        return ComparisonResult(changed=score > threshold, score=score,
                                threshold=threshold, strategy=self.name,
                                detail={"baseline_text": ..., "current_text": ...})
```

- Implementation defaults: `similarity_threshold=0.92`, `psm=6`, `lang="por+eng"`,
  `upscale=2`. The text is normalized (`" ".join(txt.split())`).
- `upscale` uses **pixel repetition** (`np.repeat`) — enough for a small ROI and without the
  optional dependency on `cv2` (the `ocr-preproc` extra brings `opencv-python` for experiments, but
  it is not required by the default path).
- **Tesseract path**: resolved behind `platform/tesseract.py` (explicit > `PATH` >
  common directories). Never use `TESSDATA_PREFIX` — the `tessdata` comes from the binary.
- **Recommended preprocessing for difficult ROIs** (future extensions): grayscale +
  Otsu, `image_to_data` for scattered text; measure with `compare-modes` before changing defaults.
- **Performance**: OCR takes 100–500 ms per call. In `advanced` mode it **is** the detector (it runs
  on every tick); that is why it is not combined with OCR at 1 Hz — the default interval is 2 s.

**Text watch (`compare/text_watch.py::TextWatchStrategy`, optional)**:

```python
class TextWatchStrategy:              # wraps OCRTextDiffStrategy in advanced mode
    name = "advanced"
    def initialize(self, baseline):   # OCR of the baseline; stores present_before
    def compare(self, current):       # changed = expected presence transition (severity=3)
                                      # detail = {baseline_text, current_text, ocr_score,
                                      #           ocr_threshold, text_watch: {...}}
```

- **Filter semantics**: with a `text_watch` configured (`compare_options.advanced.text_watch` in the
  profile or `overrides.text_watch` in the selection, which takes precedence), the alert fires
  **only on the configured transition** (`expect: appears|disappears`); other text changes do not.
  The `changed` from the OCR is **not** propagated — only the watch verdict is authoritative — and the
  OCR `score`/`threshold` stay in the `detail` (visible in `compare-modes`).
- **Matching**: substring, `case_sensitive: false` and `ignore_accents: true` by default
  (NFKD + diacritics removal on both sides). `text` is required (non-empty).
- **Severity = 3** on the transition (definitive event): a severity derived from the OCR score could
  stay below `severity_min` and the alert would fail silently.
- **Presence state follows the stream** (edge filter): a transition fires once; re-arm/re-baseline
  recomputes the baseline presence, so the state never desyncs.
- **Only `advanced`** (`config.text_watch_needs_advanced` elsewhere); the GUI clears the override
  when the mode changes.
- Because it decides `changed`, the **actions also run only on the transition**.

### 10.5 Pipeline with short-circuit

```python
MODE_STAGES: dict[str, tuple[str, ...]] = {
    "light": ("light",),
    "default": ("default",),
    "advanced": ("default", "advanced"),  # phash gate: OCR only runs when the pixels changed
}

class ComparePipeline:
    def compare(self, current: Frame) -> ComparisonResult:
        last = self.stages[0].compare(current)
        for stage in self.stages[1:]:
            if not last.changed:
                return last        # the first stage that returns False ends the pipeline
            last = stage.compare(current)
        if last.changed and last.severity == 0:
            last = replace(last, severity=compute_severity(last.score, last.threshold))
        return last
```

**Recorded decision (updated)**: `advanced` runs `("default", "advanced")` — the phash runs **before**
the OCR as a *pixel gate*: the OCR only runs/scores when the pixels changed, which cut repeated false
positives on near-identical frames (the OCR noise on static screens). **With a `text_watch`
configured, the gate is bypassed** (`build_pipeline` builds `("advanced",)`): the OCR runs on every
tick and the watch verdict (presence/absence, not similarity) is authoritative, so the transition is
never hidden by the gate; the accepted cost is OCR per tick (100–500 ms, default interval 2 s). The
short-circuit mechanism remains implemented and tested for other compositions (e.g.
`[MeanColor, PerceptualHash]` as a "strict" mode).

**Rule**: the first stage that returns `changed=False` ends the pipeline. The final verdict is from the
last stage that ran, with `severity` computed when absent.

### 10.6 Initial state

**Non-negotiable rule**: the first frame is **baseline**, not change. The pipeline is initialized
with it via `initialize`, and `compare` is only called from the **second** frame onward. The same
applies after re-arm/re-baseline: the frame that re-initializes does not generate an alert.

---

## 11. Alerts

### 11.1 Protocol

```python
class Notifier(Protocol):
    name: str
    enabled: bool
    severity_min: int
    cooldown_s: float

    def notify(self, result: ComparisonResult, frame: Frame) -> None: ...
```

**Rules**:
- `severity_min`: the notifier only fires if the change severity is >= this value.
- `cooldown_s`: after **attempting** to fire, the notifier is silenced for N seconds,
  regardless of new changes (including on failure — backoff, see §11.3). The key is the alert **`id`**
  (`uid`), not the notifier class name (§11.2).
- `frame` is passed complete to allow attaching the ROI image (Telegram) or logging context.

### 11.2 Prototype notifiers

**Sound (`sound.py`)**:
- All playback goes through the `platform/audio.py` boundary; `alerts/` does **not** know
  `sys.platform`, Qt or miniaudio.
- **Layers** (dispatch order): **Qt** (`QMediaPlayer`/QtMultimedia, created on the GUI thread via
  `install_qt_player()`; playback queued with `QueuedConnection`, so the monitor-loop thread never
  touches Qt) → **miniaudio** (core dependency; CLI/`run`; runs on a **daemon thread**, WAV/MP3/OGG/
  FLAC, no AAC/M4A) → **legacy** (`winsound`, WAV only; `paplay`/`aplay -q`/`ffplay`/`afplay`).
- Format matrix by context: GUI on Windows/macOS (Media Foundation/AVFoundation) plays M4A/AAC; on
  Linux the GUI depends on the GStreamer plugins; the CLI relies on miniaudio (M4A/AAC only through
  an external player, otherwise `beep`).
- A relative `file` is resolved by `platform/audio.py::resolve_sound_path` in this order:
  **`app_home()/sounds`** (user) → **`resources.bundled_sounds_dir()`** (`screen_watch/assets/sounds`,
  where the default `alert.mp3` lives) → **CWD**. An absolute `file` is used as-is; a user file always
  wins over the bundled one. Missing file or unsupported format → `beep()` + log warning (never
  silence/exception).
- **Default `"alert.mp3"`** (bundled): `AlertOptions.file`, the `loader.py` parse and `SoundNotifier`
  all default to `"alert.mp3"`. Existing configs with `alert.wav` (or any other path) are unchanged;
  the new default only applies to new configs or when the user edits the line.
- Optional `simpleaudio` extra (`pip install -e ".[sound]"`); it does **not** go into the installers
  (no reliable wheel for Python 3.13) and is only tried for WAV.
- **Do not use** `playsound` (abandoned).
- **Sound picker writes back to the YAML (v0.8.0)**: after choosing a file, the GUI asks for
  confirmation and writes `file:` into the first alert with `type: sound` of the **active profile**
  via `config/loader.py::set_profile_sound_file`, creating the alert with the default shape when it
  is missing. `save_config` is atomic and keeps `config.yaml.bak`, so a write failure leaves the
  original file intact. Config v1 is refused (`config.v1_not_editable`) with a message pointing to
  `migrate-config`. When the selected target has `overrides.alerts`, that override replaces the
  profile alerts, so the GUI warns (`dialog.sound_override_warning`) that the sound will not apply
  to it.

**Popup (`popup.py`)**:
- Library: `plyer.notification`.

**Telegram (`telegram.py`)**:
- Sent via `httpx` to `https://api.telegram.org/bot<token>/sendPhoto` (with `attach_roi: true`,
  default) or `sendMessage`.
- **Attaches the ROI screenshot** at alert time — essential to validate false positives.
- Serializes `rgb` → PNG in memory (`PIL.Image.fromarray(...).save(buf, format="PNG")`).
- Short timeout (**5 s**) so as not to block the loop; token read from `bot_token_env`
  (`TELEGRAM_BOT_TOKEN` by default) — **never** in the YAML.
- **Sanitized errors**: HTTP failures become `TelegramAPIError` with Telegram's description
  (e.g. `chat not found`), without URL/token — `httpx` would include the token (which lives in
  the URL) in the error message, leaking it into the chain log.

**ntfy (`ntfy.py`, v0.9.0)**:
- Plain-text `POST {server}/{topic}` with headers `Title`, `Priority` (severity→1..5 mapping,
  default `1→3`, `2→4`, `3→5`) and optional `Tags`; `attach_roi: true` switches to an image `PUT`
  (`Filename: roi.png`, the `Message` header carries the rendered text).
- `token_env` is **optional** and empty by default (anonymous topic); when set to a variable name
  that is missing, the notifier logs and skips (same rule as Telegram). Errors
  (`alert.ntfy_unavailable`, `alert.ntfy_status`) carry only the redacted server
  (`scheme://host/…`).

**E-mail / SMTP (`smtp.py`, v0.9.0)**:
- Stdlib `smtplib` + `email.message.EmailMessage`; `security` is `starttls` (default), `ssl` or
  `none`. `subject`/`message` are templates (same `${...}` rules, §11.2 webhook); `attach_roi`
  adds the ROI PNG as `image/png`.
- `host`, `from_addr` and a non-empty `to` list are required at config load. `username_env` /
  `password_env` (defaults `SMTP_USERNAME`/`SMTP_PASSWORD`) log in only when the user variable is
  set; secrets never appear in errors/logs.
- Errors: `alert.smtp_unavailable` (connect/TLS), `alert.smtp_auth_failed` (login),
  `alert.smtp_send_failed` (message rejected); server text is sanitized of credentials.

**MQTT (`mqtt.py`, v0.9.0)**:
- Optional extra `mqtt` (`paho-mqtt`); the import is lazy. A configured channel without the extra
  raises `alert.mqtt_missing_extra` (visible `FAILED`, never a silent skip).
- `host`/`topic` required; `port` defaults to 1883 (8883 when `tls`), `qos` 0/1/2, `retain`,
  `client_id`, `username_env`/`password_env` (same defaults as SMTP). The payload is a template
  mapping (default `text`/`target`/`severity`/`strategy`/`score`/`threshold`/`timestamp`) or
  `payload_raw`. **No image**.
- Errors: `alert.mqtt_unavailable` (connect), `alert.mqtt_publish_failed` (publish rejected).

**Log (`log.py`)**:
- `JsonlNotifier`: one JSON line per firing in `app-data/logs/alerts.jsonl` (or the path
  configured in `path`). Fields: `ts`, `strategy`, `changed`, `score`, `threshold`, `severity`,
  `window_handle`, `absolute_rect`, `sequence`, `detail`. The record has **no channel/target/evidence
  path**, so the v0.8.0 history filters date/severity/strategy and locates the print best-effort
  (nearest `*_change.png` within ±2 s — `alerts/history.py`).

**Webhook / HTTP POST (`http.py`)**:
- `post_json` does `POST`/`PUT`/`PATCH` JSON via `httpx`, redirects **not** followed, success = 2xx
  (non-2xx → `alert.http_status`; network failure → `alert.http_unreachable`).
- `WebhookNotifier` uses `url` or `url_env`; `HttpPostNotifier` also accepts `scheme`/`host`/`port`/
  `path`. Default payload `{"text": "${message}"}`; `payload_raw` sends a non-object body.
- **Payload template** (`alerts/template.py`): `string.Template` with `idpattern` extended for
  `${env:VAR}` (resolved from `os.environ` **at send time**); placeholders `message`, `strategy`,
  `score`, `threshold`, `severity`, `target`, `timestamp`, `window_handle`, `changed`, `roi`. An unknown
  placeholder is a config error (`config.alert_unknown_placeholder`).
- **Secrets**: the resolved URL is redacted (`scheme://host/…`) in errors/logs; `verify_tls: false`
  warns **on every send**.
- **No image/ROI** (attaching a print stays exclusive to Telegram).

**Syslog (`syslog.py`)**:
- `logging.handlers.SysLogHandler` to `(host, port)`; `socktype=SOCK_DGRAM` (udp, default) or
  `SOCK_STREAM` (tcp); `facility` default `local0`; `app_name` becomes the `ident`/tag; `append_nul=False`.
- `timeout=` on `SysLogHandler` only exists in Python 3.14, so `createSocket` is overridden to call
  `settimeout`; on Windows, use **UDP**.
- **Informational by default** (the real severity goes in the text via `${severity}`), with an optional
  `severity_map` (keys 0..3). UDP is *fire-and-forget* (it does not confirm delivery) → prefer TCP when
  delivery must be confirmed.

**`id` and cooldown key**:
- Every alert has an optional `id` (default `type`; `type#n` when repeated in the same profile,
  validated). `build_notifier` assigns `notifier.uid = id or type`; `AlertChain` uses
  `getattr(n, "uid", n.name)` as the cooldown key, so two webhooks do not share the cooldown.

**Rule**: an unknown `type` is a **config error** (`config.alert_unknown_type`) — `build_notifier` also
keeps a defensive `log.warning` + `None`.

### 11.3 Chaining, outcomes and re-arm

```python
class AlertChain:
    def __init__(self, notifiers, gate: AlertGate | None = None): ...
    def dispatch(self, result: ComparisonResult, frame: Frame) -> DispatchOutcome:
        # gate active (snooze/mute) -> SUPPRESSED_MANUAL (no notifier is tried)
        # no enabled notifiers -> NONE_ENABLED
        # none with severity >= severity_min -> BELOW_MIN
        # for each eligible one outside the cooldown: notify; a failure does not stop the others
        #   -> FIRED (some fired) / FAILED (all failed) /
        #      SUPPRESSED_COOLDOWN (all in cooldown)
```

**Outcomes** (`DispatchOutcome`): `FIRED`, `SUPPRESSED_COOLDOWN`, `SUPPRESSED_MANUAL`, `BELOW_MIN`,
`NONE_ENABLED`, `FAILED`. `MonitorSession` uses the outcome for the **edge-triggered re-arm**:

- With `rearm: true` (default), the baseline advances after `FIRED`, `BELOW_MIN` or `NONE_ENABLED` — a
  sustained change alarms once, and a new change re-arms.
- On `SUPPRESSED_COOLDOWN`, `SUPPRESSED_MANUAL` and `FAILED` the baseline is **kept**: the pending
  change alarms when the cooldown/snooze expires or the mute is lifted, and failures are retried
  respecting the cooldown (backoff) — without hammering on every tick.
- A failure in one notifier records the attempt (`_last_attempt`) and does not prevent the others;
  each has its own `try`.
- Manual re-arm: tray/"Re-arm baseline" button/hotkey `rearm`, via `MonitorSession.request_rebaseline()`
  (thread-safe) or `rebaseline_now(frame)`.

**Manual suppression (`AlertGate`, v0.9.0)**: a thread-safe gate shared by the sessions holds
`snooze_until` (epoch) and `muted`, initialized from `state.json` (`alerts_snooze_until`,
`alerts_muted`) and persisted on every GUI/tray change. While active, `dispatch` returns
`SUPPRESSED_MANUAL` before looking at the notifiers and the baseline is kept, so the pending change is
reported when the snooze expires or the mute is lifted. An explicit `test-alert` ignores the gate.
A snooze can outlive a transient change: if the screen returns to the baseline before it expires, the
pending change is dropped (documented risk of snoozing).

**Escalation (repeat until acknowledged, v0.9.0)**: `defaults.escalation` (or `overrides.escalation`)
has `enabled` (default false) and `severity_min` (default 2). With it enabled and a `FIRED` outcome at
`severity >= severity_min`, the baseline is **not** advanced; `MonitorSession.awaiting_ack` becomes
true and every following tick dispatches again — the repeat cadence is each alert's `cooldown_s`
(there is no separate escalation interval). `acknowledge()` (GUI button, tray item, optional
`ui.hotkeys.acknowledge`) clears the state and re-arms the baseline on the next frame, stopping the
repeats; manual `rearm` does the same. If the change disappears on its own the escalation still waits
for an explicit acknowledgement. Evidence: `record_change` is written **only when the chain actually
attempted a delivery** (`FIRED`/`FAILED`) — a change suppressed by cooldown/snooze/mute or below the
minimum no longer writes a print every tick (§11.5).

### 11.4 Pseudo-human actions (opt-in, `actions/`)

Reaction **separate** from the alerts: the `change` trigger is evaluated after `AlertChain.dispatch`
when `result.changed`, and the time triggers are evaluated on **every frame after the baseline**
(even without a change) — in both cases **without altering** the `DispatchOutcome` or the alert
re-arm. It only executes when **armed**; by default it stays in **rehearsal** (dry-run), which
records what it would do and saves evidence, without clicking. The time triggers have **no
rehearsal**: armed is the only state where they are evaluated.

- **Trigger (v0.10.0)**: exactly one per action, `when.trigger` = `change` (default) | `at` |
  `every` | `after`.
  - `change` keeps the previous semantics: `changed` (only `true` accepted; `changed: false` is a
    validation error), effective `severity_min` (`when.severity_min` > `severity_min`) and OCR
    filters (`text_any`/`text_all`/`text_regex`, case-insensitive by default). Text filters require
    `mode: advanced` (validation refuses in the other modes).
  - `at`: `at: ["HH:MM", ...]` (24 h) + optional `days` (3-letter names `mon`..`sun`, the same set as
    `schedule.days`; missing = every day). Fires when the time is **crossed while armed**; the
    crossing reference resets on arming, so times already passed that day do not fire.
  - `every`: `every_s >= 1`; the phase starts at arming and **restarts on each firing** (next due =
    firing + `every_s`); re-arming restarts the phase; no bursts and no catch-up after
    sleep/suspension (a due time older than the tolerance is recorded as `missed`).
  - `after`: `after_s >= 1`, single delay relative to arming; disarm cancels, re-arm restarts; fires
    once (`done` until the next arming).
  - Time triggers must not carry `change` fields (`changed`, `severity_min`, `text_*`,
    `case_sensitive`) and are rejected with `rebaseline: true`; `cooldown_s >= every_s` is an error
    for `every`. Occurrences later than **60 s** (tolerance/grace) become
    `skipped -> missed` in `logs/actions.jsonl` and are never executed; the naive local clock used
    by `at` means DST can double or lose a firing (documented limitation). The evaluator is the pure
    `actions/triggers.py` (injectable clocks; `at` uses wall time, `every`/`after` the monotonic
    arming clock from `ArmingController.armed_since`).
- **Steps**: `activate`/`click`/`move`/`type`/`key`/`wait`; `ref` is `roi` (relative to
  `frame.absolute_rect`), `window` (`frame.window_rect`) or `screen`. A click requires `activate`
  before it (explicit focus + `isActive` verification). Since Windows `SetForegroundWindow` is
  asynchronous/blocked (foreground lock), focus is confirmed with small pauses (up to ~0.5 s before
  aborting); the reason distinguishes `activate refused` from `focus not confirmed`
  (`focus_changed: ...`).
- **Humanization** (`defaults.humanize`, §12.2): mouse movement interpolated over `mouse_steps`
  points with `jitter_px`; pauses with `wait_jitter_ms` jitter; typing with a default interval of
  `key_interval_ms`; `seed` for deterministic tests.
- **Cooldown**: a trigger ignored due to `cooldown_s` (change or time) does **not** go to the JSONL
  (so as not to pollute it), but is published in the live log as `skipped -> cooldown`.
- **Limits**: `max_per_min` (60 s sliding window) and `max_per_session`, checked before execution
  (`reason: rate_limited` in the result/audit).
- **Synchronous execution on the loop thread**: capture/comparison pause during the sequence
  (no re-entrancy); `settle_s` at the end. Between steps, the runner re-checks arming/abort.
  `on_tick` runs on the same thread; the loop caps its wait by the next armed deadline
  (`ActionDispatcher.next_deadline_delay()`, §3.5) so a punctual `at` fires on time.
- **Re-arm**: `rebaseline: false` by default (the baseline remains after the action); `rebaseline: true`
  opt-in repeats the trigger (report/page). Manual re-arm at runtime (tray/button/hotkey `rearm`,
  via `MonitorSession.request_rebaseline()`).
- **Rehearsal x armed**: `ArmingController` with `disarmed`/`armed`/`timed` states; state only in
  memory, it starts disarmed on every session. `Esc` aborts immediately (`aborted`). Time triggers
  are not evaluated while disarmed (state reset on the next arming; `armed_since` restarts the
  phase/crossing reference).
- **Scheduler (suspension gate)**: outside the time window the action is suspended
  (`suspended_schedule`); for time triggers the due occurrence is **consumed** by the suspension (no
  replay when the window reopens). Monitoring and alerts continue. `schedule` never fires anything:
  firing is decided solely by `when.trigger`.
- **Auditing**: `logs/actions.jsonl` (rehearsal, execution, suspension, `missed`, reason, duration
  and paths of the evidence). Every record carries `trigger` (`change`/`at`/`every`/`after`).
- **Creation via the GUI**: `gui/action_editor.py` (`New action...`/`Edit...`/`Remove action`) writes
  to `overrides.actions` of the selection JSON, including the v0.10.0 trigger selector (`change`
  keeps the when/severity fields; `at`/`every`/`after` show only their own fields). Since
  `resolve_actions` reads the overrides before the profile, this also works with config v1
  (`targets:`), without migration. Validation reuses `parse_actions` (click requires `activate`,
  `text_*` requires `mode: advanced`, time-trigger rules included), so the YAML rules apply in the
  window; profile/YAML actions are read-only in the GUI.
- **Position locator**: `gui/locator.py::run_locator` ("Locate mouse
  position..." button in the `click`/`move` steps) shows a box following the cursor; Enter/left click
  confirms, Esc/right click cancels. It returns the **logical** global point (same base as the `Frame`)
  and converts it by the `ref` via `overlay_geometry.resolve_ref_point` (`roi`→`absolute_rect`,
  `window`→`window_rect`, `screen`→origin); without a base, it falls back to `screen`. It differs from
  the countdown: here focus is required to capture the Enter.
- **Per-session selection**: checklist in the GUI (and `--actions` in the CLI, one-shot) reduces the
  subset by **action name**; it applies only on the next `build_target`. The state lives in
  `state.json["action_selection"][selection]` (missing key = all, empty list = none).
  `resolve_actions` keeps the OCR/mode validation; the filter only subtracts names (it never
  re-enables `enabled: false`).
- **Live log**: each trigger emits an ephemeral payload (`ActionDispatcher.on_event` →
  `MonitorSession.on_action` → `kind: "action_event"` in the GUI queue, distinct from `action` =
  tray/hotkey commands); the source of truth remains the JSONL. Payloads carry `trigger`.
- **3s countdown**: one-off flows (`test-action --armed`, `record-actions` and the "Execute
  action (3s)" button in the GUI) use `gui/countdown.py::run_countdown` — a borderless, always-on-top
  Qt overlay with `WindowDoesNotAcceptFocus`, **without** `activateWindow` (the target window may be
  focused during the countdown); a click cancels. Instantiated by `gui/qt_app.py::ensure_app` with
  `QEventLoop` (callable from inside the GUI). The loop's automatic firing **has no** countdown.
  Textual fallback in the console without Qt/display. One-off flows ignore the action trigger
  (explicit run) and print a notice (`trigger <t> ignored (explicit run)`); `record-actions` keeps
  generating the commented `when` (change) plus a commented hint of the time-trigger fields.
- **Backend**: `pynput` as an optional extra (`pip install -e ".[input]"`), lazy import in
  `platform/input.py`; without it, hotkeys fall back to tray-only and real execution fails with a
  clear message (`InputUnavailable`). Wayland/elevation remain out of scope.

### 11.5 Evidence (prints)

Output subsystem, like the alerts: it saves **prints of the whole window** (unmasked) of the baseline
and of each detected change, for visual auditing.

- **Format/folder**: `<folder>/<target>/<YYYYMMDD-HHMMSS-mmm>_<baseline|change>.png` (actions use
  `_action`/`_action-<step>`). Writing is **synchronous** (called by the loop/session); failures only
  `log.warning` and never break the loop. The effective folder is
  `evidence.dir` when configured; otherwise `%TEMP%/screen_watch/captures`
  (`platform.paths`/`evidence.recorder.captures_dir`, displayed in `show-paths` as `captures:`).
- **Retention**: `keep_per_target` (count per target) and `max_total_mb` (total cap), pruned after
  each write.
- **On/off**: `evidence.enabled` in the YAML v2 **or** the runtime toggle
  `state.json["evidence_enabled"]` ("Record prints" checkbox in the GUI), which has **precedence** and
  also works with config v1. `app.effective_evidence_options()` does the composition.
- **Change prints are tied to delivery attempts (v0.9.0)**: `record_change` runs only when the chain
  outcome is `FIRED`/`FAILED`; a change kept pending by cooldown/snooze/mute/below-min does not write
  a print per tick (baseline prints are unchanged). During escalation the prints follow each firing.
- **One-off flows**: `test-evidence` and the `run_actions` path (`test-action --armed` and the
  "Execute action (3s)" button) record with `force_enabled=True`, respecting `per_step` (print per step)
  and registering the paths in the action audit.
- **Open folder/file**: always goes through `platform/shell.py::open_path`; the GUI warns when the
  loop prints are off.

---

## 12. Configuration

### 12.1 YAML v2 schema (global config per profile)

The YAML is no longer a list of targets and became **global configuration**. Targets live in JSON
selection files (`app-data/selections/*.json`); the YAML defines profiles, alerts, hotkeys,
scheduler, humanization and evidence.

```yaml
version: 2
profile: default                 # active profile; switchable with --profile / GUI selector
profiles:
  default:
    defaults:
      mode: "advanced"           # "light" | "default" | "advanced"
      poll_interval_s: 2.0       # minimum 1.0
      rearm: true
      humanize:                  # pseudo-human noise of the actions (§11.4)
        mouse_steps: 24
        key_interval_ms: 60
        jitter_px: 3
        wait_jitter_ms: 150
        seed: null               # only for deterministic tests
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
      - type: webhook                    # Teams Workflows / Slack / Discord / Mattermost…
        id: teams
        severity_min: 2
        cooldown_s: 60
        options: { url_env: TEAMS_WEBHOOK, payload: { text: "Change on ${target} sev=${severity}" } }
      - type: http_post
        id: erp-api
        options: { scheme: http, host: "10.0.0.20", port: 8080, path: "/alerta" }
      - type: syslog
        id: siem
        options: { host: "10.0.0.9", port: 514, protocol: udp, facility: local0 }
      - type: ntfy                     # phone push (v0.9.0)
        id: celular
        options: { server: "https://ntfy.sh", topic: "meu-topico-secreto",
                   token_env: NTFY_TOKEN, priority_map: { 1: 3, 2: 4, 3: 5 },
                   attach_roi: true }
      - type: smtp                     # e-mail (v0.9.0)
        id: email
        options: { host: "smtp.example.com", port: 587, security: starttls,
                   from_addr: "watch@example.com", to: ["oncall@example.com"],
                   username_env: SMTP_USERNAME, password_env: SMTP_PASSWORD }
      - type: mqtt                     # optional extra `mqtt` (v0.9.0)
        id: barramento
        options: { host: "10.0.0.30", topic: "screen-watch/default",
                   qos: 1, retain: false, username_env: MQTT_USERNAME,
                   password_env: MQTT_PASSWORD, tls: false }
    actions: []                  # see §11.4
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
- Tokens and secrets **never** in the YAML. Use environment variables (`bot_token_env`, `url_env`,
  `${env:VAR}` in `headers`/`payload`); errors/logs never expose the resolved URL or the variable values.
- Alert `type`: `sound`/`popup`/`telegram`/`log` keep **flat fields**; `webhook`/`http_post`/
  `syslog`/`ntfy`/`smtp`/`mqtt` use a nested **`options:`** block. An unknown `type` is `ConfigError`
  (`config.alert_unknown_type`).
- Every alert has an optional **`id`** (default `type`; `type#n` when repeated) used as the **cooldown
  key** and for the send test. `payload` XOR `payload_raw`; unknown `${...}` → `ConfigError`.
- The GUI sound picker edits the active profile's `sound` alert **on disk** through
  `set_profile_sound_file` + `save_config` (atomic, `.bak`, comments not preserved — §12.4); a v1
  config is refused with `config.v1_not_editable`.
- `version` accepts 1 or 2 (any other value is `ConfigError`); v2 **requires** `profiles`; a
  nonexistent `profile` is `ConfigError` (`config.profile_unknown`).
- `version` absent with `targets:` is the legacy v1: it loads for one version, with a warning, and is
  converted by `migrate-config` (`config.yaml.bak` backup, one JSON selection per target).
- An unknown `ui.language` generates a warning and falls back to `auto` (not an error).
- `TargetConfig` remains the runtime's internal contract; the profile + the selection are resolved
  into it by `persistence.selection.build_target`.

### 12.2 Profiles and defaults

Named profiles (`profiles.<name>.defaults` + `.alerts` + `.actions`) allow switching parameter sets
with `--profile` (CLI) or the GUI/tray selector. The switch **applies on the next start** (not live).
The active profile is also written to `state.json.profile`.

`defaults` covers: `mode`, `poll_interval_s` (>= 1.0), `rearm`, `compare_options`, `humanize`
(§11.4) and `escalation` (`enabled`/`severity_min`, §11.3; also overrideable per selection).
Profiles also carry `actions:`; each action `when:` accepts `trigger: change|at|every|after`
(§11.4) — `at`/`days`/`every_s`/`after_s` are the v0.10.0 time-trigger fields and `days` reuses the
`schedule` names (`mon`..`sun`).
`humanize` has no UI of its own: edit the YAML (the GUI creates actions, not humanization).
`ui.snooze_minutes` lists the durations offered by the Snooze menu (GUI + tray); `ui.max_sessions`
(default 4, range 1..16) limits the simultaneous GUI sessions (§3.5).

### 12.3 Selection JSON and overrides

Each selection is a JSON v2; `overrides` is optional and **replaces** (does not add to) the profile
values for that target: `mode`, `poll_interval_s`, `rearm`, `masks`, `alerts`, `actions` and
`text_watch` (the watch override is applied to `compare_options.advanced`).
`version: 1` selections still load without overrides.

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

**Mode precedence**: explicit `mode` from `build_target` (GUI selector) > `overrides.mode` >
`selection.mode`. `actions` overrides are parsed with the resolved mode (`text_*` filters require
`advanced`; §11.4) and so is `text_watch` (`config.text_watch_needs_advanced` otherwise).
`window_title_hint` is only a human hint; the lookup uses `window_handle`.

**Name and rename** (`name`, optional): `build_target` copies it to `TargetConfig.label`, which the
GUI/CLI prefer over the file stem in status/`run`; the stem remains the file key
(`state.json:last_selection`, action selection). The GUI field confirms with the Rename button or
Enter: `plan_rename` computes the slug (`naming.slugify`, accents stripped, max 60 chars) and
`rename_selection` writes the destination + removes the old file, **never overwriting** (conflict →
`selection.name_conflict`) and rolling back on failure (`selection.rename_failed`); a slug equal to
the current stem is a no-op that only records `name`. `last_selection` is updated when it pointed to
the old file name. Renaming is blocked while a session runs.

**Region re-edit (GUI)**: double-click reopens the overlay for the selection window and rewrites
`roi_relative`/`origin_at_selection`, preserving `name`, `mode`, `overrides`, `app_name` and
`window_title_hint`; `masks` (both `selection.masks` and `overrides.masks`) are **cleared** because
they are relative to the old ROI.

**Mask editor (GUI, v0.8.0)**: the editor loads the **effective** masks (`overrides.masks` when the
key exists — it has precedence — otherwise `selection.masks`) and writes back to the **same place**:
existing `overrides.masks` is updated, else non-empty `selection.masks` is updated, else
`overrides.masks` is created (target-specific, higher precedence). It never migrates or clears the
other field silently, and saving with the same empty masks is a no-op when neither field had content.
Saving uses the atomic `dump_selection` (§12.4).

**Selection lifecycle CLI (v0.9.0)**: `edit-selection`, `rename-selection` and `remove-selection`
apply the same precedence rules from the command line (details in §7.3); `list-selections --json`
exposes the resolved file/mode/effective-mask count/override keys for scripting.

### 12.4 State, app-data and writing

`platform/paths.py` centralizes `app_home()`, `config_path()`, `selections_dir()`, `logs_dir()`,
`sounds_dir()` (user sound files: relative `file` is looked up there first) and `state_path()`.
Bundled sounds live in `resources.bundled_sounds_dir()` (`screen_watch/assets/sounds`, the default
`alert.mp3`); the resolution order is user → package → CWD (§11.2).
Base: `%APPDATA%\screen_watch` on Windows, `~/.config/screen_watch` on Linux,
`~/Library/Application Support/screen_watch` on macOS, or the `SCREEN_WATCH_HOME` override.

`state.json` stores `{"last_selection": "...", "profile": "...", "language": "...",
"action_selection": {"<selection>": ["action-name", ...]}, "evidence_enabled": true|false,
"alerts_muted": false, "alerts_snooze_until": 0.0}` and is updated on a successful `run`/GUI start
(the `action_selection`, `evidence_enabled`, `alerts_muted` and `alerts_snooze_until` keys are
optional and backward compatible). The two alert-gate keys feed `AlertGate` on the next GUI/`run`
start (§11.3); an expired `alerts_snooze_until` is simply ignored.

The YAML is rewritten atomically (temp + `os.replace`) with a `config.yaml.bak` backup **without
preserving comments**; `state.json` is atomic, without backup; the selection JSON (`dump_selection`)
is also atomic (temp + `os.replace`), without backup. `migrate-config` reloads from disk
before rewriting.

The effective prints folder comes from `evidence/recorder.py::captures_dir(options)` (`evidence.dir`
when configured, otherwise `%TEMP%/screen_watch/captures`) and `ensure_captures_dir` creates it if
missing; `show-paths` prints it as `captures:` (with an override note). Opening a folder/file is done
exclusively by `platform/shell.py::open_path` (best-effort) — the "Open prints folder" button in the
GUI and "Open YAML" use that helper.

Turning the loop prints on/off does not depend on the YAML: `app.effective_evidence_options(config)`
starts from the YAML `evidence` (v2) and applies the runtime toggle
`state.json["evidence_enabled"]` ("Record prints" checkbox in the GUI), which has precedence — it
also works with config v1 (§11.5).

### 12.5 Scheduler, profiles in the UI and recorder

- **Profiles in the UI**: window selector + tray submenu; the switch applies on the next start and
  persists in `state.json.profile` (`--profile` in the CLI).
- **Scheduler × triggers** (`scheduler/schedule.py::is_open`, pure function with an injectable
  clock; `gate()` returns the callable): `schedule` is only the **suspension gate** — it never fires
  anything. Firing is decided by each action's `when.trigger` (§11.4): `change` reacts to detected
  changes; `at`/`every`/`after` are time-based and require armed. Outside the time window only the
  **actions** are suspended (`suspended_schedule`, consuming a due time-trigger occurrence); capture,
  comparison and alerts continue. Windows crossing midnight are accepted; a scheduler enabled
  without `days`/`windows` does not restrict.
- **Recorder** (`actions/recorder.py` + `record-actions`): with the `input` extra, it captures
  clicks/keys (`F10` ends), converts absolute coordinates to `ref: roi`/`window`/`screen` and
  generates an `actions:` snippet with `when` commented out. Default: 3s countdown and automatic
  recording (the countdown runs on the main thread, before the `pynput` listeners); `--no-countdown`
  keeps the explicit `F9`. Clicks outside the window fall back to `ref: screen`. The snippet keeps
  the commented `when` (change trigger) and adds a commented hint line with the time-trigger fields
  (`trigger`/`at`/`days`/`every_s`/`after_s`); the recorder never records a trigger.
- **Action selection in the UI**: "Session actions" checklist (`describe_action`/`describe_actions`
  in `actions/summary.py`) + "N of M" counter; persists per selection name
  (`actions/selection.py::load_action_selection`/`save_action_selection`) and applies on the next
  start. In the CLI, `--actions a,b|all|none` (one-shot, does not persist, precedes the saved one) and
  `list-actions` to check; `run` prints the summary and the live lines
  `[action] rehearsal|armed <name> -> ok|failed|rehearsal`.
- **Tests/validation**: `is_open` and the trigger evaluator with fake clocks, recorder conversion
  without a real listener and profile switching (next start).

### 12.6 Languages (i18n)

- **Catalog**: JSON inside the package (`screen_watch/i18n/<tag>.json`), discovered at runtime by
  `i18n.available_locales()` (uses `_meta.code`). Initial ones: `pt-BR` (fallback) and `en-US`. No
  language comes from app-data.
- **Scope**: GUI + help (`help.*`) + displayed summary/labels + errors translated by code
  (`errors.py::ERROR_CODES` → `error.<code>`). **CLI and `logging` remain in fixed English**; the GUI
  log panel is also English (it is a log). `str(exc)` of `AppError`/`ConfigError` is English and
  `render_error(exc)` translates by code (without a code, it falls back to `str(exc)`).
- **Choice**: `--language` > `state.json["language"]` > `ui.language` > `auto` (OS locale via
  `QLocale.system()` with fallback to `locale`/`LANG`); exact match (`pt-BR`) → same language
  (`pt` → `pt-BR`) → `pt-BR`. The switch applies **on the next start**; the window selector writes
  `state.json["language"]`. An unknown `ui.language` warns and falls back to `auto`.
- **Validation**: `python -m screen_watch validate-i18n` (also in CI) checks for missing/extra keys
  vs. fallback, untranslated `error.*`/`help.*` and an invalid `_meta`.
- **Hover help**: 2 s `QTimer` + HTML tooltip (`title`, `purpose`, `example`) in
  `gui/help.py` (pure) + `gui/hover_help.py` (Qt).

### 12.7 Errors with stable code

- `AppError` carries `code` + `params`; `str(exc)` renders **in English** (CLI/log).
- `ConfigError` inherits from `AppError` (not `ValueError`); the loader converts action errors
  (`ActionError`) into `ConfigError` preserving code/params.
- The GUI calls `render_error(exc)`, which translates `error.<code>` through the active catalog and
  falls back to `str(exc)` when there is no code/translation.
- Codes are **stable** (contract with the catalogs): renaming a code breaks the translation.
- Alert channels add `config.alert_*` codes (unknown type, options/URL/port/protocol/facility/method,
  payload conflict, unknown placeholder, severity map, duplicate id) and the runtime
  `alert.http_status`/`alert.http_unreachable`/`alert.syslog_unavailable`;

---

## 13. Test ladder (implementation history and current validation)

The implementation followed the ladder below, in order; **the scripts remain in the repository** as
diagnostic tools. On capture/DPI regressions, redo the ladder — do not start with the GUI.

1. **`scripts/step1_absolute_roi.py`** — hardcoded absolute ROI, prints a hash every 1 s. Validates
   capture and measures real Hz.
2. **`scripts/step2_anchored_roi.py`** — anchoring via `pywinctl` (Model B). Moves the window and
   confirms that the ROI follows. Validates DPI and multi-monitor.
3. **`scripts/step3_selection_overlay.py`** — PyQt6 overlay, mouse selection, JSON dump.
   Validates logical↔physical conversion.
4. **JSON loading** — load the selection from step 3 and run anchored capture (today:
   `run`/`select-manual`).
5. **Mask** — confirm that touching the masked area does not change the hash.
6. **Comparison** — test the three strategies separately before composing (`compare-modes`).
7. **Local alerts** — sound + popup (`test-alert`).
8. **Telegram** — webhook with attached image (opt-in integration test).
9. **Full GUI** — main window, tray, action editing.

**Do not skip steps.** The cost of debugging DPI/multi-monitor through the GUI is orders of magnitude
higher than via script.

---

## 14. Known pitfalls (for the implementing AI)

Each item below is a **real** pitfall already discussed and resolved. Do not reintroduce it. Items
1–15 are the originals; items 16–29 were recorded during implementation.

1. **Wayland**: `mss` does not capture. Detect and warn. Do not try to work around it in the prototype.
2. **DPI awareness out of order**: if `SetProcessDpiAwareness` is called after `mss` or Qt,
   it has no effect. Call it first.
3. **`window_title_hint` as a key**: never. Use `window_handle`.
4. **`time.sleep` in the loop**: never. Use `Event.wait`, subtracting work time.
5. **Comparison inside the capture `try`**: never. Separation of responsibilities.
6. **First frame as change**: never. It is baseline.
7. **`setMask` in the overlay**: never. Use `CompositionMode_Clear`.
8. **Re-querying `window.getRect()` after I/O**: never. Capture immediately after the drag.
9. **`hash_size=16` as default**: never. 8.
10. **OCR on every tick**: never. Only in the advanced pipeline, with short-circuit.
11. **`playsound`**: abandoned. Use the `platform/audio.py` boundary.
12. **`pygetwindow`**: abandoned. Use `pywinctl`.
13. **Token in the YAML**: never. Environment variable.
14. **Creating `mss.mss()` on every tick**: never. Reused instance.
15. **Trusting `devicePixelRatio()` as 1.0**: never. Test at 125/150/200%.
16. **`mss` outside the loop thread**: never. It is not thread-safe; the backend is created/closed
    inside the worker (including the reused instance).
17. **Importing `pynput`/`winsound`/`mss`/`pywinctl` outside `platform/`**: never. Every OS dependency
    stays behind the boundary (CI runs without `pynput`).
18. **Assuming `simpleaudio`**: never. It has no reliable wheel for 3.13; sound is an optional extra
    with fallback to an external player; the installers do **not** include it.
19. **Using raw `%APPDATA%` on Windows with Store/MSIX Python**: the path is redirected to
    inside the package. `platform/paths.py` detects this and uses the real path.
20. **Replacing the `.deb` wrapper with a symlink**: never. PyInstaller resolves `_internal` by the
    real path; the wrapper uses `exec`.
21. **Setting `TESSDATA_PREFIX`**: never. The `tessdata` comes from the binary; `advanced.py` does
    not pass `--tessdata-dir`.
22. **Publishing a tag != `__version__`**: `release.yml` fails on purpose. The tag `vX.Y.Z` must be
    identical (without `v`) to `screen_watch.__version__`.
23. **Painting over the ROI in the highlight**: never. The dim layer is computed **outside** the ROI
    (`dim_rects`) and the border is drawn 2 px outside the hole; a single painted pixel inside the
    ROI could become a false positive if a monitoring tick captures during the 2 s highlight (§3.7).
24. **Using `itemActivated` for Enter in the selection list**: never. It also fires on double-click,
    which would start/stop and re-edit the region in the same gesture; use `QShortcut` with
    `WidgetShortcut` (§3.7).
25. **Renaming with a plain move/`os.replace`**: never. `plan_rename`/`rename_selection` validate the
    slug (empty/too long/conflict), never overwrite, roll back on failure and update
    `last_selection`; a region re-edit additionally clears `masks`/`overrides.masks` (they are
    relative to the old ROI).
26. **Replaying a missed time trigger**: never. An occurrence later than the 60 s tolerance is
    recorded as `skipped -> missed` and dropped (no burst after sleep/suspend and no catch-up across
    restarts); `at` uses the naive local clock, so DST can double or lose a firing (§11.4).
27. **Rehearsing a time trigger**: never. `at`/`every`/`after` are evaluated only while armed and
    have no dry-run; the §11.4 rehearsal path belongs to `trigger: change` alone.
28. **Firing the wrong trigger path**: never. `on_result` evaluates only `trigger: change` actions;
    time triggers run once per post-baseline frame in `ActionDispatcher.on_tick`, even when the
    comparison did not change (§11.4).
29. **Busy-waiting for a trigger**: never. `MonitorLoop` caps its `Event.wait` by
    `next_deadline_delay()` (floor 0.05 s, §3.5); no polling/spin loops.

---

## 15. Dependencies (implemented)

Pinned in `pyproject.toml`. Organized by layer (mandatory core):

| Layer | Package | Use |
|---|---|---|
| Capture | `mss` | screen capture |
| Capture | `numpy` | canonical buffer |
| Window | `pywinctl` | window location and geometry |
| Comparison | `Pillow` | `numpy` ↔ `imagehash`/Tesseract bridge |
| Comparison | `imagehash` | phash |
| Comparison | `pytesseract` | OCR (requires the Tesseract binary installed) |
| GUI | `PyQt6` | overlay and main window |
| Tray | `pystray` | tray icon |
| Alerts | `plyer` | popup |
| Alerts | `httpx` | Telegram |
| Alerts | `miniaudio` | CLI/`run` sound playback (WAV/MP3/OGG/FLAC; the GUI uses the bundled Qt Multimedia) |
| Config | `PyYAML` | config |

**Optional extras** (`pyproject.toml::[project.optional-dependencies]`):

| Extra | Packages | Note |
|---|---|---|
| `sound` | `simpleaudio>=1.0.4` | no reliable wheel on 3.13; it does **not** go into the bundle |
| `input` | `pynput>=1.7` | pseudo-human actions and global hotkeys |
| `ocr-preproc` | `opencv-python>=4.8` | OCR preprocessing experiments (not required) |
| `logging` | `structlog>=24.1` | optional structured logging |
| `mqtt` | `paho-mqtt>=2.1` | MQTT alert channel (v0.9.0); not bundled in the installers |
| `dev` | `pytest>=8.0`, `pytest-cov>=5.0`, `ruff==0.16.9` | development and CI |
| `build` | `pyinstaller>=6.11.1` | packaging (supports 3.13 from this version on) |

**External requirements**:
- **Tesseract** installed on the system (it does not come with `pytesseract`), with the `por` and
  `eng` traineddata. On Windows the installer downloads a pinned release (with SHA256 verification),
  and on the Linux `.deb` it becomes a `Depends:`. Path searchable via
  `compare_options.advanced.tesseract_cmd`.
- **Sound on Linux**: the CLI/`run` uses the bundled `miniaudio`; for the legacy formats the GUI
  depends on the GStreamer plugins and an external player (`paplay`/`aplay`/`ffplay`) remains a
  fallback; in the `.deb`, `pulseaudio-utils` and `alsa-utils` come as `Recommends`.
- **Linux**: X11 session (Wayland out of scope).

---

## 16. Contracts between modules (executive summary)

For quick reference by the implementing AI:

```
platform/dpi.set_dpi_awareness()   → call FIRST (first line of main)
platform/window.find_window_by_handle(handle) → WindowInfo | None

capture/resolver.resolve(window_info, roi_relative, logical_to_physical=...) → Rect | None
capture/backend.MssCaptureBackend.bounds() → Rect          (virtual desktop, can be negative)
capture/backend.MssCaptureBackend.capture(abs_rect) → np.ndarray   (RGB)
capture/mask.apply_mask(rgb, masks) → np.ndarray
capture/frame.Frame(rgb, timestamp, absolute_rect, window_rect, window_handle, sequence)

compare/protocol.CompareStrategy.initialize(baseline: Frame)
compare/protocol.CompareStrategy.compare(current: Frame) → ComparisonResult
compare/pipeline.MODE_STAGES / ComparePipeline.compare(current) → ComparisonResult

alerts/chain.AlertChain(notifiers, gate=...) → chain
alerts/chain.AlertChain.dispatch(result, frame) → DispatchOutcome
alerts/gate.AlertGate.snooze(minutes)/mute()/unmute()/status()/active() → manual suppression
actions/dispatch.ActionDispatcher.on_result(result, frame) → rebaseline: bool   (trigger: change)
actions/dispatch.ActionDispatcher.on_tick(frame) → None                         (time triggers)
actions/dispatch.ActionDispatcher.next_deadline_delay() → float | None          (loop wait cap)
actions/triggers.evaluate(action, state, now_wall=..., now_mono=..., armed_since=...) → decision

config/loader.load_config(path) → AppConfig
gui/session_manager.SessionManager(events, gate=..., max_sessions=...) → manager
SessionManager.start(target, recorder=...) → name; .stop(name|None)/.names()/.running/.actions(name)
persistence/selection.build_target(selection, profile, name=..., mode=..., schedule=...,
                                   action_filter=...) → TargetConfig
app.MonitorSession(target, recorder=..., on_action=..., on_frame=..., on_compare=..., gate=...) → sink(frame)
app.MonitorSession.acknowledge()/.awaiting_ack → escalation control (thread-safe flags)
app.build_loop(target, session, on_event=..., on_error=...) → MonitorLoop (wires next_deadline_delay)
scheduler/loop.MonitorLoop.start()/.stop()/.join()
scheduler/schedule.is_open(options, now=...) → bool; gate(options) → Callable | None

evidence/recorder.EvidenceRecorder.from_options(options, force_enabled=...) → recorder
app.effective_evidence_options(config) → EvidenceOptions
```

**Data flow**:

```
MonitorLoop._tick
  → window_lookup → resolve → clip → backend.capture → normalize → apply_mask
  → Frame
  → MonitorSession.__call__(frame)
      → (1st frame / re-arm) pipeline.initialize  (baseline; records evidence)
      → pipeline.compare
      → AlertChain.dispatch            (sound/popup/Telegram/log; cooldown; DispatchOutcome)
      → ActionDispatcher.on_result     (trigger: change; rehearsal/armed; scheduler; limits; audit)
      → ActionDispatcher.on_tick       (time triggers every post-baseline frame; deadlines; audit)
      → baseline re-arm (outcome/rebaseline) + change evidence
```

`MonitorSession` optional callbacks (v0.8.0): `on_frame(frame, is_baseline)` runs on every tick
(before the comparison) and `on_compare(result)` runs on every comparison, including
`changed == False`; both default to `None`. The GUI controller uses them for the preview thumbnails
and the calibration ring buffer (`gui/session_manager.py`), never touching Qt from the loop thread.

`SessionManager` (v0.9.0) builds one such pair per running selection in the GUI and funnels the
callbacks into the same event queue with a `session` key; `preview(name)`/`calibration(name)` read
the per-session buffers and `actions(name)`/`acknowledge(name)`/`rebaseline(name)` route to the
chosen session (`name=None` = all/aggregate).

---

## 17. Glossary

- **ROI** — Region of Interest; the monitored rectangle inside the window.
- **Baseline** — first frame captured in a session (or after re-arm); reference for
  comparison. It is never a change.
- **Model B** — anchoring by window origin: `abs = roi_relative + window_rect.topLeft()`.
- **Pipeline** — composition of comparison strategies with short-circuit.
- **Frame** — immutable dataclass with `rgb` (numpy) and capture metadata.
- **Tick** — one iteration of the capture loop.
- **DPR** — device pixel ratio; factor between logical and physical space.
- **Chrome** — non-client elements of a window (title bar, borders).
- **Profile** — named set of defaults/alerts/actions in the YAML v2 (`profiles.<name>`), switchable
  on the next start.
- **Overrides** — selection JSON fields that **replace** (do not add to) the profile values
  for that target.
- **Arming / rehearsal** — in-memory state that decides whether the actions execute (`armed`/`timed`)
  or only record (`disarmed` = rehearsal). It always starts disarmed.
- **Evidence** — print (baseline/change/per step) saved by the `EvidenceRecorder` for visual
  auditing.
- **Outcome (`DispatchOutcome`)** — result of a `dispatch` (`FIRED`, `SUPPRESSED_COOLDOWN`,
  `SUPPRESSED_MANUAL`, `BELOW_MIN`, `NONE_ENABLED`, `FAILED`) used by the edge-triggered re-arm.
- **Snooze / mute** — manual suppression in `AlertGate`: snooze expires after N minutes, mute lasts
  until unmuted; both persist in `state.json` and keep the pending change.
- **Escalation / acknowledge** — with `escalation.enabled`, a `FIRED` alert repeats (at each alert's
  cooldown) until `acknowledge()` re-arms the baseline; the state lives only in memory.
- **Session** — one monitored selection with its own `MonitorLoop`/thread/backend, managed by
  `SessionManager`; the GUI can run up to `ui.max_sessions` simultaneously (GUI-only in v0.9.0).
- **Trigger** — per-action firing condition (`when.trigger`): `change` (detected visual change, the
  previous behavior) or the time triggers `at`/`every`/`after` (v0.10.0); time triggers exist only
  while armed.
- **Tolerance (grace)** — 60 s window for a time trigger to fire after its due time; beyond it the
  occurrence is recorded as `missed` and never executed.
- **Missed** — audited late occurrence (`skipped -> missed` in `logs/actions.jsonl`) of a time
  trigger; it is dropped, never replayed.

---

## 18. Final notes for the implementing AI

1. **Read this entire document before touching the code.** Many decisions here seem
   arbitrary in isolation, but have recorded motivation.
2. **Use the test ladder (§13) when investigating capture/DPI regressions.** It exists to reduce
   the bug search space.
3. **If something here seems wrong or insufficient, record it as a comment/issue — do not change it
   silently.** If the code changed on purpose, update the document with the new reason and the
   decision history.
4. **Every OS dependency stays in `platform/`.** Never import `pywinctl`/`pynput`/`mss`/
   `winsound` outside that folder.
5. **Comparison never touches screen, window, or sleep.** If your implementation needs any
   of those, the design has been violated.
6. **The first frame is baseline.** If your code fires an alert on the first tick, there is a bug.
7. **If a test fails at 125% or 150% scaling on Windows, that is the most important bug in the
   project.** Prioritize it before any feature.
8. **Document every empirical experiment** (thresholds, hash_size, psm, upscale) with the context in
   which it was tuned. The defaults are starting points, not truths.
