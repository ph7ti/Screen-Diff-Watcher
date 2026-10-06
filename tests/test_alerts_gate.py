from __future__ import annotations

import math

from screen_watch.alerts.gate import AlertGate


def test_snooze_expires_with_fake_now():
    gate = AlertGate()
    gate.snooze(15, now=1000.0)

    assert gate.status(now=1000.0) == "snoozed"
    assert gate.status(now=1899.0) == "snoozed"
    assert gate.status(now=1900.0) is None
    assert gate.active(now=1900.0) is False


def test_snooze_remaining_minutes():
    gate = AlertGate()
    gate.snooze(10, now=0.0)
    assert gate.snooze_remaining_s(now=-1.0) == 601.0
    assert gate.snooze_remaining_s(now=300.0) == 300.0
    assert gate.snooze_remaining_s(now=10_000.0) == 0.0


def test_mute_has_precedence_and_unmute():
    gate = AlertGate()
    gate.snooze(1, now=0.0)
    gate.mute()

    assert gate.status(now=0.0) == "muted"
    assert gate.snooze_remaining_s(now=0.0) == math.inf

    gate.unmute()
    assert gate.status(now=0.0) == "snoozed"


def test_mute_does_not_clear_snooze():
    gate = AlertGate()
    gate.mute()
    gate.snooze(5, now=100.0)
    gate.unmute()
    assert gate.status(now=100.0) == "snoozed"


def test_clear_resets_both():
    gate = AlertGate(muted=True, snooze_until=999.0)
    gate.clear()
    assert gate.status(now=0.0) is None
    assert gate.to_state_fields() == {"alerts_muted": False, "alerts_snooze_until": 0.0}


def test_from_state_tolerates_invalid_values():
    assert AlertGate.from_state({}).status(now=0.0) is None
    assert AlertGate.from_state({"alerts_muted": "yes"}).muted is True
    gate = AlertGate.from_state({"alerts_snooze_until": "not-a-number"})
    assert gate.snooze_until == 0.0
    gate = AlertGate.from_state({"alerts_snooze_until": "123.5"})
    assert gate.snooze_until == 123.5


def test_state_round_trip():
    gate = AlertGate()
    gate.snooze(30, now=50.0)
    restored = AlertGate.from_state(gate.to_state_fields())
    assert restored.snooze_until == 1850.0
    assert restored.muted is False
