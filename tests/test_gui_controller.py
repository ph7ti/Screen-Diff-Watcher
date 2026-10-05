from __future__ import annotations

import numpy as np

from screen_watch.alerts.chain import DispatchOutcome
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import TargetConfig
from screen_watch.gui.controller import CALIBRATION_MAX, MonitorController, new_event_queue


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


def test_publishes_action_event():
    events = new_event_queue()
    controller = MonitorController(events)

    controller._on_action({"mode": "armed", "action": "a", "executed": True})

    event = events.get_nowait()
    assert event["kind"] == "action_event"
    assert event["payload"]["action"] == "a"
    assert event["payload"]["executed"] is True


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
        def __init__(
            self,
            target,
            on_result=None,
            recorder=None,
            on_action=None,
            on_frame=None,
            on_compare=None,
        ):
            self.target = target
            self.recorder = recorder
            self.on_action = on_action
            self.on_frame = on_frame
            self.on_compare = on_compare

    import screen_watch.app as app

    monkeypatch.setattr(app, "MonitorSession", FakeSession)
    monkeypatch.setattr(app, "build_loop", lambda target, session, **kwargs: FakeLoop())

    controller.start(_target())
    assert controller.running is True
    assert events.get_nowait()["kind"] == "started"

    from screen_watch.errors import AppError

    try:
        controller.start(_target())
    except AppError as exc:
        assert exc.code == "runtime.already_running"
    else:
        raise AssertionError("segundo start deveria falhar")

    controller.stop()
    assert controller.running is False
    assert events.get_nowait()["kind"] == "stopped"


def test_actions_property_and_rebaseline():
    controller = MonitorController(new_event_queue())
    assert controller.actions is None

    calls: list[bool] = []

    class FakeSession:
        actions = "dispatcher"

        def request_rebaseline(self):
            calls.append(True)

    controller._session = FakeSession()
    assert controller.actions == "dispatcher"
    controller.rebaseline()
    assert calls == [True]


def test_preview_keeps_downsampled_latest_and_baseline(make_frame):
    controller = MonitorController(new_event_queue())
    first = make_frame(np.full((480, 640, 3), 10, dtype=np.uint8))
    second = make_frame(np.full((480, 640, 3), 20, dtype=np.uint8))

    controller._on_frame(first, True)
    controller._on_frame(second, False)

    latest, baseline = controller.preview()
    assert latest is not None and baseline is not None
    assert max(latest.shape[:2]) <= 240
    assert int(latest[0, 0, 0]) == 20
    assert int(baseline[0, 0, 0]) == 10


def test_preview_clears(make_frame):
    controller = MonitorController(new_event_queue())
    controller._on_frame(make_frame(np.zeros((10, 10, 3), dtype=np.uint8)), True)

    controller.clear_preview()

    latest, baseline = controller.preview()
    assert latest is None and baseline is None


def test_on_compare_collects_calibration_samples():
    controller = MonitorController(new_event_queue())
    result = ComparisonResult(
        changed=False, score=1.5, threshold=6.0, strategy="default", severity=0
    )

    controller._on_compare(result)

    samples = controller.calibration()
    assert len(samples) == 1
    _ts, strategy, score, threshold, severity = samples[0]
    assert strategy == "default"
    assert score == 1.5
    assert threshold == 6.0
    assert severity == 0


def test_calibration_buffer_is_bounded():
    controller = MonitorController(new_event_queue())
    for index in range(CALIBRATION_MAX + 20):
        controller._on_compare(
            ComparisonResult(
                changed=False, score=index, threshold=1.0, strategy="light", severity=0
            )
        )

    samples = controller.calibration()
    assert len(samples) == CALIBRATION_MAX
    assert samples[-1][2] == CALIBRATION_MAX + 19
