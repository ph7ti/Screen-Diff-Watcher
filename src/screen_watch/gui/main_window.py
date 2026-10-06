"""Janela principal da GUI minima (doc 13.9, P3/P6/P10; layout do UI.txt).

Nao faz I/O de rede nem toca no loop: apenas reflete a config/selecoes, dispara
iniciar/parar no `SessionManager` (N sessoes, v0.9.0) e consome eventos da fila
via `QTimer`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
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
from screen_watch.errors import AppError, ConfigError, render_error
from screen_watch.gui.hover_help import attach_help
from screen_watch.gui.labels import selection_label
from screen_watch.gui.preview_widget import PreviewPanel
from screen_watch.gui.session_manager import SessionManager, new_event_queue
from screen_watch.i18n import available_locales, current_language, locale_meta, tr

POLL_MS = 200
TARGET_ROLE = 1
ACTION_NAME_ROLE = 2
LABEL_ROLE = 3
MODES = ("light", "default", "advanced")
SOUND_FILTER = (
    "Audio (*.wav *.mp3 *.m4a *.aac *.ogg *.oga *.flac *.wma);;All files (*)"
)


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
        self, controller: SessionManager, config_path, profile: str | None = None, on_quit=None
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
        # Som escolhido no seletor para pre-visualizar (nunca persistido).
        self._sound_choice: str | None = None
        # Selecao cujo texto do watch foi editado sem commit (guarda contra
        # `editingFinished` depois de trocar a selecao).
        self._watch_edit_stem: str | None = None
        # (dialog, widget) da calibracao ao vivo, enquanto o dialogo estiver aberto.
        self._calibration_dialog: tuple[QDialog, object] | None = None

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
        upper_layout = QGridLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setColumnStretch(0, 3)
        upper_layout.setColumnStretch(1, 2)

        selections = QGroupBox(tr("main.selections"))
        sel = QVBoxLayout(selections)
        selection_buttons = QHBoxLayout()
        self.btn_new = QPushButton(tr("main.btn_new"))
        self.btn_remove = QPushButton(tr("main.btn_remove"))
        self.btn_reload = QPushButton(tr("main.btn_reload"))
        self.btn_show_roi = QPushButton(tr("main.btn_show_roi"))
        self.btn_show_roi.setEnabled(False)
        self.btn_masks = QPushButton(tr("main.btn_edit_masks"))
        self.btn_masks.setEnabled(False)
        for widget in (
            self.btn_new,
            self.btn_remove,
            self.btn_reload,
            self.btn_show_roi,
            self.btn_masks,
        ):
            selection_buttons.addWidget(widget)
        selection_buttons.addStretch(1)
        sel.addLayout(selection_buttons)
        sel.addWidget(QLabel(tr("main.selections_legend")))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        sel.addWidget(self.list)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("main.selection_name_label")))
        self.selection_name = QLineEdit()
        self.selection_name.setEnabled(False)
        name_row.addWidget(self.selection_name, 1)
        self.btn_rename = QPushButton(tr("main.btn_rename"))
        self.btn_rename.setEnabled(False)
        name_row.addWidget(self.btn_rename)
        sel.addLayout(name_row)
        upper_layout.addWidget(selections, 0, 0)

        monitoring = QGroupBox(tr("main.monitoring"))
        mon = QGridLayout(monitoring)
        mon.setColumnStretch(0, 1)
        mon.setColumnStretch(1, 1)
        self.btn_start = QPushButton(tr("main.btn_start"))
        self.btn_stop = QPushButton(tr("main.btn_stop"))
        self.btn_stop.setEnabled(False)
        self.btn_rearm = QPushButton(tr("main.btn_rearm"))
        self.btn_rearm.setEnabled(False)
        self.btn_minimize = QPushButton(tr("main.btn_minimize"))
        mon.addWidget(self.btn_start, 0, 0)

        language_row = QHBoxLayout()
        language_row.addWidget(QLabel(tr("main.language_label")))
        self.language_combo = QComboBox()
        language_row.addWidget(self.language_combo, 1)
        mon.addLayout(language_row, 0, 1)

        mon.addWidget(self.btn_stop, 1, 0)
        mon.addWidget(self.btn_rearm, 1, 1)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(tr("main.mode_label")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODES)
        mode_row.addWidget(self.mode_combo, 1)
        mon.addLayout(mode_row, 2, 0)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel(tr("main.profile_label")))
        self.profile_combo = QComboBox()
        profile_row.addWidget(self.profile_combo, 1)
        self.profile_note = QLabel("")
        profile_row.addWidget(self.profile_note)
        mon.addLayout(profile_row, 2, 1)

        self.btn_arm = QPushButton(tr("main.btn_arm"))
        self.btn_disarm = QPushButton(tr("main.btn_disarm"))
        mon.addWidget(self.btn_arm, 3, 0)
        mon.addWidget(self.btn_disarm, 3, 1)

        self.btn_arm_for = QPushButton(tr("main.btn_arm_for"))
        self._arm_menu = QMenu(self.btn_arm_for)
        self.btn_arm_for.setMenu(self._arm_menu)
        mon.addWidget(self.btn_arm_for, 4, 0)
        mon.addWidget(self.btn_minimize, 4, 1)

        self.chk_evidence = QCheckBox(tr("main.chk_evidence"))
        mon.addWidget(self.chk_evidence, 5, 0, 1, 2)

        self.arming_label = QLabel("")
        self.arming_label.setWordWrap(True)
        mon.addWidget(self.arming_label, 6, 0, 1, 2)

        self.preview = PreviewPanel()
        mon.addWidget(self.preview, 7, 0, 1, 2)
        mon.setRowStretch(8, 1)
        upper_layout.addWidget(monitoring, 0, 1)

        actions_group = QGroupBox(tr("main.actions_session"))
        actions_layout = QVBoxLayout(actions_group)
        self.action_list = QListWidget()
        self.action_list.setMaximumHeight(160)
        actions_layout.addWidget(self.action_list)
        self.action_count = QLabel("")
        actions_layout.addWidget(self.action_count)

        action_buttons = QHBoxLayout()
        self.btn_action_new = QPushButton(tr("main.btn_action_new"))
        self.btn_action_edit = QPushButton(tr("main.btn_action_edit"))
        self.btn_action_remove = QPushButton(tr("main.btn_action_remove"))
        self.btn_run_action = QPushButton(tr("main.btn_action_run"))
        for button in (
            self.btn_action_new,
            self.btn_action_edit,
            self.btn_action_remove,
            self.btn_run_action,
        ):
            action_buttons.addWidget(button)
        action_buttons.addStretch(1)
        actions_layout.addLayout(action_buttons)
        upper_layout.addWidget(actions_group, 1, 0)

        alerts_group = QGroupBox(tr("main.alerts_group"))
        alerts_layout = QVBoxLayout(alerts_group)

        watch_row = QHBoxLayout()
        watch_row.addWidget(QLabel(tr("main.text_watch_label")))
        self.text_watch_edit = QLineEdit()
        watch_row.addWidget(self.text_watch_edit, 1)
        alerts_layout.addLayout(watch_row)

        watch_flags = QHBoxLayout()
        self.case_check = QCheckBox(tr("main.text_watch_case"))
        self.accents_check = QCheckBox(tr("main.text_watch_accents"))
        self.accents_check.setChecked(True)
        watch_flags.addWidget(self.case_check)
        watch_flags.addWidget(self.accents_check)
        watch_flags.addWidget(QLabel(tr("main.text_watch_action")))
        self.expect_combo = QComboBox()
        self.expect_combo.addItem(tr("main.text_watch_appears"), "appears")
        self.expect_combo.addItem(tr("main.text_watch_disappears"), "disappears")
        watch_flags.addWidget(self.expect_combo)
        watch_flags.addWidget(QLabel(tr("main.text_watch_note")))
        watch_flags.addStretch(1)
        alerts_layout.addLayout(watch_flags)

        sound_row = QHBoxLayout()
        sound_row.addWidget(QLabel(tr("main.sound_label")))
        self.sound_path = QLineEdit()
        self.sound_path.setReadOnly(True)
        sound_row.addWidget(self.sound_path, 1)
        alerts_layout.addLayout(sound_row)

        sound_buttons = QHBoxLayout()
        self.btn_sound_choose = QPushButton(tr("main.sound_choose"))
        self.btn_sound_play = QPushButton(tr("main.sound_play"))
        self.btn_sound_copy = QPushButton(tr("main.sound_copy"))
        for button in (self.btn_sound_choose, self.btn_sound_play, self.btn_sound_copy):
            sound_buttons.addWidget(button)
        sound_buttons.addStretch(1)
        alerts_layout.addLayout(sound_buttons)
        alerts_layout.addWidget(QLabel(tr("main.sound_note")))

        gate_row = QHBoxLayout()
        self.btn_snooze = QPushButton(tr("main.btn_snooze"))
        self._snooze_menu = QMenu(self.btn_snooze)
        self.btn_snooze.setMenu(self._snooze_menu)
        self.btn_mute = QPushButton(tr("main.btn_mute"))
        self.btn_ack = QPushButton(tr("main.btn_ack"))
        self.btn_ack.setEnabled(False)
        gate_row.addWidget(self.btn_snooze)
        gate_row.addWidget(self.btn_mute)
        gate_row.addWidget(self.btn_ack)
        gate_row.addStretch(1)
        alerts_layout.addLayout(gate_row)
        self.gate_label = QLabel("")
        alerts_layout.addWidget(self.gate_label)
        upper_layout.addWidget(alerts_group, 1, 1)

        lower = QGroupBox(tr("main.status_label"))
        lower_layout = QHBoxLayout(lower)
        status_column = QVBoxLayout()
        status_row = QHBoxLayout()
        self.status = QLabel(tr("status.stopped"))
        status_row.addWidget(self.status)
        status_row.addStretch(1)
        status_row.addWidget(QLabel(tr("main.last_label")))
        self.last = QLabel(tr("status.last_none"))
        status_row.addWidget(self.last)
        status_column.addLayout(status_row)

        status_column.addWidget(QLabel(tr("main.log_label")))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        status_column.addWidget(self.log)

        side_buttons = QVBoxLayout()
        self.btn_open_captures = QPushButton(tr("main.btn_captures"))
        self.btn_history = QPushButton(tr("main.btn_alert_history"))
        self.btn_calibration = QPushButton(tr("main.btn_calibration"))
        self.btn_test_alert = QPushButton(tr("main.btn_test_alert"))
        self.btn_open = QPushButton(tr("main.btn_open_yaml"))
        for button in (
            self.btn_open_captures,
            self.btn_history,
            self.btn_calibration,
            self.btn_test_alert,
            self.btn_open,
        ):
            side_buttons.addWidget(button)
        side_buttons.addStretch(1)

        lower_layout.addLayout(status_column, 3)
        lower_layout.addLayout(side_buttons, 1)

        splitter.addWidget(upper)
        splitter.addWidget(lower)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

        # ligacoes
        self.list.currentItemChanged.connect(self._item_changed)
        # Duplo clique reedita a regiao; Enter na lista inicia/para (QShortcut com
        # WidgetShortcut: `itemActivated` tambem dispararia no duplo clique).
        self.list.itemDoubleClicked.connect(lambda _item: self._edit_region())
        self._list_shortcuts = [
            QShortcut(QKeySequence(text), self.list) for text in ("Return", "Enter")
        ]
        for shortcut in self._list_shortcuts:
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self._toggle_clicked)
        self.mode_combo.currentTextChanged.connect(self._mode_changed)
        self.profile_combo.currentTextChanged.connect(self._profile_changed)
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        self.action_list.itemChanged.connect(self._actions_changed)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_rearm.clicked.connect(self._rearm)
        self.btn_minimize.clicked.connect(self.hide)
        self.btn_show_roi.clicked.connect(self._show_roi)
        self.btn_masks.clicked.connect(self._edit_masks)
        self.btn_rename.clicked.connect(self._rename_selection)
        self.selection_name.returnPressed.connect(self._rename_selection)
        self.btn_arm.clicked.connect(lambda: self._handle_action({"action": "arm"}))
        self.btn_disarm.clicked.connect(lambda: self._handle_action({"action": "disarm"}))
        self.btn_run_action.clicked.connect(self._run_action_once)
        self.btn_action_new.clicked.connect(self._action_new)
        self.btn_action_edit.clicked.connect(self._action_edit)
        self.btn_action_remove.clicked.connect(self._action_remove)
        self.btn_new.clicked.connect(self._new_target)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_reload.clicked.connect(self._reload)
        self.btn_open.clicked.connect(self._open_yaml)
        self.btn_open_captures.clicked.connect(self._open_captures)
        self.btn_history.clicked.connect(self._open_history)
        self.btn_calibration.clicked.connect(self._open_calibration)
        self.btn_test_alert.clicked.connect(self._test_alert)
        self.chk_evidence.toggled.connect(self._toggle_evidence)
        self.btn_sound_choose.clicked.connect(self._choose_sound)
        self.btn_sound_play.clicked.connect(self._play_sound)
        self.btn_sound_copy.clicked.connect(self._copy_sound_snippet)
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.btn_ack.clicked.connect(self._acknowledge)
        self.text_watch_edit.textEdited.connect(self._mark_text_watch_edited)
        self.text_watch_edit.editingFinished.connect(self._commit_text_watch)
        self.expect_combo.currentIndexChanged.connect(self._save_text_watch)
        self.case_check.toggled.connect(self._save_text_watch)
        self.accents_check.toggled.connect(self._save_text_watch)

        # ajuda no hover (>2 s)
        self._help(self.btn_start, "window.start")
        self._help(self.btn_stop, "window.stop")
        self._help(self.btn_rearm, "window.rearm")
        self._help(self.btn_minimize, "window.minimize")
        self._help(self.btn_show_roi, "window.show_roi")
        self._help(self.btn_masks, "window.edit_masks")
        self._help(self.selection_name, "window.selection_name")
        self._help(self.btn_rename, "window.selection_name")
        self._help(self.mode_combo, "window.mode")
        self._help(self.profile_combo, "window.profile")
        self._help(self.language_combo, "window.language")
        self._help(self.btn_arm, "window.arm")
        self._help(self.btn_disarm, "window.disarm")
        self._help(self.btn_arm_for, "window.arm_for")
        self._help(self.btn_run_action, "window.run_action")
        self._help(self.btn_new, "window.new_target")
        self._help(self.btn_remove, "window.remove")
        self._help(self.btn_reload, "window.reload")
        self._help(self.btn_open, "window.open_yaml")
        self._help(self.btn_open_captures, "window.captures")
        self._help(self.btn_history, "window.alert_history")
        self._help(self.btn_calibration, "window.calibration")
        self._help(self.btn_test_alert, "window.test_alert")
        self._help(self.chk_evidence, "window.evidence")
        self._help(self.action_list, "window.actions_list")
        self._help(self.btn_action_new, "window.action_new")
        self._help(self.btn_action_edit, "window.action_edit")
        self._help(self.btn_action_remove, "window.action_remove")
        self._help(self.btn_sound_choose, "window.sound_choose")
        self._help(self.btn_sound_play, "window.sound_play")
        self._help(self.btn_sound_copy, "window.sound_copy")
        self._help(self.btn_snooze, "window.snooze")
        self._help(self.btn_mute, "window.mute")
        self._help(self.btn_ack, "window.ack")
        self._help(self.text_watch_edit, "window.text_watch")
        self._help(self.expect_combo, "window.text_watch_expect")
        self._help(self.case_check, "window.text_watch_case")
        self._help(self.accents_check, "window.text_watch_accents")
        self._help(self.preview, "window.preview")

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
        self._populate_snooze_menu()
        self._populate_languages()

        for path in sorted(selections_dir().glob("*.json")):
            self._entries.append(("selection", path))

        for kind, value in self._entries:
            label = self._label_for(kind, value)
            item = QListWidgetItem(label)
            item.setData(TARGET_ROLE, (kind, value))
            item.setData(LABEL_ROLE, label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)

        self._populate_profiles()
        self._append(
            f"loaded: {len(self._entries)} selection(s) — profile {self._profile_label()}"
        )
        if self.list.count():
            self.list.setCurrentRow(0)
        self._populate_selection_name()
        self._update_show_roi_button()
        self._populate_actions()
        self._refresh_alerts_group()

    def _populate_arm_menu(self) -> None:
        self._arm_menu.clear()
        for minutes in self.arm_durations():
            action = self._arm_menu.addAction(tr("main.arm_minutes", minutes=minutes))
            action.triggered.connect(
                lambda _checked=False, value=minutes: self._handle_action(
                    {"action": "arm_for", "minutes": value}
                )
            )

    def _populate_snooze_menu(self) -> None:
        self._snooze_menu.clear()
        for minutes in self.snooze_minutes():
            action = self._snooze_menu.addAction(tr("main.snooze_minutes", minutes=minutes))
            action.triggered.connect(
                lambda _checked=False, value=minutes: self._snooze(value)
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
        self._refresh_alerts_group()

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

    def snooze_minutes(self) -> tuple[int, ...]:
        if self._config is None or self._config.legacy:
            return (5, 15, 30, 60)
        return self._config.ui.snooze_minutes or (5, 15, 30, 60)

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

    def _checked_entries(self) -> list:
        """Entradas marcadas com o checkbox (conjunto a iniciar no Start)."""
        entries = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                data = item.data(TARGET_ROLE)
                if data is not None:
                    entries.append(data)
        return entries

    def selection_names(self) -> tuple[str, ...]:
        return tuple(Path(value).stem for _kind, value in self._entries)

    def max_sessions(self) -> int:
        if self._config is None or self._config.legacy:
            return 4
        return self._config.ui.max_sessions or 4

    def _focused_session(self) -> str | None:
        """Sessao em foco: a linha selecionada (se ativa), senao a primeira ativa."""
        selected = self._selected()
        if selected is not None:
            name = Path(selected[1]).stem
            if self._controller.is_running(name):
                return name
        names = self._controller.names()
        return names[0] if names else None

    def _entry_mode(self, entry) -> str:
        if entry is None:
            return self.mode_combo.currentText() or MODES[-1]
        _kind, value = entry
        from screen_watch.persistence.selection import load_selection

        try:
            return load_selection(value).mode
        except (ConfigError, OSError, ValueError):
            return MODES[-1]

    def _resolve_entry_target(self, entry, mode: str):
        if entry is None:
            return None
        _kind, value = entry
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

    def _resolve_target(self, mode: str):
        return self._resolve_entry_target(self._selected(), mode)

    # -- nome da selecao ---------------------------------------------------
    def _populate_selection_name(self) -> None:
        selected = self._selected()
        if selected is None:
            self.selection_name.clear()
            self.selection_name.setEnabled(False)
            self.btn_rename.setEnabled(False)
            return
        _kind, value = selected
        from screen_watch.persistence.selection import load_selection

        try:
            selection = load_selection(value)
        except (ConfigError, OSError, ValueError):
            selection = None
        if selection is None:
            text = Path(value).stem
        else:
            text = selection.name or selection.app_name or Path(value).stem
        self.selection_name.setText(text)
        self.selection_name.setEnabled(True)
        self.btn_rename.setEnabled(True)

    def _select_path(self, path: Path) -> None:
        """Seleciona na lista o item cujo arquivo e `path` (apos renomear)."""
        wanted = str(path)
        for row in range(self.list.count()):
            item = self.list.item(row)
            data = item.data(TARGET_ROLE)
            if data is not None and str(data[1]) == wanted:
                self.list.setCurrentItem(item)
                self.list.scrollToItem(item)
                return

    def _rename_selection(self) -> None:
        if self._controller.running:
            QMessageBox.information(self, tr("main.title"), tr("dialog.rename_running"))
            return
        selected = self._selected()
        if selected is None:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_selection"))
            return
        _kind, value = selected
        old_path = Path(value)
        typed = self.selection_name.text().strip()
        if not typed:  # nome vazio mantem o atual
            self._populate_selection_name()
            return

        from screen_watch.persistence.selection import plan_rename, rename_selection
        from screen_watch.platform.paths import selections_dir

        try:
            new_path = plan_rename(selections_dir(), old_path, typed)
            rename_selection(old_path, new_path, name=typed)
        except Exception as exc:
            title = (
                tr("dialog.rename_conflict")
                if getattr(exc, "code", "") == "selection.name_conflict"
                else tr("main.title")
            )
            QMessageBox.warning(self, title, render_error(exc))
            return
        if new_path == old_path:
            self._append(f"selection name -> {typed!r} ({old_path.stem})")
        else:
            self._append(
                f"selection renamed: {old_path.stem} -> {new_path.stem} ({typed!r})"
            )
        self._reload()
        self._select_path(new_path)
        QMessageBox.information(
            self, tr("main.title"), tr("dialog.rename_done", name=typed)
        )

    # -- regiao na tela ----------------------------------------------------
    def _update_show_roi_button(self) -> None:
        enabled = self._selected() is not None
        self.btn_show_roi.setEnabled(enabled)
        self.btn_masks.setEnabled(enabled)

    def _show_roi(self) -> None:
        selected = self._selected()
        if selected is None:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_selection"))
            return
        _kind, value = selected
        from screen_watch.capture.roi import (
            absolute_roi_for_selection,
            roi_unavailable_error,
        )
        from screen_watch.persistence.selection import load_selection

        try:
            selection = load_selection(value)
        except (ConfigError, OSError, ValueError) as exc:
            self._append(f"unreadable selection: {exc}")
            return
        try:
            rect = absolute_roi_for_selection(selection)
        except Exception as exc:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.load_failed", error=render_error(exc))
            )
            return
        if rect is None:
            QMessageBox.warning(self, tr("main.title"), render_error(roi_unavailable_error(selection)))
            return
        x, y, w, h = rect
        name = (
            selection.name
            or selection.app_name
            or selection.window_title_hint
            or Path(value).stem
        )
        from screen_watch.gui.highlight import show_roi_highlight

        show_roi_highlight(rect, tr("highlight.label", name=name, x=x, y=y, w=w, h=h))
        self._append(f"region highlighted for {Path(value).stem}: {x},{y} {w}x{h}")

    def _edit_region(self) -> None:
        if self._controller.running:
            QMessageBox.information(self, tr("main.title"), tr("dialog.edit_running"))
            return
        selected = self._selected()
        if selected is None:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_selection"))
            return
        _kind, value = selected
        from screen_watch.persistence.selection import load_selection
        from screen_watch.platform.window import find_window_by_handle

        try:
            selection = load_selection(value)
        except (ConfigError, OSError, ValueError) as exc:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.load_failed", error=render_error(exc))
            )
            return
        try:
            info = find_window_by_handle(selection.window_handle)
        except Exception:
            info = None
        if info is None or not info.exists or info.is_minimized:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.reedit_window_missing")
            )
            return

        from screen_watch.cli.commands import overlay_relative_roi

        try:
            relative, info = overlay_relative_roi(selection.window_handle)
        except AppError as exc:
            if exc.code == "runtime.selection_cancelled":
                return  # cancelar o overlay e um no-op
            QMessageBox.warning(self, tr("main.title"), render_error(exc))
            return
        except Exception as exc:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.selection_failed", error=render_error(exc))
            )
            return

        updated = replace(
            selection,
            roi_relative=relative,
            origin_at_selection=(info.rect[0], info.rect[1]),
            masks=(),
        )
        if isinstance(updated.overrides, dict) and "masks" in updated.overrides:
            # `overrides.masks` teria precedencia no build_target e e relativo a ROI antiga.
            overrides = dict(updated.overrides)
            overrides.pop("masks", None)
            updated = replace(updated, overrides=overrides or None)
        from screen_watch.persistence.selection import dump_selection

        try:
            dump_selection(value, updated)
        except OSError as exc:
            self._append(f"could not save the region: {exc}")
            return
        item = self.list.currentItem()
        if item is not None:
            item.setText(self._label_for("selection", value))
        self._append(f"region updated for {Path(value).stem}: {relative}")
        self._append(f"masks cleared (region changed): {Path(value).stem}")

    def _edit_masks(self) -> None:
        if self._controller.running:
            QMessageBox.information(self, tr("main.title"), tr("dialog.masks_running"))
            return
        selected = self._selected()
        if selected is None:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_selection"))
            return
        _kind, value = selected
        from screen_watch.persistence.selection import (
            dump_selection,
            effective_masks,
            load_selection,
            set_masks,
        )
        from screen_watch.platform.window import find_window_by_handle

        try:
            selection = load_selection(value)
        except (ConfigError, OSError, ValueError) as exc:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.load_failed", error=render_error(exc))
            )
            return
        try:
            info = find_window_by_handle(selection.window_handle)
        except Exception:
            info = None
        if info is None or not info.exists or info.is_minimized:
            QMessageBox.warning(
                self, tr("main.title"), tr("dialog.masks_window_missing")
            )
            return

        from screen_watch.gui.mask_overlay import run_mask_editor

        try:
            edited = run_mask_editor(
                info.rect, selection.roi_relative, effective_masks(selection)
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr("main.title"),
                tr("dialog.masks_failed", error=render_error(exc)),
            )
            return
        if edited is None:
            return  # cancelar o editor e um no-op
        updated = set_masks(selection, edited)
        try:
            dump_selection(value, updated)
        except OSError as exc:
            QMessageBox.warning(
                self,
                tr("main.title"),
                tr("dialog.masks_failed", error=render_error(exc)),
            )
            return
        self._append(f"masks updated for {Path(value).stem}: {len(edited)}")
        QMessageBox.information(
            self, tr("main.title"), tr("dialog.masks_saved", count=len(edited))
        )

    # -- acoes -------------------------------------------------------------
    def _item_changed(self, _current, _previous) -> None:
        self._populate_selection_name()
        self._update_show_roi_button()
        selected = self._selected()
        if selected is None:
            self._populate_actions()
            self._refresh_alerts_group()
            return
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText(self._entry_mode(selected))
        self.mode_combo.blockSignals(False)
        self._populate_actions()
        self._print_action_summary()
        self._refresh_alerts_group()

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
            self._update_watch_state()
            return
        _kind, value = selected
        try:
            from screen_watch.persistence.selection import (
                dump_selection,
                load_selection,
                set_override_text_watch,
            )

            selection = load_selection(value)
            overrides = selection.overrides if isinstance(selection.overrides, dict) else {}
            if mode != "advanced" and "text_watch" in overrides:
                # O filtro de texto exige o modo advanced; sem isto o start falharia
                # com config.text_watch_needs_advanced.
                selection = set_override_text_watch(selection, None)
                self._append(f"text_watch cleared (requires advanced): {Path(value).stem}")
            dump_selection(value, replace(selection, mode=mode))
        except (ConfigError, OSError, ValueError) as exc:
            self._append(f"could not save the mode: {exc}")
            return
        item = self.list.currentItem()
        if item is not None:
            item.setText(self._label_for("selection", value))
        self._append(f"mode of {Path(value).stem} -> {mode}")
        self._refresh_alerts_group()

    # -- deteccao e alertas (som + texto) ----------------------------------
    def _refresh_alerts_group(self) -> None:
        self._populate_sound()
        self._populate_text_watch()
        self._update_watch_state()

    @staticmethod
    def _first_sound_file(alerts) -> str | None:
        for alert in alerts or ():
            if alert.type == "sound":
                return alert.file
        return None

    def _effective_sound_file(self) -> str | None:
        selected = self._selected()
        if selected is not None:
            try:
                target = self._resolve_target(self.mode_combo.currentText())
            except Exception:
                target = None
            if target is not None:
                return self._first_sound_file(target.alerts)
        from screen_watch.app import profile_from_config

        try:
            profile = profile_from_config(self._config, self._profile)
        except Exception:
            return None
        return self._first_sound_file(profile.alerts)

    def _populate_sound(self) -> None:
        value = self._sound_choice or self._effective_sound_file()
        self.sound_path.setText(
            tr("main.sound_snippet", path=value) if value else tr("main.sound_none")
        )
        self.btn_sound_play.setEnabled(bool(value))
        self.btn_sound_copy.setEnabled(bool(value))

    def _choose_sound(self) -> None:
        from screen_watch.platform.paths import app_home, sounds_dir

        start = sounds_dir() if sounds_dir().is_dir() else app_home()
        path, _selected = QFileDialog.getOpenFileName(
            self, tr("main.sound_choose"), str(start), SOUND_FILTER
        )
        if not path:
            return
        self._sound_choice = path
        self.sound_path.setText(tr("main.sound_snippet", path=path))
        self.btn_sound_play.setEnabled(True)
        self.btn_sound_copy.setEnabled(True)
        self._confirm_sound_write(path)

    def _selection_overrides_alerts(self) -> bool:
        selected = self._selected()
        if selected is None:
            return False
        _kind, value = selected
        from screen_watch.persistence.selection import load_selection

        try:
            selection = load_selection(value)
        except Exception:
            return False
        overrides = selection.overrides
        return isinstance(overrides, dict) and "alerts" in overrides

    def _confirm_sound_write(self, path: str) -> None:
        profile = self._profile or "default"
        text = tr("dialog.sound_confirm", path=path, profile=profile)
        if self._selection_overrides_alerts():
            text = f"{text}\n\n{tr('dialog.sound_override_warning')}"
        box = QMessageBox(self)
        box.setWindowTitle(tr("dialog.sound_title"))
        box.setText(text)
        save_button = box.addButton(
            tr("dialog.sound_save"), QMessageBox.ButtonRole.AcceptRole
        )
        copy_button = box.addButton(
            tr("dialog.sound_copy_open"), QMessageBox.ButtonRole.ActionRole
        )
        open_button = box.addButton(
            tr("dialog.sound_open_only"), QMessageBox.ButtonRole.ActionRole
        )
        box.addButton(tr("dialog.sound_close"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is copy_button:
            self._copy_sound_snippet()
            self._open_yaml()
            return
        if clicked is open_button:
            self._open_yaml()
            return
        if clicked is not save_button:
            return
        if self._config is not None and self._config.legacy:
            QMessageBox.information(self, tr("main.title"), tr("dialog.sound_v1"))
            return
        from screen_watch.config.loader import set_profile_sound_file

        try:
            set_profile_sound_file(self._config_path, profile, path)
        except Exception as exc:
            QMessageBox.warning(self, tr("main.title"), render_error(exc))
            return
        self._append(f"sound saved in profile {profile}: {path}")
        self._reload()
        QMessageBox.information(
            self,
            tr("main.title"),
            tr("dialog.sound_saved", profile=profile, path=path),
        )

    def _play_sound(self) -> None:
        from screen_watch.platform.audio import play_file, resolve_sound_path

        value = self._sound_choice or self._effective_sound_file()
        if not value:
            return
        resolved = resolve_sound_path(value)
        if not Path(resolved).is_file():
            self._append(tr("main.sound_not_found", path=value))
            return
        if not play_file(resolved):
            self._append(f"could not play: {resolved}")

    def _copy_sound_snippet(self) -> None:
        value = self._sound_choice or self._effective_sound_file()
        if not value:
            return
        text = tr("main.sound_snippet", path=value)
        QApplication.clipboard().setText(text)
        self._append(f"copied: {text}")

    def _populate_text_watch(self) -> None:
        from screen_watch.persistence.selection import load_selection, override_text_watch

        watch = None
        selected = self._selected()
        if selected is not None:
            _kind, value = selected
            try:
                watch = override_text_watch(load_selection(value))
            except (ConfigError, OSError, ValueError) as exc:
                self._append(f"text_watch unavailable: {exc}")
        widgets = (self.text_watch_edit, self.expect_combo, self.case_check, self.accents_check)
        for widget in widgets:
            widget.blockSignals(True)
        self.text_watch_edit.setText(watch.text if watch is not None else "")
        index = self.expect_combo.findData(watch.expect if watch is not None else "appears")
        self.expect_combo.setCurrentIndex(max(0, index))
        self.case_check.setChecked(watch is not None and watch.case_sensitive)
        self.accents_check.setChecked(watch.ignore_accents if watch is not None else True)
        for widget in widgets:
            widget.blockSignals(False)

    def _update_watch_state(self) -> None:
        enabled = self._selected() is not None and self.mode_combo.currentText() == "advanced"
        for widget in (self.text_watch_edit, self.expect_combo, self.case_check, self.accents_check):
            widget.setEnabled(enabled)

    def _mark_text_watch_edited(self, _text: str) -> None:
        selected = self._selected()
        self._watch_edit_stem = Path(selected[1]).stem if selected is not None else None

    def _commit_text_watch(self) -> None:
        """Commita o texto editado somente se a selecao nao mudou no meio."""
        selected = self._selected()
        stem = Path(selected[1]).stem if selected is not None else None
        edited = self._watch_edit_stem
        self._watch_edit_stem = None
        if stem is None or edited != stem:
            return
        self._save_text_watch()

    def _save_text_watch(self, *_args) -> None:
        if self.mode_combo.currentText() != "advanced":
            return
        selected = self._selected()
        if selected is None:
            return
        _kind, value = selected
        from screen_watch.config.schema import TextWatchOptions
        from screen_watch.persistence.selection import (
            dump_selection,
            load_selection,
            set_override_text_watch,
        )

        text = self.text_watch_edit.text()
        try:
            selection = load_selection(value)
            watch = (
                TextWatchOptions(
                    text=text,
                    expect=self.expect_combo.currentData() or "appears",
                    case_sensitive=self.case_check.isChecked(),
                    ignore_accents=self.accents_check.isChecked(),
                )
                if text.strip()
                else None
            )
            dump_selection(value, set_override_text_watch(selection, watch))
        except (ConfigError, OSError, ValueError) as exc:
            self._append(f"could not save the text watch: {exc}")
            return
        if watch is None:
            self._append(f"text_watch of {Path(value).stem}: cleared (applies on next start)")
        else:
            self._append(
                f"text_watch of {Path(value).stem} -> {watch.expect} {watch.text!r} "
                "(applies on next start)"
            )

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
        # Checkboxes definem o conjunto; sem nenhuma marcada, inicia a linha selecionada.
        entries = self._checked_entries()
        if not entries:
            selected = self._selected()
            entries = [selected] if selected is not None else []
        self._start_entries(entries)

    def _start_entries(self, entries) -> None:
        if not entries:
            QMessageBox.information(self, tr("main.title"), tr("dialog.select_selection"))
            return
        started: list[str] = []
        errors: list[str] = []
        try:
            from screen_watch.app import evidence_recorder

            recorder = evidence_recorder(self._config)
        except Exception as exc:  # pragma: no cover - defensivo
            QMessageBox.critical(
                self, tr("main.title"), tr("dialog.start_failed", error=render_error(exc))
            )
            return
        for entry in entries:
            try:
                target = self._resolve_entry_target(entry, self.mode_combo.currentText())
                if target is None:
                    continue
                self._controller.start(target, recorder=recorder)
                started.append(target.name)
            except Exception as exc:
                errors.append(render_error(exc))
        if errors:
            QMessageBox.warning(
                self,
                tr("main.title"),
                tr("dialog.start_failed", error="\n".join(errors)),
            )
        if not started:
            return
        self._active_name = started[-1]
        from screen_watch.platform.paths import update_state

        fields: dict[str, object] = {}
        if len(started) == 1:
            fields["last_selection"] = f"{started[0]}.json"
        if self._profile:
            fields["profile"] = self._profile
        if fields:
            update_state(**fields)
        self._update_running_status()
        self._set_running(True)
        self._print_action_summary()

    def _update_running_status(self) -> None:
        names = self._controller.names()
        if not names:
            self.status.setText(tr("status.stopped"))
        elif len(names) == 1:
            self.status.setText(tr("status.monitoring_short", name=names[0]))
        else:
            self.status.setText(
                tr("status.monitoring_multi", count=len(names), names=", ".join(names))
            )

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

    # -- snooze/mute/escalation (doc, secao 11.3) --------------------------
    def _snooze(self, minutes: int) -> None:
        if minutes <= 0:
            return
        self._controller.snooze(minutes)
        self._append(f"alerts snoozed for {minutes} min")
        self._update_gate_status()

    def _toggle_mute(self) -> None:
        if self._controller.gate.muted:
            self._controller.unmute()
            self._append("alerts unmuted")
        else:
            self._controller.mute()
            self._append("alerts muted")
        self._update_gate_status()

    def _acknowledge(self) -> None:
        if not self._controller.escalating:
            return
        self._controller.acknowledge()
        self._append("escalation acknowledged")
        self._update_gate_status()

    def _update_gate_status(self) -> None:
        parts: list[str] = []
        status = self._controller.gate_status()
        if status == "muted":
            parts.append(tr("status.muted"))
        elif status == "snoozed":
            remaining = self._controller.gate_remaining_s()
            minutes = max(1, int((remaining + 59) // 60))
            parts.append(tr("status.snoozed", minutes=minutes))
        if self._controller.escalating:
            parts.append(tr("status.escalating"))
        self.gate_label.setText(" — ".join(parts))
        self.btn_mute.setText(
            tr("main.btn_unmute") if status == "muted" else tr("main.btn_mute")
        )
        self.btn_ack.setEnabled(self._controller.escalating)

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
        for name in sorted(remove_names):
            if self._controller.is_running(name):
                self._controller.stop(name)
        if self._active_name in remove_names or not self._controller.running:
            self._active_name = ""
        self._update_running_status()
        self._set_running(self._controller.running)

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

    def _open_history(self) -> None:
        from screen_watch.app import effective_evidence_options
        from screen_watch.evidence.recorder import ensure_captures_dir
        from screen_watch.gui.history_dialog import AlertHistoryDialog

        captures = None
        try:
            captures = ensure_captures_dir(effective_evidence_options(self._config))
        except OSError as exc:
            self._append(f"could not create the captures folder: {exc}")
        AlertHistoryDialog(self, captures_dir=captures).exec()

    def _open_calibration(self) -> None:
        from screen_watch.gui.calibration_widget import CalibrationWidget

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("main.calibration_title"))
        dialog.resize(620, 240)
        layout = QVBoxLayout(dialog)
        widget = CalibrationWidget()
        layout.addWidget(widget)
        close_button = QPushButton(tr("history.close"))
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        widget.set_samples(self._controller.calibration(self._focused_session()))
        self._calibration_dialog = (dialog, widget)
        dialog.finished.connect(self._calibration_closed)
        dialog.exec()

    def _calibration_closed(self, _result: int) -> None:
        self._calibration_dialog = None

    def _update_calibration(self) -> None:
        if self._calibration_dialog is None:
            return
        _dialog, widget = self._calibration_dialog
        widget.set_samples(self._controller.calibration(self._focused_session()))

    # -- eventos -----------------------------------------------------------
    def _arming_text(self) -> str:
        dispatcher = self._controller.actions(self._focused_session())
        if dispatcher is None:
            return tr("arming.none")
        arming = dispatcher.arming
        state = arming.state
        if state == TIMED:
            remaining = arming.remaining_s() or 0.0
            return tr("arming.timed", remaining=f"{remaining:.0f}")
        return tr("arming.armed") if state == ARMED else tr("arming.disarmed")

    def _update_arming_buttons(self) -> None:
        active = (
            self._controller.running
            and self._controller.actions(self._focused_session()) is not None
        )
        for button in (self.btn_arm, self.btn_disarm, self.btn_arm_for):
            button.setEnabled(active)

    def _set_running(self, running: bool) -> None:
        self.btn_start.setEnabled(len(self._controller.names()) < self.max_sessions())
        self.btn_stop.setEnabled(running)
        self.btn_rearm.setEnabled(running)
        self.btn_run_action.setEnabled(not running)
        self.btn_new.setEnabled(not running)
        self.btn_remove.setEnabled(not running)
        self.btn_reload.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.language_combo.setEnabled(not running)
        self._update_arming_buttons()
        self._update_show_roi_button()

    def _drain(self) -> None:
        self._update_action_status()
        self._update_gate_status()
        self._update_preview()
        self._update_calibration()
        while True:
            try:
                event = self._controller.events.get_nowait()
            except Exception:
                return
            self._handle(event)

    def _update_preview(self) -> None:
        name = self._focused_session()
        if name is None:
            self.preview.clear()
            return
        latest, baseline = self._controller.preview(name)
        self.preview.update_frames(latest, baseline)

    def _session_tag(self, event: dict) -> str:
        """Prefixo `[sessao]` quando ha mais de uma sessao ativa."""
        session = event.get("session")
        if session and len(self._controller.names()) > 1:
            return f"[{session}] "
        return ""

    def _handle(self, event: dict) -> None:
        kind = event.get("kind")
        if kind == "started":
            self._update_running_status()
            self._set_running(True)
        elif kind == "stopped":
            if self._controller.running:
                self._update_running_status()
            else:
                self.status.setText(tr("status.stopped"))
                self._set_running(False)
                self.preview.clear()
        elif kind == "result":
            line = tr(
                "status.last",
                strategy=event["strategy"],
                score=f"{event['score']:.3f}",
                severity=event["severity"],
                outcome=event["outcome"],
            )
            self.last.setText(f"{self._session_tag(event)}{line}")
        elif kind == "error":
            self._append(f"{self._session_tag(event)}error: {event.get('message')}")
        elif kind == "event":
            name = event.get("name")
            self.status.setText(
                tr("status.state", name=name, payload=event.get("payload") or "").strip()
            )
            self._append(
                f"{self._session_tag(event)}event: {name} {event.get('payload') or ''}"
            )
        elif kind == "tray":
            self._handle_tray(event.get("action"))
        elif kind == "target":
            self._handle_target(event)
        elif kind == "gate":
            self._handle_gate(event)
        elif kind == "action":
            self._handle_action(event)
        elif kind == "action_event":
            self._handle_action_event(event.get("payload") or {}, self._session_tag(event))
        elif kind == "profile":
            self._select_profile(str(event.get("name") or ""))

    def _handle_target(self, event: dict) -> None:
        """Start/stop individual vindo do menu do tray."""
        action = event.get("action")
        name = str(event.get("name") or "")
        if not name:
            return
        if action == "start":
            entry = next(
                (item for item in self._entries if Path(item[1]).stem == name), None
            )
            if entry is not None:
                self._start_entries([entry])
        elif action == "stop":
            self._controller.stop(name)
            self._update_running_status()
            self._set_running(self._controller.running)

    def _handle_action_event(self, payload: dict, tag: str = "") -> None:
        action = payload.get("action") or "?"
        mode = payload.get("mode") or "?"
        if mode == "armed":
            status = "ok" if payload.get("executed") else f"failed ({payload.get('reason') or '?'})"
        elif mode == "rehearsal":
            status = "rehearsal"
        else:
            status = payload.get("reason") or "?"
        self._append(f"{tag}actions: {mode} {action} -> {status}")

    def _handle_gate(self, event: dict) -> None:
        action = event.get("action")
        if action == "snooze":
            self._snooze(int(event.get("minutes") or 0))
        elif action == "mute":
            self._controller.mute()
            self._append("alerts muted")
            self._update_gate_status()
        elif action == "unmute":
            self._controller.unmute()
            self._append("alerts unmuted")
            self._update_gate_status()
        elif action == "acknowledge":
            self._acknowledge()

    def _handle_action(self, event: dict) -> None:
        if event.get("action") == "acknowledge":
            self._acknowledge()
            return
        dispatcher = self._controller.actions(self._focused_session())
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
        dispatcher = self._controller.actions(self._focused_session())
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
    from screen_watch.platform.audio import install_qt_player, uninstall_qt_player

    # Player de audio criado no thread da GUI (o `AlertChain` despacha na thread
    # do loop; `QMediaPlayer` nao pode ser criado/usado la).
    if not install_qt_player():
        import logging

        logging.getLogger(__name__).debug("Qt sound player unavailable; using miniaudio/legacy")
    events = new_event_queue()
    from screen_watch.alerts.gate import load_gate

    controller = SessionManager(events, gate=load_gate())
    window = MainWindow(controller, config_path, profile=profile, on_quit=app.quit)
    controller.set_max_sessions(window.max_sessions())
    tray = start_tray(
        events,
        arm_durations=window.arm_durations(),
        profiles=window.profile_names(),
        snooze_minutes=window.snooze_minutes(),
        selections=window.selection_names(),
    )
    window.show()
    try:
        return int(app.exec())
    finally:
        stop_tray(tray)
        controller.stop()
        uninstall_qt_player()
