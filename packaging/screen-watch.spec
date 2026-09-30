# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller (onedir) com dois executaveis.

Um unico `Analysis` produz dois `EXE` (`screen-watch` console e
`screen-watch-gui` sem console) que compartilham o mesmo `PYZ`/`COLLECT`.

Nota: se os dois scripts de entrada fossem passados inteiros a cada `EXE`, o
bootloader executaria os dois em sequencia. Por isso `a.scripts` e filtrado para
manter os runtime hooks e apenas a entrada de cada executavel.

Rode com ``scripts/build_release.py`` (nao diretamente): ele define a versao e o
diretorio de saida.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).resolve().parent
SRC = PROJECT_ROOT / "src"
PACKAGE = SRC / "screen_watch"
ICON = PROJECT_ROOT / "packaging" / "icons" / "ScreenDiffWatcher.ico"

CLI_ENTRY = "__main__"
GUI_ENTRY = "gui_main"


def _collect(name):
    """Submodulos de um pacote opcional, sem quebrar se ele nao estiver instalado."""
    try:
        return collect_submodules(name)
    except Exception:
        return []


# `pystray`/`pynput`/`plyer`/`pywinctl`/`mss` escolhem backend por import dinamico.
hiddenimports = []
for module in ("pynput", "pystray", "plyer", "pywinctl", "pymonctl", "mss"):
    hiddenimports += _collect(module)

if sys.platform == "win32":
    hiddenimports += ["plyer.platforms.win.notification"]
else:
    hiddenimports += ["plyer.platforms.linux.notification", "Xlib.ext.randr"]

datas = [
    (str(PACKAGE / "assets" / "icons"), "screen_watch/assets/icons"),
    (str(PACKAGE / "i18n"), "screen_watch/i18n"),
]

# `simpleaudio` foi deliberadamente excluido do bundle (sem wheel confiavel no
# 3.13); o extra segue instalavel a mao. `build/` e `dev` nao entram.
excludes = [
    "pytest",
    "ruff",
    "simpleaudio",
    "tkinter",
    "IPython",
    "setuptools",
    "pip",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineQuick",
]

a = Analysis(
    [str(PACKAGE / "__main__.py"), str(PACKAGE / "gui_main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

# Runtime hooks + o unico script de entrada de cada EXE.
_runtime_hooks = [entry for entry in a.scripts if entry[0] not in (CLI_ENTRY, GUI_ENTRY)]


def _entry(name):
    return _runtime_hooks + [entry for entry in a.scripts if entry[0] == name]


icon = str(ICON) if sys.platform == "win32" and ICON.is_file() else None

exe_cli = EXE(
    pyz,
    _entry(CLI_ENTRY),
    exclude_binaries=True,
    name="screen-watch",
    console=True,
    icon=icon,
)

exe_gui = EXE(
    pyz,
    _entry(GUI_ENTRY),
    exclude_binaries=True,
    name="screen-watch-gui",
    console=False,
    icon=icon,
)

coll = COLLECT(
    exe_cli,
    exe_gui,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="screen-watch",
)
