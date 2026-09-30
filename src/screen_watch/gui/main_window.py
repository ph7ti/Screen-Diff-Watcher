"""Janela principal da GUI minima (doc 13.9, P3/P6/P10; layout do UI.txt).

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
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from screen_watch.actions.arming import ARMED, TIMED
from screen_watch.errors import ConfigError, render_error
from screen_watch.gui.controller import MonitorController, new_event_queue
from screen_watch.gui.hover_help import attach_help
from screen_watch.gui.labels import selection_label
from screen_watch.i18n import available_locales, current_language, locale_meta, tr

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
        self.setWindowTitle(tr("main.title"))
        self.resize(960, 640)
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
        self._help_filters: list[object] = []

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._drain)

        self._build_ui()
        self._reload()
        self._start_hotkeys()
        self._timer.start()

    # -- construcao --------------------------------------------------------
    def _help(self, widget, key: str) -> None:
        self._help_filters.append(attach_help(widget, key))

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Vertical)
        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)

        columns = QHBoxLayout()

        monitoring = QGroupBox(tr("main.monitoring"))
        mon = QVBoxLayout(monitoring)
        self.btn_start = QPushButton(tr("main.btn_start"))
        self.btn_stop = QPushButton(tr("main.btn_stop"))
        self.btn_stop.setEnabled(False)
        self.btn_rearm = QPushButton(tr("main.btn_rearm"))
        self.btn_rearm.setEnabled(False)
        self.btn_minimize = QPushButton(tr("main.btn_minimize"))
        for button in (self.btn_start, self.btn_stop, self.btn_rearm, self.btn_minimize):
            mon.addWidget(button)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(tr("main.mode_label")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODES)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        mon.addLayout(mode_row)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel(tr("main.profile_label")))
        self.profile_combo = QComboBox()
        profile_row.addWidget(self.profile_combo)
        self.profile_note = QLabel("")
        profile_row.addWidget(self.profile_note)
        profile_row.addStretch(1)
        mon.addLayout(profile_row)

        language_row = QHBoxLayout()
        language_row.addWidget(QLabel(tr("main.language_label")))
        self.language_combo = QComboBox()
        language_row.addWidget(self.language_combo)
        language_row.addStretch(1)
        mon.addLayout(language_row)

        arm_row = QHBoxLayout()
        self.btn_arm = QPushButton(tr("main.btn_arm"))
        self.btn_disarm = QPushButton(tr("main.btn_disarm"))
        self.btn_arm_for = QPushButton(tr("main.btn_arm_for"))
        self._arm_menu = QMenu(self.btn_arm_for)
        self.btn_arm_for.setMenu(self._arm_menu)
        for button in (self.btn_arm, self.btn_disarm, self.btn_arm_for):
            arm_row.addWidget(button)
        arm_row.addStretch(1)
        mon.addLayout(arm_row)

        self.arming_label = QLabel("")
        self.arming_label.setWordWrap(True)
        mon.addWidget(self.arming_label)
        mon.addStretch(1)

        columns.addWidget(monitoring, 1)

        selections = QGroupBox(tr("main.selections"))
        sel = QVBoxLayout(selections)
        sel.addWidget(QLabel(tr("main.selections_legend")))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        sel.addWidget(self.list)
        columns.addWidget(selections, 2)

        upper_layout.addLayout(columns)

        buttons = QHBoxLayout()
        self.btn_new = QPushButton(tr("main.btn_new"))
        self.btn_remove = QPushButton(tr("main.btn_remove"))
        self.btn_reload = QPushButton(tr("main.btn_reload"))
        self.btn_open = QPushButton(tr("main.btn_open_yaml"))
        self.btn_open_captures = QPushButton(tr("main.btn_captures"))
        self.btn_test_alert = QPushButton(tr("main.btn_test_alert"))
        self.chk_evidence = QCheckBox(tr("main.chk_evidence"))
        for widget in (
            self.btn_new,
            self.btn_remove,
            self.btn_reload,
            self.btn_open,
            self.btn_open_captures,
            self.btn_test_alert,
            self.chk_evidence,
        ):
            buttons.addWidget(widget)
        buttons.addStretch(1)
        upper_layout.addLayout(buttons)

        actions_group = QGroupBox(tr("main.actions_session"))
        actions_layout = QHBoxLayout(actions_group)
        actions_left = QVBoxLayout()
        self.action_list = QListWidget()
        self.action_list.setMaximumHeight(160)
        actions_left.addWidget(self.action_list)
        self.action_count = QLabel("")
        actions_left.addWidget(self.action_count)
        actions_layout.addLayout(actions_left, 3)

        actions_right = QVBoxLayout()
        self.btn_action_new = QPushButton(tr("main.btn_action_new"))
        self.btn_action_edit = QPushButton(tr("main.btn_action_edit"))
        self.btn_action_remove = QPushButton(tr("main.btn_action_remove"))
        self.btn_action_arm = QPushButton(tr("main.btn_action_arm"))
        self.btn_run_action = QPushButton(tr("main.btn_action_run"))
        for button in (
            self.btn_action_new,
            self.btn_action_edit,
            self.btn_action_remove,
            self.btn_action_arm,
            self.btn_run_action,
        ):
            actions_right.addWidget(button)
        actions_right.addStretch(1)
        actions_layout.addLayout(actions_right, 2)
        upper_layout.addWidget(actions_group)
        upper_layout.addStretch(1)

        lower = QWidget()
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel(tr("main.status_label")))
        self.status = QLabel(tr("status.stopped"))
        status_row.addWidget(self.status, 1)
        lower_layout.addLayout(status_row)

        last_row = QHBoxLayout()
        last_row.addWidget(QLabel(tr("main.last_label")))
        self.last = QLabel(tr("status.last_none"))
        last_row.addWidget(self.last, 1)
        lower_layout.addLayout(last_row)

        lower_layout.addWidget(QLabel(tr("main.log_label")))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        lower_layout.addWidget(self.log)

        splitter.addWidget(upper)
        splitter.addWidget(lower)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

        # ligacoes
        self.list.currentItemChanged.connect(self._item_changed)
        self.list.itemDoubleClicked.connect(lambda _item: self._toggle_clicked())
        self.mode_combo.currentTextChanged.connect(self._mode_changed)
        self.profile_combo.currentTextChanged.connect(self._profile_changed)
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        self.action_list.itemChanged.connect(self._actions_changed)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_rearm.clicked.connect(self._rearm)
        self.btn_minimize.clicked.connect(self.hide)
        self.btn_arm.clicked.connect(lambda: self._handle_action({"action": "arm"}))
        self.btn_disarm.clicked.connect(lambda: self._handle_action({"action": "disarm"}))
        self.btn_run_action.clicked.connect(self._run_action_once)
        self.btn_action_arm.clicked.connect(lambda: self._handle_action({"action": "arm"}))
        self.btn_action_new.clicked.connect(self._action_new)
        self.btn_action_edit.clicked.connect(self._action_edit)
        self.btn_action_remove.clicked.connect(self._action_remove)
        self.btn_new.clicked.connect(self._new_target)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_reload.clicked.connect(self._reload)
        self.btn_open.clicked.connect(self._open_yaml)
        self.btn_open_captures.clicked.connect(self._open_captures)
        self.btn_test_alert.clicked.connect(self._test_alert)
        self.chk_evidence.toggled.connect(self._toggle_evidence)

        # ajuda no hover (>2 s)
        self._help(self.btn_start, "window.start")
        self._help(self.btn_stop, "window.stop")
        self._help(self.btn_rearm, "window.rearm")
        self._help(self.btn_minimize, "window.minimize")
        self._help(self.mode_combo, "window.mode")
        self._help(self.profile_combo, "window.profile")
        self._help(self.language_combo, "window.language")
        self._help(self.btn_arm, "window.arm")
        self._help(self.btn_disarm, "window.disarm")
        self._help(self.btn_arm_for, "window.arm_for")
        self._help(self.btn_run_action, "window.run_action")
        self._help(self.btn_action_arm, "window.arm")
        self._help(self.btn_new, "window.new_target")
        self._help(self.btn_remove, "window.remove")
        self._help(self.btn_reload, "window.reload")
        self._help(self.btn_open, "window.open_yaml")
        self._help(self.btn_open_captures, "window.captures")
        self._help(self.btn_test_alert, "window.test_alert")
        self._help(self.chk_evidence, "window.evidence")
        self._help(self.action_list, "window.actions_list")
        self._help(self.btn_action_new, "window.action_new")
        self._help(self.btn_action_edit, "window.action_edit")
        self._help(self.btn_action_remove, "window.action_remove")

        self._update_action_status()

    # -- dados -------------------------------------------------------------
    def _reload(self) -> None:
        from screen_watch.config.loader import (
            default_config_dict,
            load_config,
            save_config,
        )
        from screen_watch.platform.paths import selections_dir

        self.list.clear()
        self._entries.clear()
        self._config = None

        if not self._config_path.exists():
            # Primeiro uso: cria o default no app-data do usuario (o instalador nao
            # roda init-config para nao gravar no perfil do admin).
            try:
                save_config(self._config_path, default_config_dict())
                self._append(f"default config created at: {self._config_path}")
            except OSError as exc:
                self._append(f"could not create config: {exc}")

        try:
            self._config = load_config(self._config_path)
        except ConfigError as exc:
            self._append(f"config unavailable: {exc}")
        if self._config is not None and self._config.legacy:
            self._append("warning: legacy v1 YAML (targets); run 'migrate-config' for v2")
        self._sync_evidence_toggle()
        self._populate_arm_menu()
        self._populate_languages()

        for path in sorted(selections_dir().glob("*.json")):
            self._entries.append(("selection", path))

        for kind, value in self._entries:
            item = QListWidgetItem(self._label_for(kind, value))
            item.setData(TARGET_ROLE, (kind, value))
            self.list.addItem(item)

        self._populate_profiles()
        self._append(
            f"loaded: {len(self._entries)} selection(s) — profile {self._profile_label()}"
        )
        if self.list.count():
            self.list.setCurrentRow(0)
        self._populate_actions()

    def _populate_arm_menu(self) -> None:
        self._arm_menu.clear()
        for minutes in self.arm_durations():
            action = self._arm_menu.addAction(tr("main.arm_minutes", minutes=minutes))
            action.triggered.connect(
                lambda _checked=False, value=minutes: self._handle_action(
                    {"action": "arm_for", "minutes": value}
                )
            )

    def _populate_languages(self) -> None:
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        active = current_language()
        for tag in available_locales():
            label = locale_meta(tag).get("name") or tag
            self.language_combo.addItem(str(label), tag)
        index = self.language_combo.findData(active)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self.language_combo.blockSignals(False)

    def _language_changed(self, _index: int) -> None:
        tag = self.language_combo.currentData()
        if not tag or tag == current_language():
            return
        from screen_watch.platform.paths import update_state

        try:
            update_state(language=str(tag))
        except OSError as exc:
            self._append(f"could not save the language preference: {exc}")
            return
        self._append(f"language -> {tag} (applies on next start)")

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
        pending = tr("main.pending_start") if self._controller.running else ""
        self.profile_note.setText(pending)
        self._append(f"profile -> {name} {pending}".strip())
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
            return f"{self._profile or 'default'} (legacy/no config)"
        return self._profile or self._config.profile

    def arm_durations(self) -> tuple[int, ...]:
        if self._config is None or self._config.legacy:
            return (1, 5, 15, 30)
        return self._config.ui.arm_durations_min or (1, 5, 15, 30)

    def _label_for(self, _kind: str, value) -> str:
        from screen_watch.persistence.selection import load_selection

        try:
            selection = load_selection(value)
        except (ConfigError, OSError, ValueError) as exc:
            return tr("label.unreadable", stem=Path(value).stem, error=exc)
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
        except (ConfigError, OSError, ValueError):
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
        schedule = (
            self._config.schedule if self._config is not None and not self._config.legacy else None
        )
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
            self.action_count.setText(tr("main.no_selection"))
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
            self.action_count.setText(tr("main.actions_unavailable", error=render_error(exc)))
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
            self.action_count.setText(tr("main.no_actions"))
            return
        checked = sum(
            1
            for index in range(total)
            if self.action_list.item(index).checkState() == Qt.CheckState.Checked
        )
        text = tr("main.actions_count", checked=checked, total=total)
        if checked == 0:
            text += tr("main.actions_none_selected")
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
            self._append(f"could not save the action selection: {exc}")
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
        except (ConfigError, OSError, ValueError) as exc:
            self._append(f"unreadable selection: {exc}")
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
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_selection"))
            return
        from screen_watch.gui.action_editor import ActionEditorDialog
        from screen_watch.persistence.selection import override_actions

        mode = self.mode_combo.currentText() or selection.mode
        roi_rect, window_rect = self._locator_bases(mode)
        raw = ActionEditorDialog(
            self,
            mode=mode,
            title=tr("dialog.new_action_title"),
            roi_rect=roi_rect,
            window_rect=window_rect,
        ).run()
        if raw is None:
            return
        actions = override_actions(selection)
        if any(item.get("name") == raw["name"] for item in actions):
            QMessageBox.warning(
                self,
                tr("main.title"),
                tr("dialog.action_duplicate", name=repr(raw["name"])),
            )
            return
        actions.append(raw)
        self._save_override_actions(value, selection, actions)
        self._sync_saved_action(Path(value).stem, add=raw["name"])
        self._append(f"action added: {raw['name']} (applies on next start)")
        self._populate_actions()
        self._print_action_summary()

    def _action_edit(self) -> None:
        value, selection = self._current_selection()
        if selection is None:
            return
        name = self._selected_action_name()
        if name is None:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_action"))
            return
        from screen_watch.gui.action_editor import ActionEditorDialog
        from screen_watch.persistence.selection import override_actions

        actions = override_actions(selection)
        index = next((i for i, item in enumerate(actions) if item.get("name") == name), None)
        if index is None:
            QMessageBox.information(
                self, tr("main.title"), tr("dialog.action_from_profile_edit")
            )
            return
        mode = self.mode_combo.currentText() or selection.mode
        roi_rect, window_rect = self._locator_bases(mode)
        raw = ActionEditorDialog(
            self,
            mode=mode,
            action=actions[index],
            title=tr("dialog.edit_action_title"),
            roi_rect=roi_rect,
            window_rect=window_rect,
        ).run()
        if raw is None:
            return
        actions[index] = raw
        self._save_override_actions(value, selection, actions)
        if raw["name"] != name:
            self._sync_saved_action(Path(value).stem, add=raw["name"], remove=name)
        self._append(f"action updated: {name} -> {raw['name']}")
        self._populate_actions()
        self._print_action_summary()

    def _action_remove(self) -> None:
        value, selection = self._current_selection()
        if selection is None:
            return
        name = self._selected_action_name()
        if name is None:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_action"))
            return
        from screen_watch.persistence.selection import override_actions

        actions = override_actions(selection)
        remaining = [item for item in actions if item.get("name") != name]
        if len(remaining) == len(actions):
            QMessageBox.information(
                self, tr("main.title"), tr("dialog.action_from_profile_remove")
            )
            return
        confirm = QMessageBox.question(
            self,
            tr("dialog.remove_action_title"),
            tr("dialog.remove_action_confirm", name=repr(name)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._save_override_actions(value, selection, remaining)
        self._sync_saved_action(Path(value).stem, remove=name)
        self._append(f"action removed: {name}")
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
            self._append(f"actions unavailable: {render_error(exc)}")
            return
        self._append(f"actions of {stem}: {len(actions)}")
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
        except (ConfigError, OSError, ValueError) as exc:
            self._append(f"could not save the mode: {exc}")
            return
        item = self.list.currentItem()
        if item is not None:
            item.setText(self._label_for("selection", value))
        self._append(f"mode of {Path(value).stem} -> {mode}")

    def _toggle_clicked(self) -> None:
        if self._controller.running:
            self._stop()
        else:
            self._start()

    def _run_action_once(self) -> None:
        if self._controller.running:
            QMessageBox.information(self, tr("main.title"), tr("dialog.stop_before_run"))
            return
        try:
            target = self._resolve_target(self.mode_combo.currentText())
        except Exception as exc:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.load_failed", error=render_error(exc))
            )
            return
        if target is None:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_selection"))
            return
        if not target.actions:
            QMessageBox.information(self, tr("main.title"), tr("main.no_action_selected"))
            return

        import time

        from screen_watch.actions.once import run_actions
        from screen_watch.app import evidence_recorder
        from screen_watch.capture.frame import Frame
        from screen_watch.cli.commands import _capture_target_roi
        from screen_watch.gui.countdown import run_countdown

        try:
            rgb, abs_rect, info = _capture_target_roi(target)
        except Exception as exc:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.capture_failed", error=render_error(exc))
            )
            return
        frame = Frame(
            rgb=rgb,
            timestamp=time.time(),
            absolute_rect=abs_rect,
            window_rect=info.rect,
            window_handle=info.handle,
            sequence=1,
        )
        self._append("running action (3s); focus the target window...")
        recorder = evidence_recorder(self._config, force_enabled=True)
        code, lines = run_actions(
            target, frame, armed=True, recorder=recorder, countdown=run_countdown
        )
        for line in lines:
            self._append(line)
        if code != 0:
            self._append("run not completed")

    def _start(self) -> None:
        if self._controller.running:
            return
        try:
            target = self._resolve_target(self.mode_combo.currentText())
        except Exception as exc:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.load_failed", error=render_error(exc))
            )
            return
        if target is None:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_selection"))
            return
        try:
            from screen_watch.app import evidence_recorder

            recorder = evidence_recorder(self._config)
            self._controller.start(target, recorder=recorder)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("main.title"), tr("dialog.start_failed", error=render_error(exc))
            )
            return
        self._active_name = target.name
        from screen_watch.platform.paths import update_state

        fields: dict[str, object] = {"last_selection": f"{target.name}.json"}
        if self._profile:
            fields["profile"] = self._profile
        update_state(**fields)
        self.status.setText(tr("status.monitoring", name=target.name, mode=target.mode))
        self._set_running(True)
        self._print_action_summary()

    def _stop(self) -> None:
        self._controller.stop()
        self._active_name = ""
        self.status.setText(tr("status.stopped"))
        self._set_running(False)

    def _rearm(self) -> None:
        if not self._controller.running:
            return
        self._controller.rebaseline()
        self._append("baseline re-armed (next frame)")

    def _start_hotkeys(self) -> None:
        if self._config is None or self._config.legacy:
            return
        mapping = dict(self._config.ui.hotkeys)
        if not mapping:
            return
        from screen_watch.gui.hotkeys import start_hotkeys

        self._hotkeys = start_hotkeys(self._controller.events, mapping)
        if self._hotkeys is None:
            self._append("global hotkeys unavailable (install the 'input' extra)")

    def _remove(self) -> None:
        items = self.list.selectedItems()
        if not items:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_items"))
            return

        entries = [item.data(TARGET_ROLE) for item in items]
        preview = ", ".join(item.text() for item in items[:3])
        if len(items) > 3:
            preview += ", ..."
        confirm = QMessageBox.question(
            self,
            tr("dialog.remove_title"),
            tr("dialog.remove_confirm", count=len(items), preview=preview),
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

        self._append(f"removed: {removed}")
        if errors:
            QMessageBox.warning(self, tr("main.title"), "failures:\n" + "\n".join(errors))
        self._reload()

    def _new_target(self) -> None:
        from screen_watch.platform.window import app_window_label, list_app_windows

        windows = list_app_windows()
        if not windows:
            QMessageBox.warning(self, tr("main.title"), tr("dialog.no_app_windows"))
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
            self, tr("dialog.choose_window_title"), tr("dialog.choose_window_label"), labels, 0, False
        )
        if not ok:
            return
        info = windows[labels.index(choice)]

        from screen_watch.cli.commands import capture_selection_for_window

        try:
            captured = capture_selection_for_window(
                info.handle, mode=self.mode_combo.currentText()
            )
        except Exception as exc:
            QMessageBox.critical(
                self, tr("main.title"), tr("dialog.selection_failed", error=render_error(exc))
            )
            return
        self._append(f"selection saved: {captured.path}")
        self._reload()

    def _open_yaml(self) -> None:
        path = self._config_path
        if not path.exists():
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.config_missing", path=path)
            )
            return
        from screen_watch.platform.shell import open_path

        if not open_path(path):
            self._append(f"open manually: {path}")

    def _test_alert(self) -> None:
        try:
            target = self._resolve_target(self.mode_combo.currentText())
        except Exception as exc:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.load_failed", error=render_error(exc))
            )
            return
        if target is None:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_selection"))
            return
        if not target.alerts:
            QMessageBox.information(self, tr("main.title"), tr("main.no_alerts"))
            return
        from screen_watch.gui.alert_dialog import AlertTestDialog

        AlertTestDialog(self, target).exec()

    def _sync_evidence_toggle(self) -> None:
        from screen_watch.app import effective_evidence_options

        enabled = bool(effective_evidence_options(self._config).enabled)
        self.chk_evidence.blockSignals(True)
        self.chk_evidence.setChecked(enabled)
        self.chk_evidence.blockSignals(False)

    def _toggle_evidence(self, checked: bool) -> None:
        from screen_watch.platform.paths import update_state

        try:
            update_state(evidence_enabled=bool(checked))
        except OSError as exc:
            self._append(f"could not save the captures preference: {exc}")
            return
        self._append(f"captures (evidence) -> {'on' if checked else 'off'}")

    def _open_captures(self) -> None:
        from screen_watch.app import effective_evidence_options
        from screen_watch.evidence.recorder import ensure_captures_dir
        from screen_watch.platform.shell import open_path

        options = effective_evidence_options(self._config)
        try:
            directory = ensure_captures_dir(options)
        except OSError as exc:
            self._append(f"could not create the captures folder: {exc}")
            return
        if not options.enabled:
            self._append(
                "warning: monitoring captures are OFF — check 'Record captures (evidence)' "
                "and restart the session (the 'Run action' button always saves one capture)"
            )
        if not open_path(directory):
            self._append(f"open manually: {directory}")

    # -- eventos -----------------------------------------------------------
    def _arming_text(self) -> str:
        dispatcher = self._controller.actions
        if dispatcher is None:
            return tr("arming.none")
        arming = dispatcher.arming
        state = arming.state
        if state == TIMED:
            remaining = arming.remaining_s() or 0.0
            return tr("arming.timed", remaining=f"{remaining:.0f}")
        return tr("arming.armed") if state == ARMED else tr("arming.disarmed")

    def _update_arming_buttons(self) -> None:
        active = self._controller.running and self._controller.actions is not None
        for button in (self.btn_arm, self.btn_disarm, self.btn_arm_for, self.btn_action_arm):
            button.setEnabled(active)

    def _set_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_rearm.setEnabled(running)
        self.btn_run_action.setEnabled(not running)
        self.btn_new.setEnabled(not running)
        self.btn_remove.setEnabled(not running)
        self.btn_reload.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.language_combo.setEnabled(not running)
        self._update_arming_buttons()

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
            self.status.setText(tr("status.monitoring_short", name=event.get("target")))
            self._set_running(True)
        elif kind == "stopped":
            self.status.setText(tr("status.stopped"))
            self._set_running(False)
        elif kind == "result":
            self.last.setText(
                tr(
                    "status.last",
                    strategy=event["strategy"],
                    score=f"{event['score']:.3f}",
                    severity=event["severity"],
                    outcome=event["outcome"],
                )
            )
        elif kind == "error":
            self._append(f"error: {event.get('message')}")
        elif kind == "event":
            name = event.get("name")
            self.status.setText(
                tr("status.state", name=name, payload=event.get("payload") or "").strip()
            )
            self._append(f"event: {name} {event.get('payload') or ''}")
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
            status = "ok" if payload.get("executed") else f"failed ({payload.get('reason') or '?'})"
        elif mode == "rehearsal":
            status = "rehearsal"
        else:
            status = payload.get("reason") or "?"
        self._append(f"actions: {mode} {action} -> {status}")

    def _handle_action(self, event: dict) -> None:
        dispatcher = self._controller.actions
        if dispatcher is None:
            self._append("no actions configured for this selection")
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
        self._append(f"actions: {arming.label()}")
        self._update_action_status()

    def _update_action_status(self) -> None:
        dispatcher = self._controller.actions
        text = self._arming_text()
        self.arming_label.setText(text)
        self._update_arming_buttons()
        if dispatcher is None:
            self.status.setToolTip(tr("arming.none"))
            return
        parts = [tr("arming.status", state=text)]
        if not dispatcher.is_schedule_open():
            parts.append(tr("arming.outside_schedule"))
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
