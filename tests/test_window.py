from __future__ import annotations

import pytest

from screen_watch.platform import window as window_module
from screen_watch.platform.window import WindowInfo, app_window_label


def _info(title="", app_name="", rect=(0, 0, 800, 600)):
    return WindowInfo(
        handle=1, title=title, rect=rect, is_minimized=False, exists=True, app_name=app_name
    )


def test_label_prefers_app_name_then_title():
    assert (
        app_window_label(_info(app_name="Google Chrome", title="Nova guia"))
        == "Google Chrome — Nova guia  [800x600]"
    )


def test_label_uses_title_when_no_app_name():
    assert app_window_label(_info(title="WhatsApp Beta")) == "WhatsApp Beta  [800x600]"


def test_label_avoids_duplicating_app_and_title():
    assert app_window_label(_info(title="Notepad", app_name="Notepad")) == "Notepad  [800x600]"


def test_label_falls_back_when_empty():
    assert app_window_label(_info()) == "(sem titulo)  [800x600]"


def test_app_name_defaults_empty():
    info = WindowInfo(handle=1, title="x", rect=(0, 0, 1, 1), is_minimized=False, exists=True)
    assert info.app_name == ""


def test_window_queries_require_pywinctl(monkeypatch):
    monkeypatch.setattr(window_module, "pywinctl", None)
    with pytest.raises(RuntimeError, match="pywinctl indisponivel"):
        window_module.list_windows()
    with pytest.raises(RuntimeError, match="pywinctl indisponivel"):
        window_module.find_window_by_handle(1)
    with pytest.raises(RuntimeError, match="pywinctl indisponivel"):
        window_module.list_app_windows()


def test_pywinctl_error_chains_original_cause(monkeypatch):
    monkeypatch.setattr(window_module, "pywinctl", None)
    monkeypatch.setattr(window_module, "_PYWINCTL_ERROR", SystemExit(1))
    with pytest.raises(RuntimeError) as excinfo:
        window_module.list_windows()
    assert isinstance(excinfo.value.__cause__, SystemExit)
