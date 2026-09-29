from __future__ import annotations

import pytest

from screen_watch.actions.plan import ActionError, parse_actions
from screen_watch.config.loader import ConfigError, config_from_dict
from screen_watch.config.loader import parse_actions as loader_parse_actions


def test_parse_minimal_action():
    actions = parse_actions([{"name": "x", "steps": [{"activate": True}, {"click": {"x": 1, "y": 2}}]}])
    assert actions[0].name == "x"
    assert [step.kind for step in actions[0].steps] == ["activate", "click"]
    assert actions[0].steps[1].ref == "roi"
    assert actions[0].steps[1].button == "left"


def test_parse_all_step_kinds():
    raw = [
        {
            "name": "x",
            "steps": [
                {"activate": True},
                {"move": {"x": 1, "y": 2, "ref": "window"}},
                {"click": {"x": 3, "y": 4, "button": "right", "clicks": 2}},
                {"wait": {"ms": 100}},
                {"key": {"keys": "ctrl+s"}},
                {"type": {"text": "abc", "interval_ms": 10}},
            ],
        }
    ]
    steps = parse_actions(raw)[0].steps
    assert [step.kind for step in steps] == ["activate", "move", "click", "wait", "key", "type"]
    assert steps[1].ref == "window"
    assert steps[2].button == "right" and steps[2].clicks == 2
    assert steps[5].interval_ms == 10


def test_unknown_step_raises():
    with pytest.raises(ActionError):
        parse_actions([{"name": "x", "steps": [{"teleport": {}}]}])


def test_step_with_two_keys_raises():
    with pytest.raises(ActionError):
        parse_actions([{"name": "x", "steps": [{"activate": True, "wait": {"ms": 1}}]}])


def test_invalid_ref_raises():
    with pytest.raises(ActionError):
        parse_actions([{"name": "x", "steps": [{"move": {"x": 1, "y": 2, "ref": "mars"}}]}])


def test_click_without_activate_raises():
    with pytest.raises(ActionError):
        parse_actions([{"name": "x", "steps": [{"click": {"x": 1, "y": 1}}]}])


def test_text_filters_require_advanced_mode():
    raw = [{"name": "x", "when": {"text_any": ["erro"]}, "steps": []}]
    with pytest.raises(ActionError):
        parse_actions(raw, mode="default")
    assert parse_actions(raw, mode="advanced")[0].text_any == ("erro",)


def test_when_changed_false_raises():
    with pytest.raises(ActionError):
        parse_actions([{"name": "x", "when": {"changed": False}}])


def test_invalid_regex_raises():
    with pytest.raises(ActionError):
        parse_actions([{"name": "x", "when": {"text_regex": "("}, }], mode="advanced")


def test_duplicate_names_raise():
    with pytest.raises(ActionError):
        parse_actions([{"name": "x"}, {"name": "x"}])


def test_missing_name_raises():
    with pytest.raises(ActionError):
        parse_actions([{"steps": []}])


def test_loader_wraps_action_error_as_config_error():
    with pytest.raises(ConfigError):
        loader_parse_actions([{"steps": []}])


def test_profile_actions_rejected_when_mode_lacks_ocr():
    raw = {
        "version": 2,
        "profile": "default",
        "profiles": {
            "default": {
                "defaults": {"mode": "default"},
                "actions": [{"name": "a", "when": {"text_any": ["x"]}}],
            }
        },
    }
    with pytest.raises(ConfigError):
        config_from_dict(raw)


def test_profile_actions_parsed_in_advanced_mode():
    raw = {
        "version": 2,
        "profile": "default",
        "profiles": {
            "default": {
                "defaults": {"mode": "advanced"},
                "actions": [
                    {
                        "name": "a",
                        "when": {"text_any": ["x"]},
                        "steps": [{"activate": True}, {"click": {"x": 1, "y": 2}}],
                    }
                ],
            }
        },
    }
    config = config_from_dict(raw)
    action = config.resolve().actions[0]
    assert action.name == "a"
    assert action.text_any == ("x",)
    assert action.effective_severity_min == 1


def test_parse_step_error_branches():
    bad_steps = [
        {"click": {"x": 1}},
        {"click": {"x": 1, "y": 1, "clicks": 0}},
        {"click": {"x": 1, "y": 1, "button": "top"}},
        {"move": {"x": 1}},
        {"move": {"x": 1, "y": 2, "ref": 3}},
        {"key": {}},
        {"type": {}},
        {"wait": {"ms": -1}},
        {"move": {"x": "a", "y": 1}},
    ]
    for step in bad_steps:
        with pytest.raises(ActionError):
            parse_actions([{"name": "x", "steps": [step]}])


def test_parse_action_scalar_error_branches():
    bad_actions = [
        {"name": "x", "enabled": "yes"},
        {"name": "x", "severity_min": True},
        {"name": "x", "cooldown_s": "x"},
        {"name": "x", "settle_s": "x"},
        {"name": "x", "max_per_min": "x"},
        {"name": "x", "when": 3},
        {"name": "x", "steps": "x"},
        {"name": "x", "steps": [3]},
        {"name": "x", "when": {"text_any": 3}},
        {"name": "x", "when": {"text_regex": "("}},
    ]
    for action in bad_actions:
        with pytest.raises(ActionError):
            parse_actions([action], mode="advanced")


def test_parse_action_negative_limits_and_cooldown():
    for field in ("cooldown_s", "settle_s"):
        with pytest.raises(ActionError):
            parse_actions([{"name": "x", field: -1}])
    with pytest.raises(ActionError):
        parse_actions([{"name": "x", "max_per_session": -1}])
