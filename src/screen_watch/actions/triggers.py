"""Avaliador puro dos gatilhos de tempo das acoes (doc, secao 11.4, v0.10.0).

O chamador injeta os dois relogios: `now_wall` (epoch, tempo do `at`) e
`now_mono` (monotonic, fase de `every`/`after` a partir de
`ArmingController.armed_since`). O estado por acao vive em `TriggerState`,
criado e mantido pelo dispatcher na thread do loop.

Sem I/O, sem `sleep` e sem dependencia de Qt. A tolerancia (`grace_s`) decide
entre disparar e registrar `missed`: ocorrencias atrasadas alem dela nunca
executam (sem catch-up e sem rajada).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from screen_watch.actions.protocol import WEEKDAYS, ActionSpec

TRIGGER_GRACE_S = 60.0


@dataclass
class TriggerState:
    """Estado de uma acao de tempo entre ticks (resetado a cada novo armar)."""

    armed_since: float | None = None
    prev_wall: float | None = None
    consumed_mono: float | None = None
    done: bool = False


@dataclass(frozen=True)
class TriggerDecision:
    """Veredito de uma avaliacao: disparar, perdeu o horario ou nada ainda."""

    fire: bool = False
    missed: bool = False
    late_s: float = 0.0


def _reset(state: TriggerState, armed_since: float | None) -> None:
    state.armed_since = armed_since
    state.prev_wall = None
    state.consumed_mono = None
    state.done = False


def _arm(state: TriggerState, armed_since: float) -> None:
    if state.armed_since != armed_since:
        _reset(state, armed_since)


def _at_timestamp(day, text: str) -> float:
    hour, minute = text.split(":")
    return datetime.combine(day, time(int(hour), int(minute))).timestamp()


def _at_occurrences(action: ActionSpec, start_wall: float, end_wall: float) -> list[float]:
    """Horarios de `at` no intervalo (start_wall, end_wall], dias permitidos."""
    found: list[float] = []
    day = datetime.fromtimestamp(start_wall).date()
    last = datetime.fromtimestamp(end_wall).date()
    while day <= last:
        if not action.days or WEEKDAYS[day.weekday()] in action.days:
            for text in action.at:
                ts = _at_timestamp(day, text)
                if start_wall < ts <= end_wall:
                    found.append(ts)
        day += timedelta(days=1)
    return found


def _next_at_timestamp(action: ActionSpec, now_wall: float) -> float | None:
    now = datetime.fromtimestamp(now_wall)
    for offset in range(8):
        day = (now + timedelta(days=offset)).date()
        if action.days and WEEKDAYS[day.weekday()] not in action.days:
            continue
        for text in sorted(action.at):
            ts = _at_timestamp(day, text)
            if ts > now_wall:
                return ts
    return None


def evaluate(
    action: ActionSpec,
    state: TriggerState,
    *,
    now_wall: float,
    now_mono: float,
    armed_since: float | None,
    grace_s: float = TRIGGER_GRACE_S,
) -> TriggerDecision:
    """Avalia a acao de tempo e atualiza `state` (deterministico, sem I/O)."""
    if action.trigger == "change" or armed_since is None:
        _reset(state, None)
        return TriggerDecision()
    _arm(state, armed_since)

    if action.trigger == "at":
        prev = state.prev_wall if state.prev_wall is not None else now_wall
        if now_wall <= prev:  # relogio andou para tras (DST): apenas reancora
            state.prev_wall = now_wall
            return TriggerDecision()
        occurrences = _at_occurrences(action, prev, now_wall)
        state.prev_wall = now_wall
        if not occurrences:
            return TriggerDecision()
        due = max(occurrences)
        late = now_wall - due
        return TriggerDecision(fire=late <= grace_s, missed=late > grace_s, late_s=late)

    if action.trigger == "every":
        anchor = state.consumed_mono if state.consumed_mono is not None else armed_since
        due = anchor + action.every_s
        if now_mono < due:
            return TriggerDecision()
        late = now_mono - due
        state.consumed_mono = now_mono  # reinicia a fase no disparo/perda
        return TriggerDecision(fire=late <= grace_s, missed=late > grace_s, late_s=late)

    if action.trigger == "after":
        if state.done:
            return TriggerDecision()
        due = armed_since + action.after_s
        if now_mono < due:
            return TriggerDecision()
        late = now_mono - due
        state.done = True
        return TriggerDecision(fire=late <= grace_s, missed=late > grace_s, late_s=late)

    return TriggerDecision()


def next_delay_s(
    action: ActionSpec,
    state: TriggerState,
    *,
    now_wall: float,
    now_mono: float,
    armed_since: float | None,
) -> float | None:
    """Segundos ate a proxima avaliacao relevante (None sem ocorrencia)."""
    if action.trigger == "change" or armed_since is None:
        return None
    _arm(state, armed_since)

    if action.trigger == "at":
        ts = _next_at_timestamp(action, now_wall)
        return None if ts is None else max(0.0, ts - now_wall)

    if action.trigger == "every":
        anchor = state.consumed_mono if state.consumed_mono is not None else armed_since
        return max(0.0, anchor + action.every_s - now_mono)

    if action.trigger == "after":
        if state.done:
            return None
        return max(0.0, armed_since + action.after_s - now_mono)

    return None


def at_text(values: tuple[str, ...]) -> str:
    """Lista de horarios -> texto do editor ("08:00, 18:00")."""
    return ", ".join(values)


def parse_at_text(text: str) -> tuple[str, ...]:
    """Texto do editor -> tupla de horarios (separa por virgula/ponto-e-virgula)."""
    return tuple(
        part.strip() for part in text.replace(";", ",").split(",") if part.strip()
    )
