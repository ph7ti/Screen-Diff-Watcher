"""Editor de acoes da selecao na GUI (novo recurso pos-plano).

Cria/edita uma acao escrita em `overrides.actions` do JSON de selecao. A validacao
reusa `parse_actions`, de modo que as regras do YAML (clique exige `activate`,
filtros `text_*` exigem mode advanced, etc.) valem tambem pela janela.

Qt importado no topo deste modulo, que so e importado de forma preguicosa pela
GUI (a coleta de testes nao depende de display).
"""

from __future__ import annotations

import copy

from PyQt6.QtWidgets import (
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

from screen_watch.actions.protocol import BUTTONS, REF_KINDS, STEP_KINDS
from screen_watch.actions.summary import describe_raw_step

_PARAMS_BY_KIND = {
    "activate": set(),
    "click": {"x", "y", "ref", "button", "clicks"},
    "move": {"x", "y", "ref"},
    "key": {"keys"},
    "type": {"text"},
    "wait": {"ms"},
}


class ActionEditorDialog(QDialog):
    """Formulario de uma acao: gatilho/limites + lista de passos."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        mode: str = "advanced",
        action: dict | None = None,
        title: str = "Nova acao",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._mode = mode
        self._steps: list[dict] = []
        self._param_rows: dict[str, list[QWidget]] = {}
        self._build_ui()
        if action is not None:
            self._load(action)
        self._update_param_visibility()

    # -- construcao --------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow("Nome", self.name_edit)

        self.enabled_check = QCheckBox("Habilitada")
        self.enabled_check.setChecked(True)
        form.addRow("", self.enabled_check)

        self.severity_spin = QSpinBox()
        self.severity_spin.setRange(0, 10)
        self.severity_spin.setValue(1)
        form.addRow("severity_min (gatilho)", self.severity_spin)

        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(0, 3600)
        self.cooldown_spin.setDecimals(1)
        self.cooldown_spin.setValue(30.0)
        form.addRow("cooldown_s", self.cooldown_spin)

        self.settle_spin = QDoubleSpinBox()
        self.settle_spin.setRange(0, 600)
        self.settle_spin.setDecimals(1)
        self.settle_spin.setValue(1.5)
        form.addRow("settle_s (pausa final)", self.settle_spin)

        self.rebaseline_check = QCheckBox("rebaseline (repete o gatilho)")
        form.addRow("", self.rebaseline_check)
        layout.addLayout(form)

        layout.addWidget(QLabel("Passos (a ordem importa)"))

        self.steps_list = QListWidget()
        layout.addWidget(self.steps_list)

        step_buttons = QHBoxLayout()
        self.remove_step_btn = QPushButton("Remover passo")
        self.remove_step_btn.clicked.connect(self._remove_step)
        step_buttons.addWidget(self.remove_step_btn)
        step_buttons.addStretch(1)
        layout.addLayout(step_buttons)

        layout.addWidget(QLabel("Adicionar passo"))
        step_form = QFormLayout()
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(STEP_KINDS)
        self.kind_combo.currentTextChanged.connect(self._update_param_visibility)
        step_form.addRow("tipo", self.kind_combo)

        self.x_spin = self._int_spin(-100000, 100000)
        self._add_param(step_form, "x", "x", self.x_spin)
        self.y_spin = self._int_spin(-100000, 100000)
        self._add_param(step_form, "y", "y", self.y_spin)

        self.ref_combo = QComboBox()
        self.ref_combo.addItems(REF_KINDS)
        self._add_param(step_form, "ref", "ref", self.ref_combo)

        self.button_combo = QComboBox()
        self.button_combo.addItems(BUTTONS)
        self._add_param(step_form, "button", "botao", self.button_combo)

        self.clicks_spin = self._int_spin(1, 5)
        self._add_param(step_form, "clicks", "cliques", self.clicks_spin)

        self.keys_edit = QLineEdit()
        self.keys_edit.setPlaceholderText("ex.: ctrl+s")
        self._add_param(step_form, "keys", "teclas", self.keys_edit)

        self.text_edit = QLineEdit()
        self._add_param(step_form, "text", "texto", self.text_edit)

        self.ms_spin = self._int_spin(0, 600000)
        self._add_param(step_form, "ms", "ms", self.ms_spin)

        layout.addLayout(step_form)

        self.add_step_btn = QPushButton("Adicionar passo")
        self.add_step_btn.clicked.connect(self._add_step)
        layout.addWidget(self.add_step_btn)

        hint = QLabel(
            "Dica: cliques exigem um passo 'activate' antes; filtros de texto "
            "exigem mode advanced (use when no YAML ou selecione advanced)."
        )
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

    def _add_param(self, form: QFormLayout, key: str, label: str, widget: QWidget) -> None:
        form.addRow(label, widget)
        label_widget = form.labelForField(widget)
        self._param_rows[key] = [item for item in (label_widget, widget) if item is not None]

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

    def _add_step(self) -> None:
        self._steps.append(self._collect_step())
        self._refresh_steps()

    def _remove_step(self) -> None:
        row = self.steps_list.currentRow()
        if 0 <= row < len(self._steps):
            del self._steps[row]
            self._refresh_steps()

    def _refresh_steps(self) -> None:
        self.steps_list.clear()
        for index, step in enumerate(self._steps):
            self.steps_list.addItem(f"{index + 1}. {describe_raw_step(step)}")

    # -- dados -------------------------------------------------------------
    def _load(self, action: dict) -> None:
        self.name_edit.setText(str(action.get("name", "")))
        self.enabled_check.setChecked(bool(action.get("enabled", True)))
        self.severity_spin.setValue(int(action.get("severity_min", 1)))
        self.cooldown_spin.setValue(float(action.get("cooldown_s", 30.0)))
        self.settle_spin.setValue(float(action.get("settle_s", 1.5)))
        self.rebaseline_check.setChecked(bool(action.get("rebaseline", False)))
        self._steps = [copy.deepcopy(step) for step in (action.get("steps") or [])]
        self._refresh_steps()

    def result_action(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "enabled": self.enabled_check.isChecked(),
            "severity_min": self.severity_spin.value(),
            "cooldown_s": self.cooldown_spin.value(),
            "settle_s": self.settle_spin.value(),
            "rebaseline": self.rebaseline_check.isChecked(),
            "steps": list(self._steps),
        }

    def accept(self) -> None:  # noqa: N802 - API do Qt
        from screen_watch.config.loader import ConfigError, parse_actions  # noqa: PLC0415

        try:
            parse_actions([self.result_action()], prefix="acao", mode=self._mode)
        except ConfigError as exc:
            QMessageBox.warning(self, "Acao invalida", str(exc))
            return
        super().accept()

    def run(self) -> dict | None:
        """Mostra o dialogo e devolve a acao crua, ou None se cancelar."""
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.result_action()
        return None
