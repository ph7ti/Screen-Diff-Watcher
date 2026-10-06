from __future__ import annotations

import numpy as np

from screen_watch.alerts.chain import DispatchOutcome
from screen_watch.app import MonitorSession
from screen_watch.config.schema import EscalationOptions, TargetConfig


def _target(**extra) -> TargetConfig:
    return TargetConfig(
        name="t", window_handle=1, roi_relative=(0, 0, 10, 10), mode="light", **extra
    )


class _RecordingDispatch:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def __call__(self, result, frame):
        self.calls += 1
        return self.outcome


def test_first_frame_is_baseline(make_frame, solid):
    session = MonitorSession(_target())
    dispatched = []
    session.chain.dispatch = lambda result, frame: dispatched.append(result)

    session(make_frame(solid(100), sequence=1))
    assert dispatched == []
    assert session._initialized is True


def test_identical_second_frame_does_not_alert(make_frame, solid):
    session = MonitorSession(_target())
    dispatched = []
    session.chain.dispatch = lambda result, frame: dispatched.append(result)

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(100), sequence=2))
    assert dispatched == []


def test_change_after_baseline_alerts(make_frame, solid):
    session = MonitorSession(_target())
    dispatched = []
    session.chain.dispatch = lambda result, frame: dispatched.append(result)

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    assert len(dispatched) == 1
    assert dispatched[0].changed is True


def test_unknown_mode_raises():
    target = TargetConfig(name="t", window_handle=1, roi_relative=(0, 0, 10, 10), mode="nope")
    try:
        MonitorSession(target)
    except ValueError:
        return
    raise AssertionError("modo invalido deveria levantar ValueError")


def test_pipeline_uses_frame_data_only(make_frame, solid):
    session = MonitorSession(_target())
    frame = make_frame(solid(10))
    session(frame)
    assert isinstance(frame.rgb, np.ndarray)


def test_rearm_on_fired_suppresses_sustained_change(make_frame, solid):
    session = MonitorSession(_target())
    dispatch = _RecordingDispatch(DispatchOutcome.FIRED)
    session.chain.dispatch = dispatch

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    assert dispatch.calls == 1

    session(make_frame(solid(250), sequence=3))
    assert dispatch.calls == 1


def test_cooldown_keeps_change_pending(make_frame, solid):
    session = MonitorSession(_target())
    dispatch = _RecordingDispatch(DispatchOutcome.SUPPRESSED_COOLDOWN)
    session.chain.dispatch = dispatch

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    session(make_frame(solid(250), sequence=3))
    assert dispatch.calls == 2


def test_below_min_rearms(make_frame, solid):
    session = MonitorSession(_target())
    dispatch = _RecordingDispatch(DispatchOutcome.BELOW_MIN)
    session.chain.dispatch = dispatch

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    session(make_frame(solid(250), sequence=3))
    assert dispatch.calls == 1


def test_none_enabled_rearms(make_frame, solid):
    session = MonitorSession(_target())
    dispatch = _RecordingDispatch(DispatchOutcome.NONE_ENABLED)
    session.chain.dispatch = dispatch

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    session(make_frame(solid(250), sequence=3))
    assert dispatch.calls == 1


def test_failed_keeps_change_pending(make_frame, solid):
    session = MonitorSession(_target())
    dispatch = _RecordingDispatch(DispatchOutcome.FAILED)
    session.chain.dispatch = dispatch

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    session(make_frame(solid(250), sequence=3))
    assert dispatch.calls == 2


def test_rearm_false_never_moves_baseline(make_frame, solid):
    session = MonitorSession(_target(rearm=False))
    dispatch = _RecordingDispatch(DispatchOutcome.FIRED)
    session.chain.dispatch = dispatch

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    session(make_frame(solid(250), sequence=3))
    assert dispatch.calls == 2


# -- escalacao (v0.9.0) ----------------------------------------------------


def test_escalation_repeats_until_acknowledge(make_frame, solid):
    target = _target(escalation=EscalationOptions(enabled=True, severity_min=3))
    session = MonitorSession(target)
    dispatch = _RecordingDispatch(DispatchOutcome.FIRED)
    session.chain.dispatch = dispatch

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))  # severidade 3
    assert dispatch.calls == 1
    assert session.awaiting_ack is True

    session(make_frame(solid(250), sequence=3))
    assert dispatch.calls == 2  # baseline mantido: repete a cada tick

    session.acknowledge()
    session(make_frame(solid(250), sequence=4))  # re-arma sem alertar
    assert dispatch.calls == 2
    assert session.awaiting_ack is False

    session(make_frame(solid(250), sequence=5))
    assert dispatch.calls == 2


def test_escalation_disabled_rearms_on_fired(make_frame, solid):
    session = MonitorSession(_target(escalation=EscalationOptions(enabled=True, severity_min=3)))
    dispatch = _RecordingDispatch(DispatchOutcome.FIRED)
    session.chain.dispatch = dispatch

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(116), sequence=2))  # severidade 2 < minimo 3
    assert session.awaiting_ack is False
    session(make_frame(solid(116), sequence=3))
    assert dispatch.calls == 1  # re-armou normalmente


def test_escalation_manual_rearm_clears_state(make_frame, solid):
    target = _target(escalation=EscalationOptions(enabled=True, severity_min=3))
    session = MonitorSession(target)
    session.chain.dispatch = _RecordingDispatch(DispatchOutcome.FIRED)

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    assert session.awaiting_ack is True

    session.request_rebaseline()
    assert session.awaiting_ack is False
    session(make_frame(solid(250), sequence=3))
    assert session.awaiting_ack is False


# -- evidencia atrelada a tentativa (v0.9.0) -------------------------------


class _EvidenceRecorder:
    def __init__(self):
        self.baselines = 0
        self.changes = 0

    def record_baseline(self, frame, name):
        self.baselines += 1

    def record_change(self, frame, name):
        self.changes += 1


def test_change_evidence_only_on_delivery_attempt(make_frame, solid):
    recorder = _EvidenceRecorder()
    session = MonitorSession(_target(), recorder=recorder)
    session.chain.dispatch = _RecordingDispatch(DispatchOutcome.SUPPRESSED_COOLDOWN)

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    session(make_frame(solid(250), sequence=3))
    assert recorder.changes == 0  # sem tentativa real: sem print por tick

    session.chain.dispatch = _RecordingDispatch(DispatchOutcome.FIRED)
    session(make_frame(solid(250), sequence=4))
    assert recorder.changes == 1


def test_change_evidence_on_failed_attempt(make_frame, solid):
    recorder = _EvidenceRecorder()
    session = MonitorSession(_target(), recorder=recorder)
    session.chain.dispatch = _RecordingDispatch(DispatchOutcome.FAILED)

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    assert recorder.changes == 1
