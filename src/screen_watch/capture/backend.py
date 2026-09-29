"""Protocolo do backend de captura. A comparacao nunca ve isto."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from screen_watch.capture.frame import Rect


@runtime_checkable
class ScreenCaptureBackend(Protocol):
    """Captura uma regiao absoluta (espaco fisico) e devolve RGB uint8 (H, W, 3)."""

    def capture(self, rect: Rect) -> np.ndarray: ...

    def close(self) -> None: ...
