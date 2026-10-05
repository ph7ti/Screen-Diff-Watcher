# Development, tests and CI

**English** · [Português (Brasil)](Desenvolvimento-Testes-e-CI.md)

## Setting up the environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"     # core + ruff/pytest
```

Extras that affect development: `input` (pynput — actions/hotkeys), `build` (pyinstaller),
`sound`/`ocr-preproc`/`logging` (optional), `dev` (tests).

## Quality and tests

```powershell
ruff check .
python -m pytest                  # unit tests (default)
python -m pytest -q -m "not integration"
```

Tests that depend on `imagehash`/`pytesseract` are skipped automatically if the dependency is not
installed. CI does not install `simpleaudio`, does not use Tesseract (OCR is mocked) and does not import Qt
during collection.

### Integration (opt-in, outside CI)

```powershell
$env:TEST_REAL_CAPTURE="1"; python -m pytest -m integration
$env:TEST_REAL_TELEGRAM="1"; $env:TELEGRAM_BOT_TOKEN="..."; `
  $env:TELEGRAM_TEST_CHAT_ID="..."; python -m pytest -m integration
$env:TEST_REAL_WEBHOOK_URL="https://..."; python -m pytest -m integration
$env:TEST_REAL_HTTP_URL="https://..."; python -m pytest -m integration
$env:TEST_REAL_AUDIO="1"; $env:TEST_REAL_AUDIO_FILE="C:\sounds\alert.mp3"; python -m pytest -m integration
```

`TEST_REAL_CAPTURE` really captures from the primary monitor; `TEST_REAL_TELEGRAM` sends a synthetic
photo and fails if the HTTP is not 2xx; `TEST_REAL_WEBHOOK_URL`/`TEST_REAL_HTTP_URL` send a synthetic
JSON payload to the given URL; `TEST_REAL_AUDIO` plays the `TEST_REAL_AUDIO_FILE` (WAV/MP3/OGG/FLAC)
through the CLI sound path and fails if playback does not succeed.

## Validation ladder (capture/DPI diagnostics)

In capture/DPI regressions, use the scripts in order — **do not start with the GUI**:

1. `python scripts/step1_absolute_roi.py` — hardcoded absolute ROI; validates capture and measures real Hz.
2. `python scripts/step2_anchored_roi.py` — anchoring via `pywinctl` (Model B); move the window and
   confirm that the ROI follows.
3. `python scripts/step3_selection_overlay.py` — PyQt6 overlay; mouse selection and JSON dump.
4. `python scripts/probe_dpi.py` — DPI matrix (mss × Qt × scale).

## CI (GitHub Actions)

`.github/workflows/ci.yml` runs, on **`ubuntu-latest` and `windows-latest`** × **Python 3.11 and 3.13**:

- `ruff check .`
- `python -m screen_watch validate-i18n`
- `pytest -m "not integration"`

In pull requests, the `package` job also builds the installers **without publishing** (it catches packaging
breakage).

`.github/workflows/release.yml` builds the installers from a `v*.*.*` tag (Windows
`windows-latest` + Inno Setup; Linux `ubuntu-22.04`) and publishes the GitHub Release with
`SHA256SUMS.txt`. It **fails** if the tag (without `v`) differs from `screen_watch.__version__`. With
`workflow_dispatch` and the `version` input, it generates only the workflow artifacts (no release).

## Local build of the installers

Run it on the target OS (the script refuses cross-build):

```powershell
python -m pip install -e ".[dev,build,input]"
python scripts/build_release.py --windows   # on Windows (requires Inno Setup 6 / ISCC.exe)
python scripts/build_release.py --linux     # on Linux (requires dpkg-deb)
```

Artifacts in `dist/installers/` (+ `build-info.json`). Full guide (version, Tesseract pin,
icon, validation, troubleshooting): [`doc/01-Build_and_Release.md`](../doc/01-Build_and_Release.md).

## Repository rules

- **Version**: single source in `src/screen_watch/__init__.py::__version__`; never edit `version` in
  `pyproject.toml` (it is dynamic). The tag is `vX.Y.Z` (the part without `v` equals `__version__`).
- **Never commit** `dist/`, `build/` or secrets.
- `ruff` and `pytest` green before any PR; `validate-i18n` included in CI.
- Actions/tokens only via environment variables (`TELEGRAM_BOT_TOKEN` etc.).

## Related

- [Installation](Installation.md) — setting up the usage environment
- [Usage (CLI)](CLI-Usage.md) — `features`, `probe-dpi`, `validate-config`, `validate-i18n`
- [doc/00](../doc/00-Architecture_and_Specification.md) — design decisions
