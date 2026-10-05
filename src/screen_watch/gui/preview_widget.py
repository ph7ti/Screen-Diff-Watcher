"""Painel de preview (ultimo frame + baseline) da GUI (doc, secao 3.7).

O controller entrega thumbnails prontos (arrays numpy) e este modulo constroi o
`QImage`/`QPixmap` sempre na GUI thread; cada frame e copiado antes de exibir.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from screen_watch.i18n import tr

PREVIEW_SIZE = (200, 110)


class _FrameTile(QWidget):
    def __init__(self, caption: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(QLabel(caption))
        self.image = QLabel()
        self.image.setFixedSize(*PREVIEW_SIZE)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setStyleSheet("background:#111; color:#888;")
        self.image.setText(tr("main.preview_none"))
        layout.addWidget(self.image)

    def set_frame(self, rgb) -> None:
        height, width = rgb.shape[:2]
        image = QImage(
            rgb.tobytes(), width, height, 3 * width, QImage.Format.Format_RGB888
        ).copy()
        self.image.setPixmap(
            QPixmap.fromImage(image).scaled(
                self.image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def clear(self) -> None:
        self.image.clear()
        self.image.setText(tr("main.preview_none"))


class PreviewPanel(QWidget):
    """Mostra baseline + ultimo frame; ignora atualizacoes com o mesmo array."""

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._latest_ref = None
        self._baseline_ref = None
        self.baseline_tile = _FrameTile(tr("main.preview_baseline"))
        self.latest_tile = _FrameTile(tr("main.preview_latest"))
        layout.addWidget(self.baseline_tile)
        layout.addWidget(self.latest_tile)

    def update_frames(self, latest, baseline) -> None:
        if latest is not None and latest is not self._latest_ref:
            self._latest_ref = latest
            self.latest_tile.set_frame(latest)
        if baseline is not None and baseline is not self._baseline_ref:
            self._baseline_ref = baseline
            self.baseline_tile.set_frame(baseline)

    def clear(self) -> None:
        self._latest_ref = None
        self._baseline_ref = None
        self.baseline_tile.clear()
        self.latest_tile.clear()
