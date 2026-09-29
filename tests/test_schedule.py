from __future__ import annotations

from datetime import datetime

from screen_watch.config.schema import ScheduleOptions
from screen_watch.scheduler.schedule import gate, is_open


def _opts(days=("mon",), windows=("08:00-12:00",)):
    return ScheduleOptions(enabled=True, days=days, windows=windows)


def test_disabled_is_always_open():
    assert is_open(ScheduleOptions(enabled=False)) is True


def test_inside_window():
    # 2026-09-28 e uma segunda-feira.
    assert is_open(_opts(), datetime(2026, 9, 28, 9, 0)) is True


def test_outside_window():
    assert is_open(_opts(), datetime(2026, 9, 28, 13, 0)) is False


def test_wrong_day():
    assert is_open(_opts(days=("mon",)), datetime(2026, 9, 29, 9, 0)) is False


def test_multiple_windows():
    options = _opts(windows=("08:00-12:00", "13:30-18:00"))
    assert is_open(options, datetime(2026, 9, 28, 14, 0)) is True
    assert is_open(options, datetime(2026, 9, 28, 12, 30)) is False


def test_window_crossing_midnight():
    options = _opts(days=("mon",), windows=("22:00-02:00",))
    assert is_open(options, datetime(2026, 9, 28, 23, 0)) is True
    assert is_open(options, datetime(2026, 9, 28, 1, 0)) is True
    assert is_open(options, datetime(2026, 9, 28, 3, 0)) is False


def test_enabled_without_windows_and_days_is_open():
    assert is_open(ScheduleOptions(enabled=True, days=(), windows=())) is True


def test_gate_returns_none_when_disabled():
    assert gate(ScheduleOptions(enabled=False)) is None
    assert gate(None) is None
    assert callable(gate(_opts()))
