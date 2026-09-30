"""Escala (DPI) por monitor — mitigacao inicial do P1.

Detecta a escala de cada monitor para indicar quais sao seguros (100%). A
conversao logico->fisico definitiva fica para a Etapa B; aqui fica apenas a
verificacao de inicializacao que avisa onde a ROI pode sofrer deslocamento.

Qt e importado de forma preguicosa: a coleta de testes nao depende de PyQt6.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

Rect = tuple[int, int, int, int]

# Mantem o QApplication vivo: sem referencia explicita o Qt pode ser coletado e
# derrubar o processo. Reutilizado se a GUI (Etapa G) criar o seu.
_QT_APP: object | None = None


@dataclass(frozen=True)
class MonitorScale:
    name: str
    rect: Rect  # (x, y, w, h) em espaco logico
    device_pixel_ratio: float
    is_primary: bool = False

    @property
    def is_suitable(self) -> bool:
        return abs(self.device_pixel_ratio - 1.0) < 1e-6

    @property
    def scale_percent(self) -> int:
        return round(self.device_pixel_ratio * 100)

    def contains(self, x: int, y: int) -> bool:
        rx, ry, rw, rh = self.rect
        return rx <= x < rx + rw and ry <= y < ry + rh


def display_available() -> bool:
    """False sem sessao grafica (ex.: Linux headless, sem X11 nem Wayland).

    Criar um `QApplication` sem display derruba o processo no Qt, entao a
    verificacao precisa vir antes (usada por `features` e pelos probes).
    """
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def list_monitor_scales() -> list[MonitorScale] | None:
    """Escalas por monitor via Qt, ou None se o PyQt6/display nao estiver disponivel."""
    global _QT_APP
    if not display_available():
        return None
    try:
        from PyQt6.QtWidgets import QApplication  # noqa: PLC0415
    except Exception:
        return None

    app = QApplication.instance() or QApplication([])
    _QT_APP = app
    primary = app.primaryScreen()

    scales: list[MonitorScale] = []
    for screen in app.screens():
        geometry = screen.geometry()
        scales.append(
            MonitorScale(
                name=screen.name(),
                rect=(geometry.x(), geometry.y(), geometry.width(), geometry.height()),
                device_pixel_ratio=float(screen.devicePixelRatio()),
                is_primary=(screen is primary),
            )
        )
    return scales


def suitable_monitors(scales: list[MonitorScale]) -> list[MonitorScale]:
    return [scale for scale in scales if scale.is_suitable]


def monitor_for_rect(scales: list[MonitorScale], rect: Rect) -> MonitorScale | None:
    """Monitor que contem o centro da janela; senao o primeiro com interseccao."""
    x, y, w, h = rect
    center_x, center_y = x + w // 2, y + h // 2
    for scale in scales:
        if scale.contains(center_x, center_y):
            return scale
    for scale in scales:
        rx, ry, rw, rh = scale.rect
        if not (x + w <= rx or rx + rw <= x or y + h <= ry or ry + rh <= y):
            return scale
    return None


def describe_scales(scales: list[MonitorScale]) -> list[str]:
    lines = []
    for scale in scales:
        mark = "OK " if scale.is_suitable else "!! "
        primary = " (primario)" if scale.is_primary else ""
        lines.append(f"  {mark}{scale.name!r} escala {scale.scale_percent}%{primary}")
    return lines
