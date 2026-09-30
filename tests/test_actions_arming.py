from __future__ import annotations

from screen_watch.actions.arming import ARMED, DISARMED, TIMED, ArmingController


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_starts_disarmed_in_rehearsal():
    arming = ArmingController()
    assert arming.state == DISARMED
    assert arming.is_armed() is False
    assert arming.label() == "disarmed (rehearsal)"
    assert arming.remaining_s() is None


def test_arm_disarm_toggle():
    arming = ArmingController()
    arming.arm()
    assert arming.state == ARMED and arming.is_armed() is True
    assert arming.label() == "armed"

    assert arming.toggle() == DISARMED
    assert arming.toggle() == ARMED


def test_arm_for_expires_and_labels_remaining():
    clock = FakeClock()
    arming = ArmingController(clock=clock)
    arming.arm_for(2)
    assert arming.state == TIMED and arming.is_armed() is True
    assert arming.remaining_s() == 120.0
    assert "armed for" in arming.label()

    clock.advance(119)
    assert arming.is_armed() is True
    clock.advance(2)
    assert arming.state == DISARMED
    assert arming.is_armed() is False
    assert arming.remaining_s() is None


def test_abort_sets_flag_disarms_and_clears_on_arm():
    arming = ArmingController()
    arming.arm()
    arming.abort()
    assert arming.abort_pending() is True
    assert arming.state == DISARMED

    arming.clear_abort()
    assert arming.abort_pending() is False

    arming.abort()
    arming.arm()
    assert arming.abort_pending() is False
    assert arming.state == ARMED

    arming.abort()
    arming.arm_for(1)
    assert arming.abort_pending() is False
