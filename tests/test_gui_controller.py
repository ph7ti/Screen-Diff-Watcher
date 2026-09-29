from __future__ import annotations

from screen_watch.alerts.chain import DispatchOutcome
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import TargetConfig
from screen_watch.gui.controller import MonitorController, new_event_queue


def _target() -> TargetConfig:
    return TargetConfig(name="t", window_handle=1, roi_relative=(0, 0, 10, 10), mode="light")


def test_publishes_result_event():
    events = new_event_queue()
    controller = MonitorController(events)
    result = ComparisonResult(
        changed=True, score=0.5, threshold=0.1, strategy="advanced", severity=2
    )

    controller._on_result(result, DispatchOutcome.FIRED)

    event = events.get_nowait()
    assert event["kind"] == "result"
    assert event["strategy"] == "advanced"
    assert event["severity"] == 2
    assert event["outcome"] == "fired"


def test_publishes_event_and_error():
    events = new_event_queue()
    controller = MonitorController(events)

    controller._on_event("target_unavailable", {"reason": "not_found"})
    controller._on_error(RuntimeError("boom"))

    first = events.get_nowait()
    assert first["kind"] == "event"
    assert first["name"] == "target_unavailable"
    second = events.get_nowait()
    assert second["kind"] == "error"
    assert "boom" in second["message"]


def test_stop_without_start_is_safe():
    controller = MonitorController(new_event_queue())
    assert controller.running is False
    controller.stop()
    assert controller.running is False


def test_start_then_reject_second_start(monkeypatch):
    events = new_event_queue()
    controller = MonitorController(events)

    class FakeLoop:
        def __init__(self):
            self.running = False

        def start(self):
            self.running = True

        def stop(self, timeout=None):
            self.running = False

    class FakeSession:
        def __init__(self, target, on_result=None, recorder=None):
            self.target = target
            self.recorder = recorder

    import screen_watch.app as app

    monkeypatch.setattr(app, "MonitorSession", FakeSession)
    monkeypatch.setattr(app, "build_loop", lambda target, session, **kwargs: FakeLoop())

    controller.start(_target())
    assert controller.running is True
    assert events.get_nowait()["kind"] == "started"

    try:
        controller.start(_target())
    except RuntimeError:
        pass
    else:
        raise AssertionError("segundo start deveria falhar")

    controller.stop()
    assert controller.running is False
    assert events.get_nowait()["kind"] == "stopped"
