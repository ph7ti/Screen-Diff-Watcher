from __future__ import annotations

from screen_watch.capture.resolver import resolve


class FakeWindow:
    def __init__(self, rect=(10, 20, 100, 50), minimized=False, exists=True, handle=7):
        self.rect = rect
        self.is_minimized = minimized
        self.exists = exists
        self.handle = handle
        self.title = "fake"


def test_relative_to_origin():
    assert resolve(FakeWindow(), (5, 6, 30, 40)) == (15, 26, 30, 40)


def test_none_window():
    assert resolve(None, (0, 0, 10, 10)) is None


def test_missing_window():
    assert resolve(FakeWindow(exists=False), (0, 0, 10, 10)) is None


def test_minimized_window_rect_is_garbage():
    assert resolve(FakeWindow(minimized=True), (0, 0, 10, 10)) is None


def test_degenerate_roi():
    assert resolve(FakeWindow(), (0, 0, 0, 10)) is None


def test_converter_is_applied():
    def double(x, y, w, h):
        return (x * 2, y * 2, w * 2, h * 2)

    assert resolve(FakeWindow(), (5, 6, 30, 40), logical_to_physical=double) == (30, 52, 60, 80)
