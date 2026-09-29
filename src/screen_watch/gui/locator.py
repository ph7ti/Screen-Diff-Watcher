"""Localizador de posicao do mouse para o editor de acoes (Qt).

Mostra uma caixa com X/Y seguindo o cursor (valores ja no `ref` escolhido, alem do
absoluto). `Enter`/clique esquerdo confirma; `Esc`/clique direito cancela. Devolve
o ponto global **logico** (a mesma base do `Frame`); o chamador converte pelo `ref`
via `overlay_geometry.resolve_ref_point`.

O localizador e aberto **de dentro do dialogo do editor**, que esta em `exec()` (modal
de aplicacao) — por isso a janela precisa ser filha do dialogo (imune a modalidade) e
capturar teclado/mouse explicitamente; sem isso, Enter/Esc/cliques nao chegam ao
overlay (o pop-up aparece, mas nao responde). Qt e importado dentro da funcao (CI sem
display); sem Qt devolve `None` (o chamador segue digitando os valores).
"""

from __future__ import annotations

from collections.abc import Callable

Rect = tuple[int, int, int, int]


def run_locator(
    ref: str = "screen",
    *,
    roi_rect: Rect | None = None,
    window_rect: Rect | None = None,
    screen=None,
    parent=None,
    status: Callable[[str], None] | None = None,
) -> tuple[int, int] | None:
    """Devolve o ponto global (logico) confirmado, ou `None` se cancelado/sem Qt."""
    try:
        from PyQt6.QtCore import QEventLoop, Qt, QTimer  # noqa: PLC0415
        from PyQt6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter  # noqa: PLC0415
        from PyQt6.QtWidgets import QWidget  # noqa: PLC0415

        from screen_watch.gui.overlay_geometry import resolve_ref_point  # noqa: PLC0415
        from screen_watch.gui.qt_app import ensure_app  # noqa: PLC0415

        ensure_app()
    except Exception:
        return None

    result: dict[str, tuple[int, int] | None] = {"point": None}

    class _Locator(QWidget):
        def __init__(self) -> None:
            # Filho do dialogo modal: janelas filhas recebem entrada mesmo com o
            # dialogo em exec() (application-modal).
            super().__init__(parent)
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setCursor(Qt.CursorShape.CrossCursor)
            target = screen or QGuiApplication.primaryScreen()
            self.setGeometry(target.virtualGeometry() if target else self.geometry())
            self._font = QFont()
            self._font.setPointSize(12)
            self._font.setBold(True)

        def _paint(self) -> None:
            point = QCursor.pos()
            effective_ref, relative = resolve_ref_point(
                (point.x(), point.y()), ref, roi_rect=roi_rect, window_rect=window_rect
            )
            self._rel = (effective_ref, relative)
            self._abs = (point.x(), point.y())
            self.update()

        def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
            if not hasattr(self, "_rel"):
                return
            effective_ref, (rel_x, rel_y) = self._rel
            abs_x, abs_y = self._abs
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            cursor = QCursor.pos()
            origin = self.geometry().topLeft()
            local_x = cursor.x() - origin.x()
            local_y = cursor.y() - origin.y()
            lines = [
                f"X {rel_x}  Y {rel_y}   ({effective_ref})",
                f"abs {abs_x},{abs_y}",
                "Enter confirma · Esc cancela",
            ]
            painter.setFont(self._font)
            metrics = painter.fontMetrics()
            width = max(metrics.horizontalAdvance(line) for line in lines) + 24
            height = metrics.height() * len(lines) + 16
            box_x = min(max(0, local_x + 18), max(0, self.width() - width))
            box_y = min(max(0, local_y + 18), max(0, self.height() - height))
            painter.setBrush(QColor(20, 20, 20, 215))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(box_x, box_y, width, height, 8, 8)
            painter.setPen(QColor(255, 255, 255))
            text_y = box_y + 12 + metrics.ascent()
            for line in lines:
                painter.drawText(box_x + 12, text_y, line)
                text_y += metrics.height()

        def keyPressEvent(self, event) -> None:  # noqa: N802 - API do Qt
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                pos = QCursor.pos()
                result["point"] = (pos.x(), pos.y())
                loop.quit()
            elif event.key() == Qt.Key.Key_Escape:
                result["point"] = None
                loop.quit()

        def mousePressEvent(self, event) -> None:  # noqa: N802 - API do Qt
            pos = QCursor.pos()
            if event.button() == Qt.MouseButton.LeftButton:
                result["point"] = (pos.x(), pos.y())
                loop.quit()
            elif event.button() == Qt.MouseButton.RightButton:
                result["point"] = None
                loop.quit()

    loop = QEventLoop()
    widget = _Locator()
    widget.show()
    widget.raise_()
    widget.activateWindow()
    widget.setFocus()
    # Grabs explicitas: garantem teclado/mouse no overlay mesmo sem foco de janela.
    widget.grabKeyboard()
    widget.grabMouse()
    timer = QTimer()
    timer.setInterval(30)
    timer.timeout.connect(widget._paint)
    timer.start()
    widget._paint()
    if status is not None:
        status("localize o ponto e pressione Enter (Esc cancela)")
    try:
        loop.exec()
    finally:
        timer.stop()
        widget.releaseMouse()
        widget.releaseKeyboard()
        widget.close()
    return result["point"]
