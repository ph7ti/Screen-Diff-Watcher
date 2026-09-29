"""Resolve janela + ROI relativa -> ROI absoluta (Modelo B, doc secao 3.3).

`abs = roi_relative + window_rect.topLeft()`, seguido da conversao de espaco
logico para fisico quando um conversor e fornecido.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from screen_watch.capture.frame import Rect

if TYPE_CHECKING:
    from screen_watch.platform.window import WindowInfo

LogicalToPhysical = Callable[[int, int, int, int], tuple[int, int, int, int]]


def identity_converter(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    """Conversor padrao. Com DPI awareness + PassThrough, dpr costuma ser 1.0."""
    return (x, y, w, h)


def resolve(
    window_info: "WindowInfo | None",
    roi_relative: Rect,
    *,
    logical_to_physical: LogicalToPhysical | None = None,
) -> Rect | None:
    """Devolve a ROI absoluta em espaco fisico, ou None se nao houver o que capturar.

    None cobre: janela ausente, janela minimizada (rect e lixo) e ROI degenerada.
    """
    if window_info is None or not window_info.exists or window_info.is_minimized:
        return None

    win_x, win_y, _win_w, _win_h = window_info.rect
    rx, ry, rw, rh = roi_relative
    x, y = win_x + rx, win_y + ry
    w, h = rw, rh

    converter = logical_to_physical or identity_converter
    x, y, w, h = converter(x, y, w, h)

    x, y, w, h = int(x), int(y), int(w), int(h)
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)
