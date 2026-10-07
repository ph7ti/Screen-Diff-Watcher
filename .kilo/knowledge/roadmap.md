# Roadmap — agent knowledge base

Status: v0.11.0 · Scope: prioritized backlog for v1.0.0

Rules:

- Semver: MINOR for features, PATCH for fixes; `__version__` is the single source and the release tag must match.
- **Every design change goes through `doc/00` before implementation** — it is the SSoT.
- This file is the backlog index only. Each increment becomes its own plan in `.kilo/plans/`; when
  completed, the implementing session marks it here and updates `doc/00`, README/wiki,
  `CHANGELOG.md` and `doc/releases/vX.Y.Z.md` (EN/PT).
- Keep entries short; implementation detail belongs in the increment's own plan.

## v0.8.0 — Usability + quality + visual reliability (done)

Shipped as **0.8.0** (2026-10-05); details and evidence in `doc/releases/v0.8.0.md` (EN) +
`v0.8.0.pt-BR.md`, `CHANGELOG.md` and `doc/00` §1.4.

- [x] Visual mask editor: overlay draw/remove, effective-location write rule, atomic selection JSON, blocked while running — `doc/00` §8.3/§12.3/§12.4.
- [x] Sound picker writes `file:` into the active profile YAML (atomic + `.bak`, v1 refused, override warning) — `doc/00` §11.2/§12.1.
- [x] Quality: CI matrix py3.11/3.12/3.13, `coverage-xml` artifact (no gate), documented manual wiki runbook (automation deferred until `WIKI_PUSH_TOKEN`).
- [x] Frame preview: baseline + latest thumbnails, bounded and copied off the loop thread — `doc/00` §3.7/§16.
- [x] Alert history over `logs/alerts.jsonl`: date/severity/strategy filters, best-effort evidence print (`±2 s` heuristic).
- [x] Live calibration: per-session ring buffer (600) of every comparison, custom chart + CSV export.

Follow-up noted for v0.9.0+: the log record has no channel/target/evidence path, so richer history
needs an `alerts.jsonl` schema decision.

## v0.9.0 — Reach: alerts + selections + multiple ROIs (done)

Shipped as **0.9.0** (2026-10-06); details and evidence in `doc/releases/v0.9.0.md` (EN) +
`v0.9.0.pt-BR.md`, `CHANGELOG.md` and `doc/00` §1.4. **0.9.1** (patch, 2026-10-06) fixes the GUI
startup crash caused by leftover property-style `escalating` uses after the `SessionManager`
refactor (see `doc/releases/v0.9.1.md`).

- [x] New channels `ntfy`, `smtp` (stdlib `smtplib`, password via env) and `mqtt` (extra
      `paho-mqtt`), following the extensible map by `type` + i18n error codes + tests + wiki.
      `doc/00` §3.6/§11.2/§12.1/§15.
- [x] Snooze/mute (temporary, `state.json` + tray/GUI) and escalation (repeat until acknowledged) —
      `DispatchOutcome.SUPPRESSED_MANUAL` added, `AlertGate` + `acknowledge()` + evidence tied to
      delivery attempts; `doc/00` §11.3/§11.5.
- [x] Selection CLI — `remove-selection`, `rename-selection` (reusing `plan_rename`/
      `rename_selection`), `edit-selection` (mode/ROI/masks/overrides) and `list-selections --json`;
      headless flow documented (the README "Radar" item is resolved). `doc/00` §7.3/§12.3.
- [x] Multiple ROIs — `gui/session_manager.py::SessionManager` runs N `MonitorLoop`s (replacing
      `MonitorController`), checkbox set + aggregated status/tray + per-selection tray start/stop,
      `ui.max_sessions` (default 4) documented; CLI `run` stays single-selection. `doc/00` §3.5/§3.7/§16.

Follow-ups noted for v1.0.0+: multi-ROI in the CLI/headless flow; persistence of the monitored
checkbox set; `alerts.jsonl` schema with channel/target/evidence path.

## v0.10.0 — Action scheduler (done)

Shipped as **0.10.0** (2026-10-06); details and evidence in `doc/releases/v0.10.0.md` (EN) +
`v0.10.0.pt-BR.md`, `CHANGELOG.md` and `doc/00` §1.4/§11.4.

- [x] Per-action trigger `when.trigger: change|at|every|after` (default `change`): `at` (`HH:MM` +
      `days` reusing the `schedule` names), `every` (phase restarts on each firing), `after` (once,
      counted from arming); strict validation (change fields, `rebaseline`, `cooldown_s >= every_s`)
      — `doc/00` §11.4/§12.2/§12.5.
- [x] Pure evaluator `actions/triggers.py` with injectable clocks, 60 s tolerance (`skipped ->
      missed`, no catch-up) and `ArmingController.armed_since`; `MonitorLoop` caps its wait by
      `ActionDispatcher.next_deadline_delay()` — `doc/00` §3.5.
- [x] GUI editor trigger selector, `list-actions` summary, one-off notice, recorder hint and i18n in
      both catalogs; tests with fake clocks — `doc/00` §12.5/§14/§17.

## v0.11.0 — Update check, macOS, installer consent, housekeeping (done)

Shipped as **0.11.0** (2026-10-06); details and evidence in `doc/releases/v0.11.0.md` (EN) +
`v0.11.0.pt-BR.md`, `CHANGELOG.md` and `doc/00` §1.4.

- [x] Passive update check (`src/screen_watch/updates.py`): at most one anonymous GitHub `GET`/day,
  `state.json` cache (`update_check`, 24 h TTL, `notified_version`), opt-out `ui.update_check`,
  GUI log + tray item opening the release — no popup, no download, daemon thread, CLI offline —
  `doc/00` §3.8/§12.1/§12.4/§15.
- [x] macOS arm64: CI cell (py3.13, `QT_QPA_PLATFORM=offscreen`), `build_release.py --macos`
  (`.zip` via `ditto`), PyInstaller `BUNDLE` + `plyer.platforms.macosx.notification`, release job
  publishes the unsigned `.app`; hardware validation deferred to v1.0.0 —
  `doc/00` §1.1/§3.1/§5.3/§15.
- [x] Wayland spike recorded: portal `org.freedesktop.portal.ScreenCast` + PipeWire evaluated and
  **kept out of scope for the 1.x line** (frame stack/packaging, stream-vs-ROI anchoring model,
  per-compositor consent); future backend behind `capture/backend.py`, no new dependencies now —
  `doc/00` §3.2/§5.1.
- [x] Windows installer: Tesseract **optional with consent** (interactive Yes/No; silent only with
  `/TESSERACT=yes`; failure never aborts; pin/SHA256/uninstall preserved) — `doc/01` §5/§9.
- [x] Housekeeping: unused `logging`/`structlog` extra removed (structlog rejected); **mypy**
  dev-only with the core scope in `[tool.mypy]` + CI gate on Linux/3.13 — `doc/00` §3.1/§15.

## v1.0.0 — Manual validation + closing

Only what cannot be automated or delegated:

1. **Manual validation (user, physical hardware)** — execute and record:
   - clean-machine bundle checklist (`doc/01` §9): icon, `StartupWMClass`, package size, SmartScreen
     and the **Tesseract consent flow** (accept/decline/offline/silent `/TESSERACT=yes`);
   - GUI/tray/overlay and DPI at 100/125/150% (`doc/00` §5.1, §9.5);
   - macOS on Apple hardware, if available: TCC permissions (Screen Recording/Accessibility), tray,
     audio, first run of the unsigned `.app` (Gatekeeper).
   Fix any failure as a PATCH before closing.
2. **Close 1.0.0** — bump `__version__`, update docs/release notes, tag `v1.0.0` (publish only after
   the validation above is recorded).

Deferred follow-ups (not v1.0.0 blockers): multi-ROI in the CLI/headless flow; persistence of the
monitored checkbox set; `alerts.jsonl` schema with channel/target/evidence path; Wayland backend
(portal + PipeWire, post-1.0 — `doc/00` §3.2).
