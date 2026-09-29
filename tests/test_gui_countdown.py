from __future__ import annotations

import sys

from screen_watch.gui import countdown


def test_run_countdown_falls_back_to_console_without_qt(monkeypatch):
    monkeypatch.setitem(sys.modules, "PyQt6", None)
    sleeps: list[float] = []
    monkeypatch.setattr(countdown, "_sleep", lambda seconds: sleeps.append(seconds))

    assert countdown.run_countdown(seconds=2.5) is True
    assert sleeps == [1.0, 1.0, 1.0]


def test_run_countdown_console_prints_numbers(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "PyQt6", None)
    monkeypatch.setattr(countdown, "_sleep", lambda seconds: None)

    assert countdown.run_countdown(seconds=3) is True

    out = capsys.readouterr().out
    assert "3..." in out
    assert "1..." in out


def test_run_countdown_zero_seconds_does_not_sleep(monkeypatch):
    monkeypatch.setitem(sys.modules, "PyQt6", None)
    sleeps: list[float] = []
    monkeypatch.setattr(countdown, "_sleep", lambda seconds: sleeps.append(seconds))

    assert countdown.run_countdown(seconds=0) is True
    assert sleeps == []
