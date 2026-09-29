from __future__ import annotations

import sys

from screen_watch.platform.display import (
    MonitorScale,
    describe_scales,
    list_monitor_scales,
    monitor_for_rect,
    suitable_monitors,
)


def _scale(name="a", rect=(0, 0, 100, 100), dpr=1.0, primary=False):
    return MonitorScale(name=name, rect=rect, device_pixel_ratio=dpr, is_primary=primary)


def test_suitability_only_at_100_percent():
    assert _scale(dpr=1.0).is_suitable is True
    assert _scale(dpr=1.25).is_suitable is False


def test_scale_percent_is_rounded():
    assert _scale(dpr=1.25).scale_percent == 125
    assert _scale(dpr=1.0).scale_percent == 100


def test_suitable_monitors_filter():
    scales = [_scale("a", (0, 0, 100, 100), 1.25, True), _scale("b", (100, 0, 100, 100), 1.0)]
    assert [s.name for s in suitable_monitors(scales)] == ["b"]


def test_monitor_for_rect_uses_center():
    scales = [_scale("a", (0, 0, 100, 100), 1.25), _scale("b", (100, 0, 100, 100), 1.0)]
    assert monitor_for_rect(scales, (110, 10, 20, 20)).name == "b"


def test_monitor_for_rect_falls_back_to_intersection():
    scales = [_scale("a", (0, 0, 100, 100), 1.0)]
    assert monitor_for_rect(scales, (90, 90, 40, 40)).name == "a"


def test_monitor_for_rect_returns_none_when_offscreen():
    assert monitor_for_rect([_scale("a", (0, 0, 100, 100), 1.0)], (500, 500, 10, 10)) is None


def test_describe_marks_unsuitable_and_primary():
    lines = describe_scales([_scale("a", (0, 0, 1, 1), 1.25, True)])
    assert "!!" in lines[0]
    assert "125%" in lines[0]
    assert "primario" in lines[0]


def test_list_monitor_scales_returns_none_without_qt(monkeypatch):
    monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", None)
    assert list_monitor_scales() is None
