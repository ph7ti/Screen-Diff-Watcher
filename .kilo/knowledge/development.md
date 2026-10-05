# Development — agent knowledge base

Status: v0.7.1 · Scope: setup, quality gates, tests, CI, release, app-data

Commands below were verified against the repository at v0.7.1. Build/release details are in
`doc/01-Build_and_Release.md`; design rationale in `doc/00`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1                    # Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"               # core + pytest/pytest-cov/ruff
python -m pip install -e ".[input]"             # optional: pynput (actions, global hotkeys)
python -m pip install -e ".[sound]"             # optional: simpleaudio (legacy; no 3.13 wheel)
python -m pip install -e ".[ocr-preproc]"       # optional: opencv (OCR experiments)
python -m pip install -e ".[logging]"           # optional: structlog (currently unused in src/)
python -m pip install -e ".[build]"             # optional: PyInstaller
python -m pip install -e ".[dev,build,input]"   # what CI/release installs
```

## Quality gates (run before finishing)

```powershell
ruff check .                                     # line-length 100, py311, E4/E7/E9/F/W/I/UP
python -m screen_watch validate-i18n             # catalogs: keys, errors, help, _meta
python -m pytest -q -m "not integration"         # unit suite
```

No coverage gate, mypy or pyright exists today (roadmap items). On Linux, GUI tests need a display:
`xvfb-run -a python -m pytest -q -m "not integration"`.

## Tests

- 55 test files under `tests/`; `tests/conftest.py` has an **autouse fixture forcing i18n to pt-BR**
  and provides the `make_frame` / `solid` fixtures.
- GUI tests do not instantiate `QApplication` at collection time; on Linux CI they run under `xvfb-run`.
- Integration tests are opt-in via the `integration` marker (excluded from CI):

```powershell
$env:TEST_REAL_CAPTURE="1"; python -m pytest -m integration
$env:TEST_REAL_TELEGRAM="1"; $env:TELEGRAM_BOT_TOKEN="..."; $env:TELEGRAM_TEST_CHAT_ID="..."; python -m pytest -m integration
$env:TEST_REAL_WEBHOOK_URL="https://..."; python -m pytest -m integration
$env:TEST_REAL_HTTP_URL="https://..."; python -m pytest -m integration
$env:TEST_REAL_AUDIO="1"; $env:TEST_REAL_AUDIO_FILE="C:\sounds\alert.mp3"; python -m pytest -m integration
```

**Known doc gap**: `README.md`/`README.pt-BR.md` still list only the first four env pairs —
`TEST_REAL_AUDIO` + `TEST_REAL_AUDIO_FILE` (real playback of a WAV/MP3/OGG/FLAC file) are documented
in the wiki pages (EN/PT) but not in the README.

## Test ladder (capture/DPI regressions)

Run on a real desktop, not CI; rationale in `doc/00` §13 and its pitfalls §14.

- `python scripts/probe_dpi.py` — mss × Qt monitor matrix.
- `python scripts/step1_absolute_roi.py` — absolute ROI capture.
- `python scripts/step2_anchored_roi.py` — Model B anchoring.
- `python scripts/step3_selection_overlay.py` — selection overlay.

## CI (`.github/workflows/`)

- `ci.yml`: matrix ubuntu-latest/windows-latest × Python 3.11 and 3.13; steps are install `.[dev]`,
  `ruff check .`, `validate-i18n`, `pytest -q -m "not integration"` (Linux under `xvfb-run`). A
  PR-only `package` job builds installers with `build_release.py` and uploads artifacts, no publish.
- `release.yml`: triggered by tags `v*.*.*` (or `workflow_dispatch` with a version input). A version
  guard fails when the ref does not equal `screen_watch.__version__`; builds the Windows `.exe` and
  Linux `.deb`, smoke-tests `features --json`, writes `SHA256SUMS.txt` and creates the GitHub Release
  with notes taken from `CHANGELOG.md`.

## Release process (increment)

1. Bump `src/screen_watch/__init__.py::__version__` (MINOR for features, PATCH for fixes; `pyproject.toml` is dynamic).
2. Green gates: ruff + unit tests + `validate-i18n`.
3. Update `doc/00` (if design changed), wiki/README (EN + PT mirrors), `CHANGELOG.md` (PT) and `doc/releases/vX.Y.Z.md` + `.pt-BR.md`.
4. Build on the target OS: `python scripts/build_release.py --windows` / `--linux`; smoke `dist/screen-watch/screen-watch features --json`.
5. PR into `main`; then tag `vX.Y.Z` (equal to `__version__`) and push — `release.yml` publishes.

Packaging specifics: Tesseract pin `packaging/windows/tesseract.json`, icon
`python packaging/make_ico.py`, `.deb` dependencies in `packaging/linux/control.template`; manual
clean-machine checklist `doc/01` §9, quick checklist §12.

## App-data and state (`platform/paths.py`)

- Root: `%APPDATA%\screen_watch` (Windows), `~/.config/screen_watch` (Linux/X11),
  `~/Library/Application Support/screen_watch` (macOS), or the `SCREEN_WATCH_HOME` override.
- Files: `config.yaml` (+ `config.yaml.bak`), `selections/`, `sounds/`, `logs/alerts.jsonl`,
  `logs/actions.jsonl`, `state.json`.
- `state.json` keys: `last_selection`, `profile`, `language`, `action_selection`, `evidence_enabled`.
- `save_config` is atomic and keeps a backup; `state.json` writes are atomic but disposable (no backup).

## Diagnostics

`features` (environment diagnostics, `--json` for CI), `probe-dpi`, `show-paths`, `compare-modes`
(calibration), `test-alert --list/--only ID`, `list-actions`. Full CLI reference: `wiki/CLI-Usage.md`
and `README.md`.
