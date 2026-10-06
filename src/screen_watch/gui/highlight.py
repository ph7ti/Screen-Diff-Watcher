"""Realce temporario da ROI na tela (Qt), sem tocar nos pixels dela.

Uma janela por monitor, *top-most*, **transparente a cliques e foco**
(`WindowTransparentForInput` + `WA_TransparentForMouseEvents`), sem *grabs* e
sem modalidade. Pinta uma camada escura **apenas fora** da ROI (retangulos de
`dim_rects`), uma borda em volta do buraco e o rotulo. Fecha sozinha apos
`duration_ms` via `QTimer`.

Invariante de correcao: nenhum pixel dentro da ROI e pintado, entao o realce
pode rodar com a sessao monitorando sem virar falso positivo.

`rect` chega em espaco **fisico** (mss/pywinctl); o Qt pinta em espaco
**logico**, entao cada janela converte o retangulo com a origem e o dpr do seu
monitor antes de desenhar (doc secao 9.5).

Qt e importado dentro da funcao (CI sem display; doc P12).
"""

from __future__ import annotations

Rect = tuple[int, int, int, int]

# Referencias vivas das janelas abertas: sem isso o coletor do Python poderia
# destruir um widget antes de o timer fechar (nao ha parent Qt).
_ACTIVE: list[object] = []


def show_roi_highlight(rect: Rect, label: str = "", duration_ms: int = 2000) -> None:
    """Destaca `rect` (fisico global) por `duration_ms`; nunca captura entrada."""
    from PyQt6.QtCore import Qt, QTimer  # noqa: PLC0415
    from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen  # noqa: PLC0415
    from PyQt6.QtWidgets import QWidget  # noqa: PLC0415

    from screen_watch.gui.overlay_geometry import (  # noqa: PLC0415
        clip_rect,
        dim_rects,
        rect_to_logical,
    )
    from screen_watch.gui.qt_app import ensure_app  # noqa: PLC0415

    ensure_app()

    dim_color = QColor(0, 0, 0, 110)
    border_color = QColor("#0052d6")
    text_color = QColor(255, 255, 255)
    box_color = QColor(20, 20, 20, 215)

    class _HighlightWindow(QWidget):
        def __init__(self, screen) -> None:
            super().__init__()
            self._screen = screen
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowTransparentForInput
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setGeometry(screen.geometry())
            font = QFont()
            font.setBold(True)
            self._font = font

        def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
            geometry = self.geometry()
            sx, sy = geometry.x(), geometry.y()
            screen_rect = (sx, sy, geometry.width(), geometry.height())
            # Converte o retangulo fisico para o espaco logico deste monitor
            # (doc secao 9.5); com dpr 1.0 a conversao e identidade.
            roi = rect_to_logical(
                rect,
                screen_origin=(sx, sy),
                device_pixel_ratio=float(self._screen.devicePixelRatio()),
            )
            painter = QPainter(self)
            for gx, gy, gw, gh in dim_rects(roi, screen_rect):
                painter.fillRect(gx - sx, gy - sy, gw, gh, dim_color)

            visible = clip_rect(roi, screen_rect)
            if visible is None:
                return
            vx, vy, vw, vh = visible
            # Borda 2 px *fora* do buraco: o traco do QPen fica centrado no
            # caminho, entao o retangulo e expandido para nunca pintar 1 px
            # dentro da ROI (o monitoramento nao pode ver pixels diferentes).
            painter.setPen(QPen(border_color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(vx - sx - 2, vy - sy - 2, vw + 4, vh + 4)
            if not label:
                return

            painter.setFont(self._font)
            metrics = painter.fontMetrics()
            text_w = metrics.horizontalAdvance(label)
            text_h = metrics.height()
            box_w = min(text_w + 16, max(0, self.width()))
            box_h = text_h + 8
            box_x = min(max(0, vx - sx), max(0, self.width() - box_w))
            if vy - sy - box_h - 8 >= 0:  # acima da ROI, fora dela
                box_y = vy - sy - box_h - 8
            else:  # abaixo da ROI, fora dela
                box_y = min(max(0, self.height() - box_h - 2), vy - sy + vh + 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(box_color)
            painter.drawRoundedRect(box_x, box_y, box_w, box_h, 6, 6)
            painter.setPen(text_color)
            painter.drawText(box_x + 8, box_y + 4 + metrics.ascent(), label)

    windows = []
    for screen in QGuiApplication.screens():
        window = _HighlightWindow(screen)
        window.show()
        window.raise_()
        windows.append(window)
    _ACTIVE.extend(windows)

    def _close_all() -> None:
        for window in windows:
            try:
                window.close()
            except RuntimeError:  # pragma: no cover - widget ja destruido
                pass
        for window in windows:
            try:
                _ACTIVE.remove(window)
            except ValueError:
                pass

    QTimer.singleShot(max(1, int(duration_ms)), _close_all)
