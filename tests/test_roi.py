from __future__ import annotations

from types import SimpleNamespace

import pytest

from screen_watch.capture.roi import (
    absolute_roi_for_selection,
    resolve_window_roi,
    roi_unavailable_error,
)
from screen_watch.errors import AppError
from screen_watch.persistence.selection import Selection


def _selection(**extra) -> Selection:
    fields = {
        "window_handle": 7,
        "origin_at_selection": (0, 0),
        "roi_relative": (10, 20, 30, 40),
    }
    fields.update(extra)
    return Selection(**fields)


def _window(monkeypatch, info) -> None:
    monkeypatch.setattr(
        "screen_watch.platform.window.find_window_by_handle", lambda handle: info
    )


def _info(*, exists=True, minimized=False, rect=(100, 200, 300, 150)):
    return SimpleNamespace(
        handle=7, title="janela", rect=rect, is_minimized=minimized, exists=exists
    )


def test_absolute_roi_for_selection_resolves_window_origin(monkeypatch):
    _window(monkeypatch, _info())
    assert absolute_roi_for_selection(_selection()) == (110, 220, 30, 40)


def test_absolute_roi_for_selection_missing_window_is_none(monkeypatch):
    _window(monkeypatch, None)
    assert absolute_roi_for_selection(_selection()) is None


def test_absolute_roi_for_selection_minimized_is_none(monkeypatch):
    _window(monkeypatch, _info(minimized=True))
    assert absolute_roi_for_selection(_selection()) is None


def test_absolute_roi_for_selection_degenerate_is_none(monkeypatch):
    _window(monkeypatch, _info())
    assert absolute_roi_for_selection(_selection(roi_relative=(0, 0, 0, 0))) is None


def test_resolve_window_roi_reports_window_not_found(monkeypatch):
    _window(monkeypatch, None)
    with pytest.raises(AppError) as excinfo:
        resolve_window_roi(7, (1, 2, 3, 4))
    assert excinfo.value.code == "runtime.window_not_found"


def test_resolve_window_roi_reports_minimized(monkeypatch):
    _window(monkeypatch, _info(minimized=True))
    with pytest.raises(AppError) as excinfo:
        resolve_window_roi(7, (1, 2, 3, 4))
    assert excinfo.value.code == "runtime.window_minimized"


def test_resolve_window_roi_reports_invalid_roi(monkeypatch):
    _window(monkeypatch, _info())
    with pytest.raises(AppError) as excinfo:
        resolve_window_roi(7, (0, 0, -1, 10))
    assert excinfo.value.code == "runtime.roi_invalid"


def test_roi_unavailable_error_matches_the_reason(monkeypatch):
    _window(monkeypatch, None)
    assert roi_unavailable_error(_selection()).code == "runtime.window_not_found"
    _window(monkeypatch, _info(minimized=True))
    assert roi_unavailable_error(_selection()).code == "runtime.window_minimized"
    _window(monkeypatch, _info())
    assert roi_unavailable_error(_selection()).code == "runtime.roi_invalid"
