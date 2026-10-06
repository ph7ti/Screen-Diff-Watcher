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


def test_armed_since_tracks_arming_cycles():
    clock = FakeClock(10.0)
    arming = ArmingController(clock=clock)
    assert arming.armed_since is None

    arming.arm()
    assert arming.armed_since == 10.0

    clock.advance(5)
    arming.arm()  # rearmar reinicia a fase
    assert arming.armed_since == 15.0

    arming.disarm()
    assert arming.armed_since is None


def test_armed_since_cleared_on_timed_expiry():
    clock = FakeClock()
    arming = ArmingController(clock=clock)
    arming.arm_for(1)
    assert arming.armed_since == 0.0

    clock.advance(61)
    assert arming.armed_since is None
    assert arming.state == DISARMED
