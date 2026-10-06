from __future__ import annotations

import json

from screen_watch.actions.arming import ArmingController
from screen_watch.actions.audit import ActionAudit
from screen_watch.actions.dispatch import ActionDispatcher
from screen_watch.actions.protocol import ActionSpec, ActionStep
from screen_watch.actions.runner import ActionRunner
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import HumanizeOptions


class FakeBackend:
    def __init__(self):
        self.moves: list[tuple[int, int]] = []
        self.clicks: list[tuple[int, int, str, int]] = []
        self.keys: list[str] = []
        self.typed: list[tuple[str, int]] = []

    def move(self, x, y):
        self.moves.append((x, y))

    def click(self, x, y, *, button="left", clicks=1):
        self.clicks.append((x, y, button, clicks))

    def press(self, keys):
        self.keys.append(keys)

    def type_text(self, text, *, interval_ms=60):
        self.typed.append((text, interval_ms))


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class FakeRecorder:
    def __init__(self, per_step=False):
        self.per_step = per_step
        self.calls: list[tuple[str, int]] = []

    def record_action(self, frame, name, step=0):
        self.calls.append((name, step))
        return f"/tmp/{name}-{step}.png"


def _result(severity=3, text=None):
    detail = {"current_text": text} if text is not None else {}
    return ComparisonResult(
        changed=True, score=1.0, threshold=0.1, strategy="advanced", severity=severity, detail=detail
    )


def _dispatcher(
    tmp_path,
    actions,
    *,
    clock=None,
    schedule_open=None,
    recorder=None,
    on_event=None,
    wall_clock=None,
):
    clock = clock or FakeClock()
    backend = FakeBackend()
    runner = ActionRunner(
        backend_factory=lambda: backend,
        humanize=HumanizeOptions(mouse_steps=1, jitter_px=0, wait_jitter_ms=0, seed=1),
        clock=clock,
        sleep=lambda seconds: None,
        activate=lambda handle: True,
        is_active=lambda handle: True,
    )
    arming = ArmingController(clock=clock)
    audit = ActionAudit(tmp_path / "actions.jsonl")
    dispatcher = ActionDispatcher(
        actions,
        arming=arming,
        runner=runner,
        target_name="alvo",
        audit=audit,
        recorder=recorder,
        on_event=on_event,
        schedule_open=schedule_open,
        clock=clock,
        wall_clock=wall_clock or clock,
    )
    return dispatcher, arming, backend, audit


def _records(audit) -> list[dict]:
    if not audit.path.exists():
        return []
    return [json.loads(line) for line in audit.path.read_text(encoding="utf-8").splitlines()]


def _key_action(**extra) -> ActionSpec:
    return ActionSpec(
        name=extra.pop("name", "a"),
        settle_s=0.0,
        steps=(ActionStep(kind="key", keys="a"),),
        **extra,
    )


def test_text_filter_matches_and_rehearses(tmp_path, make_frame, solid):
    action = _key_action(when_severity_min=1, text_any=("erro",))
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,))
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(text="ERRO 500"), frame)

    records = _records(audit)
    assert records and records[0]["mode"] == "rehearsal"
    assert backend.keys == []


def test_text_filter_rejects_non_match(tmp_path, make_frame, solid):
    action = _key_action(text_any=("falha",))
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,))
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(text="tudo ok"), frame)

    assert _records(audit) == []


def test_severity_gate(tmp_path, make_frame, solid):
    action = _key_action(severity_min=2)
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,))
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(severity=1), frame)

    assert _records(audit) == []


def test_armed_executes_and_audits(tmp_path, make_frame, solid):
    action = _key_action()
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,))
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(), frame)

    records = _records(audit)
    assert records[0]["mode"] == "armed"
    assert records[0]["executed"] is True
    assert backend.keys == ["a"]


def test_suspended_schedule_skips_even_armed(tmp_path, make_frame, solid):
    action = _key_action()
    dispatcher, arming, backend, audit = _dispatcher(
        tmp_path, (action,), schedule_open=lambda: False
    )
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(), frame)

    records = _records(audit)
    assert records[0]["mode"] == "skipped"
    assert records[0]["reason"] == "suspended_schedule"
    assert backend.keys == []


def test_cooldown_blocks_second_trigger(tmp_path, make_frame, solid):
    action = _key_action(cooldown_s=30.0)
    clock = FakeClock()
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,), clock=clock)
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(), frame)
    clock.advance(10)
    dispatcher.on_result(_result(), frame)

    assert len(_records(audit)) == 1
    clock.advance(30)
    dispatcher.on_result(_result(), frame)
    assert len(_records(audit)) == 2


def test_cooldown_emits_live_event_without_audit(tmp_path, make_frame, solid):
    events: list[dict] = []
    action = _key_action(cooldown_s=30.0)
    clock = FakeClock()
    dispatcher, arming, backend, audit = _dispatcher(
        tmp_path, (action,), clock=clock, on_event=events.append
    )
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(), frame)
    clock.advance(10)
    dispatcher.on_result(_result(), frame)

    assert len(_records(audit)) == 1
    assert events[-1] == {
        "mode": "skipped",
        "reason": "cooldown",
        "action": "a",
        "trigger": "change",
    }


def test_disabled_action_ignored(tmp_path, make_frame, solid):
    action = _key_action(enabled=False)
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,))
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(), frame)

    assert _records(audit) == []
    assert backend.keys == []


def test_rebaseline_only_when_opted_in(tmp_path, make_frame, solid):
    action = _key_action(rebaseline=True)
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,))
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    assert dispatcher.on_result(_result(), frame) is True

    action2 = _key_action(name="b", rebaseline=False)
    dispatcher2, arming2, _, _ = _dispatcher(tmp_path, (action2,))
    arming2.arm()
    assert dispatcher2.on_result(_result(), frame) is False


def test_evidence_per_step(tmp_path, make_frame, solid):
    action = ActionSpec(
        name="a",
        settle_s=0.0,
        steps=(ActionStep(kind="key", keys="a"), ActionStep(kind="key", keys="b")),
    )
    recorder = FakeRecorder(per_step=True)
    dispatcher, arming, backend, audit = _dispatcher(
        tmp_path, (action,), recorder=recorder
    )
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(), frame)

    assert recorder.calls == [("alvo", 0), ("alvo", 1)]


def test_evidence_per_batch(tmp_path, make_frame, solid):
    action = ActionSpec(
        name="a",
        settle_s=0.0,
        steps=(ActionStep(kind="key", keys="a"), ActionStep(kind="key", keys="b")),
    )
    recorder = FakeRecorder(per_step=False)
    dispatcher, arming, backend, audit = _dispatcher(
        tmp_path, (action,), recorder=recorder
    )
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(), frame)

    assert recorder.calls == [("alvo", 0)]


def test_rehearsal_records_evidence(tmp_path, make_frame, solid):
    action = _key_action()
    recorder = FakeRecorder(per_step=False)
    dispatcher, arming, backend, audit = _dispatcher(
        tmp_path, (action,), recorder=recorder
    )
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(), frame)

    assert recorder.calls == [("alvo", 0)]
    records = _records(audit)
    assert records[0]["mode"] == "rehearsal"
    assert records[0]["evidence"] == ["/tmp/alvo-0.png"]


def test_on_event_receives_rehearsal_payload(tmp_path, make_frame, solid):
    events: list[dict] = []
    dispatcher, arming, backend, audit = _dispatcher(
        tmp_path, (_key_action(),), on_event=events.append
    )
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(), frame)

    assert events and events[0]["mode"] == "rehearsal"
    assert events[0]["action"] == "a"


def test_on_event_receives_armed_payload(tmp_path, make_frame, solid):
    events: list[dict] = []
    dispatcher, arming, backend, audit = _dispatcher(
        tmp_path, (_key_action(),), on_event=events.append
    )
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_result(_result(), frame)

    assert events[0]["mode"] == "armed"
    assert events[0]["executed"] is True


def test_build_dispatcher_passes_on_event(tmp_path, make_frame, solid):
    from screen_watch.actions.dispatch import build_dispatcher
    from screen_watch.config.schema import TargetConfig

    events: list[dict] = []
    target = TargetConfig(
        name="t",
        window_handle=1,
        roi_relative=(0, 0, 10, 10),
        actions=(ActionSpec(name="a", settle_s=0.0, steps=(ActionStep(kind="key", keys="a"),)),),
    )
    dispatcher = build_dispatcher(
        target, audit=ActionAudit(tmp_path / "a.jsonl"), on_event=events.append
    )
    dispatcher.on_result(_result(), make_frame(solid(10), rect=(0, 0, 10, 10)))

    assert events and events[0]["mode"] == "rehearsal"


def test_build_dispatcher_none_without_actions():
    from screen_watch.actions.dispatch import build_dispatcher
    from screen_watch.config.schema import TargetConfig

    target = TargetConfig(name="t", window_handle=1, roi_relative=(0, 0, 10, 10))
    assert build_dispatcher(target) is None


def test_build_dispatcher_wires_schedule_gate(monkeypatch, tmp_path):
    from screen_watch.actions.dispatch import build_dispatcher
    from screen_watch.config.schema import ScheduleOptions, TargetConfig

    target = TargetConfig(
        name="t",
        window_handle=1,
        roi_relative=(0, 0, 10, 10),
        actions=(ActionSpec(name="a", steps=(ActionStep(kind="key", keys="a"),)),),
        schedule=ScheduleOptions(enabled=True, days=("mon",), windows=("08:00-12:00",)),
    )
    monkeypatch.setattr("screen_watch.scheduler.schedule.is_open", lambda options, now=None: False)
    dispatcher = build_dispatcher(target, audit=ActionAudit(tmp_path / "a.jsonl"))
    assert dispatcher is not None
    assert dispatcher.is_schedule_open() is False
    assert "disarmed" in dispatcher.arming.label()


def test_dispatcher_ignores_unchanged_result(tmp_path, make_frame, solid):
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (_key_action(),))
    changed = ComparisonResult(
        changed=False, score=0.0, threshold=0.1, strategy="advanced", severity=0
    )
    assert dispatcher.on_result(changed, make_frame(solid(10), rect=(0, 0, 10, 10))) is False
    assert not audit.path.exists()


def test_dispatcher_schedule_error_is_safe(tmp_path):
    from screen_watch.actions.arming import ArmingController
    from screen_watch.actions.dispatch import ActionDispatcher
    from screen_watch.actions.runner import ActionRunner

    def boom():
        raise RuntimeError("clock")

    dispatcher = ActionDispatcher(
        (ActionSpec(name="a"),),
        arming=ArmingController(),
        runner=ActionRunner(sleep=lambda seconds: None),
        schedule_open=boom,
    )
    assert dispatcher.is_schedule_open() is True


# -- gatilhos de tempo (v0.10.0) -------------------------------------------
class WallClock:
    """Relogio de parede fake independente do monotonic."""

    def __init__(self, start: float) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_on_tick_every_fires_only_when_armed(tmp_path, make_frame, solid):
    clock = FakeClock()
    action = _key_action(trigger="every", every_s=10.0, cooldown_s=0.0)
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,), clock=clock)
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_tick(frame)  # desarmado: sem disparo nem auditoria
    assert backend.keys == [] and _records(audit) == []

    arming.arm()
    dispatcher.on_tick(frame)
    assert backend.keys == []
    clock.advance(10)
    dispatcher.on_tick(frame)

    assert backend.keys == ["a"]
    records = _records(audit)
    assert records[0]["mode"] == "armed"
    assert records[0]["trigger"] == "every"


def test_on_result_ignores_time_actions(tmp_path, make_frame, solid):
    action = _key_action(trigger="after", after_s=5.0)
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,))
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    assert dispatcher.on_result(_result(), frame) is False
    assert backend.keys == [] and _records(audit) == []


def test_on_tick_after_fires_once(tmp_path, make_frame, solid):
    clock = FakeClock()
    action = _key_action(trigger="after", after_s=5.0, cooldown_s=0.0)
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,), clock=clock)
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_tick(frame)
    clock.advance(5)
    dispatcher.on_tick(frame)
    assert backend.keys == ["a"]

    clock.advance(60)
    dispatcher.on_tick(frame)
    assert backend.keys == ["a"]
    assert len(_records(audit)) == 1


def test_on_tick_missed_records_audit_without_running(tmp_path, make_frame, solid):
    clock = FakeClock()
    action = _key_action(trigger="every", every_s=10.0, cooldown_s=0.0)
    dispatcher, arming, backend, audit = _dispatcher(tmp_path, (action,), clock=clock)
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    clock.advance(1000)
    dispatcher.on_tick(frame)

    records = _records(audit)
    assert records[0]["mode"] == "skipped"
    assert records[0]["reason"] == "missed"
    assert records[0]["trigger"] == "every"
    assert backend.keys == []


def test_on_tick_at_uses_wall_clock(tmp_path, make_frame, solid):
    from datetime import datetime

    clock = FakeClock()
    wall = WallClock(datetime(2026, 10, 6, 7, 59, 50).timestamp())
    action = _key_action(trigger="at", at=("08:00",), cooldown_s=0.0)
    dispatcher, arming, backend, audit = _dispatcher(
        tmp_path, (action,), clock=clock, wall_clock=wall
    )
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    dispatcher.on_tick(frame)  # ancora o cruzamento no armar (07:59:50)
    wall.advance(5)
    dispatcher.on_tick(frame)  # 07:59:55: ainda nao
    assert backend.keys == []

    wall.advance(7)
    dispatcher.on_tick(frame)  # 08:00:02: cruzou
    assert backend.keys == ["a"]


def test_on_tick_suspended_schedule_consumes_occurrence(tmp_path, make_frame, solid):
    clock = FakeClock()
    gate = {"open": False}
    action = _key_action(trigger="every", every_s=10.0, cooldown_s=0.0)
    dispatcher, arming, backend, audit = _dispatcher(
        tmp_path, (action,), clock=clock, schedule_open=lambda: gate["open"]
    )
    arming.arm()
    frame = make_frame(solid(10), rect=(0, 0, 10, 10))

    clock.advance(10)
    dispatcher.on_tick(frame)
    records = _records(audit)
    assert records[0]["reason"] == "suspended_schedule"
    assert backend.keys == []

    gate["open"] = True
    dispatcher.on_tick(frame)  # ocorrencia consumida; nao repete ao reabrir
    assert backend.keys == []

    clock.advance(10)
    dispatcher.on_tick(frame)
    assert backend.keys == ["a"]


def test_next_deadline_delay_reports_minimum_and_resets(tmp_path):
    clock = FakeClock()
    every = _key_action(name="e", trigger="every", every_s=30.0, cooldown_s=0.0)
    after = _key_action(name="f", trigger="after", after_s=60.0, cooldown_s=0.0)
    dispatcher, arming, _, _ = _dispatcher(tmp_path, (every, after), clock=clock)

    assert dispatcher.next_deadline_delay() is None  # desarmado
    arming.arm()
    assert dispatcher.next_deadline_delay() == 30.0
    clock.advance(10)
    assert dispatcher.next_deadline_delay() == 20.0
    arming.disarm()
    assert dispatcher.next_deadline_delay() is None
