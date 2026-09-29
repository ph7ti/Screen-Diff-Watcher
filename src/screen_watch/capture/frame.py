"""Contrato de dados entre captura e comparacao (doc, secao 6)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Rect = tuple[int, int, int, int]  # (x, y, w, h)


@dataclass(frozen=True)
class Frame:
    rgb: np.ndarray  # (H, W, 3) uint8, ordem RGB, ja mascarado
    timestamp: float
    absolute_rect: Rect  # espaco fisico (mss / debug)
    window_rect: Rect  # espaco logico (debug)
    window_handle: int
    sequence: int  # monotono por sessao; descarta frames obsoletos
