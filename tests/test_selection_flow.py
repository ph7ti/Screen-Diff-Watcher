from __future__ import annotations

from types import SimpleNamespace

import pytest

from screen_watch.cli.commands import capture_selection_for_window
from screen_watch.errors import AppError


def _result():
    return SimpleNamespace(
        global_logical=(10, 10, 50, 50),
        screen_origin=(0, 0),
        device_pixel_ratio=1.0,
        screen_name="x",
    )


def _patch_env(monkeypatch, tmp_path, window_rect):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    monkeypatch.setattr("screen_watch.gui.overlay.run_selection", lambda: _result())
    info = SimpleNamespace(
        handle=1, title="t", rect=window_rect, is_minimized=False, exists=True
    )
    monkeypatch.setattr(
        "screen_watch.platform.window.find_window_by_handle", lambda handle: info
    )
    monkeypatch.setattr(
        "screen_watch.platform.window.friendly_app_name", lambda handle, title="": "app"
    )


def test_selection_inside_window_is_saved(monkeypatch, tmp_path):
    _patch_env(monkeypatch, tmp_path, (0, 0, 100, 100))

    captured = capture_selection_for_window(1)

    assert captured.roi_relative == (10, 10, 50, 50)
    assert captured.path.exists()


def test_selection_outside_window_is_rejected(monkeypatch, tmp_path):
    _patch_env(monkeypatch, tmp_path, (0, 0, 40, 40))

    with pytest.raises(AppError) as excinfo:
        capture_selection_for_window(1)

    assert excinfo.value.code == "runtime.roi_outside_window"
    assert not list((tmp_path / "selections").glob("*.json"))


def test_selection_negative_offset_is_rejected(monkeypatch, tmp_path):
    _patch_env(monkeypatch, tmp_path, (50, 50, 100, 100))

    with pytest.raises(AppError) as excinfo:
        capture_selection_for_window(1)

    assert excinfo.value.code == "runtime.roi_outside_window"
