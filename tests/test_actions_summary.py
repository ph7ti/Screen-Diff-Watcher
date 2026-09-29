from __future__ import annotations

from screen_watch.actions.protocol import ActionSpec, ActionStep
from screen_watch.actions.summary import (
    describe_action,
    describe_actions,
    describe_raw_step,
    format_action,
)


def _action(**extra) -> ActionSpec:
    return ActionSpec(
        name=extra.pop("name", "a"),
        settle_s=0.0,
        steps=extra.pop(
            "steps",
            (ActionStep(kind="activate"), ActionStep(kind="key", keys="ctrl+s")),
        ),
        **extra,
    )


def test_describe_action_marks_selection():
    selected = describe_action(_action())
    assert selected.startswith("[x] a — ")
    assert "passos: activate, key: ctrl+s" in selected

    unselected = describe_action(_action(), selected=False)
    assert unselected.startswith("[ ] a — ")


def test_describe_action_details():
    action = _action(
        name="click",
        cooldown_s=30.0,
        rebaseline=True,
        when_severity_min=4,
        text_any=("erro", "falha"),
        enabled=False,
        steps=(
            ActionStep(kind="click", x=10, y=20, ref="roi"),
            ActionStep(kind="wait", ms=1500),
        ),
    )
    line = describe_action(action)
    assert "sev>=4" in line
    assert "cooldown 30s" in line
    assert "rebaseline" in line
    assert "desabilitada" in line
    assert "quando: text_any=['erro', 'falha']" in line
    assert "click: (10,20) ref=roi leftx1" in line
    assert "wait: 1500ms" in line


def test_describe_action_without_steps():
    assert "(sem passos)" in describe_action(_action(steps=()))


def test_describe_actions_selection_filter():
    actions = (_action(name="a"), _action(name="b"))

    assert all(line.startswith("[x]") for line in describe_actions(actions))

    lines = describe_actions(actions, ("b",))
    assert lines[0].startswith("[ ] a")
    assert lines[1].startswith("[x] b")


def test_format_action_has_no_marker():
    text = format_action(_action())
    assert not text.startswith("[")
    assert text.startswith("a — ")


def test_describe_raw_step():
    assert describe_raw_step({"activate": True}) == "activate"
    assert (
        describe_raw_step({"click": {"x": 1, "y": 2, "ref": "roi"}})
        == "click: (1,2) ref=roi leftx1"
    )
    assert describe_raw_step({"move": {"x": 3, "y": 4, "ref": "window"}}) == "move: (3,4) ref=window"
    assert describe_raw_step({"key": {"keys": "ctrl+s"}}) == "key: ctrl+s"
    assert describe_raw_step({"type": {"text": "abc"}}) == "type: 3 char(s)"
    assert describe_raw_step({"wait": {"ms": 250}}) == "wait: 250ms"
