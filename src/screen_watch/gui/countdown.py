"""Contagem regressiva antes de gravar/executar acoes (plano, Fase C).

Overlay **sem foco**: o usuario precisa focar a janela-alvo durante a contagem,
por isso nao chamamos `activateWindow()` e usamos `WindowDoesNotAcceptFocus`.
Cancelar e um clique esquerdo no overlay. Sem Qt/display (headless/Wayland),
cai numa contagem textual no console e devolve `True`. Qt e importado dentro da
funcao (CI coleta sem display).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

BORDER_MARGIN = 40
DEFAULT_SECONDS = 3.0

# Mantido para os testes injetarem um sleep falso.
_sleep = time.sleep


def _console_countdown(seconds: float, status: Callable[[str], None] = print) -> None:
    remaining = max(0, int(math.ceil(float(seconds))))
    for value in range(remaining, 0, -1):
        status(f"  {value}...")
        _sleep(1.0)


def run_countdown(
    seconds: float = DEFAULT_SECONDS, message: str = "Prepare-se...", screen=None
) -> bool:
    """Conta `seconds`..1 no topo-centro. True se terminou; False se cancelado.

    `screen` e um `QScreen` (opcional); sem ele usa o monitor primario. Nunca
    rouba foco: a janela-alvo pode ser focada durante a contagem.
    """
    try:
        from PyQt6.QtCore import QEventLoop, Qt, QTimer  # noqa: PLC0415
        from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter  # noqa: PLC0415
        from PyQt6.QtWidgets import QWidget  # noqa: PLC0415

        from screen_watch.gui.qt_app import ensure_app  # noqa: PLC0415

        ensure_app()
    except Exception:
        _console_countdown(seconds)
        return True

    duration = max(0.0, float(seconds))
    state = {"remaining": int(math.ceil(duration)), "cancelled": False}

    class _CountdownOverlay(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowDoesNotAcceptFocus
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setFixedSize(260, 140)
            self._center()

        def _center(self) -> None:
            target = screen or QGuiApplication.primaryScreen()
            if target is None:
                return
            geometry = target.availableGeometry()
            x = geometry.center().x() - self.width() // 2
            y = geometry.top() + BORDER_MARGIN
            self.move(x, y)

        def set_remaining(self, value: int) -> None:
            state["remaining"] = value
            self.update()

        def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(20, 20, 20, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect(), 16, 16)
            painter.setPen(QColor(255, 255, 255))
            number_font = QFont()
            number_font.setPointSize(48)
            number_font.setBold(True)
            painter.setFont(number_font)
            painter.drawText(
                self.rect().adjusted(0, 10, 0, 0),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                str(max(0, state["remaining"])),
            )
            message_font = QFont()
            message_font.setPointSize(11)
            painter.setFont(message_font)
            painter.drawText(
                self.rect().adjusted(0, 0, 0, -14),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
                message,
            )

        def mousePressEvent(self, event) -> None:  # noqa: N802 - API do Qt
            if event.button() == Qt.MouseButton.LeftButton:
                cancel()

        def keyPressEvent(self, event) -> None:  # noqa: N802 - API do Qt
            if event.key() == Qt.Key.Key_Escape:
                cancel()

    loop = QEventLoop()
    overlay = _CountdownOverlay()
    timer = QTimer()

    def cancel() -> None:
        state["cancelled"] = True
        timer.stop()
        loop.quit()

    started = time.monotonic()

    def _tick() -> None:
        elapsed = time.monotonic() - started
        overlay.set_remaining(int(math.ceil(duration - elapsed)))
        if elapsed >= duration:
            timer.stop()
            loop.quit()

    timer.setInterval(100)
    timer.timeout.connect(_tick)
    overlay.show()
    timer.start()
    _tick()
    loop.exec()
    timer.stop()
    overlay.close()
    return not state["cancelled"]
