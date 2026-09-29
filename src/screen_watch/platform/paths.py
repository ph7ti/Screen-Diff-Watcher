"""Caminhos em app-data (plano, Etapa A.3).

Base: ``%APPDATA%\\screen_watch`` no Windows, ou o override ``SCREEN_WATCH_HOME``.
Config, selecoes e logs vivem aqui; o YAML nunca guarda segredos.

Python da Microsoft Store (MSIX) redireciona silenciosamente ``%APPDATA%`` para
dentro do pacote, de modo que o arquivo existe para o Python mas nao para o
Explorer/editor. Nesse caso usamos o caminho real do pacote, que e visivel fora
dele.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

APP_DIR_NAME = "screen_watch"
ENV_HOME = "SCREEN_WATCH_HOME"
CONFIG_FILENAME = "config.yaml"
SELECTIONS_DIRNAME = "selections"
LOGS_DIRNAME = "logs"

_ERROR_INSUFFICIENT_BUFFER = 122


def package_family_name() -> str | None:
    """Nome da familia do pacote MSIX atual, ou None se o processo nao for empacotado."""
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        length = wintypes.UINT(0)
        result = kernel32.GetCurrentPackageFamilyName(ctypes.byref(length), None)
        if result != _ERROR_INSUFFICIENT_BUFFER:
            return None
        buffer = ctypes.create_unicode_buffer(length.value)
        result = kernel32.GetCurrentPackageFamilyName(ctypes.byref(length), buffer)
        if result != 0:
            return None
        return buffer.value or None
    except (AttributeError, OSError):
        return None


def _packaged_appdata() -> Path | None:
    """Caminho real de app-data quando o Python e empacotado (Store/MSIX)."""
    family = package_family_name()
    if not family:
        return None
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    package_dir = Path(local) / "Packages" / family
    if not package_dir.is_dir():
        return None
    return package_dir / "LocalCache" / "Roaming" / APP_DIR_NAME


def app_home() -> Path:
    """Diretorio raiz do app: override explicito ou local padrao do SO."""
    override = os.environ.get(ENV_HOME)
    if override:
        return Path(override).expanduser()

    packaged = _packaged_appdata()
    if packaged is not None:
        return packaged

    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


def config_path() -> Path:
    return app_home() / CONFIG_FILENAME


def selections_dir() -> Path:
    return app_home() / SELECTIONS_DIRNAME


def logs_dir() -> Path:
    return app_home() / LOGS_DIRNAME


def ensure_dirs() -> Path:
    """Cria as pastas de app-data se faltarem e devolve a raiz."""
    home = app_home()
    for path in (home, selections_dir(), logs_dir()):
        path.mkdir(parents=True, exist_ok=True)
    return home
