"""Geometria do overlay de selecao (puro, sem Qt) — plano P4/P1, doc secao 9.

O Qt entrega o retangulo arrastado em espaco **logico**; o `mss` e o `pywinctl`
trabalham em espaco **fisico**. Aqui ficam as conversoes, testaveis sem display.

Convencao: `Rect` e `(x, y, w, h)`; `Point` e `(x, y)`.
"""

from __future__ import annotations

MIN_SELECTION_SIDE = 10

Rect = tuple[int, int, int, int]
Point = tuple[int, int]


def normalize_corners(a: Point, b: Point) -> Rect:
    """Retangulo normalizado a partir de dois cantos arrastados."""
    x1, y1 = min(a[0], b[0]), min(a[1], b[1])
    x2, y2 = max(a[0], b[0]), max(a[1], b[1])
    return (x1, y1, x2 - x1, y2 - y1)


def global_from_local(local: Rect, screen_origin: Point) -> Rect:
    return (screen_origin[0] + local[0], screen_origin[1] + local[1], local[2], local[3])


def local_from_global(global_rect: Rect, screen_origin: Point) -> Rect:
    return (
        global_rect[0] - screen_origin[0],
        global_rect[1] - screen_origin[1],
        global_rect[2],
        global_rect[3],
    )


def to_physical(global_logical: Rect, *, screen_origin: Point, device_pixel_ratio: float) -> Rect:
    """Retangulo global logico -> global fisico (doc secao 9.5).

    Ancora na origem da tela: o layout virtual do Windows preserva a origem de
    cada monitor, entao a origem logica da tela e o ponto de ancoragem. Para a
    tela primaria (origem 0,0) equivale ao `x * dpr` do doc.
    """
    local_x = global_logical[0] - screen_origin[0]
    local_y = global_logical[1] - screen_origin[1]
    return (
        screen_origin[0] + int(local_x * device_pixel_ratio),
        screen_origin[1] + int(local_y * device_pixel_ratio),
        int(global_logical[2] * device_pixel_ratio),
        int(global_logical[3] * device_pixel_ratio),
    )


def to_relative(global_physical: Rect, window_origin: Point) -> Rect:
    """Retangulo global fisico -> relativo a janela (doc secao 7.1, passo 6)."""
    return (
        global_physical[0] - window_origin[0],
        global_physical[1] - window_origin[1],
        global_physical[2],
        global_physical[3],
    )


def resolve_ref_point(
    point: Point,
    ref: str,
    *,
    roi_rect: Rect | None = None,
    window_rect: Rect | None = None,
) -> tuple[str, Point]:
    """Ponto global (logico) relativo ao `ref` de uma acao (`roi`/`window`/`screen`).

    Mesma base do `ActionRunner`: `roi` parte de `frame.absolute_rect`, `window` de
    `frame.window_rect`, `screen` da origem (0, 0). Sem a base pedida, cai para
    `screen` e devolve o `ref` efetivo (para o chamador nao gravar um offset
    relativo sem base).
    """
    if ref == "roi" and roi_rect is not None:
        return "roi", (int(point[0] - roi_rect[0]), int(point[1] - roi_rect[1]))
    if ref == "window" and window_rect is not None:
        return "window", (int(point[0] - window_rect[0]), int(point[1] - window_rect[1]))
    return "screen", (int(point[0]), int(point[1]))


def is_valid_selection(rect: Rect, *, min_side: int = MIN_SELECTION_SIDE) -> bool:
    """Area minima em pixels **logicos** (doc secao 9.6)."""
    return rect[2] >= min_side and rect[3] >= min_side


def fits_in_window(relative: Rect, window_size: Point) -> bool:
    """True se a ROI relativa cabe inteiramente na janela (doc secao 9.6)."""
    x, y, w, h = relative
    width, height = window_size
    return x >= 0 and y >= 0 and x + w <= width and y + h <= height
