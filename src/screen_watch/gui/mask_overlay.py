"""Editor visual de mascaras em PyQt6 (doc, secao 8.3).

Uma janela por monitor, no mesmo padrao visual do overlay de selecao: escurece
apenas fora da ROI, desenha a borda da ROI e as mascaras efetivas. Arrastar com
o botao esquerdo adiciona uma mascara; clique direito remove a mascara sob o
cursor; Enter confirma (retorna a lista) e Esc cancela (None). O chamador deve
bloquear a edicao com sessao rodando (a GUI mostra o aviso antes de chamar).

Importado apenas de forma preguicosa pela GUI: a coleta de testes nao depende de
Qt (doc P12).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PyQt6.QtCore import QEventLoop, QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QKeyEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from screen_watch.gui.mask_editor_geometry import (
    Rect,
    clamp_mask_to_roi,
    hit_test_masks,
    mask_from_drag,
    mask_local_logical,
    remove_mask_at,
    roi_global_physical,
    roi_local_logical,
    to_global_physical,
)
from screen_watch.gui.overlay_geometry import dim_rects
from screen_watch.i18n import tr

Point = tuple[int, int]

ROI_COLOR = "#0052d6"
DIM_COLOR = QColor(0, 0, 0, 90)
MASK_FILL = QColor(214, 45, 32, 110)
MASK_BORDER = QColor("#d62d20")
DRAG_BORDER = QColor("#e67e00")


class MaskEditorOverlay(QWidget):
    def __init__(
        self,
        screen,
        controller: "_MaskEditorController",
        roi_global: Rect,
    ) -> None:
        super().__init__()
        self._screen = screen
        self._controller = controller
        self._roi_global = roi_global
        origin = screen.geometry().topLeft()
        self._screen_origin: Point = (origin.x(), origin.y())
        self._dpr = float(screen.devicePixelRatio())
        self._roi_local = roi_local_logical(
            roi_global,
            screen_origin=self._screen_origin,
            device_pixel_ratio=self._dpr,
        )
        self._drag_origin: QPoint | None = None
        self._drag_current: QPoint | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(screen.geometry())

    @property
    def roi_size(self) -> Point:
        return (self._roi_global[2], self._roi_global[3])

    def _to_roi_physical(self, point: QPoint) -> Point:
        global_physical = to_global_physical(
            (self._screen_origin[0] + point.x(), self._screen_origin[1] + point.y()),
            screen_origin=self._screen_origin,
            device_pixel_ratio=self._dpr,
        )
        return (
            global_physical[0] - self._roi_global[0],
            global_physical[1] - self._roi_global[1],
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        painter = QPainter(self)
        screen_rect = (0, 0, self.width(), self.height())
        for rect in dim_rects(self._roi_local, screen_rect):
            painter.fillRect(QRect(*rect), DIM_COLOR)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(ROI_COLOR), 2))
        painter.drawRect(QRect(*self._roi_local))
        for mask in self._controller.masks:
            local = mask_local_logical(mask, self._roi_local, self._dpr)
            painter.fillRect(QRect(*local), MASK_FILL)
            painter.setPen(QPen(MASK_BORDER, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(*local))
        if self._drag_origin is not None and self._drag_current is not None:
            drag = QRect(self._drag_origin, self._drag_current).normalized()
            painter.setPen(QPen(DRAG_BORDER, 1, Qt.PenStyle.DashLine))
            painter.drawRect(drag)
        painter.setPen(QColor("white"))
        painter.drawText(12, 24, tr("overlay_masks.title"))
        painter.drawText(12, 44, tr("overlay_masks.hint"))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if event.button() == Qt.MouseButton.RightButton:
            index = hit_test_masks(
                self._controller.masks, self._to_roi_physical(event.position().toPoint())
            )
            if index is not None:
                self._controller.remove_at(index)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.position().toPoint()
            self._drag_current = self._drag_origin
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if self._drag_origin is not None:
            self._drag_current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if (
            event.button() != Qt.MouseButton.LeftButton
            or self._drag_origin is None
            or self._drag_current is None
        ):
            return
        mask = mask_from_drag(
            (self._drag_origin.x(), self._drag_origin.y()),
            (self._drag_current.x(), self._drag_current.y()),
            screen_origin=self._screen_origin,
            device_pixel_ratio=self._dpr,
            roi_global=self._roi_global,
        )
        self._drag_origin = None
        self._drag_current = None
        clamped = clamp_mask_to_roi(mask, self.roi_size)
        if clamped is not None:
            self._controller.add(clamped)
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - API do Qt
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._controller.finish()
        elif event.key() == Qt.Key.Key_Escape:
            self._controller.cancel()
        else:
            super().keyPressEvent(event)


class _MaskEditorController:
    def __init__(
        self, masks: Sequence[Rect], quit_loop: Callable[[], None]
    ) -> None:
        self.masks: tuple[Rect, ...] = tuple(masks)
        self.result: tuple[Rect, ...] | None = None
        self._quit_loop = quit_loop
        self._overlays: list[MaskEditorOverlay] = []

    def build(self, roi_global: Rect) -> list[MaskEditorOverlay]:
        self._overlays = [
            MaskEditorOverlay(screen, self, roi_global)
            for screen in QGuiApplication.screens()
        ]
        return self._overlays

    def add(self, mask: Rect) -> None:
        self.masks = (*self.masks, mask)
        self._refresh()

    def remove_at(self, index: int) -> None:
        self.masks = remove_mask_at(self.masks, index)
        self._refresh()

    def finish(self) -> None:
        self.result = self.masks
        self._close_all()

    def cancel(self) -> None:
        self.result = None
        self._close_all()

    def _refresh(self) -> None:
        for overlay in self._overlays:
            overlay.update()

    def _close_all(self) -> None:
        for overlay in self._overlays:
            overlay.close()
        self._quit_loop()


def run_mask_editor(
    window_rect: Rect,
    roi_relative: Rect,
    masks: Sequence[Rect],
) -> tuple[Rect, ...] | None:
    """Mostra o editor em cada monitor; devolve as mascaras ou None se cancelar.

    `window_rect` e a janela em pixels fisicos globais; `masks` sao as mascaras
    efetivas atuais (relativas a ROI). Usa um `QEventLoop` proprio para poder ser
    chamado de dentro da GUI sem encerrar o loop principal.
    """
    from screen_watch.gui.qt_app import ensure_app  # noqa: PLC0415

    ensure_app()

    roi_global = roi_global_physical(window_rect, roi_relative)
    loop = QEventLoop()
    controller = _MaskEditorController(masks, loop.quit)
    for overlay in controller.build(roi_global):
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        overlay.setFocus()
    loop.exec()
    return controller.result
