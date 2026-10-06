"""Catalogo de ajuda (hover) da GUI (plano GUI/UX, F6) — puro, sem Qt.

`HELP_KEYS` define os controles cobertos e `build_help_html` monta o HTML rico a
partir do catalogo (`help.<key>.titulo/proposito/exemplo`). O filtro Qt fica em
`gui/hover_help.py`, importado apenas pela GUI; a coleta de testes headless usa
so este modulo.
"""

from __future__ import annotations

HELP_KEYS: tuple[str, ...] = (
    # janela
    "window.start",
    "window.stop",
    "window.rearm",
    "window.minimize",
    "window.show_roi",
    "window.edit_masks",
    "window.selection_name",
    "window.mode",
    "window.profile",
    "window.language",
    "window.arm",
    "window.disarm",
    "window.arm_for",
    "window.run_action",
    "window.new_target",
    "window.remove",
    "window.reload",
    "window.open_yaml",
    "window.captures",
    "window.test_alert",
    "window.evidence",
    "window.actions_list",
    "window.action_new",
    "window.action_edit",
    "window.action_remove",
    "window.sound_choose",
    "window.sound_play",
    "window.sound_copy",
    "window.snooze",
    "window.mute",
    "window.ack",
    "window.text_watch",
    "window.text_watch_expect",
    "window.text_watch_case",
    "window.text_watch_accents",
    "window.preview",
    "window.alert_history",
    "window.calibration",
    # editor
    "editor.name",
    "editor.enabled",
    "editor.severity_min",
    "editor.cooldown_s",
    "editor.settle_s",
    "editor.rebaseline",
    "editor.steps_list",
    "editor.step_kind",
    "editor.step_x",
    "editor.step_y",
    "editor.step_ref",
    "editor.step_button",
    "editor.step_clicks",
    "editor.step_keys",
    "editor.step_text",
    "editor.step_ms",
    "editor.step_add",
    "editor.step_remove",
    "editor.step_up",
    "editor.step_down",
    "editor.step_edit",
    "editor.step_duplicate",
    "editor.step_locate",
    # teste de alerta
    "test_alert",
)

HEADER_KEYS = ("titulo", "proposito", "exemplo")


def _lookup(key: str, suffix: str, catalog) -> str:
    if catalog is not None:
        return str(catalog.get(f"help.{key}.{suffix}", ""))
    from screen_watch.i18n import tr  # noqa: PLC0415

    return tr(f"help.{key}.{suffix}")


def build_help_html(key: str, catalog=None) -> str:
    """HTML rico (titulo, proposito, exemplo) para `key` (sem o prefixo `help.`)."""
    title = _lookup(key, "titulo", catalog)
    purpose = _lookup(key, "proposito", catalog)
    example = _lookup(key, "exemplo", catalog)
    if not any((title, purpose, example)):
        return ""
    parts = []
    if title:
        parts.append(f"<b>{title}</b>")
    if purpose:
        parts.append(purpose)
    if example:
        parts.append(f"<i>{example}</i>")
    return "<br>".join(parts)
