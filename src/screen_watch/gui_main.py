"""Entrada do executavel grafico sem console (`screen-watch-gui`).

Espelha o subcomando `gui` do CLI, mas e um modulo proprio para o PyInstaller ter
um script de entrada `console=False`. `set_dpi_awareness()` roda antes de
qualquer import de Qt (doc, secao 5.1); Qt e importado de forma preguicosa.
"""

from __future__ import annotations

import argparse

from screen_watch.platform.dpi import is_wayland, set_dpi_awareness
from screen_watch.platform.paths import config_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="screen-watch-gui", description="Screen Diff Watcher (GUI)"
    )
    parser.add_argument("--config", default=str(config_path()), help="path to the config YAML")
    parser.add_argument("--profile", default=None, help="active profile (default: the YAML one)")
    parser.add_argument(
        "--language",
        default=None,
        help="GUI language: a discovered tag (e.g. pt-BR, en-US) or 'auto' (default: auto)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    set_dpi_awareness()
    if is_wayland():
        print("Wayland detected: the Qt GUI is not supported in this prototype.")
        return 2
    from screen_watch.__main__ import _resolve_language  # noqa: PLC0415
    from screen_watch.gui.main_window import run_gui  # noqa: PLC0415

    _resolve_language(args)
    return run_gui(args.config, profile=args.profile)


if __name__ == "__main__":
    raise SystemExit(main())
