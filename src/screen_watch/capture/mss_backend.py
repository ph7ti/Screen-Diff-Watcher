"""Backend `mss` — unico backend do prototipo (doc, secao 3.2).

A instancia de `mss` e criada uma vez e reutilizada (nunca por tick). Ela nao e
thread-safe: o `MonitorLoop` cria o backend dentro da propria thread.
"""

from __future__ import annotations

import mss
import numpy as np

from screen_watch.capture.frame import Rect


def open_mss():
    """Instancia o `mss` de forma compativel (`mss.MSS` novo, `mss.mss` legado)."""
    factory = getattr(mss, "MSS", None) or mss.mss
    return factory()


class MssCaptureBackend:
    def __init__(self) -> None:
        self._sct = open_mss()

    def bounds(self) -> Rect:
        """Retangulo do desktop virtual (fisico), incluindo coordenadas negativas."""
        monitor = self._sct.monitors[0]
        return (
            int(monitor["left"]),
            int(monitor["top"]),
            int(monitor["width"]),
            int(monitor["height"]),
        )

    def capture(self, rect: Rect) -> np.ndarray:
        x, y, w, h = rect
        if w <= 0 or h <= 0:
            raise ValueError(f"rect invalido: {rect!r}")
        shot = self._sct.grab({"left": x, "top": y, "width": w, "height": h})
        bgra = np.asarray(shot, dtype=np.uint8)
        rgb = bgra[:, :, [2, 1, 0]]
        return np.ascontiguousarray(rgb)

    def close(self) -> None:
        self._sct.close()
