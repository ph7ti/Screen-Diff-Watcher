"""Gera ``packaging/icons/ScreenDiffWatcher.ico`` a partir dos PNGs do projeto.

O ``.ico`` multi-resolucao e usado pelo PyInstaller (icone do EXE grafico) e pelo
Inno Setup (``SetupIconFile``). Rode na raiz do repositorio::

    python packaging/make_ico.py

Pillow ja e uma dependencia de runtime, entao nao ha etapa extra de instalacao.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PNG = REPO_ROOT / "src" / "screen_watch" / "assets" / "icons" / "ScreenDiffWatcher.png"
OUTPUT_ICO = Path(__file__).resolve().parent / "icons" / "ScreenDiffWatcher.ico"

# Ordem do menor para o maior: o Windows escolhe o melhor por contexto.
SIZES = (16, 24, 32, 48, 64, 128, 256)


def build_ico(source: Path = SOURCE_PNG, output: Path = OUTPUT_ICO) -> Path:
    """Le o PNG base e grava o ``.ico`` multi-resolucao; devolve o caminho gerado."""
    if not source.is_file():
        raise FileNotFoundError(f"PNG base nao encontrado: {source}")
    base = Image.open(source).convert("RGBA")
    output.parent.mkdir(parents=True, exist_ok=True)
    base.save(output, format="ICO", sizes=[(size, size) for size in SIZES])
    return output


def main() -> int:
    path = build_ico()
    print(f"ico gerado: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
