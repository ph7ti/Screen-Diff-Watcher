# Architecture — agent knowledge base

Status: v0.9.0 · Design SSoT: `doc/00-Architecture_and_Specification.md` (cite as `doc/00 §X`)

This page is a pointer summary. Every design decision stays in `doc/00`; do not restate or re-decide
it here. Principles: `doc/00` §2. Decisions (ADR): §3. Pitfalls never to reintroduce: §14.

## Data flow (one page)

```text
MonitorLoop._tick (scheduler/loop.py)
  → window_lookup → resolver.resolve (Model B) → intersect_rect (clip)
  → MssCaptureBackend.capture → BGRA→RGB → capture/mask.apply_mask
  → Frame (capture/frame.py)
  → MonitorSession.__call__ (app.py)
      → 1st frame / re-arm: pipeline.initialize  (baseline; records evidence)
      → ComparePipeline.compare  (light | default | advanced; short-circuit)
      → AlertChain.dispatch → DispatchOutcome (sound/popup/telegram/log/webhook/http_post/syslog)
      → ActionDispatcher.on_result (rehearsal/armed; scheduler; limits; audit)
      → baseline re-arm (outcome/rebaseline) + change evidence
```

Contracts between modules: `doc/00` §16. Capture chain details: §7. Comparison: §10. Alerts: §11.
DPI: §5.1. Logical→physical: §9.5. Masks: §8. Config: §12. Glossary: §17.

## Module map (`src/screen_watch/`)

- `__init__.py` — `__version__`, the single version source.
- `__main__.py` — `python -m screen_watch` entry point.
- `app.py` — orchestration: `build_pipeline` :42, `build_alert_chain` :184, `effective_evidence_options` :243, `MonitorSession` :267 (`__call__` :298, `request_rebaseline` :327), `build_loop` :339.
- `cli/` — `parser.py` (22 subcommands + global `--verbose`/`--language`) and `commands.py`.
- `gui/` — `main_window.py`, `session_manager.py` (`SessionManager`, N sessions/loops; preview + calibration buffers under locks and the shared `AlertGate`), `tray.py`, `overlay.py`, `overlay_geometry.py`, `mask_overlay.py`, `mask_editor_geometry.py` (pure), `preview_widget.py`, `preview_geometry.py` (pure), `history_dialog.py`, `calibration_widget.py`, `calibration.py` (pure), `countdown.py`, `locator.py`, `action_editor.py`, `alert_dialog.py`, `hotkeys.py`, `help.py`, `hover_help.py`, `labels.py`, `highlight.py`, `qt_app.py`.
- `capture/` — `frame.py` (immutable Frame), `backend.py` (Protocol) + `mss_backend.py`, `resolver.py` (Model B), `roi.py` (shared by capture/Highlight), `geometry.py` (`intersect_rect`), `mask.py` (`apply_mask`).
- `compare/` — `protocol.py` (`ComparisonResult`, severity), `light.py`, `default.py`, `advanced.py`, `pipeline.py` (`MODE_STAGES`, short-circuit).
- `alerts/` — `protocol.py`, `sound.py`, `popup.py`, `telegram.py`, `ntfy.py`, `smtp.py`, `mqtt.py`, `log.py`, `http.py`, `syslog.py`, `template.py`, `test_send.py`, `gate.py` (`AlertGate` snooze/mute), `chain.py` (`AlertChain`, `DispatchOutcome`), `history.py` (pure JSONL read/filters/evidence heuristic).
- `actions/` — opt-in pseudo-human actions: `protocol.py`, `plan.py`, `dispatch.py`, `runner.py`, `arming.py` (memory only), `audit.py`, `selection.py`, `summary.py`, `once.py`, `recorder.py`.
- `evidence/` — `recorder.py` (baseline/change/step prints, retention).
- `scheduler/` — `loop.py` (`MonitorLoop`: thread + `Event.wait`), `schedule.py` (pure time-window gate).
- `config/` — `schema.py` (dataclasses), `loader.py` (YAML ↔ dataclasses, defaults, v1→v2 migration; `save_config` :1063 atomic + `.bak`, `set_profile_sound_file` :772).
- `persistence/` — `selection.py`: selection JSON v1/v2, `build_target` :364 (override precedence), `dump_selection` :105 atomic, `set_masks`/`effective_masks` (mask editor), `plan_rename`/`rename_selection` (validated, no overwrite, rollback).
- `platform/` — the only OS boundary: `dpi.py` (`set_dpi_awareness()` first, `is_wayland()`), `window.py`, `paths.py` (app-data/state), `display.py`, `tesseract.py`, `audio.py`, `input.py`, `shell.py`.
- `i18n/` — JSON catalogs pt-BR (fallback)/en-US, `tr()` resolution.
- `errors.py`, `naming.py`, `resources.py`, `gui_main.py` — stable error codes/`AppError`, slugify, package resources, windowed entry point.

## Configuration summary (details `doc/00` §12)

- YAML v2: `profiles.<name>` with `defaults`/`alerts`/`actions`, plus `ui`, `schedule`, `evidence`.
- Selection JSON (v1/v2) with `overrides` that **replace** profile values; `persistence.selection.build_target` is the resolution/precedence point.
- Writing: `save_config` writes atomically (temp + `os.replace`) and keeps `config.yaml.bak` via `shutil.copy2` (comments are not preserved); `dump_selection`/`state.json` are atomic without backup; callers must reload from disk before rewriting (`doc/00` §12.4).

## Current state and known limitations (v0.8.0)

- Implemented: capture/anchoring (Model B), `light`/`default`/`advanced` + `text_watch`, alert channels (sound/popup/Telegram/ntfy/smtp/mqtt/log/webhook/http_post/syslog) with cooldown/re-arm, selectable sound + bundled `alert.mp3`, snooze/mute + escalation, evidence, actions + recorder, scheduler, profiles + v1→v2 migration, selection name/rename + headless CLI lifecycle (`remove`/`rename`/`edit-selection`, `list-selections --json`), GUI/tray with i18n, packaging and tag-driven release (`doc/00` §1.4).
- **v0.8.0**: visual mask editor (atomic selection JSON, `overrides.masks` precedence), sound picker writes the active profile YAML (atomic + `.bak`, v1 refused), frame preview, alert history over `logs/alerts.jsonl` (best-effort evidence print), live calibration (score vs threshold, CSV), CI on py3.11/3.12/3.13 with coverage artifact + manual wiki runbook.
- **v0.9.0**: ntfy/SMTP/MQTT channels (env-only secrets; MQTT is the optional `mqtt` extra), `AlertGate` snooze/mute in `state.json` + escalation until `acknowledge()`, CLI selection lifecycle/headless flow, and `SessionManager` with N concurrent GUI sessions (`ui.max_sessions`, default 4; CLI `run` stays single-selection).
- Wayland cannot capture (`mss`); occluded windows compare whatever is on screen; macOS is not validated; GNOME tray may need an extension; M4A/AAC in the CLI needs an external player (`ffplay`); ARM is not built.
- Manual validation pending: GUI/tray/overlay (including multi-session and the v0.8.0/v0.9.0 widgets) at 100/125/150% and the clean-machine bundle checklist (`doc/01` §9).

## Release history (one line each)

GitHub releases: https://github.com/ph7ti/Screen-Diff-Watcher/releases

- v0.2.1 — GUI action editor, mouse locator, countdown, action checklist, evidence, `features`, first packaging (PyInstaller/Inno Setup/.deb).
- v0.3.0 — i18n pt-BR/en-US, stable error codes, new layout, arm/disarm in the GUI, step editor and hover help; bilingual docs.
- v0.4.0 — removal of deprecations (`--target`, `schedule.timezone`, `seed: null`) + internal refactor.
- v0.4.1 — CLI split into the `cli/` package; centralized log/audit paths.
- v0.5.0 — webhook/http_post/syslog channels, stable `id` + per-id cooldown, `test-alert --list/--only`.
- v0.6.0 — selectable sound (Qt/miniaudio/legacy), `text_watch`, phash gate in `advanced`, ROI outside the window rejected.
- v0.7.0 — selection name + slug rename, Highlight, double-click region re-edit.
- v0.7.1 — bundled `alert.mp3` default, sound popup and 2×2 window layout.
- v0.8.0 — mask editor, sound written to the YAML, preview/history/calibration, CI py3.12 + coverage, wiki runbook.
- v0.9.0 — ntfy/SMTP/MQTT channels, snooze/mute + escalation, CLI selection lifecycle (headless), multiple ROIs via `SessionManager`.

Detailed notes: `doc/releases/vX.Y.Z.md` + `.pt-BR.md` (from v0.5.0 on); `CHANGELOG.md` is the
semantic log (PT). Note: 0.7.1 was a deliberate PATCH despite the documented MINOR rule.
