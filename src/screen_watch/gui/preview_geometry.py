"""Reducao pura de frames para o preview da GUI (sem Qt) — doc secao 3.7."""

from __future__ import annotations

import numpy as np


def downsample(rgb: np.ndarray, max_side: int = 240) -> np.ndarray:
    """Copia reduzida por passo inteiro com no maximo `max_side` no maior lado.

    Sempre devolve um array novo: a GUI pode guardar/desenhar sem tocar no buffer
    da thread do loop.
    """
    height, width = rgb.shape[:2]
    longest = max(height, width)
    step = max(1, -(-longest // max_side))
    return np.array(rgb[::step, ::step], copy=True)
