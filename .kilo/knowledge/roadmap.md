# Roadmap — agent knowledge base

Status: v0.8.0 · Scope: prioritized backlog for v0.9.0 → v1.0.0

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
