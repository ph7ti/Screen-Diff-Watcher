"""Abertura de pasta/arquivo no gerenciador padrao do SO (doc, secao 5.2).

Unica porta para abrir caminhos no sistema: `sys.platform` fica restrito a
`platform/`. Best-effort: devolve `False` (com `log.warning`) quando nao houver
associacao de arquivo ou utilitario (`xdg-open`/`open`) disponivel, em vez de
derrubar a GUI/CLI. Stdlib apenas.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _open_startfile(path: str) -> None:
    os.startfile(path)  # type: ignore[attr-defined]  # Windows


def _open_macos(path: str) -> None:
    subprocess.Popen(["open", path])


def _open_linux(path: str) -> None:
    subprocess.Popen(["xdg-open", path])


_OPENERS = {
    "win32": _open_startfile,
    "darwin": _open_macos,
}


def open_path(path: str | Path) -> bool:
    """Abre `path` no gerenciador padrao. True em caso de sucesso, False se falhar."""
    value = str(path)
    opener = _OPENERS.get(sys.platform, _open_linux)
    try:
        opener(value)
    except (OSError, AttributeError) as exc:
        log.warning("nao foi possivel abrir %s: %s", value, exc)
        return False
    return True
