# Roadmap — agent knowledge base

Status: v0.7.1 · Scope: prioritized backlog for v0.8.0 → v1.0.0

Rules:

- Semver: MINOR for features, PATCH for fixes; `__version__` is the single source and the release tag must match.
- **Every design change goes through `doc/00` before implementation** — it is the SSoT.
- This file is the backlog index only. Each increment becomes its own plan in `.kilo/plans/`; when
  completed, the implementing session marks it here and updates `doc/00`, README/wiki,
  `CHANGELOG.md` and `doc/releases/vX.Y.Z.md` (EN/PT).
- Keep entries short; implementation detail belongs in the increment's own plan.

## v0.8.0 — Usability + quality + visual reliability

Suggested order: CI/quality → masks → sound → preview → history → calibration (first what does not
touch the capture path; preview changes `MonitorController`). Risks: Qt threading/memory for the
preview; YAML write-back not preserving comments; wiki publish needs a push secret (PAT).

1. **Visual mask editor** — overlay to draw/remove masks relative to the ROI; write to
   `overrides.masks` (precedence) or `masks`; blocked while a session is running (same rule as
   rename); pure, testable geometry helpers; i18n + hover help.
   - Affects: `gui/overlay*.py`, `capture/mask.py` + geometry helpers, `persistence/selection.py`, i18n catalogs.
   - Acceptance: masks drawable/removable without editing JSON; atomic write; blocked with session running; unit tests.
   - `doc/00`: §8.3, §12.3.
2. **Sound recorded directly in the YAML** — the picker writes `file:` into the active profile's
   `type: sound` alert via `config/loader.py::save_config` (atomic + `.bak`); creates the alert if
   absent; rollback on failure; clear message for config v1; the current popup becomes confirmation.
   - Affects: `config/loader.py`, `gui` sound picker, i18n.
   - Acceptance: choice persisted with backup/rollback; v1 handled clearly; unit tests.
   - `doc/00`: §11.2, §12.1.
3. **Quality** — add Python 3.12 to the CI matrix; `pytest --cov=screen_watch` as report/artifact (no
   hard gate initially); decide automatic wiki publication (requires a push secret, e.g. PAT
   `WIKI_PUSH_TOKEN`) or keep a documented manual runbook.
   - Affects: `.github/workflows/ci.yml`, wiki dev page (and an optional publish workflow).
   - Acceptance: CI green on py3.12 with coverage report; wiki published automatically or runbook documented.
4. **Frame preview** — last frame + baseline in the GUI (copy/downsample through the event queue;
   never hand the loop thread's `numpy` array to Qt directly; memory bounded).
   - Affects: `gui/controller.py`, `gui/main_window.py`, `app.py`.
   - Acceptance: Qt touched only on the GUI thread; bounded memory; unit tests.
   - `doc/00`: §3.7.
5. **Alert history** — table over `logs/alerts.jsonl` with filters (date/severity/channel) and opening
   the evidence print.
   - Affects: `gui/` (new widget), small read helpers around `alerts/log.py`.
   - Acceptance: tolerant to invalid JSONL lines; filters and image open tested.
   - `doc/00`: §3.7.
6. **Live calibration** — per-session ring buffer of `ComparisonResult` (score/threshold/severity) +
   custom widget (no new dependency) + CSV export.
   - Affects: `gui/controller.py`, `compare/protocol.py` consumers, `gui/` widget.
   - Acceptance: CSV export; unit tests.
   - `doc/00`: §3.7.

Version gate: ruff + unit tests + `validate-i18n` green; `doc/00` §8.3/§12.3 (masks), §11.2/§12.1
(sound) and §3.7 (observability) updated; wiki updated.

## v0.9.0 — Reach: alerts + selections + multiple ROIs

Risks: channel secrets must stay in env; snooze/escalation changes `DispatchOutcome` semantics;
multi-ROI resource limits and aggregated UI/tray behavior.

1. **New channels** `ntfy`, `smtp` (stdlib `smtplib`, password via env) and `mqtt` (extra
   `paho-mqtt`), following the extensible map by `type` + i18n error codes + tests + wiki.
   - Acceptance: each channel with a mocked test and i18n codes.
   - `doc/00`: §3.6, §11.2, §12.1.
2. **Snooze/mute** (temporary, `state.json` + tray/GUI) and **escalation** (repeat until
   acknowledged) — revisit the `DispatchOutcome`/cooldown/re-arm semantics.
   - Acceptance: decision recorded in `doc/00` §11.3; `DispatchOutcome` tests.
   - `doc/00`: §11.3.
3. **Selection CLI** — `remove-selection`, `rename-selection` (reuse
   `persistence/selection.py::plan_rename`/`rename_selection`), edit mode/masks/overrides; complete
   headless flow (the README "Radar" item).
   - Affects: `cli/parser.py`, `cli/commands.py`, `persistence/selection.py`, wiki.
   - Acceptance: commands tested and documented; "Radar" resolved.
   - `doc/00`: §7.3, §12.3.
4. **Multiple ROIs** — `SessionManager` running N `MonitorLoop`s (today `MonitorController._session`
   is single); aggregated UI/tray; resource limits; decision recorded in `doc/00`.
   - Affects: `gui/controller.py`, new session manager, `app.py`, tray/main window.
   - Acceptance: 2+ concurrent sessions stable (per-thread isolation for `mss` already exists),
     aggregated UI/tray, limits documented.
   - `doc/00`: §3.5, §16.

## v1.0.0 — Stabilization + platforms

Risks: platform scope creep; passive update check must stay opt-out/cached; typing and the unused
`logging` extra are small but touch many files if done late.

1. **Manual validation** — execute and record the clean-install checklist (`doc/01` §9) and DPI
   100/125/150% (`doc/00` §5.1); fix failures (patch v1.0.x if needed).
2. **Passive update check** — GitHub releases via `httpx`, daily cache in `state.json`, no
   auto-download, opt-out.
   - Acceptance: passive, cached, opt-out; tests.
   - `doc/00`: §3.8, §15.
3. **Platforms** — macOS (validate paths/audio/capture; optional unsigned build job), ARM64
   (PyInstaller target + `.deb` architecture) and a Wayland spike (xdg-desktop-portal) with the
   decision recorded in `doc/00` (support or declare out of scope).
   - `doc/00`: §3.2, §15.
4. **Housekeeping** — use or remove the `logging` extra (structlog is unused in `src/`); gradual
   typing (pyright/mypy) on core modules.
   - Acceptance: decisions recorded in `doc/00`; `logging` resolved; typing scope/config defined and
     green in CI.
