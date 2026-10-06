"""Modelo do editor de acoes: gatilhos de tempo (v0.10.0).

Testa o modulo puro `gui/action_editor_model.py` (sem Qt/QApplication), usado
pelo dialogo `ActionEditorDialog`; a mesma logica vale para a GUI.
"""

from __future__ import annotations

import pytest

from screen_watch.actions.plan import ActionError, parse_actions
from screen_watch.actions.protocol import WEEKDAYS
from screen_watch.gui.action_editor_model import action_from_form, form_from_action


def _build(**overrides) -> dict:
    fields = {
        "name": "a",
        "enabled": True,
        "severity_min": 1,
        "cooldown_s": 30.0,
        "settle_s": 1.5,
        "rebaseline": False,
        "trigger": "change",
        "at_text_value": "",
        "days": list(WEEKDAYS),
        "every_s": 60.0,
        "after_s": 300.0,
        "when_extra": {},
        "steps": [],
    }
    fields.update(overrides)
    return action_from_form(**fields)


def test_default_action_has_no_when():
    assert "when" not in _build()


def test_at_roundtrip():
    raw = _build(trigger="at", at_text_value="08:00, 18:00", days=["mon", "fri"])
    assert raw["when"] == {"trigger": "at", "at": ["08:00", "18:00"], "days": ["mon", "fri"]}

    form = form_from_action(raw)
    assert form["trigger"] == "at"
    assert form["at"] == "08:00, 18:00"
    assert form["days"] == ("mon", "fri")


def test_all_days_are_omitted():
    raw = _build(trigger="at", at_text_value="08:00", days=list(WEEKDAYS))
    assert raw["when"] == {"trigger": "at", "at": ["08:00"]}


def test_every_and_after_payloads():
    assert _build(trigger="every", every_s=45.0)["when"] == {
        "trigger": "every",
        "every_s": 45.0,
    }
    assert _build(trigger="after", after_s=300.0)["when"] == {
        "trigger": "after",
        "after_s": 300.0,
    }


def test_change_trigger_preserves_text_filters():
    raw = _build(when_extra={"text_any": ["erro"], "case_sensitive": True})
    assert raw["when"] == {"text_any": ["erro"], "case_sensitive": True}
    form = form_from_action(raw)
    assert form["when_extra"] == {"text_any": ["erro"], "case_sensitive": True}


def test_time_trigger_forces_rebaseline_off():
    assert _build(rebaseline=True)["rebaseline"] is True
    assert _build(trigger="every", rebaseline=True)["rebaseline"] is False


def test_form_from_action_tolerates_unknown_trigger_and_missing_when():
    form = form_from_action({"name": "a", "when": {"trigger": "mars"}})
    assert form["trigger"] == "change"
    assert form["when_extra"] == {}


def test_invalid_at_is_rejected_by_validation():
    raw = _build(trigger="at", at_text_value="25:00")
    with pytest.raises(ActionError) as info:
        parse_actions([raw], mode="advanced")
    assert info.value.code == "action.trigger_at_format"

    raw = _build(trigger="at", at_text_value="08:00")
    action = parse_actions([raw], mode="advanced")[0]
    assert action.trigger == "at" and action.at == ("08:00",)
