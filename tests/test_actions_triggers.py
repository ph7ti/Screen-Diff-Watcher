"""Testes do avaliador puro dos gatilhos de tempo (doc, secao 11.4, v0.10.0)."""

from __future__ import annotations

from datetime import datetime

import pytest

from screen_watch.actions.protocol import ActionSpec
from screen_watch.actions.triggers import (
    TRIGGER_GRACE_S,
    TriggerState,
    at_text,
    evaluate,
    next_delay_s,
    parse_at_text,
)

# Terca-feira 2026-10-06 08:00 (relogio local, mesma base do avaliador).
TUE_0800 = datetime(2026, 10, 6, 8, 0).timestamp()


def _at(*times: str, days: tuple[str, ...] = ()) -> ActionSpec:
    return ActionSpec(name="x", trigger="at", at=times, days=days)


def _every(seconds: float) -> ActionSpec:
    return ActionSpec(name="x", trigger="every", every_s=seconds)


def _after(seconds: float) -> ActionSpec:
    return ActionSpec(name="x", trigger="after", after_s=seconds)


def _eval(action, state, wall, mono, armed_since, grace=TRIGGER_GRACE_S):
    return evaluate(
        action,
        state,
        now_wall=wall,
        now_mono=mono,
        armed_since=armed_since,
        grace_s=grace,
    )


# -- at ---------------------------------------------------------------------
def test_at_fires_when_crossed():
    state = TriggerState()
    assert _eval(_at("08:00"), state, TUE_0800 - 90, 0.0, 100.0).fire is False
    decision = _eval(_at("08:00"), state, TUE_0800 + 5, 0.0, 100.0)
    assert decision.fire is True and decision.missed is False
    assert decision.late_s == pytest.approx(5.0)


def test_at_arming_does_not_retrofire_past_times():
    state = TriggerState()
    # Primeira avaliacao ja depois das 08:00: ancora em `now`, sem disparo.
    assert _eval(_at("08:00"), state, TUE_0800 + 30, 0.0, 100.0).fire is False
    assert _eval(_at("08:00"), state, TUE_0800 + 31, 0.0, 100.0).fire is False


def test_at_grace_edge():
    state = TriggerState()
    _eval(_at("08:00"), state, TUE_0800 - 1, 0.0, 100.0)
    on_time = _eval(_at("08:00"), state, TUE_0800 + TRIGGER_GRACE_S, 0.0, 100.0)
    assert on_time.fire is True

    late_state = TriggerState()
    _eval(_at("08:00"), late_state, TUE_0800 - 1, 0.0, 100.0)
    late = _eval(_at("08:00"), late_state, TUE_0800 + TRIGGER_GRACE_S + 0.001, 0.0, 100.0)
    assert late.missed is True and late.fire is False


def test_at_multiple_times_fires_only_the_latest_crossing():
    state = TriggerState()
    _eval(_at("08:00", "12:00"), state, TUE_0800 - 1, 0.0, 100.0)
    decision = _eval(_at("08:00", "12:00"), state, TUE_0800 + 4 * 3600 + 10, 0.0, 100.0)
    assert decision.fire is True
    assert decision.late_s == pytest.approx(10.0)


def test_at_days_filter_skips_other_weekdays():
    state = TriggerState()
    monday_only = _at("08:00", days=("mon",))
    _eval(monday_only, state, TUE_0800 - 1, 0.0, 100.0)
    assert _eval(monday_only, state, TUE_0800 + 1, 0.0, 100.0).fire is False
    # Proxima ocorrencia permitida: segunda 12/10 08:00.
    expected = datetime(2026, 10, 12, 8, 0).timestamp()
    assert next_delay_s(
        monday_only, TriggerState(), now_wall=TUE_0800, now_mono=0.0, armed_since=100.0
    ) == pytest.approx(expected - TUE_0800)


def test_at_clock_going_backwards_reanchors():
    state = TriggerState()
    _eval(_at("08:00"), state, TUE_0800 + 10, 0.0, 100.0)
    assert _eval(_at("08:00"), state, TUE_0800, 0.0, 100.0).fire is False
    assert state.prev_wall == TUE_0800


# -- every ------------------------------------------------------------------
def test_every_phase_and_fire():
    state = TriggerState()
    assert _eval(_every(10), state, 0.0, 100.0, 100.0).fire is False
    first = _eval(_every(10), state, 0.0, 110.0, 100.0)
    assert first.fire is True and first.late_s == pytest.approx(0.0)
    assert _eval(_every(10), state, 0.0, 115.0, 100.0).fire is False
    assert _eval(_every(10), state, 0.0, 120.0, 100.0).fire is True


def test_every_restarts_phase_on_fire():
    state = TriggerState()
    _eval(_every(10), state, 0.0, 111.0, 100.0)  # dispara 1 s atrasado
    assert _eval(_every(10), state, 0.0, 120.0, 100.0).fire is False
    assert _eval(_every(10), state, 0.0, 121.0, 100.0).fire is True


def test_every_no_burst_after_sleep():
    state = TriggerState()
    _eval(_every(10), state, 0.0, 110.0, 100.0)
    slept = _eval(_every(10), state, 0.0, 1000.0, 100.0)
    assert slept.missed is True and slept.fire is False
    # Uma unica perda registrada; a fase reinicia sem rajada.
    assert _eval(_every(10), state, 0.0, 1001.0, 100.0).fire is False
    assert _eval(_every(10), state, 0.0, 1010.0, 100.0).fire is True


def test_every_grace_edge():
    state = TriggerState()
    due = 100.0 + 10.0
    assert _eval(_every(10), state, 0.0, due + TRIGGER_GRACE_S, 100.0).fire is True
    late_state = TriggerState()
    assert (
        _eval(_every(10), late_state, 0.0, due + TRIGGER_GRACE_S + 0.001, 100.0).missed
        is True
    )


def test_every_rearm_restarts_phase():
    state = TriggerState()
    _eval(_every(10), state, 0.0, 110.0, 100.0)
    assert _eval(_every(10), state, 0.0, 115.0, 200.0).fire is False
    assert _eval(_every(10), state, 0.0, 210.0, 200.0).fire is True


# -- after ------------------------------------------------------------------
def test_after_fires_once():
    state = TriggerState()
    assert _eval(_after(30), state, 0.0, 110.0, 100.0).fire is False
    assert _eval(_after(30), state, 0.0, 130.0, 100.0).fire is True
    assert _eval(_after(30), state, 0.0, 200.0, 100.0).fire is False
    assert state.done is True


def test_after_missed_beyond_grace():
    state = TriggerState()
    decision = _eval(_after(30), state, 0.0, 200.0, 100.0)
    assert decision.missed is True and decision.fire is False
    assert state.done is True


def test_after_rearm_restarts_countdown():
    state = TriggerState()
    _eval(_after(30), state, 0.0, 130.0, 100.0)
    assert _eval(_after(30), state, 0.0, 310.0, 300.0).fire is False
    assert _eval(_after(30), state, 0.0, 330.0, 300.0).fire is True


def test_disarmed_resets_state():
    state = TriggerState()
    _eval(_every(10), state, 0.0, 110.0, 100.0)
    decision = _eval(_every(10), state, 0.0, 120.0, None)
    assert decision.fire is False
    assert state.armed_since is None and state.consumed_mono is None


# -- next_delay_s -----------------------------------------------------------
def test_next_delay_for_at():
    action = _at("08:00")
    assert next_delay_s(
        action, TriggerState(), now_wall=TUE_0800 - 3600, now_mono=0.0, armed_since=1.0
    ) == pytest.approx(3600.0)
    assert next_delay_s(
        action, TriggerState(), now_wall=TUE_0800 + 3600, now_mono=0.0, armed_since=1.0
    ) == pytest.approx(86400.0 - 3600.0)


def test_next_delay_for_every_and_after():
    every = _every(10)
    assert next_delay_s(
        every, TriggerState(), now_wall=0.0, now_mono=104.0, armed_since=100.0
    ) == pytest.approx(6.0)
    assert next_delay_s(
        every, TriggerState(), now_wall=0.0, now_mono=200.0, armed_since=100.0
    ) == pytest.approx(0.0)
    after = _after(30)
    assert next_delay_s(
        after, TriggerState(), now_wall=0.0, now_mono=110.0, armed_since=100.0
    ) == pytest.approx(20.0)
    done = TriggerState(armed_since=100.0, done=True)
    assert next_delay_s(
        after, done, now_wall=0.0, now_mono=110.0, armed_since=100.0
    ) is None


def test_next_delay_none_for_change_or_disarmed():
    change = ActionSpec(name="x")
    assert next_delay_s(
        change, TriggerState(), now_wall=0.0, now_mono=0.0, armed_since=None
    ) is None
    assert next_delay_s(
        _every(10), TriggerState(), now_wall=0.0, now_mono=0.0, armed_since=None
    ) is None


# -- helpers do editor ------------------------------------------------------
def test_at_text_roundtrip():
    assert at_text(("08:00", "18:30")) == "08:00, 18:30"
    assert parse_at_text(" 08:00 ; 18:30 , ") == ("08:00", "18:30")
    assert parse_at_text("") == ()
