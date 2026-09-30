"""Filtro Qt de ajuda no hover (>2 s) da GUI (plano GUI/UX, F6).

So a GUI importa este modulo (Qt no topo); `gui/help.py` continua puro.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QToolTip, QWidget

from screen_watch.gui.help import build_help_html

HOVER_DELAY_MS = 2000


class HoverHelpFilter(QObject):
    """Mostra um tooltip HTML apos `delay_ms` com o mouse parado sobre o widget."""

    def __init__(self, widget: QWidget, key: str, *, delay_ms: int = HOVER_DELAY_MS) -> None:
        super().__init__(widget)
        self._widget = widget
        self._key = key
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._show)
        widget.setAccessibleName(key)

    def eventFilter(self, _obj, event) -> bool:  # noqa: N802 - API do Qt
        kind = event.type()
        if kind == QEvent.Type.Enter:
            self._timer.start()
        elif kind in (
            QEvent.Type.Leave,
            QEvent.Type.FocusOut,
            QEvent.Type.MouseButtonPress,
        ):
            self._timer.stop()
            QToolTip.hideText()
        return False

    def _show(self) -> None:
        html = build_help_html(self._key)
        if html:
            QToolTip.showText(QCursor.pos(), html, self._widget)


def attach_help(widget: QWidget, key: str, *, delay_ms: int = HOVER_DELAY_MS) -> HoverHelpFilter:
    """Instala o filtro em `widget`; mantenha a referencia devolvida viva."""
    filter_ = HoverHelpFilter(widget, key, delay_ms=delay_ms)
    widget.installEventFilter(filter_)
    return filter_
