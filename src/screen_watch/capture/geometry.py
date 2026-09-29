"""Geometria de retangulos para captura (pura, testavel sem display).

Usado para recortar a ROI contra o desktop virtual (doc secao 7.2, P5): `mss`
trabalha no espaco fisico e pode receber retangulos parcialmente fora da tela
(coordenadas negativas ou maximizadas).
"""

from __future__ import annotations

Rect = tuple[int, int, int, int]


def intersect_rect(rect: Rect, bounds: Rect) -> Rect | None:
    """Intersecao de `rect` com `bounds`, ou None se nao houver area comum."""
    x1 = max(rect[0], bounds[0])
    y1 = max(rect[1], bounds[1])
    x2 = min(rect[0] + rect[2], bounds[0] + bounds[2])
    y2 = min(rect[1] + rect[3], bounds[1] + bounds[3])
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2 - x1, y2 - y1)
