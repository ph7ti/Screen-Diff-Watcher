"""Resolucao de janela + ROI para captura e realce (sem Qt).

Ponto unico da regra `window_rect.topLeft() + roi_relative` (doc, secao 3.3):
o mesmo caminho alimenta o `_capture_target_roi` (tick/testes do CLI) e o
"Ver local" da GUI, entao o retangulo destacado e exatamente o capturado.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_watch.capture.resolver import Rect
from screen_watch.errors import AppError

if TYPE_CHECKING:
    from screen_watch.persistence.selection import Selection
    from screen_watch.platform.window import WindowInfo


def resolve_window_roi(
    window_handle: int, roi_relative: Rect
) -> tuple["WindowInfo", Rect]:
    """Devolve `(janela, ROI absoluta)`; `AppError` se nao houver o que capturar.

    Codigos: `runtime.window_not_found` (sumiu), `runtime.window_minimized` e
    `runtime.roi_invalid` (degenerada).
    """
    from screen_watch.capture.resolver import resolve  # noqa: PLC0415
    from screen_watch.platform.window import find_window_by_handle  # noqa: PLC0415

    info = find_window_by_handle(int(window_handle))
    if info is None or not info.exists:
        raise AppError(
            code="runtime.window_not_found", params={"handle": window_handle}
        )
    if info.is_minimized:
        raise AppError(code="runtime.window_minimized")
    abs_rect = resolve(info, roi_relative)
    if abs_rect is None:
        raise AppError(code="runtime.roi_invalid")
    return info, abs_rect


def absolute_roi_for_selection(selection: "Selection") -> Rect | None:
    """ROI absoluta da selecao, ou `None` (janela ausente/minimizada/ROI invalida)."""
    try:
        _info, rect = resolve_window_roi(selection.window_handle, selection.roi_relative)
    except AppError:
        return None
    return rect


def roi_unavailable_error(selection: "Selection") -> AppError:
    """`AppError` explicando por que `absolute_roi_for_selection` devolveu None."""
    from screen_watch.platform.window import find_window_by_handle  # noqa: PLC0415

    info = find_window_by_handle(int(selection.window_handle))
    if info is None or not info.exists:
        return AppError(
            code="runtime.window_not_found", params={"handle": selection.window_handle}
        )
    if info.is_minimized:
        return AppError(code="runtime.window_minimized")
    return AppError(code="runtime.roi_invalid")
