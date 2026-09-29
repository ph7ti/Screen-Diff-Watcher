"""Mascara de regioes volateis dentro da ROI (doc, secao 8).

Retangulos sao relativos a ROI e sobrevivem a mover a janela. Pinta preto (0,0,0),
que e neutro para phash/mean color e nao gera texto fantasma no OCR.
"""

from __future__ import annotations

import numpy as np

Rect = tuple[int, int, int, int]


def apply_mask(rgb: np.ndarray, masks: "list[Rect] | tuple[Rect, ...]") -> np.ndarray:
    out = rgb.copy()
    height, width = out.shape[:2]
    for (x, y, w, h) in masks:
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(width, int(x) + int(w)), min(height, int(y) + int(h))
        if x1 > x0 and y1 > y0:
            out[y0:y1, x0:x1] = 0
    return out
