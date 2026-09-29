"""Janela de horario do agendador (plano, F3-T2).

Funcao pura e testavel com relogio falso. Fora da janela o runtime mantem
captura/comparacao e alertas, mas suspende apenas as acoes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from screen_watch.config.schema import VALID_DAYS, ScheduleOptions


def _minutes(text: str) -> int:
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def _in_window(current: int, window: str) -> bool:
    start_text, end_text = window.split("-")
    start, end = _minutes(start_text), _minutes(end_text)
    if start <= end:
        return start <= current <= end
    # Janela que cruza a meia-noite (ex.: 22:00-02:00).
    return current >= start or current <= end


def is_open(options: ScheduleOptions, now: datetime | None = None) -> bool:
    """True se o horario atual esta na janela (ou se o agendador esta desligado).

    Agendador ligado sem `days`/`windows` nao restringe (equivale a sempre aberto).
    """
    if not options.enabled or not options.days or not options.windows:
        return True
    moment = now or datetime.now()
    if VALID_DAYS[moment.weekday()] not in options.days:
        return False
    current = moment.hour * 60 + moment.minute
    return any(_in_window(current, window) for window in options.windows)


def gate(options: ScheduleOptions | None) -> Callable[[], bool] | None:
    """Callable para o dispatcher; None quando nao ha restricao de horario."""
    if options is None or not options.enabled:
        return None
    return lambda: is_open(options)
