# Screen Diff Watcher — Build and Release (Windows/Linux installers)
**English** · [Português (Brasil)](01-Build_e_Release.md)

Operational guide for a **human or AI**: how to update the build information and generate the
installers after new code increments.

Architecture decisions: [`00-Architecture_and_Specification.md`](00-Architecture_and_Specification.md) §3.8 (PyInstaller, per-platform build).
Usage summary in [`README.md`](../README.md) (section "Building the installers").

All commands assume the **repository as the current directory** (`cd ScreenDiffWatcher`).

---

## 1. Pipeline overview

```
source code  ──PyInstaller(spec)──► dist/screen-watch/  (onedir: screen-watch, screen-watch-gui)
                                         │
                       scripts/build_release.py  ──►  dist/installers/
                                         │               ├─ build-info.json
   Windows: ISCC (Inno Setup)  ─────────┘               ├─ screen-diff-watcher_<v>_windows_x64_setup.exe
   Linux:   dpkg-deb           ─────────────────────────└─ screen-watch_<v>_amd64.deb
```

- `scripts/build_release.py` runs **on the target OS** and refuses cross-builds.
- `packaging/screen-watch.spec`: 1 `Analysis` + 2 `EXE` (console and windowless) that share
  `PYZ`/`COLLECT`; bundles `screen_watch/assets/icons/`.
- `dist/installers/build-info.json` is **generated on every build** (version, OS, Python,
  `pynput`/`cv2` capabilities). Do not edit by hand.
- The `build/` and `dist/` paths are ignored by Git.

---

## 2. Prerequisites

| OS | Requirements |
|---|---|
| Windows | Python 3.13, `pip install -e ".[dev,build,input]"` and **Inno Setup 6** (`choco install innosetup -y`, or install the app; the script also looks in `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`) |
| Linux (Debian/Ubuntu) | Python 3.13, `pip install -e ".[dev,build,input]"` and `dpkg-deb` (`sudo apt-get install -y dpkg-dev`) |

Notes:
- `build = ["pyinstaller>=6.11.1"]` — **required**: PyInstaller only supports Python 3.13 from
  6.11.1 onwards.
- `simpleaudio` does **not** go into the bundle on purpose (no reliable wheel on 3.13).
- The `.deb` targets `amd64` and requires X11; build on `ubuntu-22.04` to get an older glibc.

---

## 3. Routine after new code increments

1. **Quality**: `ruff check .` and `python -m pytest -q -m "not integration"`.
2. **Bump the version** (see §4) — mandatory before publishing.
3. **Update the Tesseract pin** only when you want to adopt a new release (see §5).
4. **Regenerate the icon** only if the PNGs in `src/screen_watch/assets/icons/` change (see §6).
5. **Build** (see §7) and run the **smoke test** (see §9).
6. **Commit/tag** and let the CI publish (see §8). Never commit secrets or `dist/`/`build/`.

---

## 4. Updating the version (single source)

The version lives **only** in `src/screen_watch/__init__.py`; `pyproject.toml` is dynamic
(`[tool.setuptools.dynamic] version = {attr = "screen_watch.__version__"}`). Do not create/edit a
`version` in `pyproject`.

```python
# src/screen_watch/__init__.py
__version__ = "0.7.1"   # <- single source of truth
```

Confirm that the metadata and the attribute match:

```powershell
python -c "import importlib.metadata as m, screen_watch; print(m.version('screen-watch'), screen_watch.__version__)"
```

`scripts/build_release.py` revalidates this and aborts if `project.dynamic` does not point to
`screen_watch.__version__`. The CI (`.github/workflows/release.yml`) **fails** if the tag (without
`v`) differs from `__version__`.

---

## 5. Updating the Tesseract pin (Windows)

File: `packaging/windows/tesseract.json` — version, URL and **SHA256** of the UB-Mannheim installer and
of `por.traineddata`. The install on the client uses exactly this pin (**never "latest" at install
time**).

1. Find the release and the asset:

```powershell
$rel = Invoke-RestMethod -Headers @{ "User-Agent"="kilo" } `
  "https://api.github.com/repos/UB-Mannheim/tesseract/releases/latest"
$rel.tag_name
($rel.assets | Where-Object { $_.name -like '*w64-setup*.exe' }).browser_download_url
```

2. Download and compute the SHA256 of the installer:

```powershell
Invoke-WebRequest "<INSTALLER_URL>" -OutFile "$env:TEMP\tesseract-setup.exe"
(Get-FileHash "$env:TEMP\tesseract-setup.exe" -Algorithm SHA256).Hash
```

3. Do the same for `por.traineddata`, pinning a **commit** of `tessdata_fast`:

```powershell
$commit = (Invoke-RestMethod -Headers @{ "User-Agent"="kilo" } `
  "https://api.github.com/repos/tesseract-ocr/tessdata_fast/commits/main").sha
$commit
Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$commit/por.traineddata" `
  -OutFile "$env:TEMP\por.traineddata"
(Get-FileHash "$env:TEMP\por.traineddata" -Algorithm SHA256).Hash
```

4. Edit `packaging/windows/tesseract.json`:

```json
{
  "version": "5.4.0.20240606",
  "installer": {
    "url": "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe",
    "sha256": "<lowercase sha256 of the .exe>"
  },
  "traineddata": {
    "lang": "por",
    "url": "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/<commit>/por.traineddata",
    "sha256": "<lowercase sha256 of por.traineddata>",
    "dest": "tessdata/por.traineddata"
  }
}
```

`packaging/windows/install-tesseract.ps1` (called by the installer, elevated) verifies the SHA256,
installs with `/VERYSILENT` and validates `tesseract --list-langs` (it must contain `eng` and `por`).
Do not set `TESSDATA_PREFIX`: `compare/advanced.py` does not pass `--tessdata-dir` and uses the
binary's `tessdata`. On Linux, Tesseract comes from the `.deb`'s `Depends:` — nothing to pin.

---

## 6. Regenerating the icon (only if the PNGs change)

```powershell
python packaging/make_ico.py        # generates packaging/icons/ScreenDiffWatcher.ico
```

The `.ico` is used by PyInstaller (icon of the EXEs) and by Inno Setup's `SetupIconFile`. It is
versioned; run it only when the source PNGs change.

---

## 7. Generating the installer

**Windows** (PowerShell, generates the EXEs + `setup.exe`):

```powershell
python scripts/build_release.py --windows
```

**Linux** (generates the binaries + `.deb`):

```bash
python scripts/build_release.py --linux
```

Each run:
1. validates the version (§4) and the prerequisites (`ISCC.exe` / `dpkg-deb`);
2. runs PyInstaller with `packaging/screen-watch.spec` (`--clean --noconfirm`) → `dist/screen-watch/`;
3. writes `dist/installers/build-info.json`;
4. builds the installer into `dist/installers/`.

Running on the wrong OS (e.g. `--linux` on Windows) aborts with a clear message (no cross-build).

---

## 8. Publishing (CI)

Repository: `https://github.com/ph7ti/Screen-Diff-Watcher`.

- **PR / CI `workflow_dispatch`**: the `package` job in `ci.yml` builds the installers **without
  publishing** (artifacts `installer-Windows` / `installer-Linux`) — it catches packaging breakage.
- **Test release**: `workflow_dispatch` on `release.yml` with `version` = the value of `__version__`
  (e.g. `0.7.1-rc1`) generates **workflow artifacts only**, with no release.
- **Final release**: create the tag and push:

```powershell
git tag v0.7.1          # tag without 'v' must be EQUAL to __version__
git push origin v0.7.1
```

`release.yml` builds Windows (`windows-latest` + `choco install innosetup -y`) and Linux
(`ubuntu-22.04`), generates `SHA256SUMS.txt` and creates the GitHub Release with `gh release create`.

---

## 9. Validation (definition of done)

Quick smoke test of the bundle (without installing):

```powershell
dist\screen-watch\screen-watch.exe --help
dist\screen-watch\screen-watch.exe features --json
```

```bash
dist/screen-watch/screen-watch --help
xvfb-run -a dist/screen-watch/screen-watch features --json
```

`features --json` must show `frozen: true`, `input.available`, `tray.pystray`, the sound backend,
monitors and Tesseract (path + languages). Compare with the dev environment (`python -m screen_watch
features`) — the expected difference is `frozen`.

Manual validation (not automated):

- **Windows, clean machine without Tesseract**: install → Tesseract downloaded/installed; `features`
  shows `eng`+`por`; the GUI opens; shortcuts created; the "start with Windows" option works;
  uninstalling removes the app and **preserves** Tesseract and app-data.
- **Linux, clean container**: `apt install ./screen-watch_0.7.1_amd64.deb` resolves the dependencies
  (Tesseract along with it); `screen-watch features --json` ok; `xvfb-run -a screen-diff-watcher-gui` opens.
- Window/tray icon in the bundle, the `.desktop` `StartupWMClass`, package size and the SmartScreen
  warning (unsigned `.exe` — signing is out of scope).

---

## 10. Adjusting the `.deb` dependencies (`Depends`)

The current list is in `packaging/linux/control.template`. To check/trim it, run on the target
container and look at the binary's libs:

```bash
ldd dist/screen-watch/screen-watch-gui | grep -E 'not found' || true
ldd dist/screen-watch/screen-watch-gui | awk '{print $1}' | sort -u
```

Keep in `Depends` only what Ubuntu 22.04/24.04 does not ship by default (Qt6/X11/Tesseract/
`xdg-utils`). Sound uses an external player: `Recommends: pulseaudio-utils, alsa-utils`.

---

## 11. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ISCC.exe (Inno Setup) nao encontrado` | Install `choco install innosetup -y` or add Inno to `PATH` (the script also looks in `Program Files (x86)\Inno Setup 6`). |
| `dpkg-deb nao encontrado` | `sudo apt-get install -y dpkg-dev`. |
| PyInstaller fails on Python 3.13 | Update the `build` extra (`pyinstaller>=6.11.1`). |
| "works in the build, fails in the package" (Linux) | `/usr/bin` uses an **`exec` wrapper**, not a symlink: PyInstaller resolves `_internal` through the real path. Do not replace it with a symlink. |
| CI: version guard fails | The tag (without `v`) must be identical to `screen_watch.__version__`. |
| OCR fails on the client | Tesseract missing/language missing; `features --json` shows the path and `--list-langs`. Never use `TESSDATA_PREFIX`. |
| Accented characters in the Windows console | The CLI reconfigures `stdout`/`stderr` to UTF-8 in `_configure_std_streams()`. |

---

## 12. Quick checklist (new increment)

- [ ] `ruff check .` and `python -m pytest -q -m "not integration"` green.
- [ ] `__version__` updated (and no manual `version` in `pyproject`).
- [ ] (If changed) Tesseract pin updated in `packaging/windows/tesseract.json`.
- [ ] (If changed) `python packaging/make_ico.py`.
- [ ] `python scripts/build_release.py --windows|--linux` and smoke test of `features --json`.
- [ ] Green PR (the `package` job) before merging.
- [ ] Tag `vX.Y.Z` = `__version__` to publish the release.
