from __future__ import annotations

import queue
import sys
import types

from screen_watch.gui.tray import start_tray, stop_tray
from screen_watch.i18n import tr


def _fake_pystray() -> types.ModuleType:
    class MenuItem:
        def __init__(self, text, action=None):
            self.text = text
            self.action = action

    class Menu:
        SEPARATOR = object()

        def __init__(self, *items):
            self.items = items

    class Icon:
        def __init__(self, name, image, title, menu):
            self.name = name
            self.menu = menu
            self.stopped = False

        def run(self) -> None:
            pass

        def stop(self) -> None:
            self.stopped = True

    pkg = types.ModuleType("pystray")
    pkg.Menu = Menu
    pkg.MenuItem = MenuItem
    pkg.Icon = Icon
    return pkg


def _menu_by_text(parent) -> dict:
    return {getattr(item, "text", None): item for item in parent.items}


def test_tray_menu_publishes_events(monkeypatch):
    monkeypatch.setitem(sys.modules, "pystray", _fake_pystray())
    events: queue.Queue = queue.Queue()

    icon = start_tray(events, arm_durations=(5, 30), profiles=("default", "trabalho"))
    assert icon is not None

    items = _menu_by_text(icon.menu)
    items[tr("tray.toggle")].action(None, None)
    assert events.get_nowait() == {"kind": "tray", "action": "toggle"}
    items[tr("main.btn_minimize")].action(None, None)
    assert events.get_nowait() == {"kind": "tray", "action": "minimize"}
    items[tr("main.btn_arm")].action(None, None)
    assert events.get_nowait() == {"kind": "action", "action": "arm"}
    items[tr("main.btn_disarm")].action(None, None)
    assert events.get_nowait() == {"kind": "action", "action": "disarm"}
    items[tr("tray.rearm_baseline")].action(None, None)
    assert events.get_nowait() == {"kind": "action", "action": "rearm"}

    arm_items = _menu_by_text(items[tr("main.btn_arm_for")].action)
    arm_items[tr("main.arm_minutes", minutes=30)].action(None, None)
    assert events.get_nowait() == {"kind": "action", "action": "arm_for", "minutes": 30}

    profile_items = _menu_by_text(items[tr("tray.profile")].action)
    profile_items["trabalho"].action(None, None)
    assert events.get_nowait() == {"kind": "profile", "name": "trabalho"}

    stop_tray(icon)
    assert icon.stopped is True


def test_tray_without_pystray(monkeypatch):
    monkeypatch.setitem(sys.modules, "pystray", None)
    assert start_tray(queue.Queue()) is None
    stop_tray(None)
