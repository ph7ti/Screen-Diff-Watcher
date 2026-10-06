"""Modelo puro do editor de acoes (sem Qt; doc, secao 11.4/12.5, v0.10.0).

`form_from_action` extrai o estado do formulario a partir de uma acao crua e
`action_from_form` remonta a acao (preservando os filtros `change` em
`when_extra`). O dialogo so faz a ponte com os widgets, o que mantem a logica
testavel sem `QApplication`.
"""

from __future__ import annotations

from typing import Any

from screen_watch.actions.protocol import TRIGGERS, WEEKDAYS
from screen_watch.actions.triggers import at_text, parse_at_text


def form_from_action(action: dict) -> dict:
    """Estado do formulario: gatilho, campos de tempo e sobras de `change`."""
    when = dict(action.get("when") or {})
    trigger = str(when.pop("trigger", "change") or "change")
    if trigger not in TRIGGERS:
        trigger = "change"
    days = tuple(when.pop("days", ()) or ())
    return {
        "trigger": trigger,
        "at": at_text(tuple(when.pop("at", ()) or ())),
        "days": days,
        "every_s": max(1.0, float(when.pop("every_s", 60.0) or 60.0)),
        "after_s": max(1.0, float(when.pop("after_s", 60.0) or 60.0)),
        "when_extra": when,  # ex.: text_*/severity_min do gatilho change
    }


def action_from_form(
    *,
    name: str,
    enabled: bool,
    severity_min: int,
    cooldown_s: float,
    settle_s: float,
    rebaseline: bool,
    trigger: str,
    at_text_value: str,
    days: list[str],
    every_s: float,
    after_s: float,
    when_extra: dict,
    steps: list[dict],
) -> dict:
    """Monta a acao crua a partir dos campos do editor (com `when` quando util)."""
    if trigger == "change":
        when: dict[str, Any] = dict(when_extra)
        when.pop("trigger", None)
    else:
        when = {"trigger": trigger}
        if trigger == "at":
            times = parse_at_text(at_text_value)
            if times:
                when["at"] = list(times)
            if days and len(days) != len(WEEKDAYS):
                when["days"] = list(days)
        elif trigger == "every":
            when["every_s"] = float(every_s)
        elif trigger == "after":
            when["after_s"] = float(after_s)
    payload: dict[str, Any] = {
        "name": name,
        "enabled": bool(enabled),
        "severity_min": int(severity_min),
        "cooldown_s": float(cooldown_s),
        "settle_s": float(settle_s),
        "rebaseline": bool(rebaseline) if trigger == "change" else False,
        "steps": list(steps),
    }
    if when:
        payload["when"] = when
    return payload
