from __future__ import annotations

from screen_watch.actions.steps import (
    duplicate_step,
    move_step,
    remove_step,
    replace_step,
)


def _steps() -> list[dict]:
    return [
        {"activate": True},
        {"click": {"x": 10, "y": 20, "ref": "roi", "button": "left", "clicks": 1}},
        {"wait": {"ms": 500}},
        {"key": {"keys": "ctrl+s"}},
    ]


def test_move_up():
    result = move_step(_steps(), 2, -1)
    assert [next(iter(step)) for step in result] == ["activate", "wait", "click", "key"]


def test_move_down():
    result = move_step(_steps(), 1, 1)
    assert [next(iter(step)) for step in result] == ["activate", "wait", "click", "key"]


def test_move_clamped_low():
    steps = _steps()
    result = move_step(steps, 0, -5)
    assert result == steps


def test_move_clamped_high():
    steps = _steps()
    result = move_step(steps, len(steps) - 1, 5)
    assert result == steps


def test_move_out_of_range_and_zero_delta_are_copies():
    steps = _steps()
    for index, delta in ((-1, 1), (len(steps), 1), (99, 1), (0, 0), (2, 0)):
        result = move_step(steps, index, delta)
        assert result == steps
        assert result is not steps


def test_move_does_not_mutate_input():
    steps = _steps()
    snapshot = [dict(step) for step in steps]
    move_step(steps, 0, 2)
    assert steps == snapshot


def test_duplicate_inserts_after_and_deep_copies():
    steps = _steps()
    result = duplicate_step(steps, 1)
    assert len(result) == len(steps) + 1
    assert result[2] == steps[1]
    assert result[2] is not steps[1]
    assert result[2]["click"] is not steps[1]["click"]

    result[2]["click"]["x"] = 999
    assert steps[1]["click"]["x"] == 10


def test_duplicate_out_of_range_is_copy():
    steps = _steps()
    for index in (-1, len(steps), 99):
        result = duplicate_step(steps, index)
        assert result == steps
        assert result is not steps


def test_replace_deep_copies_and_keeps_order():
    steps = _steps()
    new_step = {"type": {"text": "ola"}}
    result = replace_step(steps, 1, new_step)
    assert result[1] == new_step
    assert result[1] is not new_step
    assert result[0] is steps[0]
    assert result[2:] == steps[2:]

    new_step["type"]["text"] = "mudou"
    assert result[1]["type"]["text"] == "ola"


def test_replace_out_of_range_is_copy():
    steps = _steps()
    for index in (-1, len(steps), 99):
        result = replace_step(steps, index, {"activate": True})
        assert result == steps
        assert result is not steps


def test_remove_step():
    steps = _steps()
    result = remove_step(steps, 1)
    assert [next(iter(step)) for step in result] == ["activate", "wait", "key"]
    assert len(steps) == 4


def test_remove_out_of_range_is_copy():
    steps = _steps()
    for index in (-1, len(steps), 99):
        result = remove_step(steps, index)
        assert result == steps
        assert result is not steps


def test_empty_list_no_ops():
    empty: list[dict] = []
    assert move_step(empty, 0, 1) == []
    assert duplicate_step(empty, 0) == []
    assert replace_step(empty, 0, {"activate": True}) == []
    assert remove_step(empty, 0) == []
