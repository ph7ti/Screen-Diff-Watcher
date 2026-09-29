from __future__ import annotations

from screen_watch.actions.arming import ArmingController
from screen_watch.actions.protocol import ActionSpec, ActionStep
from screen_watch.actions.runner import ActionRunner
from screen_watch.config.schema import HumanizeOptions


class FakeBackend:
    def __init__(self):
        self.moves: list[tuple[int, int]] = []
        self.clicks: list[tuple[int, int, str, int]] = []
        self.keys: list[str] = []
        self.typed: list[tuple[str, int]] = []
        self.on_press = None

    def move(self, x, y):
        self.moves.append((x, y))

    def click(self, x, y, *, button="left", clicks=1):
        self.clicks.append((x, y, button, clicks))

    def press(self, keys):
        self.keys.append(keys)
        if self.on_press is not None:
            self.on_press()

    def type_text(self, text, *, interval_ms=60):
        self.typed.append((text, interval_ms))


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def _runner(clock=None, backend=None, sleeps=None, **kwargs):
    backend = backend or FakeBackend()
    sleeps = sleeps if sleeps is not None else []
    runner = ActionRunner(
        backend_factory=lambda: backend,
        humanize=HumanizeOptions(
            mouse_steps=2, jitter_px=0, wait_jitter_ms=0, key_interval_ms=5, seed=1
        ),
        clock=clock or FakeClock(),
        sleep=sleeps.append,
        activate=kwargs.pop("activate", lambda handle: True),
        is_active=kwargs.pop("is_active", lambda handle: True),
        **kwargs,
    )
    return runner, backend, sleeps


def _armed():
    arming = ArmingController()
    arming.arm()
    return arming


def _frame(make_frame, solid, rect=(100, 50, 30, 20)):
    return make_frame(solid(10), rect=rect)


def test_executes_steps_in_order(make_frame, solid):
    runner, backend, sleeps = _runner()
    frame = _frame(make_frame, solid)
    action = ActionSpec(
        name="a",
        settle_s=0.0,
        steps=(
            ActionStep(kind="activate"),
            ActionStep(kind="move", x=1, y=2, ref="window"),
            ActionStep(kind="click", x=3, y=4, ref="roi", button="left", clicks=1),
            ActionStep(kind="key", keys="ctrl+s"),
            ActionStep(kind="type", text="abc", interval_ms=7),
        ),
    )

    result = runner.run(action, frame, arming=_armed())

    assert result.executed is True
    assert backend.moves[-1] == (103, 54)
    assert backend.clicks == [(103, 54, "left", 1)]
    assert backend.keys == ["ctrl+s"]
    assert backend.typed == [("abc", 7)]
    assert len(result.steps) == 5


def test_activate_focus_guard_aborts(make_frame, solid):
    runner, backend, _ = _runner(is_active=lambda handle: False)
    frame = _frame(make_frame, solid)
    action = ActionSpec(name="a", settle_s=0.0, steps=(ActionStep(kind="activate"),))

    result = runner.run(action, frame, arming=_armed())

    assert result.executed is False
    assert result.reason == "focus_changed"


def test_settle_sleeps(make_frame, solid):
    runner, backend, sleeps = _runner()
    frame = _frame(make_frame, solid)
    action = ActionSpec(name="a", settle_s=1.5, steps=(ActionStep(kind="key", keys="a"),))

    runner.run(action, frame, arming=_armed())

    assert 1.5 in sleeps


def test_max_per_session_limit(make_frame, solid):
    runner, backend, _ = _runner()
    frame = _frame(make_frame, solid)
    action = ActionSpec(
        name="a", settle_s=0.0, max_per_session=1, steps=(ActionStep(kind="key", keys="a"),)
    )

    first = runner.run(action, frame, arming=_armed())
    second = runner.run(action, frame, arming=_armed())

    assert first.executed is True
    assert second.executed is False and second.reason == "rate_limited"


def test_max_per_min_limit(make_frame, solid):
    clock = FakeClock()
    runner, backend, _ = _runner(clock=clock)
    frame = _frame(make_frame, solid)
    action = ActionSpec(
        name="a",
        settle_s=0.0,
        max_per_session=0,
        max_per_min=1,
        steps=(ActionStep(kind="key", keys="a"),),
    )
    arming = _armed()

    assert runner.run(action, frame, arming=arming).executed is True
    clock.advance(30)
    assert runner.run(action, frame, arming=arming).reason == "rate_limited"
    clock.advance(31)
    assert runner.run(action, frame, arming=arming).executed is True


def test_abort_stops_before_first_step(make_frame, solid):
    runner, backend, _ = _runner()
    frame = _frame(make_frame, solid)
    action = ActionSpec(name="a", settle_s=0.0, steps=(ActionStep(kind="key", keys="a"),))
    arming = ArmingController()
    arming.abort()

    result = runner.run(action, frame, arming=arming)

    assert result.executed is False
    assert result.reason == "aborted"
    assert backend.keys == []


def test_disarm_mid_run_stops(make_frame, solid):
    runner, backend, _ = _runner()
    arming = ArmingController()
    arming.arm()
    backend.on_press = arming.disarm
    frame = _frame(make_frame, solid)
    action = ActionSpec(
        name="a",
        settle_s=0.0,
        steps=(ActionStep(kind="key", keys="a"), ActionStep(kind="key", keys="b")),
    )

    result = runner.run(action, frame, arming=arming)

    assert result.executed is False
    assert result.reason == "disarmed_during_run"
    assert backend.keys == ["a"]


def test_evidence_hook_called_per_step(make_frame, solid):
    runner, backend, _ = _runner()
    frame = _frame(make_frame, solid)
    action = ActionSpec(
        name="a",
        settle_s=0.0,
        steps=(ActionStep(kind="key", keys="a"), ActionStep(kind="key", keys="b")),
    )
    seen: list[int] = []

    runner.run(action, frame, arming=_armed(), evidence_hook=seen.append)

    assert seen == [0, 1]


def test_input_unavailable_is_reported(make_frame, solid):
    from screen_watch.platform.input import InputUnavailable

    def factory():
        raise InputUnavailable("sem pynput")

    runner = ActionRunner(backend_factory=factory, humanize=HumanizeOptions(seed=1))
    frame = _frame(make_frame, solid)
    action = ActionSpec(name="a", steps=(ActionStep(kind="key", keys="a"),))

    result = runner.run(action, frame, arming=_armed())

    assert result.executed is False
    assert "sem pynput" in result.reason
