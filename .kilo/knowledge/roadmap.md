# Roadmap — agent knowledge base

Status: v0.10.1 · Scope: prioritized backlog for v1.0.0

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
