"""Parse e validacao de `actions:` / `overrides.actions` (plano, secao 3.2).

Erros sobem como `ActionError` (subclasse de `ValueError`); o loader os converte
em `ConfigError` para o `validate-config` nao vazar stacktrace.
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


class ActionError(ValueError):
    pass


def _as_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ActionError(f"{field_name} deve ser um inteiro (recebido {value!r})")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ActionError(f"{field_name} deve ser um inteiro (recebido {value!r})") from exc


def _as_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ActionError(f"{field_name} deve ser um numero (recebido {value!r})")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ActionError(f"{field_name} deve ser um numero (recebido {value!r})") from exc


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ActionError(f"{field_name} deve ser true/false (recebido {value!r})")


def _as_str(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    raise ActionError(f"{field_name} deve ser texto (recebido {value!r})")


def _as_str_list(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ActionError(f"{field_name} deve ser uma lista de textos")
    return tuple(_as_str(item, f"{field_name}[]") for item in value)


def _parse_step(raw: Any, field: str) -> ActionStep:
    if not isinstance(raw, dict):
        raise ActionError(f"{field} deve ser um mapeamento com um unico passo")
    keys = [key for key in raw if key in STEP_KINDS]
    unknown = [key for key in raw if key not in STEP_KINDS]
    if unknown:
        raise ActionError(f"{field} tem passo desconhecido: {unknown[0]!r}; use {STEP_KINDS}")
    if len(keys) != 1:
        raise ActionError(f"{field} deve ter exatamente um passo; recebido {list(raw)}")
    kind = keys[0]
    params = raw[kind] or {}
    if kind == "activate":
        return ActionStep(kind="activate")
    if not isinstance(params, dict):
        raise ActionError(f"{field}.{kind} deve ser um mapeamento")

    ref = _as_str(params.get("ref", "roi"), f"{field}.{kind}.ref") or "roi"
    if ref not in REF_KINDS:
        raise ActionError(f"{field}.{kind}.ref invalido: {ref!r}; use {REF_KINDS}")

    if kind in ("click", "move"):
        if "x" not in params or "y" not in params:
            raise ActionError(f"{field}.{kind} precisa de 'x' e 'y'")
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
            raise ActionError(f"{field}.click.button invalido: {button!r}; use {BUTTONS}")
        clicks = _as_int(params.get("clicks", 1), f"{field}.click.clicks")
        if clicks < 1:
            raise ActionError(f"{field}.click.clicks deve ser >= 1")
        return ActionStep(kind="click", x=step.x, y=step.y, ref=ref, button=button, clicks=clicks)

    if kind == "key":
        keys = _as_str(params.get("keys", ""), f"{field}.key.keys")
        if not keys:
            raise ActionError(f"{field}.key precisa de 'keys'")
        return ActionStep(kind="key", keys=keys)

    if kind == "type":
        text = _as_str(params.get("text", ""), f"{field}.type.text")
        if not text:
            raise ActionError(f"{field}.type precisa de 'text'")
        interval = params.get("interval_ms")
        return ActionStep(
            kind="type",
            text=text,
            interval_ms=None if interval is None else _as_int(interval, f"{field}.type.interval_ms"),
        )

    ms = _as_int(params.get("ms", 0), f"{field}.wait.ms")
    if ms < 0:
        raise ActionError(f"{field}.wait.ms deve ser >= 0")
    return ActionStep(kind="wait", ms=ms)


def _parse_when(raw: Any, field: str) -> dict[str, Any]:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ActionError(f"{field} deve ser um mapeamento")
    if raw.get("changed") is False:
        raise ActionError(f"{field}.changed: false nao e suportado nesta fase")
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
            raise ActionError(f"{field}.text_regex invalido: {exc}") from exc
        when["text_regex"] = text_regex
    return when


def parse_action(raw: Any, index: int, prefix: str = "actions", mode: str | None = None) -> ActionSpec:
    field = f"{prefix}[{index}]"
    if not isinstance(raw, dict):
        raise ActionError(f"{field} deve ser um mapeamento")
    if not raw.get("name"):
        raise ActionError(f"{field} precisa de 'name'")

    steps_raw = raw.get("steps")
    if steps_raw is None:
        steps_raw = []
    if not isinstance(steps_raw, (list, tuple)):
        raise ActionError(f"{field}.steps deve ser uma lista")
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
        raise ActionError(f"{field}.settle_s deve ser >= 0")
    if action.cooldown_s < 0:
        raise ActionError(f"{field}.cooldown_s deve ser >= 0")
    if action.max_per_min < 0 or action.max_per_session < 0:
        raise ActionError(f"{field}.max_per_min/max_per_session devem ser >= 0")
    has_click = any(step.kind == "click" for step in action.steps)
    has_activate = any(step.kind == "activate" for step in action.steps)
    if has_click and not has_activate:
        raise ActionError(
            f"{field}: passos com 'click' exigem um passo 'activate: true' antes (foco explicito)"
        )
    if action.needs_ocr and mode is not None and mode != "advanced":
        raise ActionError(
            f"{field}: filtros text_* exigem mode 'advanced' (OCR); perfil/selecao esta em {mode!r}"
        )


def parse_actions(
    raw: Any, prefix: str = "actions", mode: str | None = None
) -> tuple[ActionSpec, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ActionError(f"{prefix} deve ser uma lista")
    actions = tuple(parse_action(item, index, prefix, mode) for index, item in enumerate(raw))
    names = [action.name for action in actions]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ActionError(f"{prefix}: nomes de acao duplicados: {', '.join(duplicates)}")
    return actions
