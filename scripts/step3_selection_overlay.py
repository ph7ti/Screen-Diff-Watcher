"""Etapa B: overlay de selecao -> selection JSON (doc, secao 9).

Objetivo: validar a conversao logico<->fisico em 100/125/150%, com a janela
movida entre monitores. Uso:

    .\\.venv\\Scripts\\python.exe scripts\\step3_selection_overlay.py --handle 123456
"""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Overlay de selecao de ROI")
    parser.add_argument("--handle", type=int, required=True, help="handle da janela-alvo")
    parser.add_argument("--name", default=None, help="nome do arquivo de selecao")
    parser.add_argument("--mode", default="advanced", choices=("light", "default", "advanced"))
    args = parser.parse_args()

    from screen_watch.platform.dpi import set_dpi_awareness

    # Antes de qualquer backend de captura/janela/Qt (doc 5.1).
    set_dpi_awareness()

    from screen_watch.cli.commands import _cmd_select

    return _cmd_select(args)


if __name__ == "__main__":
    raise SystemExit(main())
