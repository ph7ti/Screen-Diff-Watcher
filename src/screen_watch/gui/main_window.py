"""Janela principal da GUI mínima (doc 13.9, P3/P6/P10).

Nao faz I/O de rede nem toca no loop: apenas reflete a config/selecoes, dispara
iniciar/parar no `MonitorController` e consome eventos da fila via `QTimer`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from screen_watch.gui.controller import MonitorController, new_event_queue
from screen_watch.gui.labels import selection_label

POLL_MS = 200
TARGET_ROLE = 1
ACTION_NAME_ROLE = 2
MODES = ("light", "default", "advanced")


def _window_icon() -> QIcon | None:
    """Icone multi-resolucao do projeto (todos os PNGs disponiveis)."""
    from screen_watch.resources import icon_paths

    paths = icon_paths()
    if not paths:
        return None
    icon = QIcon()
    for path in paths:
        icon.addFile(str(path))
    return icon


class MainWindow(QMainWindow):
    def __init__(
        self, controller: MonitorController, config_path, profile: str | None = None, on_quit=None
    ) -> None:
        super().__init__()
        self.setWindowTitle("Screen Diff Watcher")
        self.resize(820, 540)
        icon = _window_icon()
        if icon is not None:
            self.setWindowIcon(icon)
        self._controller = controller
        self._config_path = Path(config_path)
        self._profile = profile
        self._config = None
        self._on_quit = on_quit
        self._entries: list[tuple[str, object]] = []
        self._active_name = ""
        self._actions_stem: str | None = None
        self._hotkeys: object | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._drain)

        self._build_ui()
        self._reload()
        self._start_hotkeys()
        self._timer.start()

    # -- construcao --------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addWidget(QLabel("Selecoes — nome do app, ROI monitorada e modo"))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.currentItemChanged.connect(self._item_changed)
        self.list.itemDoubleClicked.connect(lambda _item: self._toggle_clicked())
        layout.addWidget(self.list)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Modo:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODES)
        self.mode_combo.currentTextChanged.connect(self._mode_changed)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Perfil:"))
        self.profile_combo = QComboBox()
        self.profile_combo.currentTextChanged.connect(self._profile_changed)
        profile_row.addWidget(self.profile_combo)
        self.profile_note = QLabel("")
        profile_row.addWidget(self.profile_note)
        profile_row.addStretch(1)
        layout.addLayout(profile_row)

        layout.addWidget(QLabel("Acoes da sessao (aplicam no proximo start)"))
        self.action_list = QListWidget()
        self.action_list.setMaximumHeight(140)
        self.action_list.itemChanged.connect(self._actions_changed)
        layout.addWidget(self.action_list)
        self.action_count = QLabel("")
        layout.addWidget(self.action_count)

        action_buttons = QHBoxLayout()
        self.btn_action_new = QPushButton("Nova acao...")
        self.btn_action_edit = QPushButton("Editar...")
        self.btn_action_remove = QPushButton("Remover acao")
        self.btn_action_new.clicked.connect(self._action_new)
        self.btn_action_edit.clicked.connect(self._action_edit)
        self.btn_action_remove.clicked.connect(self._action_remove)
        for button in (self.btn_action_new, self.btn_action_edit, self.btn_action_remove):
            action_buttons.addWidget(button)
        action_buttons.addStretch(1)
        layout.addLayout(action_buttons)

        buttons = QHBoxLayout()
        self.btn_start = QPushButton("Iniciar")
        self.btn_stop = QPushButton("Parar")
        self.btn_stop.setEnabled(False)
        self.btn_rearm = QPushButton("Re-armar")
        self.btn_rearm.setEnabled(False)
        self.btn_run_action = QPushButton("Executar acao (3s)")
        self.btn_new = QPushButton("Novo target (overlay)")
        self.btn_remove = QPushButton("Remover")
        self.btn_reload = QPushButton("Recarregar")
        self.btn_minimize = QPushButton("Minimizar para o tray")
        self.btn_open = QPushButton("Abrir YAML")
        self.btn_open_captures = QPushButton("Abrir pasta de prints")
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_rearm.clicked.connect(self._rearm)
        self.btn_run_action.clicked.connect(self._run_action_once)
        self.btn_new.clicked.connect(self._new_target)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_reload.clicked.connect(self._reload)
        self.btn_minimize.clicked.connect(self.hide)
        self.btn_open.clicked.connect(self._open_yaml)
        self.btn_open_captures.clicked.connect(self._open_captures)
        for button in (
            self.btn_start,
            self.btn_stop,
            self.btn_rearm,
            self.btn_run_action,
            self.btn_new,
            self.btn_remove,
            self.btn_reload,
            self.btn_minimize,
            self.btn_open,
            self.btn_open_captures,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.status = QLabel("parado")
        self.last = QLabel("ultimo resultado: -")
        layout.addWidget(self.status)
        layout.addWidget(self.last)

        layout.addWidget(QLabel("Log"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

    # -- dados -------------------------------------------------------------
    def _reload(self) -> None:
        from screen_watch.config.loader import ConfigError, load_config
        from screen_watch.platform.paths import selections_dir

        self.list.clear()
        self._entries.clear()
        self._config = None

        try:
            self._config = load_config(self._config_path)
        except ConfigError as exc:
            self._append(f"config indisponivel: {exc}")
        if self._config is not None and self._config.legacy:
            self._append("aviso: YAML v1 (targets); rode 'migrate-config' para v2")

        for path in sorted(selections_dir().glob("*.json")):
            self._entries.append(("selection", path))

        for kind, value in self._entries:
            item = QListWidgetItem(self._label_for(kind, value))
            item.setData(TARGET_ROLE, (kind, value))
            self.list.addItem(item)

        self._populate_profiles()
        self._append(
            f"carregado: {len(self._entries)} selecao(oes) — perfil {self._profile_label()}"
        )
        if self.list.count():
            self.list.setCurrentRow(0)
        self._populate_actions()

    def _populate_profiles(self) -> None:
        if self._config is not None and not self._config.legacy and self._config.profiles:
            names = list(self._config.profiles.keys())
            default = self._profile or self._config.profile
        else:
            names = ["default"]
            default = self._profile or "default"
        if default not in names:
            names.insert(0, default)
        self._profile_combo_update(names, default)

    def _profile_combo_update(self, names, current) -> None:
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(names)
        self.profile_combo.setCurrentText(current)
        self.profile_combo.blockSignals(False)
        self._profile = current

    def profile_names(self) -> tuple[str, ...]:
        names = [self.profile_combo.itemText(i) for i in range(self.profile_combo.count())]
        return tuple(names) or ("default",)

    def _profile_changed(self, name: str) -> None:
        if not name:
            return
        self._profile = name
        from screen_watch.platform.paths import update_state

        update_state(profile=name)
        pending = "(aplicará no próximo start)" if self._controller.running else ""
        self.profile_note.setText(pending)
        self._append(f"perfil -> {name} {pending}".strip())
        self._update_action_status()
        self._populate_actions()
        self._print_action_summary()

    def _select_profile(self, name: str) -> None:
        index = self.profile_combo.findText(name)
        if index < 0:
            self._profile_combo_update([*self.profile_names(), name], name)
        else:
            self.profile_combo.setCurrentIndex(index)
        self._profile_changed(name)

    def _profile_label(self) -> str:
        if self._config is None or self._config.legacy or not self._config.profiles:
            return f"{self._profile or 'default'} (legado/sem config)"
        return self._profile or self._config.profile

    def arm_durations(self) -> tuple[int, ...]:
        if self._config is None or self._config.legacy:
            return (1, 5, 15, 30)
        return self._config.ui.arm_durations_min or (1, 5, 15, 30)

    def _label_for(self, _kind: str, value) -> str:
        from screen_watch.persistence.selection import load_selection

        try:
            selection = load_selection(value)
        except (OSError, ValueError) as exc:
            return f"[SEL] {Path(value).stem} — ilegivel ({exc})"
        return selection_label(selection, Path(value).stem)

    def _selected(self):
        item = self.list.currentItem()
        return item.data(TARGET_ROLE) if item is not None else None

    def _entry_mode(self, entry) -> str:
        if entry is None:
            return self.mode_combo.currentText() or MODES[-1]
        _kind, value = entry
        from screen_watch.persistence.selection import load_selection

        try:
            return load_selection(value).mode
        except (OSError, ValueError):
            return MODES[-1]

    def _resolve_target(self, mode: str):
        selected = self._selected()
        if selected is None:
            return None
        _kind, value = selected
        from screen_watch.app import profile_from_config
        from screen_watch.persistence.selection import build_target, load_selection

        selection = load_selection(value)
        profile = profile_from_config(self._config, self._profile, Path(value).stem)
        schedule = self._config.schedule if self._config is not None and not self._config.legacy else None
        return build_target(
            selection,
            profile,
            name=Path(value).stem,
            mode=mode,
            schedule=schedule,
            action_filter=self._checked_action_names(),
        )

    # -- acoes -------------------------------------------------------------
    def _item_changed(self, _current, _previous) -> None:
        selected = self._selected()
        if selected is None:
            self._populate_actions()
            return
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText(self._entry_mode(selected))
        self.mode_combo.blockSignals(False)
        self._populate_actions()
        self._print_action_summary()

    def _action_check_states(self) -> dict[str, bool]:
        states: dict[str, bool] = {}
        for index in range(self.action_list.count()):
            item = self.action_list.item(index)
            name = item.data(ACTION_NAME_ROLE)
            if name is not None:
                states[str(name)] = item.checkState() == Qt.CheckState.Checked
        return states

    def _checked_action_names(self) -> tuple[str, ...] | None:
        if self.action_list.count() == 0:
            return None
        names: list[str] = []
        for index in range(self.action_list.count()):
            item = self.action_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                name = item.data(ACTION_NAME_ROLE)
                if name is not None:
                    names.append(str(name))
        return tuple(names)

    def _populate_actions(self) -> None:
        from screen_watch.actions.selection import load_action_selection
        from screen_watch.actions.summary import format_action
        from screen_watch.app import profile_from_config
        from screen_watch.persistence.selection import load_selection, resolve_actions

        previous = self._action_check_states()
        self.action_list.blockSignals(True)
        self.action_list.clear()
        selected = self._selected()
        if selected is None:
            self._actions_stem = None
            self.action_list.setEnabled(False)
            self.action_count.setText("nenhuma selecao")
            self.action_list.blockSignals(False)
            return
        _kind, value = selected
        stem = Path(value).stem
        same = stem == self._actions_stem
        try:
            selection = load_selection(value)
            profile = profile_from_config(self._config, self._profile, stem)
            actions = resolve_actions(selection, profile, self.mode_combo.currentText() or None)
        except Exception as exc:
            self._actions_stem = stem
            self.action_list.setEnabled(False)
            self.action_count.setText(f"acoes indisponiveis: {exc}")
            self.action_list.blockSignals(False)
            return
        saved = None if same else load_action_selection(stem)
        self._actions_stem = stem
        self.action_list.setEnabled(True)
        for action in actions:
            if action.name in previous:
                checked = previous[action.name]
            else:
                checked = saved is None or action.name in saved
            item = QListWidgetItem(format_action(action))
            item.setData(ACTION_NAME_ROLE, action.name)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.action_list.addItem(item)
        self.action_list.blockSignals(False)
        self._update_action_count()

    def _update_action_count(self) -> None:
        total = self.action_list.count()
        if total == 0:
            self.action_count.setText("nenhuma acao configurada")
            return
        checked = sum(
            1
            for index in range(total)
            if self.action_list.item(index).checkState() == Qt.CheckState.Checked
        )
        text = f"{checked} de {total} selecionadas"
        if checked == 0:
            text += " — nenhuma acao selecionada (a sessao so monitora)"
        self.action_count.setText(text)

    def _actions_changed(self, _item) -> None:
        selected = self._selected()
        if selected is None:
            return
        _kind, value = selected
        from screen_watch.actions.selection import save_action_selection

        try:
            save_action_selection(Path(value).stem, self._checked_action_names() or ())
        except OSError as exc:
            self._append(f"nao foi possivel salvar a selecao de acoes: {exc}")
        self._update_action_count()

    # -- editor de acoes ---------------------------------------------------
    def _current_selection(self):
        selected = self._selected()
        if selected is None:
            return None, None
        _kind, value = selected
        from screen_watch.persistence.selection import load_selection

        try:
            return value, load_selection(value)
        except (OSError, ValueError) as exc:
            self._append(f"selecao ilegivel: {exc}")
            return value, None

    def _selected_action_name(self) -> str | None:
        item = self.action_list.currentItem()
        return None if item is None else item.data(ACTION_NAME_ROLE)

    def _save_override_actions(self, value, selection, actions) -> None:
        from screen_watch.persistence.selection import dump_selection, set_override_actions

        dump_selection(value, set_override_actions(selection, actions))

    def _sync_saved_action(self, stem: str, *, add: str = "", remove: str = "") -> None:
        from screen_watch.actions.selection import (
            load_action_selection,
            save_action_selection,
        )

        try:
            saved = load_action_selection(stem)
            if saved is None:
                return  # sem subconjunto salvo = todas marcadas
            names = [name for name in saved if name != remove]
            if add and add not in names:
                names.append(add)
            save_action_selection(stem, names)
        except OSError:
            pass

    def _locator_bases(self, mode: str):
        """Bases logicas (ROI, janela) para o localizador; (None, None) se indisponivel."""
        from screen_watch.capture.resolver import resolve

        try:
            target = self._resolve_target(mode)
        except Exception:
            return None, None
        if target is None:
            return None, None
        from screen_watch.platform.window import find_window_by_handle

        try:
            info = find_window_by_handle(target.window_handle)
        except Exception:
            return None, None
        if info is None or not info.exists or info.is_minimized:
            return None, None
        return resolve(info, target.roi_relative), info.rect

    def _action_new(self) -> None:
        value, selection = self._current_selection()
        if selection is None:
            QMessageBox.information(self, "Screen Diff Watcher", "selecione uma selecao")
            return
        from screen_watch.gui.action_editor import ActionEditorDialog
        from screen_watch.persistence.selection import override_actions

        mode = self.mode_combo.currentText() or selection.mode
        roi_rect, window_rect = self._locator_bases(mode)
        raw = ActionEditorDialog(
            self, mode=mode, title="Nova acao", roi_rect=roi_rect, window_rect=window_rect
        ).run()
        if raw is None:
            return
        actions = override_actions(selection)
        if any(item.get("name") == raw["name"] for item in actions):
            QMessageBox.warning(
                self, "Screen Diff Watcher", f"ja existe uma acao {raw['name']!r} nesta selecao"
            )
            return
        actions.append(raw)
        self._save_override_actions(value, selection, actions)
        self._sync_saved_action(Path(value).stem, add=raw["name"])
        self._append(f"acao adicionada: {raw['name']} (aplica no proximo start)")
        self._populate_actions()
        self._print_action_summary()

    def _action_edit(self) -> None:
        value, selection = self._current_selection()
        if selection is None:
            return
        name = self._selected_action_name()
        if name is None:
            QMessageBox.information(self, "Screen Diff Watcher", "selecione uma acao na lista")
            return
        from screen_watch.gui.action_editor import ActionEditorDialog
        from screen_watch.persistence.selection import override_actions

        actions = override_actions(selection)
        index = next((i for i, item in enumerate(actions) if item.get("name") == name), None)
        if index is None:
            QMessageBox.information(
                self,
                "Screen Diff Watcher",
                "esta acao vem do perfil/YAML (nao editavel aqui); crie uma nova ou edite o YAML",
            )
            return
        mode = self.mode_combo.currentText() or selection.mode
        roi_rect, window_rect = self._locator_bases(mode)
        raw = ActionEditorDialog(
            self,
            mode=mode,
            action=actions[index],
            title="Editar acao",
            roi_rect=roi_rect,
            window_rect=window_rect,
        ).run()
        if raw is None:
            return
        actions[index] = raw
        self._save_override_actions(value, selection, actions)
        if raw["name"] != name:
            self._sync_saved_action(Path(value).stem, add=raw["name"], remove=name)
        self._append(f"acao atualizada: {name} -> {raw['name']}")
        self._populate_actions()
        self._print_action_summary()

    def _action_remove(self) -> None:
        value, selection = self._current_selection()
        if selection is None:
            return
        name = self._selected_action_name()
        if name is None:
            QMessageBox.information(self, "Screen Diff Watcher", "selecione uma acao na lista")
            return
        from screen_watch.persistence.selection import override_actions

        actions = override_actions(selection)
        remaining = [item for item in actions if item.get("name") != name]
        if len(remaining) == len(actions):
            QMessageBox.information(
                self,
                "Screen Diff Watcher",
                "esta acao vem do perfil/YAML; edite o YAML para remove-la",
            )
            return
        confirm = QMessageBox.question(
            self,
            "Remover acao",
            f"Remover a acao {name!r} desta selecao?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._save_override_actions(value, selection, remaining)
        self._sync_saved_action(Path(value).stem, remove=name)
        self._append(f"acao removida: {name}")
        self._populate_actions()
        self._print_action_summary()

    def _print_action_summary(self) -> None:
        from screen_watch.actions.summary import describe_actions
        from screen_watch.app import profile_from_config
        from screen_watch.persistence.selection import load_selection, resolve_actions

        selected = self._selected()
        if selected is None:
            return
        _kind, value = selected
        stem = Path(value).stem
        try:
            selection = load_selection(value)
            profile = profile_from_config(self._config, self._profile, stem)
            actions = resolve_actions(selection, profile, self.mode_combo.currentText() or None)
        except Exception as exc:
            self._append(f"acoes indisponiveis: {exc}")
            return
        self._append(f"acoes de {stem}: {len(actions)}")
        for line in describe_actions(actions, self._checked_action_names()):
            self._append(line)

    def _mode_changed(self, mode: str) -> None:
        selected = self._selected()
        if selected is None:
            return
        _kind, value = selected
        try:
            from screen_watch.persistence.selection import dump_selection, load_selection

            dump_selection(value, replace(load_selection(value), mode=mode))
        except (OSError, ValueError) as exc:
            self._append(f"nao foi possivel gravar o modo: {exc}")
            return
        item = self.list.currentItem()
        if item is not None:
            item.setText(self._label_for("selection", value))
        self._append(f"modo de {Path(value).stem} -> {mode}")

    def _toggle_clicked(self) -> None:
        if self._controller.running:
            self._stop()
        else:
            self._start()

    def _run_action_once(self) -> None:
        if self._controller.running:
            QMessageBox.information(
                self, "Screen Diff Watcher", "pare a sessao antes de executar uma acao"
            )
            return
        try:
            target = self._resolve_target(self.mode_combo.currentText())
        except Exception as exc:
            QMessageBox.warning(self, "Screen Diff Watcher", f"falha ao carregar: {exc}")
            return
        if target is None:
            QMessageBox.information(self, "Screen Diff Watcher", "selecione uma selecao")
            return
        if not target.actions:
            QMessageBox.information(
                self, "Screen Diff Watcher", "nenhuma acao selecionada para esta sessao"
            )
            return

        import time

        from screen_watch.__main__ import _capture_target_roi
        from screen_watch.actions.once import run_actions
        from screen_watch.app import evidence_recorder
        from screen_watch.capture.frame import Frame
        from screen_watch.gui.countdown import run_countdown

        try:
            rgb, abs_rect, info = _capture_target_roi(target)
        except Exception as exc:
            QMessageBox.warning(self, "Screen Diff Watcher", f"falha ao capturar ROI: {exc}")
            return
        frame = Frame(
            rgb=rgb,
            timestamp=time.time(),
            absolute_rect=abs_rect,
            window_rect=info.rect,
            window_handle=info.handle,
            sequence=1,
        )
        self._append("executando acao (3s); foque a janela-alvo...")
        recorder = evidence_recorder(self._config, force_enabled=True)
        code, lines = run_actions(
            target, frame, armed=True, recorder=recorder, countdown=run_countdown
        )
        for line in lines:
            self._append(line)
        if code != 0:
            self._append("execucao nao concluida")

    def _start(self) -> None:
        if self._controller.running:
            return
        try:
            target = self._resolve_target(self.mode_combo.currentText())
        except Exception as exc:
            QMessageBox.warning(self, "Screen Diff Watcher", f"falha ao carregar: {exc}")
            return
        if target is None:
            QMessageBox.information(self, "Screen Diff Watcher", "selecione uma selecao")
            return
        try:
            from screen_watch.app import evidence_recorder

            recorder = evidence_recorder(self._config)
            self._controller.start(target, recorder=recorder)
        except Exception as exc:
            QMessageBox.critical(self, "Screen Diff Watcher", f"falha ao iniciar: {exc}")
            return
        self._active_name = target.name
        from screen_watch.platform.paths import update_state

        fields: dict[str, object] = {"last_selection": f"{target.name}.json"}
        if self._profile:
            fields["profile"] = self._profile
        update_state(**fields)
        self.status.setText(f"monitorando {target.name!r} ({target.mode})")
        self._set_running(True)
        self._print_action_summary()

    def _stop(self) -> None:
        self._controller.stop()
        self._active_name = ""
        self.status.setText("parado")
        self._set_running(False)

    def _rearm(self) -> None:
        if not self._controller.running:
            return
        self._controller.rebaseline()
        self._append("baseline re-armado (proximo frame)")

    def _start_hotkeys(self) -> None:
        if self._config is None or self._config.legacy:
            return
        mapping = dict(self._config.ui.hotkeys)
        if not mapping:
            return
        from screen_watch.gui.hotkeys import start_hotkeys

        self._hotkeys = start_hotkeys(self._controller.events, mapping)
        if self._hotkeys is None:
            self._append("hotkeys globais indisponiveis (instale o extra 'input')")

    def _remove(self) -> None:
        items = self.list.selectedItems()
        if not items:
            QMessageBox.information(self, "Screen Diff Watcher", "selecione um ou mais itens")
            return

        entries = [item.data(TARGET_ROLE) for item in items]
        preview = ", ".join(item.text() for item in items[:3])
        if len(items) > 3:
            preview += ", ..."
        confirm = QMessageBox.question(
            self,
            "Remover",
            f"Remover {len(items)} selecao(oes)?\n{preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        remove_names = {Path(value).stem for _kind, value in entries}
        if self._controller.running and self._active_name in remove_names:
            self._stop()

        removed = 0
        errors: list[str] = []
        for _kind, value in entries:
            try:
                Path(value).unlink(missing_ok=True)
                removed += 1
            except Exception as exc:
                errors.append(f"{value}: {exc}")

        self._append(f"removido(s): {removed}")
        if errors:
            QMessageBox.warning(self, "Screen Diff Watcher", "falhas:\n" + "\n".join(errors))
        self._reload()

    def _new_target(self) -> None:
        from screen_watch.platform.window import app_window_label, list_app_windows

        windows = list_app_windows()
        if not windows:
            QMessageBox.warning(
                self, "Screen Diff Watcher", "nenhuma aplicacao com janela ativa"
            )
            return

        labels: list[str] = []
        seen: dict[str, int] = {}
        for window in windows:
            label = app_window_label(window)
            if label in seen:
                seen[label] += 1
                label = f"{label} #{seen[label]}"
            else:
                seen[label] = 1
            labels.append(label)

        choice, ok = QInputDialog.getItem(
            self, "Escolha a janela", "Aplicacao:", labels, 0, False
        )
        if not ok:
            return
        info = windows[labels.index(choice)]

        from screen_watch.__main__ import capture_selection_for_window

        try:
            captured = capture_selection_for_window(
                info.handle, mode=self.mode_combo.currentText()
            )
        except Exception as exc:
            QMessageBox.critical(self, "Screen Diff Watcher", f"falha na selecao: {exc}")
            return
        self._append(f"selecao gravada: {captured.path}")
        self._reload()

    def _open_yaml(self) -> None:
        path = self._config_path
        if not path.exists():
            QMessageBox.warning(self, "Screen Diff Watcher", f"config nao encontrado: {path}")
            return
        from screen_watch.platform.shell import open_path

        if not open_path(path):
            self._append(f"abra manualmente: {path}")

    def _open_captures(self) -> None:
        from screen_watch.evidence.recorder import ensure_captures_dir
        from screen_watch.platform.shell import open_path

        options = None
        if self._config is not None and not self._config.legacy:
            options = self._config.evidence
        try:
            directory = ensure_captures_dir(options)
        except OSError as exc:
            self._append(f"nao foi possivel criar a pasta de prints: {exc}")
            return
        if not open_path(directory):
            self._append(f"abra manualmente: {directory}")

    # -- eventos -----------------------------------------------------------
    def _set_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_rearm.setEnabled(running)
        self.btn_run_action.setEnabled(not running)
        self.btn_new.setEnabled(not running)
        self.mode_combo.setEnabled(not running)

    def _drain(self) -> None:
        self._update_action_status()
        while True:
            try:
                event = self._controller.events.get_nowait()
            except Exception:
                return
            self._handle(event)

    def _handle(self, event: dict) -> None:
        kind = event.get("kind")
        if kind == "started":
            self.status.setText(f"monitorando {event.get('target')!r}")
            self._set_running(True)
        elif kind == "stopped":
            self.status.setText("parado")
            self._set_running(False)
        elif kind == "result":
            self.last.setText(
                f"ultimo: {event['strategy']} score={event['score']:.3f} "
                f"sev={event['severity']} -> {event['outcome']}"
            )
        elif kind == "error":
            self._append(f"erro: {event.get('message')}")
        elif kind == "event":
            name = event.get("name")
            self.status.setText(f"estado: {name} {event.get('payload') or ''}".strip())
            self._append(f"evento: {name} {event.get('payload') or ''}")
        elif kind == "tray":
            self._handle_tray(event.get("action"))
        elif kind == "action":
            self._handle_action(event)
        elif kind == "action_event":
            self._handle_action_event(event.get("payload") or {})
        elif kind == "profile":
            self._select_profile(str(event.get("name") or ""))

    def _handle_action_event(self, payload: dict) -> None:
        action = payload.get("action") or "?"
        mode = payload.get("mode") or "?"
        if mode == "armed":
            status = "ok" if payload.get("executed") else f"falhou ({payload.get('reason') or '?'})"
        elif mode == "rehearsal":
            status = "ensaio"
        else:
            status = payload.get("reason") or "?"
        self._append(f"acoes: {mode} {action} -> {status}")

    def _handle_action(self, event: dict) -> None:
        dispatcher = self._controller.actions
        if dispatcher is None:
            self._append("sem acoes configuradas para esta selecao")
            return
        arming = dispatcher.arming
        action = event.get("action")
        if action == "arm":
            arming.arm()
        elif action == "disarm":
            arming.disarm()
        elif action == "toggle":
            arming.toggle()
        elif action == "arm_for":
            arming.arm_for(float(event.get("minutes") or 1))
        elif action == "abort":
            arming.abort()
        elif action == "rearm":
            self._rearm()
            self._update_action_status()
            return
        else:
            return
        self._append(f"acoes: {arming.label()}")
        self._update_action_status()

    def _update_action_status(self) -> None:
        dispatcher = self._controller.actions
        if dispatcher is None:
            self.status.setToolTip("acoes: nenhuma configurada")
            return
        parts = [f"acoes: {dispatcher.arming.label()}"]
        if not dispatcher.is_schedule_open():
            parts.append("fora do horario (acoes suspensas)")
        self.status.setToolTip(" — ".join(parts))

    def _handle_tray(self, action) -> None:
        if action == "toggle":
            self.setVisible(not self.isVisible())
        elif action == "minimize":
            self.hide()
        elif action == "start":
            self._start()
        elif action == "stop":
            self._stop()
        elif action == "quit":
            self._quit()

    def _quit(self) -> None:
        self._timer.stop()
        from screen_watch.gui.hotkeys import stop_hotkeys

        stop_hotkeys(self._hotkeys)
        self._controller.stop()
        if self._on_quit is not None:
            self._on_quit()

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text)

    def closeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        from screen_watch.gui.hotkeys import stop_hotkeys

        stop_hotkeys(self._hotkeys)
        self._controller.stop()
        super().closeEvent(event)


def run_gui(config_path, profile: str | None = None) -> int:
    """Sobe a GUI minima com tray e roda o loop de eventos do Qt."""
    from PyQt6.QtWidgets import QApplication

    from screen_watch.gui.tray import start_tray, stop_tray
    from screen_watch.platform.dpi import set_dpi_awareness

    set_dpi_awareness()
    app = QApplication.instance() or QApplication([])
    icon = _window_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    events = new_event_queue()
    controller = MonitorController(events)
    window = MainWindow(controller, config_path, profile=profile, on_quit=app.quit)
    tray = start_tray(
        events, arm_durations=window.arm_durations(), profiles=window.profile_names()
    )
    window.show()
    try:
        return int(app.exec())
    finally:
        stop_tray(tray)
        controller.stop()
