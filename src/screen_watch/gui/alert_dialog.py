"""Dialogo "Testar alerta…" (doc, secao 11): lista os alertas do alvo e envia um
teste ao destino escolhido.

O envio roda em thread de trabalho (`QThread`): um timeout de 5 s nao pode
congelar a UI. Sem ROI disponivel, `send_test` cai para modo texto. O resultado
volta por sinal e e escrito na area de resultado.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from screen_watch.alerts.test_send import list_alert_targets, send_test
from screen_watch.gui.hover_help import attach_help
from screen_watch.i18n import tr

ALERT_ID_ROLE = 1


class _SendWorker(QThread):
    done = pyqtSignal(object)

    def __init__(self, target, alert_id: str) -> None:
        super().__init__()
        self._target = target
        self._alert_id = alert_id

    def run(self) -> None:  # noqa: D102 - API do Qt
        frame = None
        try:
            from screen_watch.cli.commands import _capture_frame  # noqa: PLC0415

            frame, _rect, _info = _capture_frame(self._target, 1)
        except Exception:
            frame = None
        self.done.emit(send_test(self._target, self._alert_id, frame=frame))


class AlertTestDialog(QDialog):
    def __init__(self, parent, target) -> None:
        super().__init__(parent)
        self._target = target
        self._worker: _SendWorker | None = None
        self.setWindowTitle(tr("dialog.test_alert_title"))
        self.resize(560, 360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("dialog.test_alert_list_label")))
        self.list = QListWidget()
        self.list.setAccessibleName("test_alert")
        self._help = attach_help(self.list, "test_alert")
        for alert_id, alert_type, enabled, severity_min, destination in list_alert_targets(
            target
        ):
            state = tr("dialog.test_alert_enabled") if enabled else tr("dialog.test_alert_disabled")
            item = QListWidgetItem(
                f"{alert_id}  —  {alert_type}  ({state}, severity_min={severity_min})  -> {destination}"
            )
            item.setData(ALERT_ID_ROLE, alert_id)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        layout.addWidget(self.list)

        row = QVBoxLayout()
        self.btn_send = QPushButton(tr("dialog.test_alert_send"))
        self.btn_send.setEnabled(self.list.count() > 0)
        self.btn_send.clicked.connect(self._send)
        row.addWidget(self.btn_send)
        layout.addLayout(row)

        self.result = QLabel("")
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _selected_id(self) -> str | None:
        item = self.list.currentItem()
        return None if item is None else str(item.data(ALERT_ID_ROLE))

    def _send(self) -> None:
        alert_id = self._selected_id()
        if alert_id is None:
            return
        self.btn_send.setEnabled(False)
        self.result.setText(tr("dialog.test_alert_sending"))
        self._worker = _SendWorker(self._target, alert_id)
        self._worker.done.connect(self._on_done)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_done(self, outcome) -> None:
        self.btn_send.setEnabled(True)
        if getattr(outcome, "ok", False):
            self.result.setText(tr("dialog.test_alert_ok", message=outcome.message))
        else:
            self.result.setText(tr("dialog.test_alert_fail", message=outcome.message))

    def closeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(2000)
        super().closeEvent(event)
