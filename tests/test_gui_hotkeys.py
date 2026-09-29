from __future__ import annotations

import queue
import sys
import types

from screen_watch.gui.hotkeys import start_hotkeys, stop_hotkeys


def _fake_pynput() -> types.ModuleType:
    class Listener:
        def __init__(self, mapping):
            self.mapping = mapping
            self.daemon = False
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

    pkg = types.ModuleType("pynput")
    pkg.keyboard = types.SimpleNamespace(GlobalHotKeys=Listener)
    return pkg


def test_hotkeys_register_publish_and_stop(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynput", _fake_pynput())
    events: queue.Queue = queue.Queue()

    listener = start_hotkeys(events, {"arm": "<ctrl>+<alt>+a", "rearm": "<ctrl>+<alt>+r"})

    assert listener is not None and listener.started is True
    listener.mapping["<ctrl>+<alt>+a"]()
    assert events.get_nowait() == {"kind": "action", "action": "arm"}


def test_hotkeys_empty_and_without_pynput(monkeypatch):
    assert start_hotkeys(queue.Queue(), {}) is None
    assert start_hotkeys(queue.Queue(), {"": "<ctrl>+a"}) is None

    monkeypatch.setitem(sys.modules, "pynput", None)
    assert start_hotkeys(queue.Queue(), {"arm": "<ctrl>+a"}) is None
    stop_hotkeys(None)
