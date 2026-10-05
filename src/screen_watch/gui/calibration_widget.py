"""Widget de calibracao ao vivo (QPainter, sem dependencia nova) — doc secao 3.7.

Desenha `score` (linha) e `threshold` (linha tracejada) por amostra, com pontos
coloridos por severidade, e exporta CSV via `gui/calibration.py`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from screen_watch.gui.calibration import Sample, severity_counts, to_csv
from screen_watch.i18n import tr

SEVERITY_COLORS = {0: "#9e9e9e", 1: "#2e7d32", 2: "#e6a700", 3: "#d62d20"}


class CalibrationWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._samples: list[Sample] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.summary = QLabel(tr("calibration.empty"))
        top.addWidget(self.summary)
        top.addStretch(1)
        self.btn_export = QPushButton(tr("main.calibration_export"))
        self.btn_clear = QPushButton(tr("main.calibration_clear"))
        top.addWidget(self.btn_export)
        top.addWidget(self.btn_clear)
        layout.addLayout(top)
        self.chart = _CalibrationChart()
        self.chart.setMinimumHeight(100)
        layout.addWidget(self.chart)
        self.btn_export.clicked.connect(self._export)
        self.btn_clear.clicked.connect(self._clear)

    def set_samples(self, samples: list[Sample]) -> None:
        if samples == self._samples:
            return
        self._samples = list(samples)
        self.chart.set_samples(self._samples)
        if not self._samples:
            self.summary.setText(tr("calibration.empty"))
            return
        counts = severity_counts(self._samples)
        levels = " · ".join(
            f"sev{level}: {counts.get(level, 0)}" for level in (0, 1, 2, 3)
        )
        self.summary.setText(f"{len(self._samples)} — {levels}")

    def _clear(self) -> None:
        self.set_samples([])

    def _export(self) -> None:
        if not self._samples:
            self.summary.setText(tr("calibration.empty"))
            return
        suggested = datetime.now().strftime("calibration-%Y%m%d-%H%M%S.csv")
        path, _selected = QFileDialog.getSaveFileName(
            self, tr("main.calibration_export"), suggested, "CSV (*.csv)"
        )
        if not path:
            return
        try:
            Path(path).write_text(to_csv(self._samples), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.calibration_failed", error=exc)
            )
            return
        QMessageBox.information(
            self, tr("main.title"), tr("dialog.calibration_saved", path=path)
        )


class _CalibrationChart(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._samples: list[Sample] = []

    def set_samples(self, samples: list[Sample]) -> None:
        self._samples = list(samples)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111"))
        width, height = self.width(), self.height()
        if not self._samples:
            painter.setPen(QColor("#888"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, tr("calibration.empty")
            )
            return
        scores = [sample[2] for sample in self._samples]
        thresholds = [sample[3] for sample in self._samples]
        top = max(scores + thresholds + [0.0001])
        step = max(1, len(self._samples) - 1)

        def point(index: int, value: float) -> QPointF:
            x = 4 + (width - 8) * (index / step)
            y = height - 4 - (height - 8) * (value / top)
            return QPointF(x, y)

        painter.setPen(QPen(QColor("#4a90d9"), 1))
        for index in range(1, len(self._samples)):
            painter.drawLine(point(index - 1, scores[index - 1]), point(index, scores[index]))
        painter.setPen(QPen(QColor("#e6a700"), 1, Qt.PenStyle.DashLine))
        for index in range(1, len(self._samples)):
            painter.drawLine(
                point(index - 1, thresholds[index - 1]), point(index, thresholds[index])
            )
        for index, sample in enumerate(self._samples):
            painter.setPen(QPen(QColor(SEVERITY_COLORS.get(int(sample[4]), "#ffffff")), 2))
            painter.drawPoint(point(index, sample[2]))
