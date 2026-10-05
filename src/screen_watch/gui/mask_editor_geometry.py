"""Geometria pura do editor de mascaras (sem Qt) — doc secoes 8.3 e 12.3.

Mascaras vivem em pixels **fisicos relativos a ROI** (`capture/mask.py`); o
overlay do Qt trabalha em espaco **logico local** de cada tela. Aqui ficam as
conversoes, o clamp e o hit-test, testaveis sem display.

Convencao: `Rect` e `(x, y, w, h)`; `Point` e `(x, y)`.
"""

from __future__ import annotations

from collections.abc import Sequence

from screen_watch.gui.overlay_geometry import clip_rect, normalize_corners

MIN_MASK_SIDE = 10

Rect = tuple[int, int, int, int]
Point = tuple[int, int]


def to_global_physical(
    point: Point, *, screen_origin: Point, device_pixel_ratio: float
) -> Point:
    """Ponto global logico -> global fisico (mesma ancora de `overlay_geometry.to_physical`)."""
    return (
        screen_origin[0] + int((point[0] - screen_origin[0]) * device_pixel_ratio),
        screen_origin[1] + int((point[1] - screen_origin[1]) * device_pixel_ratio),
    )


def roi_global_physical(window_rect: Rect, roi_relative: Rect) -> Rect:
    """ROI em fisico global a partir da janela (fisica) + ROI relativa (Modelo B)."""
    return (
        window_rect[0] + roi_relative[0],
        window_rect[1] + roi_relative[1],
        roi_relative[2],
        roi_relative[3],
    )


def roi_local_logical(
    roi_global: Rect, *, screen_origin: Point, device_pixel_ratio: float
) -> Rect:
    """ROI fisico global -> logico local da tela (para desenhar no overlay)."""
    return (
        int((roi_global[0] - screen_origin[0]) / device_pixel_ratio),
        int((roi_global[1] - screen_origin[1]) / device_pixel_ratio),
        int(roi_global[2] / device_pixel_ratio),
        int(roi_global[3] / device_pixel_ratio),
    )


def mask_local_logical(mask: Rect, roi_local: Rect, device_pixel_ratio: float) -> Rect:
    """Mascara fisica relativa a ROI -> logico local (para desenhar no overlay)."""
    return (
        roi_local[0] + int(mask[0] / device_pixel_ratio),
        roi_local[1] + int(mask[1] / device_pixel_ratio),
        int(mask[2] / device_pixel_ratio),
        int(mask[3] / device_pixel_ratio),
    )


def mask_from_drag(
    a: Point,
    b: Point,
    *,
    screen_origin: Point,
    device_pixel_ratio: float,
    roi_global: Rect,
) -> Rect:
    """Drag em logico **local** -> mascara fisica relativa a ROI (pode extrapolar).

    O resultado ainda nao esta limitado a ROI; use `clamp_mask_to_roi` antes de
    aceitar.
    """
    global_logical = normalize_corners(
        (screen_origin[0] + a[0], screen_origin[1] + a[1]),
        (screen_origin[0] + b[0], screen_origin[1] + b[1]),
    )
    x1, y1 = to_global_physical(
        (global_logical[0], global_logical[1]),
        screen_origin=screen_origin,
        device_pixel_ratio=device_pixel_ratio,
    )
    x2, y2 = to_global_physical(
        (global_logical[0] + global_logical[2], global_logical[1] + global_logical[3]),
        screen_origin=screen_origin,
        device_pixel_ratio=device_pixel_ratio,
    )
    return (
        x1 - roi_global[0],
        y1 - roi_global[1],
        max(0, x2 - x1),
        max(0, y2 - y1),
    )


def clamp_mask_to_roi(mask: Rect, roi_size: Point, *, min_side: int = MIN_MASK_SIDE) -> Rect | None:
    """Intersecao com a ROI; `None` se sobrar menos que `min_side` em algum lado."""
    clipped = clip_rect(mask, (0, 0, roi_size[0], roi_size[1]))
    if clipped is None or clipped[2] < min_side or clipped[3] < min_side:
        return None
    return clipped


def contains_point(mask: Rect, point: Point) -> bool:
    x, y, w, h = mask
    return x <= point[0] < x + w and y <= point[1] < y + h


def hit_test_masks(masks: Sequence[Rect], point: Point) -> int | None:
    """Indice da mascara sob `point` (fisico relativo a ROI), do topo para a base."""
    for index in range(len(masks) - 1, -1, -1):
        if contains_point(masks[index], point):
            return index
    return None


def remove_mask_at(masks: Sequence[Rect], index: int) -> tuple[Rect, ...]:
    """Copia da lista sem o item `index` (fora do intervalo devolve copia integral)."""
    return tuple(mask for position, mask in enumerate(masks) if position != index)


def point_in_roi(point: Point, roi_size: Point) -> bool:
    """True se `point` (fisico relativo a ROI) cai dentro da ROI."""
    return 0 <= point[0] < roi_size[0] and 0 <= point[1] < roi_size[1]
