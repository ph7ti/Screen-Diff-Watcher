"""Parse e validacao de `actions:` / `overrides.actions` (plano, secao 3.2).

Erros sobem como `ActionError` (subclasse de `AppError`/`ValueError`); o loader os
converte em `ConfigError` preservando `code`/`params` para a GUI traduzir.
"""

from __future__ import annotations

import re
from typing import Any

from screen_watch.actions.protocol import (
    BUTTONS,
    REF_KINDS,
    STEP_KINDS,
    ActionSpec,
    ActionStep,
)
from screen_watch.errors import AppError


class ActionError(AppError, ValueError):
    pass


def _as_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ActionError(code="action.not_integer", params={"field": field_name, "value": value})
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ActionError(
            code="action.not_integer", params={"field": field_name, "value": value}
        ) from exc


def _as_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ActionError(code="action.not_number", params={"field": field_name, "value": value})
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ActionError(
            code="action.not_number", params={"field": field_name, "value": value}
        ) from exc


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ActionError(code="action.not_bool", params={"field": field_name, "value": value})


def _as_str(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    raise ActionError(code="action.not_text", params={"field": field_name, "value": value})


def _as_str_list(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ActionError(code="action.not_text_list", params={"field": field_name})
    return tuple(_as_str(item, f"{field_name}[]") for item in value)


def _parse_step(raw: Any, field: str) -> ActionStep:
    if not isinstance(raw, dict):
        raise ActionError(code="action.step_not_mapping", params={"field": field})
    keys = [key for key in raw if key in STEP_KINDS]
    unknown = [key for key in raw if key not in STEP_KINDS]
    if unknown:
        raise ActionError(
            code="action.step_unknown",
            params={"field": field, "value": unknown[0], "valid": STEP_KINDS},
        )
    if len(keys) != 1:
        raise ActionError(
            code="action.step_single", params={"field": field, "keys": list(raw)}
        )
    kind = keys[0]
    params = raw[kind] or {}
    if kind == "activate":
        return ActionStep(kind="activate")
    if not isinstance(params, dict):
        raise ActionError(
            code="action.step_params_not_mapping", params={"field": field, "kind": kind}
        )

    ref = _as_str(params.get("ref", "roi"), f"{field}.{kind}.ref") or "roi"
    if ref not in REF_KINDS:
        raise ActionError(
            code="action.ref_invalid",
            params={"field": field, "kind": kind, "value": ref, "valid": REF_KINDS},
        )

    if kind in ("click", "move"):
        if "x" not in params or "y" not in params:
            raise ActionError(
                code="action.xy_required", params={"field": field, "kind": kind}
            )
        step = ActionStep(
            kind=kind,
            x=_as_int(params["x"], f"{field}.{kind}.x"),
            y=_as_int(params["y"], f"{field}.{kind}.y"),
            ref=ref,
        )
        if kind == "move":
            return step
        button = _as_str(params.get("button", "left"), f"{field}.click.button") or "left"
        if button not in BUTTONS:
            raise ActionError(
                code="action.button_invalid",
                params={"field": field, "value": button, "valid": BUTTONS},
            )
        clicks = _as_int(params.get("clicks", 1), f"{field}.click.clicks")
        if clicks < 1:
            raise ActionError(code="action.clicks_min", params={"field": field})
        return ActionStep(kind="click", x=step.x, y=step.y, ref=ref, button=button, clicks=clicks)

    if kind == "key":
        keys_text = _as_str(params.get("keys", ""), f"{field}.key.keys")
        if not keys_text:
            raise ActionError(code="action.keys_required", params={"field": field})
        return ActionStep(kind="key", keys=keys_text)

    if kind == "type":
        text = _as_str(params.get("text", ""), f"{field}.type.text")
        if not text:
            raise ActionError(code="action.text_required", params={"field": field})
        interval = params.get("interval_ms")
        return ActionStep(
            kind="type",
            text=text,
            interval_ms=None if interval is None else _as_int(interval, f"{field}.type.interval_ms"),
        )

    ms = _as_int(params.get("ms", 0), f"{field}.wait.ms")
    if ms < 0:
        raise ActionError(code="action.wait_ms_min", params={"field": field})
    return ActionStep(kind="wait", ms=ms)


def _parse_when(raw: Any, field: str) -> dict[str, Any]:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ActionError(code="action.when_not_mapping", params={"field": field})
    if raw.get("changed") is False:
        raise ActionError(code="action.changed_not_supported", params={"field": field})
    regex = raw.get("text_regex")
    when: dict[str, Any] = {
        "changed": _as_bool(raw.get("changed", True), f"{field}.changed"),
        "text_any": _as_str_list(raw.get("text_any"), f"{field}.text_any"),
        "text_all": _as_str_list(raw.get("text_all"), f"{field}.text_all"),
        "case_sensitive": _as_bool(raw.get("case_sensitive", False), f"{field}.case_sensitive"),
    }
    if raw.get("severity_min") is not None:
        when["when_severity_min"] = _as_int(raw["severity_min"], f"{field}.severity_min")
    if regex:
        text_regex = _as_str(regex, f"{field}.text_regex")
        try:
            re.compile(text_regex)
        except re.error as exc:
            raise ActionError(
                code="action.regex_invalid", params={"field": field, "error": exc}
            ) from exc
        when["text_regex"] = text_regex
    return when


def parse_action(raw: Any, index: int, prefix: str = "actions", mode: str | None = None) -> ActionSpec:
    field = f"{prefix}[{index}]"
    if not isinstance(raw, dict):
        raise ActionError(code="action.action_not_mapping", params={"field": field})
    if not raw.get("name"):
        raise ActionError(code="action.missing_name", params={"field": field})

    steps_raw = raw.get("steps")
    if steps_raw is None:
        steps_raw = []
    if not isinstance(steps_raw, (list, tuple)):
        raise ActionError(code="action.steps_not_list", params={"field": field})
    steps = tuple(_parse_step(item, f"{field}.steps[{i}]") for i, item in enumerate(steps_raw))

    when = _parse_when(raw.get("when"), f"{field}.when")
    action = ActionSpec(
        name=_as_str(raw["name"], f"{field}.name"),
        enabled=_as_bool(raw.get("enabled", True), f"{field}.enabled"),
        severity_min=_as_int(raw.get("severity_min", 1), f"{field}.severity_min"),
        cooldown_s=_as_float(raw.get("cooldown_s", 30.0), f"{field}.cooldown_s"),
        settle_s=_as_float(raw.get("settle_s", 1.5), f"{field}.settle_s"),
        rebaseline=_as_bool(raw.get("rebaseline", False), f"{field}.rebaseline"),
        max_per_min=_as_int(raw.get("max_per_min", 6), f"{field}.max_per_min"),
        max_per_session=_as_int(raw.get("max_per_session", 100), f"{field}.max_per_session"),
        steps=steps,
        changed=when.get("changed", True),
        when_severity_min=when.get("when_severity_min"),
        text_any=when.get("text_any", ()),
        text_all=when.get("text_all", ()),
        text_regex=when.get("text_regex"),
        case_sensitive=when.get("case_sensitive", False),
    )
    _validate_action(action, field, mode)
    return action


def _validate_action(action: ActionSpec, field: str, mode: str | None) -> None:
    if action.settle_s < 0:
        raise ActionError(code="action.settle_min", params={"field": field})
    if action.cooldown_s < 0:
        raise ActionError(code="action.cooldown_min", params={"field": field})
    if action.max_per_min < 0 or action.max_per_session < 0:
        raise ActionError(code="action.max_min", params={"field": field})
    has_click = any(step.kind == "click" for step in action.steps)
    has_activate = any(step.kind == "activate" for step in action.steps)
    if has_click and not has_activate:
        raise ActionError(code="action.click_needs_activate", params={"field": field})
    if action.needs_ocr and mode is not None and mode != "advanced":
        raise ActionError(
            code="action.text_needs_advanced", params={"where": field, "mode": mode}
        )


def parse_actions(
    raw: Any, prefix: str = "actions", mode: str | None = None
) -> tuple[ActionSpec, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ActionError(code="action.list_not_list", params={"prefix": prefix})
    actions = tuple(parse_action(item, index, prefix, mode) for index, item in enumerate(raw))
    names = [action.name for action in actions]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ActionError(
            code="action.duplicate_names",
            params={"prefix": prefix, "names": ", ".join(duplicates)},
        )
    return actions
