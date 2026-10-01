"""Erros da aplicacao com codigo estavel (plano GUI/UX, F2).

`AppError` carrega `code` + `params`; `str(exc)` renderiza **em ingles** (e o que
o CLI e o log mostram, sem passar pelo i18n). A GUI traduz via
`render_error(exc)`, que consulta o catalogo (`error.<code>`).
"""

from __future__ import annotations

from typing import Any

# Mensagens em ingles por codigo (fonte de `str(exc)` e do catalogo en-US).
_EN: dict[str, str] = {
    # -- config/schema/loader -------------------------------------------------
    "config.not_integer": "{field} must be an integer (got {value!r})",
    "config.not_number": "{field} must be a number (got {value!r})",
    "config.not_bool": "{field} must be true/false (got {value!r})",
    "config.not_text": "{field} must be text (got {value!r})",
    "config.not_rect": "{field} must be [x, y, w, h]",
    "config.not_point": "{field} must be [x, y]",
    "config.invalid_mode": "invalid {field}: {value!r}; use one of {valid}",
    "config.interval_too_small": "{field} must be >= {minimum} (doc, section 1.1)",
    "config.rects_not_list": "{field} must be a list of [x, y, w, h]",
    "config.alerts_not_list": "{field} must be a list",
    "config.overrides_not_mapping": "overrides must be a mapping",
    "config.overrides_actions_not_list": "overrides.actions must be a list",
    "config.compare_options_not_mapping": "compare_options must be a mapping",
    "config.compare_section_not_mapping": "compare_options.{name} must be a mapping",
    "config.text_watch_not_mapping": "{field} must be a mapping",
    "config.text_watch_text_required": "{field}.text is required (non-empty)",
    "config.text_watch_invalid_expect": (
        "invalid {field}.expect: {value!r}; use one of {valid}"
    ),
    "config.text_watch_not_bool": "{field} must be true/false (got {value!r})",
    "config.text_watch_needs_advanced": (
        "text_watch requires mode 'advanced' (OCR); selection is {mode!r}"
    ),
    "config.alert_not_mapping": "{field} must be a mapping",
    "config.alert_missing_type": "{field} requires 'type'",
    "config.target_not_mapping": "each target must be a mapping",
    "config.target_missing_field": "target missing required field: {field!r}",
    "config.humanize_not_mapping": "defaults.humanize must be a mapping",
    "config.humanize_mouse_steps_min": "defaults.humanize.mouse_steps must be >= 1",
    "config.humanize_non_negative": (
        "defaults.humanize: key_interval_ms/jitter_px/wait_jitter_ms must be >= 0"
    ),
    "config.defaults_not_mapping": "defaults must be a mapping",
    "config.profile_not_mapping": "profiles.{name} must be a mapping",
    "config.evidence_not_mapping": "evidence must be a mapping",
    "config.ui_not_mapping": "ui must be a mapping",
    "config.hotkeys_not_mapping": "ui.hotkeys must be a mapping",
    "config.arm_durations_not_list": "ui.arm_durations_min must be a list of minutes",
    "config.arm_durations_positive": "ui.arm_durations_min must contain only positive minutes",
    "config.window_format": "{field} must be 'HH:MM-HH:MM' (got {value!r})",
    "config.window_invalid_time": "{field} has an invalid hour/minute: {value!r}",
    "config.schedule_not_mapping": "schedule must be a mapping",
    "config.schedule_days_not_list": "schedule.days must be a list",
    "config.schedule_windows_not_list": "schedule.windows must be a list",
    "config.schedule_invalid_days": "invalid schedule.days: {days}; use one of {valid}",
    "config.v2_missing_profiles": "config v2 requires 'profiles'",
    "config.profiles_not_mapping": "'profiles' must be a mapping",
    "config.profile_unknown": "unknown profile: {name!r}",
    "config.root_not_mapping": "YAML root must be a mapping",
    "config.version_unsupported": (
        "unsupported config version: {value}; use 1 or 2 (doc, section 12)"
    ),
    "config.targets_not_list": "'targets' must be a list",
    "config.file_not_found": "config file not found: {path}",
    "config.yaml_invalid": "invalid YAML: {error}",
    "config.migrate_no_targets": "nothing to migrate: YAML without 'targets'",
    "config.migrate_duplicate_names": "duplicate target names: {names}",
    "config.migrate_empty": "nothing to migrate: 'targets' is empty",
    "config.action_text_needs_advanced": (
        "action {name!r}: text_* filters require mode 'advanced' (OCR); selection is {mode!r}"
    ),
    "config.alert_unknown_type": (
        "invalid {field}.type: {value!r}; use one of {valid}"
    ),
    "config.alert_options_not_mapping": "{field}.options must be a mapping",
    "config.alert_missing_url": "{field} requires 'url' or 'url_env'",
    "config.alert_missing_host": "{field} requires 'host'",
    "config.alert_invalid_url": "{field}.url must start with http:// or https://",
    "config.alert_invalid_port": "{field}.port must be between 1 and 65535 (got {value!r})",
    "config.alert_invalid_protocol": (
        "invalid {field}.protocol: {value!r}; use one of {valid}"
    ),
    "config.alert_invalid_facility": (
        "invalid {field}.facility: {value!r}; use one of {valid}"
    ),
    "config.alert_invalid_method": "invalid {field}.method: {value!r}; use one of {valid}",
    "config.alert_payload_conflict": "{field}: use either 'payload' or 'payload_raw', not both",
    "config.alert_unknown_placeholder": (
        "unknown placeholder {value!r} in {field}; known: {valid}"
    ),
    "config.alert_invalid_severity_map": (
        "invalid {field}.severity_map: {value!r}; use keys 0..3 and levels {valid}"
    ),
    "config.alert_duplicate_id": "duplicate alert id {id!r} in {field}",
    # -- alerts (runtime) -----------------------------------------------------
    "alert.http_status": "http request failed: status {status} ({url})",
    "alert.http_unreachable": "could not reach {url}",
    "alert.syslog_unavailable": (
        "syslog unavailable at {host}:{port} (check host/port/protocol)"
    ),
    # -- actions --------------------------------------------------------------
    "action.not_integer": "{field} must be an integer (got {value!r})",
    "action.not_number": "{field} must be a number (got {value!r})",
    "action.not_bool": "{field} must be true/false (got {value!r})",
    "action.not_text": "{field} must be text (got {value!r})",
    "action.not_text_list": "{field} must be a list of texts",
    "action.step_not_mapping": "{field} must be a mapping with a single step",
    "action.step_unknown": "{field} has an unknown step: {value!r}; use {valid}",
    "action.step_single": "{field} must have exactly one step; got {keys}",
    "action.step_params_not_mapping": "{field}.{kind} must be a mapping",
    "action.ref_invalid": "invalid {field}.{kind}.ref: {value!r}; use {valid}",
    "action.xy_required": "{field}.{kind} requires 'x' and 'y'",
    "action.button_invalid": "invalid {field}.click.button: {value!r}; use {valid}",
    "action.clicks_min": "{field}.click.clicks must be >= 1",
    "action.keys_required": "{field}.key requires 'keys'",
    "action.text_required": "{field}.type requires 'text'",
    "action.wait_ms_min": "{field}.wait.ms must be >= 0",
    "action.when_not_mapping": "{field} must be a mapping",
    "action.changed_not_supported": "{field}.changed: false is not supported in this phase",
    "action.regex_invalid": "invalid {field}.text_regex: {error}",
    "action.missing_name": "{field} requires 'name'",
    "action.steps_not_list": "{field}.steps must be a list",
    "action.action_not_mapping": "{field} must be a mapping",
    "action.settle_min": "{field}.settle_s must be >= 0",
    "action.cooldown_min": "{field}.cooldown_s must be >= 0",
    "action.max_min": "{field}.max_per_min/max_per_session must be >= 0",
    "action.click_needs_activate": (
        "{field}: 'click' steps require an 'activate: true' step before them (explicit focus)"
    ),
    "action.text_needs_advanced": (
        "{where}: text_* filters require mode 'advanced' (OCR); it is {mode!r}"
    ),
    "action.list_not_list": "{prefix} must be a list",
    "action.duplicate_names": "{prefix}: duplicate action names: {names}",
    # -- selection ------------------------------------------------------------
    "selection.missing_field": "selection missing required field: {field!r}",
    "selection.version_unsupported": "unsupported selection version: {value!r}",
    "selection.overrides_not_object": "'overrides' must be a JSON object",
    "selection.not_object": "selection JSON must be an object",
    "selection.name_invalid": "selection name has no letters or digits",
    "selection.name_too_long": (
        "selection name is too long (max {max} characters)"
    ),
    "selection.name_conflict": "a selection named {name!r} already exists",
    "selection.rename_failed": "could not rename the selection: {error}",
    # -- runtime --------------------------------------------------------------
    "runtime.tesseract_missing": (
        "Tesseract not found. Install Tesseract (Windows: "
        "https://github.com/UB-Mannheim/tesseract/wiki) with the 'por' and 'eng' traineddata "
        "and set 'compare_options.advanced.tesseract_cmd' in the YAML, or add the executable "
        "to PATH."
    ),
    "runtime.window_not_found": (
        "window not found: handle={handle}. Run 'list-windows' and redo the selection "
        "(the handle changes when the app restarts)."
    ),
    "runtime.window_minimized": "window minimized: no ROI to capture",
    "runtime.roi_invalid": "invalid ROI (outside the window or degenerate)",
    "runtime.selection_cancelled": "selection cancelled",
    "runtime.window_missing_after_selection": (
        "window not found after selection: handle={handle}"
    ),
    "runtime.roi_outside_window": (
        "ROI {roi} does not fit inside window {window}; select a region fully inside the window"
    ),
    "runtime.already_running": "a target is already running",
}

ERROR_CODES: tuple[str, ...] = tuple(_EN)


def english_message(code: str, params: dict[str, Any] | None = None) -> str:
    """Mensagem inglesa de um codigo (usada por `str(exc)` e pela GUI sem traducao)."""
    template = _EN.get(code)
    if template is None:
        return code
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template


class AppError(Exception):
    """Erro com codigo estavel + parametros; `str()` sempre em ingles."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "",
        params: dict[str, Any] | None = None,
        detail: str = "",
    ) -> None:
        self.code = code
        self.params: dict[str, Any] = dict(params or {})
        self.detail = detail
        if code and not message:
            message = english_message(code, self.params)
        if detail:
            message = f"{message} ({detail})" if message else detail
        self._message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self._message


class ConfigError(AppError):
    """Erro de configuracao/validacao com codigo estavel."""


def render_error(exc: BaseException, language: str | None = None) -> str:
    """Traduz um `AppError` pelo codigo; sem codigo, devolve `str(exc)` como veio."""
    code = getattr(exc, "code", "")
    if not code:
        return str(exc)
    from screen_watch.i18n import current_language, set_language, tr  # noqa: PLC0415

    previous = current_language()
    switched = bool(language) and language != previous
    if switched:
        set_language(language)
    try:
        rendered = tr(f"error.{code}", **getattr(exc, "params", {}))
    finally:
        if switched:
            set_language(previous)
    if rendered == f"error.{code}":
        return str(exc)
    return rendered
