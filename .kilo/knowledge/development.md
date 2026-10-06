# Development — agent knowledge base

Status: v0.10.0 · Scope: setup, quality gates, tests, CI, release, app-data

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
python -m pip install -e ".[mqtt]"               # optional: paho-mqtt (MQTT alert channel)
python -m pip install -e ".[logging]"            # optional: structlog (currently unused in src/)
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

- 67 test files under `tests/` (739 unit tests); `tests/conftest.py` has an **autouse fixture forcing i18n to pt-BR**
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

`TEST_REAL_AUDIO` + `TEST_REAL_AUDIO_FILE` (real playback of a WAV/MP3/OGG/FLAC file) are documented
in the READMEs (EN/PT) and in the wiki pages (EN/PT).

## Test ladder (capture/DPI regressions)

Run on a real desktop, not CI; rationale in `doc/00` §13 and its pitfalls §14.

- `python scripts/probe_dpi.py` — mss × Qt monitor matrix.
- `python scripts/step1_absolute_roi.py` — absolute ROI capture.
- `python scripts/step2_anchored_roi.py` — Model B anchoring.
- `python scripts/step3_selection_overlay.py` — selection overlay.

## CI (`.github/workflows/`)

- `ci.yml`: matrix ubuntu-latest/windows-latest × Python 3.11, 3.12 and 3.13; steps are install
  `.[dev]`, `ruff check .`, `validate-i18n`, `pytest -q -m "not integration" --cov=screen_watch`
  (Linux under `xvfb-run`); the `coverage-xml` artifact comes from the Linux/3.13 cell (report only,
  no gate). A PR-only `package` job builds installers with `build_release.py`, no publish.
- `release.yml`: triggered by tags `v*.*.*` (or `workflow_dispatch` with a version input). A version
  guard fails when the ref does not equal `screen_watch.__version__`; builds the Windows `.exe` and
  Linux `.deb`, smoke-tests `features --json`, writes `SHA256SUMS.txt` and creates the GitHub Release
  with notes taken from `CHANGELOG.md`.
- **Wiki**: the GitHub Wiki is a separate repo and CI does **not** publish it; use the manual runbook
  in `doc/01` §8 (copy pages preserving the remote link style, commit and push `master`). Automation
  is deferred until a `WIKI_PUSH_TOKEN` secret exists.

## Release process (increment)

1. Bump `src/screen_watch/__init__.py::__version__` (MINOR for features, PATCH for fixes; `pyproject.toml` is dynamic) and the `Status:` headers of the 3 KB files (`tests/test_agent_kb.py` enforces the match).
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
- `state.json` keys: `last_selection`, `profile`, `language`, `action_selection`, `evidence_enabled`,
  `alerts_muted`, `alerts_snooze_until` (snooze/mute gate, v0.9.0).
- `save_config` is atomic and keeps a backup; `state.json` writes are atomic but disposable (no backup).

## Diagnostics

`features` (environment diagnostics, `--json` for CI; includes the `mqtt` extra probe), `probe-dpi`,
`show-paths`, `compare-modes` (calibration), `test-alert --list/--only ID`, `list-actions`.
Selection lifecycle (v0.9.0): `list-selections [--json]`, `remove-selection`, `rename-selection`,
`edit-selection` (mode/ROI/masks/overrides). Full CLI reference: `wiki/CLI-Usage.md` and
`README.md`.
