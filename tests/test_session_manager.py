from __future__ import annotations

import numpy as np
import pytest

from screen_watch.alerts.chain import DispatchOutcome
from screen_watch.alerts.gate import AlertGate
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import TargetConfig
from screen_watch.errors import AppError
from screen_watch.gui.session_manager import (
    CALIBRATION_MAX,
    SessionManager,
    new_event_queue,
)


def _target(name: str = "t") -> TargetConfig:
    return TargetConfig(
        name=name, window_handle=1, roi_relative=(0, 0, 10, 10), mode="light"
    )


class FakeLoop:
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True

    def stop(self, timeout=None):
        self.running = False


class FakeSession:
    def __init__(self, target, **kwargs):
        self.target = target
        self.kwargs = kwargs
        self.actions = f"dispatcher:{target.name}"
        self.awaiting_ack = False
        self.rebaselines = 0
        self.acks = 0

    def request_rebaseline(self):
        self.rebaselines += 1

    def acknowledge(self):
        self.acks += 1
        self.awaiting_ack = False


def _manager(events=None, *, max_sessions=4):
    loop = FakeLoop()
    manager = SessionManager(
        events if events is not None else new_event_queue(),
        session_factory=lambda target, **kwargs: FakeSession(target, **kwargs),
        loop_factory=lambda target, session, **kwargs: loop,
        max_sessions=max_sessions,
    )
    return manager, loop


def test_start_and_stop_single_session():
    events = new_event_queue()
    manager, _loop = _manager(events)

    name = manager.start(_target("alpha"))

    assert name == "alpha"
    assert manager.running is True
    assert manager.names() == ["alpha"]
    assert events.get_nowait() == {"kind": "started", "session": "alpha", "target": "alpha"}

    manager.stop()
    assert manager.running is False
    assert manager.names() == []
    assert events.get_nowait() == {"kind": "stopped", "session": "alpha"}


def test_stop_without_start_is_safe():
    manager, _loop = _manager()
    manager.stop()
    manager.stop("inexistente")
    assert manager.running is False


def test_two_sessions_run_independently():
    events = new_event_queue()
    loops: dict[str, FakeLoop] = {}

    def loop_factory(target, session, **kwargs):
        loop = FakeLoop()
        loops[target.name] = loop
        return loop

    manager = SessionManager(
        events,
        session_factory=lambda target, **kwargs: FakeSession(target, **kwargs),
        loop_factory=loop_factory,
    )
    manager.start(_target("a"))
    manager.start(_target("b"))
    assert manager.names() == ["a", "b"]
    assert manager.running is True

    manager.stop("a")
    assert manager.names() == ["b"]
    assert loops["a"].running is False
    assert loops["b"].running is True
    assert manager.running is True

    manager.stop_all()
    assert manager.names() == []


def test_duplicate_session_is_rejected():
    manager, _loop = _manager()
    manager.start(_target("a"))
    with pytest.raises(AppError) as excinfo:
        manager.start(_target("a"))
    assert excinfo.value.code == "runtime.session_already_running"


def test_session_limit_is_enforced():
    manager, _loop = _manager(max_sessions=1)
    manager.start(_target("a"))
    with pytest.raises(AppError) as excinfo:
        manager.start(_target("b"))
    assert excinfo.value.code == "runtime.session_limit"
    assert excinfo.value.params["max"] == 1


def test_events_are_tagged_with_session():
    events = new_event_queue()
    manager, _loop = _manager(events)
    manager.start(_target("a"))
    events.get_nowait()

    manager._on_event("a", "target_unavailable", {"reason": "not_found"})
    manager._on_action("a", {"mode": "armed", "action": "x"})
    manager._on_error("a", RuntimeError("boom"))
    manager._on_result(
        "a",
        ComparisonResult(changed=True, score=1.0, threshold=0.1, strategy="light", severity=2),
        DispatchOutcome.FIRED,
    )

    event = events.get_nowait()
    assert event["session"] == "a" and event["name"] == "target_unavailable"
    action = events.get_nowait()
    assert action["session"] == "a" and action["kind"] == "action_event"
    error = events.get_nowait()
    assert error["session"] == "a" and "boom" in error["message"]
    result = events.get_nowait()
    assert result["session"] == "a" and result["outcome"] == "fired"
    assert result["escalating"] is False


def test_preview_and_calibration_are_isolated_per_session():
    events = new_event_queue()
    manager, _loop = _manager(events)
    manager.start(_target("a"))
    manager.start(_target("b"))

    frame_a = type(
        "FrameStub",
        (),
        {"rgb": np.full((480, 640, 3), 10, dtype=np.uint8)},
    )()
    manager._on_frame("a", frame_a, True)
    # `downsample` acessa apenas `rgb`; um stub basta para isolar os buffers.
    latest_a, baseline_a = manager.preview("a")
    latest_b, baseline_b = manager.preview("b")
    assert latest_a is not None and baseline_a is not None
    assert latest_b is None and baseline_b is None
    assert max(latest_a.shape[:2]) <= 240

    for index in range(CALIBRATION_MAX + 5):
        manager._on_compare(
            "b",
            ComparisonResult(
                changed=False, score=index, threshold=1.0, strategy="light", severity=0
            ),
        )
    assert manager.calibration("a") == []
    assert len(manager.calibration("b")) == CALIBRATION_MAX


def test_actions_and_rebaseline_route_to_the_selected_session():
    events = new_event_queue()
    manager, _loop = _manager(events)
    manager.start(_target("a"))
    manager.start(_target("b"))
    session_a = manager._sessions["a"].session
    session_b = manager._sessions["b"].session

    assert manager.actions("a") == "dispatcher:a"
    manager.rebaseline("a")
    manager.acknowledge("a")
    assert session_a.rebaselines == 1 and session_a.acks == 1
    assert session_b.rebaselines == 0 and session_b.acks == 0


def test_escalating_is_any_when_name_is_none():
    manager, _loop = _manager()
    manager.start(_target("a"))
    manager.start(_target("b"))
    assert manager.escalating() is False
    manager._sessions["b"].session.awaiting_ack = True
    assert manager.escalating() is True
    assert manager.escalating("a") is False


def test_gate_controls_persist(monkeypatch):
    manager = SessionManager(new_event_queue(), gate=AlertGate())
    persisted: list[dict] = []
    monkeypatch.setattr(
        "screen_watch.gui.session_manager.persist_gate",
        lambda gate: persisted.append(gate.to_state_fields()),
    )

    manager.snooze(15)
    assert manager.gate_status() == "snoozed"
    assert manager.gate_remaining_s() > 0
    assert persisted[-1]["alerts_snooze_until"] > 0

    manager.mute()
    assert manager.gate_status() == "muted"
    manager.unmute()
    assert manager.gate_status() == "snoozed"


def test_default_focus_is_the_last_started_session():
    manager, _loop = _manager()
    manager.start(_target("a"))
    manager.start(_target("b"))
    assert manager._managed(None) is manager._sessions["b"]
    manager.stop("b")
    assert manager._managed(None) is manager._sessions["a"]
