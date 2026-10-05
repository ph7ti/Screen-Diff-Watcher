# AGENTS.md

Kilo auto-loads this file, but `.kilo/knowledge/` is **not** auto-loaded. Read these three files
before any non-trivial task:

- [.kilo/knowledge/architecture.md](.kilo/knowledge/architecture.md) — current state, data flow, module map, release history.
- [.kilo/knowledge/development.md](.kilo/knowledge/development.md) — setup, quality gates, tests, CI, release, app-data.
- [.kilo/knowledge/roadmap.md](.kilo/knowledge/roadmap.md) — prioritized backlog for v0.8.0 → v1.0.0.

## Project

Desktop app (Python 3.11+, Windows/Linux) that watches a **rectangular region (ROI) of a window**
and alerts on visual changes. PyQt6 GUI + tray and a full CLI. Current version: **0.7.1**
(`src/screen_watch/__init__.py`, single source; `pyproject.toml` is dynamic).

## Source of truth

- **Design decisions (SSoT)**: `doc/00-Architecture_and_Specification.md` (PT mirror:
  `doc/00-Documento_de_Arquitetura_e_Especificação.md`) — cite as `doc/00 §X`, never copy it.
- **Build and release**: `doc/01-Build_and_Release.md`.
- **Usage**: `wiki/` (EN + PT pages) and `README.md`.
- **History**: `CHANGELOG.md` (PT) and `doc/releases/vX.Y.Z.md` + `.pt-BR.md` (EN/PT, from v0.5.0 on).
- **Agent KB**: `.kilo/knowledge/*.md` (this file links them).

## Quick start

```powershell
python -m pip install -e ".[dev]"     # core + ruff/pytest/pytest-cov
# optional extras: input (pynput), sound (simpleaudio), ocr-preproc, logging (structlog), build (PyInstaller)
ruff check .
python -m pytest -q -m "not integration"
python -m screen_watch validate-i18n
python -m screen_watch gui
python -m screen_watch run --selection <selection-file-slug>
python scripts/build_release.py --windows   # or --linux; run on the target OS; tag vX.Y.Z == __version__
```

Integration tests are opt-in and excluded from CI: `TEST_REAL_CAPTURE`; `TEST_REAL_TELEGRAM` +
`TELEGRAM_BOT_TOKEN` + `TELEGRAM_TEST_CHAT_ID`; `TEST_REAL_WEBHOOK_URL`; `TEST_REAL_HTTP_URL`;
`TEST_REAL_AUDIO` + `TEST_REAL_AUDIO_FILE` (the audio pair is still missing from the README — see
`.kilo/knowledge/development.md`).

## Golden rules

Summarized from `doc/00` §2 (principles) and §14 (pitfalls); the link wins if they disagree.

- Version lives only in `src/screen_watch/__init__.py`; the release tag `vX.Y.Z` must equal it (`release.yml` enforces).
- Every OS dependency (`mss`, `pywinctl`, `pynput`, `winsound`) stays inside `platform/`.
- Call `platform/dpi.set_dpi_awareness()` first, before `mss`/Qt.
- The first frame is the baseline, never a change; comparison never does I/O, never touches screen/window, never sleeps.
- Capture failures emit an event and retry next tick; Wayland is detected and warned, not worked around.
- Secrets only through environment variables, never in YAML.
- CLI and log messages are fixed English; only the GUI is i18n (pt-BR/en-US).
- Design changes go through `doc/00` first; capture/DPI regressions use the test ladder (`scripts/step*.py`).

## Repository map

- `src/screen_watch/` — `app.py` (orchestration), `cli/`, `gui/`, `capture/`, `compare/`, `alerts/`, `actions/`, `evidence/`, `scheduler/`, `config/`, `persistence/`, `platform/`, `i18n/`, `assets/`.
- `tests/` — unit tests by default; `integration` marker is opt-in.
- `scripts/` — validation ladder (`step1_absolute_roi.py`, `step2_anchored_roi.py`, `step3_selection_overlay.py`, `probe_dpi.py`) and `build_release.py`.
- `packaging/` — PyInstaller spec, Inno Setup, `.deb` templates, Tesseract pin.
- `doc/`, `wiki/` — docs; `.github/workflows/` — CI (`ci.yml`) and release (`release.yml`); `.kilo/` — agent KB and plans.

## Session workflow

1. If the task changes design, update `doc/00` first — it is the SSoT.
2. Roadmap increments become their own plan in `.kilo/plans/` before coding; on completion, mark the item in `.kilo/knowledge/roadmap.md` and update `doc/00`, README/wiki, `CHANGELOG.md` and `doc/releases/vX.Y.Z.md` (EN/PT).
3. Gates before finishing: `ruff check .` and `python -m pytest -q -m "not integration"` green; `python -m screen_watch validate-i18n` when touching catalogs.
4. Release: bump `__version__` → gates → docs → build/smoke on the target OS → PR into `main` → tag `vX.Y.Z` and push.

## Never do

- Do not duplicate design decisions here or in `.kilo/knowledge/` — summarize and link `doc/00 §X`.
- Do not translate CLI output or logs (fixed English); GUI only.
- Do not add a dependency without updating `doc/00` §15 and `pyproject.toml`.
- Do not import `mss`/`pywinctl`/`pynput`/`winsound` outside `platform/`.
- Do not commit `dist/`, `build/`, secrets, or a tag whose version differs from `__version__`.
- Do not skip the test ladder when diagnosing capture/DPI regressions.
