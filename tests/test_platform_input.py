from __future__ import annotations

import random
import sys
import types

import pytest

from screen_watch.config.schema import HumanizeOptions


def test_interpolate_points_includes_endpoints():
    from screen_watch.platform.input import interpolate_points

    assert interpolate_points((0, 0), (10, 0), 5) == [(2, 0), (4, 0), (6, 0), (8, 0), (10, 0)]
    assert interpolate_points((5, 5), (5, 5), 1) == [(5, 5)]
    assert len(interpolate_points((0, 0), (10, 10), 0)) == 1


def test_interpolate_points_jitter_is_bounded_and_seeded():
    from screen_watch.platform.input import interpolate_points

    first = interpolate_points((0, 0), (100, 0), 4, jitter_px=3, rng=random.Random(42))
    second = interpolate_points((0, 0), (100, 0), 4, jitter_px=3, rng=random.Random(42))
    assert first == second
    assert all(abs(point[1]) <= 3 for point in first)


def test_make_rng_and_format_keys():
    from screen_watch.platform.input import format_keys, make_rng

    a = make_rng(HumanizeOptions(seed=1))
    b = make_rng(HumanizeOptions(seed=1))
    assert [a.randint(0, 10) for _ in range(6)] == [b.randint(0, 10) for _ in range(6)]
    assert format_keys("ctrl+s") == "ctrl+s"
    assert format_keys(["ctrl", "s"]) == "ctrl+s"


def test_available_and_backend_unavailable_without_pynput(monkeypatch):
    from screen_watch.platform.input import InputUnavailable, PynputBackend, available

    monkeypatch.setitem(sys.modules, "pynput", None)
    assert available() is False
    with pytest.raises(InputUnavailable):
        PynputBackend()


def _fake_pynput() -> types.ModuleType:
    class FakeController:
        def __init__(self) -> None:
            self.actions: list[tuple] = []
            self._pos = None

        @property
        def position(self):
            return self._pos

        @position.setter
        def position(self, value) -> None:
            self._pos = value
            self.actions.append(("pos", value))

        def click(self, button, count) -> None:
            self.actions.append(("click", button, count))

        def press(self, key) -> None:
            self.actions.append(("press", key))

        def release(self, key) -> None:
            self.actions.append(("release", key))

        def type(self, char) -> None:
            self.actions.append(("type", char))

    class Key:
        ctrl = "KEY_CTRL"
        esc = "KEY_ESC"
        enter = "KEY_ENTER"

    class Button:
        left = "BTN_LEFT"
        right = "BTN_RIGHT"

    keyboard = types.SimpleNamespace(Key=Key, Controller=FakeController)
    mouse = types.SimpleNamespace(Button=Button, Controller=FakeController)
    pkg = types.ModuleType("pynput")
    pkg.keyboard = keyboard
    pkg.mouse = mouse
    return pkg


def test_pynput_backend_translates_actions(monkeypatch):
    from screen_watch.platform.input import InputUnavailable, PynputBackend

    monkeypatch.setitem(sys.modules, "pynput", _fake_pynput())
    backend = PynputBackend()

    backend.move(1, 2)
    assert backend._mouse_ctl.position == (1, 2)

    backend.click(3, 4, button="right", clicks=2)
    assert backend._mouse_ctl.actions.count(("click", "BTN_RIGHT", 1)) == 2

    backend.press("ctrl+s")
    assert backend._key_ctl.actions == [
        ("press", "KEY_CTRL"),
        ("press", "s"),
        ("release", "s"),
        ("release", "KEY_CTRL"),
    ]
    assert backend._resolve_key("escape") == "KEY_ESC"
    assert backend._resolve_key("enter") == "KEY_ENTER"

    backend.type_text("ab", interval_ms=0)
    assert ("type", "a") in backend._key_ctl.actions
    assert ("type", "b") in backend._key_ctl.actions

    with pytest.raises(InputUnavailable):
        backend.press("tecla_invalida+")
    with pytest.raises(InputUnavailable):
        backend.press("")
