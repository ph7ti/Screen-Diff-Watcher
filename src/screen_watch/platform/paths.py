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
import json
import os
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Any

APP_DIR_NAME = "screen_watch"
ENV_HOME = "SCREEN_WATCH_HOME"
CONFIG_FILENAME = "config.yaml"
SELECTIONS_DIRNAME = "selections"
LOGS_DIRNAME = "logs"
SOUNDS_DIRNAME = "sounds"
STATE_FILENAME = "state.json"

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


def sounds_dir() -> Path:
    """Pasta de sons do usuario (``app_home()/sounds``); `file` relativo procura aqui."""
    return app_home() / SOUNDS_DIRNAME


def alerts_log_path() -> Path:
    """Caminho padrao do log de alertas (JSONL) em app-data/logs/."""
    return logs_dir() / "alerts.jsonl"


def actions_log_path() -> Path:
    """Caminho padrao da auditoria de acoes (JSONL) em app-data/logs/."""
    return logs_dir() / "actions.jsonl"


def state_path() -> Path:
    """Estado leve de runtime persistido entre sessoes (doc, secao 12.4)."""
    return app_home() / STATE_FILENAME


def load_state() -> dict[str, Any]:
    """Le `state.json`; ausente ou ilegivel devolve `{}` (estado e best-effort)."""
    path = state_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    """Grava `state.json` de forma atomica (sem backup; estado e descartavel)."""
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def update_state(**fields: Any) -> dict[str, Any]:
    """Mescla `fields` no estado atual e regrava (best-effort)."""
    state = load_state()
    state.update(fields)
    save_state(state)
    return state


def ensure_dirs() -> Path:
    """Cria as pastas de app-data se faltarem e devolve a raiz."""
    home = app_home()
    for path in (home, selections_dir(), logs_dir(), sounds_dir()):
        path.mkdir(parents=True, exist_ok=True)
    return home
