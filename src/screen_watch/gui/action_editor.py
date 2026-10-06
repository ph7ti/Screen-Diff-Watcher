"""Editor de acoes da selecao na GUI (F5: editar/reordenar passos).

Cria/edita uma acao escrita em `overrides.actions` do JSON de selecao. A validacao
reusa `parse_actions`, de modo que as regras do YAML (clique exige `activate`,
filtros `text_*` exigem mode advanced, etc.) valem tambem pela janela.

`self._steps` e a fonte unica da verdade: os botoes e o arrastar-e-soltar chamam
as funcoes puras de `actions/steps.py` e `_refresh_steps()` reconstroi o widget a
partir do modelo.

Qt importado no topo deste modulo, que so e importado de forma preguicosa pela
GUI (a coleta de testes nao depende de display).
"""

from __future__ import annotations

import copy
from collections.abc import Callable

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from screen_watch.actions.protocol import BUTTONS, REF_KINDS, STEP_KINDS, TRIGGERS, WEEKDAYS
from screen_watch.actions.steps import duplicate_step, move_step, remove_step, replace_step
from screen_watch.actions.summary import describe_raw_step
from screen_watch.errors import render_error
from screen_watch.gui.hover_help import attach_help
from screen_watch.gui.overlay_geometry import resolve_ref_point
from screen_watch.i18n import tr

_PARAMS_BY_KIND = {
    "activate": set(),
    "click": {"x", "y", "ref", "button", "clicks", "locate"},
    "move": {"x", "y", "ref", "locate"},
    "key": {"keys"},
    "type": {"text"},
    "wait": {"ms"},
}


class _StepsListWidget(QListWidget):
    """Lista de passos com reordenacao interna por arrastar-e-soltar.

    O `dropEvent` base ja mexeu nas linhas do widget; delegamos ao modelo via
    `reorder_callback(old_row, new_row)`, que recalcula a ordem a partir de
    `self._steps` e reconstroi o widget.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.reorder_callback: Callable[[int, int], None] | None = None

    def dropEvent(self, event) -> None:  # noqa: N802 - API do Qt
        old_row = self.currentRow()
        super().dropEvent(event)
        new_row = self.currentRow()
        if self.reorder_callback is not None:
            self.reorder_callback(old_row, new_row)


class ActionEditorDialog(QDialog):
    """Formulario de uma acao: gatilho/limites + lista de passos."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        mode: str = "advanced",
        action: dict | None = None,
        title: str = "Nova acao",
        roi_rect: tuple[int, int, int, int] | None = None,
        window_rect: tuple[int, int, int, int] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._mode = mode
        self._roi_rect = roi_rect
        self._window_rect = window_rect
        self._steps: list[dict] = []
        self._param_rows: dict[str, list[QWidget]] = {}
        self._trigger_rows: dict[str, list[QWidget]] = {}
        self._when_extra: dict = {}
        self._help_filters: list[object] = []
        self._edit_index: int | None = None
        self._build_ui()
        if action is not None:
            self._load(action)
        self._update_param_visibility()
        self._update_trigger_visibility()

    # -- construcao --------------------------------------------------------
    def _help(self, widget: QWidget, key: str) -> None:
        self._help_filters.append(attach_help(widget, key))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow(tr("editor.name"), self.name_edit)
        self._help(self.name_edit, "editor.name")

        self.enabled_check = QCheckBox(tr("editor.enabled"))
        self.enabled_check.setChecked(True)
        form.addRow("", self.enabled_check)
        self._help(self.enabled_check, "editor.enabled")

        self.trigger_combo = QComboBox()
        self.trigger_combo.addItems(TRIGGERS)
        self.trigger_combo.currentTextChanged.connect(self._update_trigger_visibility)
        self._add_param(form, "trigger", tr("editor.trigger"), self.trigger_combo, rows=self._trigger_rows)
        self._help(self.trigger_combo, "editor.trigger")

        self.at_edit = QLineEdit()
        self.at_edit.setPlaceholderText(tr("editor.at_placeholder"))
        self._add_param(form, "at", tr("editor.trigger_at"), self.at_edit, rows=self._trigger_rows)
        self._help(self.at_edit, "editor.trigger_at")

        self.days_widget = QWidget()
        days_row = QHBoxLayout(self.days_widget)
        days_row.setContentsMargins(0, 0, 0, 0)
        self.day_checks: dict[str, QCheckBox] = {}
        for name in WEEKDAYS:
            check = QCheckBox(tr(f"editor.day_{name}"))
            check.setChecked(True)
            self.day_checks[name] = check
            days_row.addWidget(check)
        self._add_param(
            form, "days", tr("editor.trigger_days"), self.days_widget, rows=self._trigger_rows
        )
        self._help(self.days_widget, "editor.trigger_days")

        self.every_spin = self._seconds_spin()
        self._add_param(
            form, "every", tr("editor.trigger_every"), self.every_spin, rows=self._trigger_rows
        )
        self._help(self.every_spin, "editor.trigger_every")

        self.after_spin = self._seconds_spin()
        self._add_param(
            form, "after", tr("editor.trigger_after"), self.after_spin, rows=self._trigger_rows
        )
        self._help(self.after_spin, "editor.trigger_after")

        self.severity_spin = QSpinBox()
        self.severity_spin.setRange(0, 10)
        self.severity_spin.setValue(1)
        form.addRow(tr("editor.severity_min"), self.severity_spin)
        self._help(self.severity_spin, "editor.severity_min")

        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(0, 3600)
        self.cooldown_spin.setDecimals(1)
        self.cooldown_spin.setValue(30.0)
        form.addRow(tr("editor.cooldown_s"), self.cooldown_spin)
        self._help(self.cooldown_spin, "editor.cooldown_s")

        self.settle_spin = QDoubleSpinBox()
        self.settle_spin.setRange(0, 600)
        self.settle_spin.setDecimals(1)
        self.settle_spin.setValue(1.5)
        form.addRow(tr("editor.settle_s"), self.settle_spin)
        self._help(self.settle_spin, "editor.settle_s")

        self.rebaseline_check = QCheckBox(tr("editor.rebaseline"))
        form.addRow("", self.rebaseline_check)
        self._help(self.rebaseline_check, "editor.rebaseline")
        self._change_only_rows: list[QWidget] = [
            item
            for item in (
                form.labelForField(self.severity_spin),
                self.severity_spin,
                form.labelForField(self.rebaseline_check),
                self.rebaseline_check,
            )
            if item is not None
        ]
        layout.addLayout(form)

        layout.addWidget(QLabel(tr("editor.steps_header")))

        self.steps_list = _StepsListWidget()
        self.steps_list.reorder_callback = self._apply_drop
        self.steps_list.itemDoubleClicked.connect(self._on_step_double_clicked)
        layout.addWidget(self.steps_list)
        self._help(self.steps_list, "editor.steps_list")

        step_buttons = QHBoxLayout()
        self.move_up_btn = QPushButton(tr("editor.move_up"))
        self.move_up_btn.clicked.connect(lambda: self._move_selected(-1))
        step_buttons.addWidget(self.move_up_btn)
        self._help(self.move_up_btn, "editor.step_up")

        self.move_down_btn = QPushButton(tr("editor.move_down"))
        self.move_down_btn.clicked.connect(lambda: self._move_selected(1))
        step_buttons.addWidget(self.move_down_btn)
        self._help(self.move_down_btn, "editor.step_down")

        self.edit_step_btn = QPushButton(tr("editor.edit_step"))
        self.edit_step_btn.clicked.connect(self._edit_selected)
        step_buttons.addWidget(self.edit_step_btn)
        self._help(self.edit_step_btn, "editor.step_edit")

        self.duplicate_step_btn = QPushButton(tr("editor.duplicate_step"))
        self.duplicate_step_btn.clicked.connect(self._duplicate_selected)
        step_buttons.addWidget(self.duplicate_step_btn)
        self._help(self.duplicate_step_btn, "editor.step_duplicate")

        self.remove_step_btn = QPushButton(tr("editor.remove_step"))
        self.remove_step_btn.clicked.connect(self._remove_selected)
        step_buttons.addWidget(self.remove_step_btn)
        self._help(self.remove_step_btn, "editor.step_remove")

        step_buttons.addStretch(1)
        layout.addLayout(step_buttons)

        layout.addWidget(QLabel(tr("editor.add_step_header")))
        step_form = QFormLayout()
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(STEP_KINDS)
        self.kind_combo.currentTextChanged.connect(self._update_param_visibility)
        step_form.addRow(tr("editor.step_type"), self.kind_combo)
        self._help(self.kind_combo, "editor.step_kind")

        self.x_spin = self._int_spin(-100000, 100000)
        self._add_param(step_form, "x", tr("editor.step_x"), self.x_spin)
        self._help(self.x_spin, "editor.step_x")
        self.y_spin = self._int_spin(-100000, 100000)
        self._add_param(step_form, "y", tr("editor.step_y"), self.y_spin)
        self._help(self.y_spin, "editor.step_y")

        self.locate_btn = QPushButton(tr("editor.locate"))
        self.locate_btn.clicked.connect(self._locate)
        self._add_param(step_form, "locate", "", self.locate_btn)
        self._help(self.locate_btn, "editor.step_locate")

        self.ref_combo = QComboBox()
        self.ref_combo.addItems(REF_KINDS)
        self._add_param(step_form, "ref", tr("editor.step_ref"), self.ref_combo)
        self._help(self.ref_combo, "editor.step_ref")

        self.button_combo = QComboBox()
        self.button_combo.addItems(BUTTONS)
        self._add_param(step_form, "button", tr("editor.step_button"), self.button_combo)
        self._help(self.button_combo, "editor.step_button")

        self.clicks_spin = self._int_spin(1, 5)
        self._add_param(step_form, "clicks", tr("editor.step_clicks"), self.clicks_spin)
        self._help(self.clicks_spin, "editor.step_clicks")

        self.keys_edit = QLineEdit()
        self.keys_edit.setPlaceholderText(tr("editor.keys_placeholder"))
        self._add_param(step_form, "keys", tr("editor.step_keys"), self.keys_edit)
        self._help(self.keys_edit, "editor.step_keys")

        self.text_edit = QLineEdit()
        self._add_param(step_form, "text", tr("editor.step_text"), self.text_edit)
        self._help(self.text_edit, "editor.step_text")

        self.ms_spin = self._int_spin(0, 600000)
        self._add_param(step_form, "ms", tr("editor.step_ms"), self.ms_spin)
        self._help(self.ms_spin, "editor.step_ms")

        layout.addLayout(step_form)

        commit_row = QHBoxLayout()
        self.add_step_btn = QPushButton(tr("editor.add_step"))
        self.add_step_btn.clicked.connect(self._commit_step)
        commit_row.addWidget(self.add_step_btn, 1)
        self._help(self.add_step_btn, "editor.step_add")

        self.cancel_step_btn = QPushButton(tr("editor.cancel_step"))
        self.cancel_step_btn.clicked.connect(self._cancel_edit)
        self.cancel_step_btn.setVisible(False)
        commit_row.addWidget(self.cancel_step_btn)
        layout.addLayout(commit_row)

        hint = QLabel(tr("editor.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _int_spin(low: int, high: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        return spin

    @staticmethod
    def _seconds_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(1, 86400)
        spin.setDecimals(1)
        spin.setValue(60.0)
        return spin

    def _add_param(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        widget: QWidget,
        rows: dict[str, list[QWidget]] | None = None,
    ) -> None:
        form.addRow(label, widget)
        label_widget = form.labelForField(widget)
        store = self._param_rows if rows is None else rows
        store[key] = [item for item in (label_widget, widget) if item is not None]

    # -- gatilho -----------------------------------------------------------
    def _update_trigger_visibility(self, *_args) -> None:
        """Mostra so os campos do gatilho escolhido; `change` mantem os antigos."""
        trigger = self.trigger_combo.currentText()
        visible = {"trigger"}
        if trigger == "at":
            visible |= {"at", "days"}
        elif trigger == "every":
            visible.add("every")
        elif trigger == "after":
            visible.add("after")
        for key, widgets in self._trigger_rows.items():
            for widget in widgets:
                widget.setVisible(key in visible)
        for widget in self._change_only_rows:
            widget.setVisible(trigger == "change")

    # -- passos ------------------------------------------------------------
    def _update_param_visibility(self, *_args) -> None:
        kind = self.kind_combo.currentText()
        visible = _PARAMS_BY_KIND.get(kind, set())
        for key, widgets in self._param_rows.items():
            for widget in widgets:
                widget.setVisible(key in visible)

    def _collect_step(self) -> dict:
        kind = self.kind_combo.currentText()
        if kind == "activate":
            return {"activate": True}
        if kind in ("click", "move"):
            params: dict = {
                "x": self.x_spin.value(),
                "y": self.y_spin.value(),
                "ref": self.ref_combo.currentText(),
            }
            if kind == "click":
                params["button"] = self.button_combo.currentText()
                params["clicks"] = self.clicks_spin.value()
            return {kind: params}
        if kind == "key":
            return {"key": {"keys": self.keys_edit.text().strip()}}
        if kind == "type":
            return {"type": {"text": self.text_edit.text()}}
        return {"wait": {"ms": self.ms_spin.value()}}

    def _selected_row(self) -> int | None:
        row = self.steps_list.currentRow()
        return row if 0 <= row < len(self._steps) else None

    def _commit_step(self) -> None:
        step = self._collect_step()
        if self._edit_index is not None:
            self._steps = replace_step(self._steps, self._edit_index, step)
        else:
            self._steps.append(step)
        self._refresh_steps()
        self._exit_edit_mode()

    def _load_step_for_edit(self, row: int) -> None:
        step = self._steps[row]
        kind = next((name for name in STEP_KINDS if name in step), STEP_KINDS[0])
        self.kind_combo.setCurrentText(kind)
        params = step.get(kind) or {}
        if kind in ("click", "move"):
            self.x_spin.setValue(int(params.get("x") or 0))
            self.y_spin.setValue(int(params.get("y") or 0))
            self.ref_combo.setCurrentText(str(params.get("ref", REF_KINDS[0])))
            self.button_combo.setCurrentText(str(params.get("button", BUTTONS[0])))
            self.clicks_spin.setValue(int(params.get("clicks", 1)))
        elif kind == "key":
            self.keys_edit.setText(str(params.get("keys", "")))
        elif kind == "type":
            self.text_edit.setText(str(params.get("text", "")))
        elif kind == "wait":
            self.ms_spin.setValue(int(params.get("ms", 0)))
        self._edit_index = row
        self.add_step_btn.setText(tr("editor.save_step"))
        self.cancel_step_btn.setVisible(True)

    def _edit_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, tr("editor.edit_step"), tr("dialog.select_step"))
            return
        self._load_step_for_edit(row)

    def _on_step_double_clicked(self, _item) -> None:
        row = self._selected_row()
        if row is not None:
            self._load_step_for_edit(row)

    def _cancel_edit(self) -> None:
        self._exit_edit_mode()

    def _exit_edit_mode(self) -> None:
        self._edit_index = None
        self.add_step_btn.setText(tr("editor.add_step"))
        self.cancel_step_btn.setVisible(False)

    def _move_selected(self, delta: int) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._steps = move_step(self._steps, row, delta)
        self._refresh_steps()
        self.steps_list.setCurrentRow(row + delta if 0 <= row + delta < len(self._steps) else row)

    def _duplicate_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, tr("editor.duplicate_step"), tr("dialog.select_step"))
            return
        self._steps = duplicate_step(self._steps, row)
        self._refresh_steps()
        self.steps_list.setCurrentRow(row + 1)

    def _remove_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, tr("editor.remove_step"), tr("dialog.select_step"))
            return
        self._steps = remove_step(self._steps, row)
        self._refresh_steps()
        if self._edit_index is not None and self._edit_index == row:
            self._exit_edit_mode()

    def _apply_drop(self, old_row: int, new_row: int) -> None:
        if old_row < 0 or new_row < 0:
            self._refresh_steps()
            return
        self._steps = move_step(self._steps, old_row, new_row - old_row)
        self._refresh_steps()

    def _locate(self) -> None:
        from screen_watch.gui.locator import run_locator  # noqa: PLC0415

        ref = self.ref_combo.currentText()
        point = run_locator(
            ref,
            roi_rect=self._roi_rect,
            window_rect=self._window_rect,
            parent=self,
        )
        if point is None:
            return
        effective_ref, (rel_x, rel_y) = resolve_ref_point(
            point, ref, roi_rect=self._roi_rect, window_rect=self._window_rect
        )
        if effective_ref != ref:
            self.ref_combo.setCurrentText(effective_ref)
            QMessageBox.information(
                self,
                tr("dialog.locate_title"),
                tr("dialog.locate_absolute"),
            )
        self.x_spin.setValue(rel_x)
        self.y_spin.setValue(rel_y)

    def _refresh_steps(self) -> None:
        self.steps_list.clear()
        for index, step in enumerate(self._steps):
            self.steps_list.addItem(f"{index + 1}. {describe_raw_step(step)}")

    # -- dados -------------------------------------------------------------
    def _load(self, action: dict) -> None:
        from screen_watch.gui.action_editor_model import form_from_action  # noqa: PLC0415

        self.name_edit.setText(str(action.get("name", "")))
        self.enabled_check.setChecked(bool(action.get("enabled", True)))
        self.severity_spin.setValue(int(action.get("severity_min", 1)))
        self.cooldown_spin.setValue(float(action.get("cooldown_s", 30.0)))
        self.settle_spin.setValue(float(action.get("settle_s", 1.5)))
        self.rebaseline_check.setChecked(bool(action.get("rebaseline", False)))
        form = form_from_action(action)
        self.trigger_combo.setCurrentText(form["trigger"])
        self.at_edit.setText(form["at"])
        days = form["days"]
        for name, check in self.day_checks.items():
            check.setChecked(not days or name in days)
        self.every_spin.setValue(form["every_s"])
        self.after_spin.setValue(form["after_s"])
        self._when_extra = form["when_extra"]
        self._steps = [copy.deepcopy(step) for step in (action.get("steps") or [])]
        self._refresh_steps()
        self._update_trigger_visibility()

    def result_action(self) -> dict:
        from screen_watch.gui.action_editor_model import action_from_form  # noqa: PLC0415

        return action_from_form(
            name=self.name_edit.text().strip(),
            enabled=self.enabled_check.isChecked(),
            severity_min=self.severity_spin.value(),
            cooldown_s=self.cooldown_spin.value(),
            settle_s=self.settle_spin.value(),
            rebaseline=self.rebaseline_check.isChecked(),
            trigger=self.trigger_combo.currentText(),
            at_text_value=self.at_edit.text(),
            days=[name for name in WEEKDAYS if self.day_checks[name].isChecked()],
            every_s=self.every_spin.value(),
            after_s=self.after_spin.value(),
            when_extra=self._when_extra,
            steps=list(self._steps),
        )

    def accept(self) -> None:  # noqa: N802 - API do Qt
        from screen_watch.config.loader import ConfigError, parse_actions  # noqa: PLC0415

        try:
            parse_actions([self.result_action()], prefix="acao", mode=self._mode)
        except ConfigError as exc:
            QMessageBox.warning(self, tr("editor.invalid_title"), render_error(exc))
            return
        super().accept()

    def run(self) -> dict | None:
        """Mostra o dialogo e devolve a acao crua, ou None se cancelar."""
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.result_action()
        return None
