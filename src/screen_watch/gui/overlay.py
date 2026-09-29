"""Overlay de selecao em PyQt6 (doc, secao 9).

Uma janela por monitor (doc 9.1). Botao esquerdo arrasta; botao direito cancela.
O resultado e o retangulo em coordenadas **logicas globais** mais a tela de
origem e seu `device_pixel_ratio`, para a conversao logico->fisico em
`overlay_geometry.to_physical` (doc 9.5).

Importado apenas de forma preguicosa pelo CLI: a coleta de testes nao depende de
Qt (doc P12).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QEventLoop, QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from screen_watch.gui.overlay_geometry import (
    global_from_local,
    is_valid_selection,
    normalize_corners,
)

Rect = tuple[int, int, int, int]
Point = tuple[int, int]

# Mantem o QApplication vivo quando o CLI cria um (a GUI reutiliza o existente).
_QT_APP: QApplication | None = None


@dataclass(frozen=True)
class SelectionResult:
    global_logical: Rect
    screen_origin: Point
    device_pixel_ratio: float
    screen_name: str


class SelectionOverlay(QWidget):
    def __init__(self, screen, controller: "_OverlayController") -> None:
        super().__init__()
        self._screen = screen
        self._controller = controller
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        if self._origin is not None and self._current is not None:
            selection = QRect(self._origin, self._current).normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(selection, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor("#0052d6"), 2))
            painter.drawRect(selection)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if event.button() == Qt.MouseButton.RightButton:
            self._controller.cancel()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if self._origin is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if (
            event.button() != Qt.MouseButton.LeftButton
            or self._origin is None
            or self._current is None
        ):
            return
        rect = normalize_corners(
            (self._origin.x(), self._origin.y()), (self._current.x(), self._current.y())
        )
        origin = self._screen.geometry().topLeft()
        screen_origin = (origin.x(), origin.y())
        global_logical = global_from_local(rect, screen_origin)
        if not is_valid_selection(global_logical):
            return  # muito pequeno: ignora e deixa o usuario arrastar de novo
        self._controller.finish(
            SelectionResult(
                global_logical=global_logical,
                screen_origin=screen_origin,
                device_pixel_ratio=float(self._screen.devicePixelRatio()),
                screen_name=self._screen.name(),
            )
        )


class _OverlayController:
    def __init__(self, quit_loop: Callable[[], None]) -> None:
        self._quit_loop = quit_loop
        self._overlays: list[SelectionOverlay] = []
        self.result: SelectionResult | None = None

    def build(self) -> list[SelectionOverlay]:
        self._overlays = [
            SelectionOverlay(screen, self) for screen in QGuiApplication.screens()
        ]
        return self._overlays

    def finish(self, result: SelectionResult) -> None:
        self.result = result
        self._close_all()

    def cancel(self) -> None:
        self.result = None
        self._close_all()

    def _close_all(self) -> None:
        for overlay in self._overlays:
            overlay.close()
        self._quit_loop()


def run_selection() -> SelectionResult | None:
    """Mostra o overlay em cada monitor e devolve a selecao (None se cancelar).

    Usa um `QEventLoop` proprio (nao `app.exec()`), para poder ser chamado de
    dentro da GUI sem encerrar o loop principal.
    """
    global _QT_APP

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
        _QT_APP = app

    loop = QEventLoop()
    controller = _OverlayController(loop.quit)
    for overlay in controller.build():
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
    loop.exec()
    return controller.result
