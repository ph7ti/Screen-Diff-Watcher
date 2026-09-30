"""Entry point: `python -m screen_watch <comando>`.

`set_dpi_awareness()` e a primeira coisa executada, antes de qualquer backend de
captura, janela Qt ou chamada a `pywinctl` (doc, secao 5.1).
"""

from __future__ import annotations

import logging

from screen_watch.cli.commands import _configure_std_streams, _resolve_language
from screen_watch.cli.parser import build_parser
from screen_watch.platform.dpi import set_dpi_awareness


def main(argv: list[str] | None = None) -> int:
    set_dpi_awareness()
    _configure_std_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _resolve_language(args)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
