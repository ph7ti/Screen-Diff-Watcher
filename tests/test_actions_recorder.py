from __future__ import annotations

import yaml

from screen_watch.actions.recorder import StepRecorder, convert_point, point_in_rect


def test_point_in_rect_boundaries():
    assert point_in_rect((100, 50), (100, 50, 10, 10)) is True
    assert point_in_rect((109, 59), (100, 50, 10, 10)) is True
    assert point_in_rect((110, 50), (100, 50, 10, 10)) is False


def test_convert_point_prefers_roi():
    params = convert_point(110, 60, roi_rect=(100, 50, 40, 30), window_rect=(0, 0, 500, 400))
    assert params == {"x": 10, "y": 10, "ref": "roi"}


def test_convert_point_window():
    params = convert_point(10, 10, roi_rect=(100, 50, 40, 30), window_rect=(0, 0, 500, 400))
    assert params == {"x": 10, "y": 10, "ref": "window"}


def test_convert_point_screen():
    params = convert_point(-5, 10, roi_rect=(100, 50, 40, 30), window_rect=(0, 0, 500, 400))
    assert params == {"x": -5, "y": 10, "ref": "screen"}


def test_step_recorder_raw_steps():
    recorder = StepRecorder(roi_rect=(100, 50, 40, 30), window_rect=(0, 0, 500, 400))
    recorder.add_click(110, 60)
    recorder.add_move(10, 10)
    recorder.add_key("ctrl+s")
    recorder.add_wait(200)

    steps = recorder.raw_steps()
    assert steps[0] == {
        "click": {"x": 10, "y": 10, "ref": "roi", "button": "left", "clicks": 1}
    }
    assert steps[1]["move"]["ref"] == "window"
    assert steps[2] == {"key": {"keys": "ctrl+s"}}
    assert steps[3] == {"wait": {"ms": 200}}


def test_step_recorder_without_rects_uses_screen():
    recorder = StepRecorder()
    recorder.add_click(7, 8)
    assert recorder.raw_steps()[0]["click"]["ref"] == "screen"


def test_to_yaml_snippet_is_parseable_and_has_activate():
    recorder = StepRecorder(roi_rect=(100, 50, 40, 30), window_rect=(0, 0, 500, 400))
    recorder.add_click(110, 60)
    recorder.add_key("ctrl+s")

    snippet = recorder.to_yaml("teste")
    assert "name: teste" in snippet
    assert "activate: true" in snippet
    assert "ref: roi" in snippet
    assert "# when:" in snippet

    from screen_watch.config.loader import parse_actions

    actions = parse_actions(yaml.safe_load(snippet)["actions"])
    assert actions[0].name == "teste"
    assert actions[0].steps[0].kind == "activate"
    assert actions[0].steps[1].kind == "click"
