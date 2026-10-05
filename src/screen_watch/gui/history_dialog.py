"""Janela de historico de alertas da GUI (doc, secao 3.7).

Tabela sobre `logs/alerts.jsonl` com filtros de data/severidade/strategy e
abertura best-effort do print de evidencia. Leitura de disco pequena e sincrona;
nenhuma thread/tarefa em segundo plano.
"""

from __future__ import annotations

from datetime import datetime
from datetime import time as dtime
from pathlib import Path

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from screen_watch.alerts.history import filter_records, find_evidence, read_records
from screen_watch.i18n import tr
from screen_watch.platform.paths import alerts_log_path
from screen_watch.platform.shell import open_path

STRATEGIES = ("light", "default", "advanced")


class AlertHistoryDialog(QDialog):
    def __init__(self, parent=None, *, log_path=None, captures_dir=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("history.title"))
        self.resize(780, 430)
        self._log_path = Path(log_path) if log_path else alerts_log_path()
        self._captures_dir = Path(captures_dir) if captures_dir else None
        self._records: list[dict] = []
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        filters.addWidget(QLabel(tr("history.filter_from")))
        self.from_date = QDateEdit(QDate.currentDate().addDays(-7))
        self.from_date.setCalendarPopup(True)
        filters.addWidget(self.from_date)
        filters.addWidget(QLabel(tr("history.filter_to")))
        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setCalendarPopup(True)
        filters.addWidget(self.to_date)
        filters.addWidget(QLabel(tr("history.filter_severity")))
        self.severity_combo = QComboBox()
        self.severity_combo.addItem(tr("history.filter_any"), None)
        for level in (0, 1, 2, 3):
            self.severity_combo.addItem(str(level), level)
        filters.addWidget(self.severity_combo)
        filters.addWidget(QLabel(tr("history.filter_strategy")))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItem(tr("history.filter_any"), None)
        for strategy in STRATEGIES:
            self.strategy_combo.addItem(strategy, strategy)
        filters.addWidget(self.strategy_combo)
        self.btn_refresh = QPushButton(tr("history.refresh"))
        filters.addWidget(self.btn_refresh)
        filters.addStretch(1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                tr("history.col_time"),
                tr("history.col_strategy"),
                tr("history.col_score"),
                tr("history.col_threshold"),
                tr("history.col_severity"),
                tr("history.col_changed"),
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.status = QLabel("")
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.btn_open_print = QPushButton(tr("history.open_print"))
        self.btn_open_folder = QPushButton(tr("history.open_folder"))
        self.btn_close = QPushButton(tr("history.close"))
        buttons.addWidget(self.btn_open_print)
        buttons.addWidget(self.btn_open_folder)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_close)
        layout.addLayout(buttons)

        self.btn_refresh.clicked.connect(self._reload)
        self.from_date.dateChanged.connect(self._reload)
        self.to_date.dateChanged.connect(self._reload)
        self.severity_combo.currentIndexChanged.connect(self._reload)
        self.strategy_combo.currentIndexChanged.connect(self._reload)
        self.btn_open_print.clicked.connect(self._open_print)
        self.btn_open_folder.clicked.connect(self._open_folder)
        self.btn_close.clicked.connect(self.accept)

    def _reload(self, *_args) -> None:
        records, invalid = read_records(self._log_path)
        since = datetime.combine(self.from_date.date().toPyDate(), dtime.min).timestamp()
        until = datetime.combine(self.to_date.date().toPyDate(), dtime.max).timestamp()
        filtered = filter_records(
            records,
            since=since,
            until=until,
            severity_min=self.severity_combo.currentData(),
            strategy=self.strategy_combo.currentData(),
        )
        self._records = filtered
        self.table.setRowCount(len(filtered))
        for row, record in enumerate(filtered):
            self.table.setItem(row, 0, QTableWidgetItem(_format_time(record.get("ts"))))
            self.table.setItem(row, 1, QTableWidgetItem(str(record.get("strategy", ""))))
            self.table.setItem(row, 2, QTableWidgetItem(_format_number(record.get("score"))))
            self.table.setItem(row, 3, QTableWidgetItem(_format_number(record.get("threshold"))))
            self.table.setItem(row, 4, QTableWidgetItem(str(record.get("severity", ""))))
            self.table.setItem(row, 5, QTableWidgetItem(str(record.get("changed", ""))))
        if not filtered:
            self.status.setText(tr("history.empty"))
        elif invalid:
            self.status.setText(tr("history.invalid_lines", count=invalid))
        else:
            self.status.setText("")

    def _open_print(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        timestamp = self._records[row].get("ts")
        found = (
            find_evidence(timestamp, self._captures_dir)
            if self._captures_dir is not None and isinstance(timestamp, (int, float))
            else None
        )
        if found is None:
            self.status.setText(tr("history.print_not_found"))
            return
        open_path(found)

    def _open_folder(self) -> None:
        if self._captures_dir is not None:
            open_path(self._captures_dir)


def _format_time(timestamp) -> str:
    if not isinstance(timestamp, (int, float)):
        return ""
    return datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M:%S")


def _format_number(value) -> str:
    if not isinstance(value, (int, float)):
        return ""
    return f"{float(value):.4f}"
