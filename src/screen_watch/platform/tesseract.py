"""Localizacao do executavel do Tesseract (plano P8).

Fronteira de plataforma: `compare/` nao deve conhecer `sys.platform` nem caminhos
de SO. Ordem de busca: caminho explicito da config > PATH > diretorios de
instalacao mais comuns do SO.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _common_dirs() -> list[Path]:
    if sys.platform == "win32":
        bases = (
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LOCALAPPDATA"),
        )
        dirs: list[Path] = []
        for base in bases:
            if not base:
                continue
            dirs.append(Path(base) / "Tesseract-OCR")
            dirs.append(Path(base) / "Programs" / "Tesseract-OCR")
        return dirs
    if sys.platform == "darwin":
        return [Path("/usr/local/bin"), Path("/opt/homebrew/bin"), Path("/opt/local/bin")]
    return [Path("/usr/bin"), Path("/usr/local/bin"), Path("/snap/bin")]


def resolve_tesseract_cmd(configured: str | None = None) -> str | None:
    """Devolve o executavel do Tesseract ou None.

    Nao usa caminho fixo de uma maquina: procura no PATH e nos diretorios comuns
    do SO atual, sempre atras desta fronteira.
    """
    if configured:
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    executable = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    for directory in _common_dirs():
        candidate = directory / executable
        if candidate.is_file():
            return str(candidate)
    return None
