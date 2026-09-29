"""Cadeia de alertas com cooldown por notificador (doc, secao 11.3).

Falha em um notificador nao impede os demais: cada um tem seu proprio try.
`dispatch` devolve um `DispatchOutcome` para o `MonitorSession` decidir o re-arm.
"""

from __future__ import annotations

import enum
import logging
import time

from screen_watch.alerts.protocol import Notifier
from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult

log = logging.getLogger(__name__)


class DispatchOutcome(enum.Enum):
    """Desfecho de um `dispatch`, usado pelo re-arm edge-triggered."""

    FIRED = "fired"
    SUPPRESSED_COOLDOWN = "suppressed_cooldown"
    BELOW_MIN = "below_min"
    NONE_ENABLED = "none_enabled"
    FAILED = "failed"


class AlertChain:
    def __init__(self, notifiers: list[Notifier]) -> None:
        self.notifiers = notifiers
        self._last_attempt: dict[str, float] = {}

    def dispatch(self, result: ComparisonResult, frame: Frame) -> DispatchOutcome:
        now = time.time()
        enabled = [n for n in self.notifiers if n.enabled]
        if not enabled:
            return DispatchOutcome.NONE_ENABLED

        eligible = [n for n in enabled if result.severity >= n.severity_min]
        if not eligible:
            return DispatchOutcome.BELOW_MIN

        fired = False
        failed = False
        for notifier in eligible:
            last = self._last_attempt.get(notifier.name, 0.0)
            if now - last < notifier.cooldown_s:
                continue
            try:
                notifier.notify(result, frame)
                self._last_attempt[notifier.name] = now
                fired = True
            except Exception as exc:
                log.error("notifier %s falhou: %s", notifier.name, exc)
                # Backoff: registra a tentativa para nao martelar a cada tick
                # enquanto a falha persistir (ex.: token/rede fora).
                self._last_attempt[notifier.name] = now
                failed = True

        if fired:
            return DispatchOutcome.FIRED
        if failed:
            return DispatchOutcome.FAILED
        return DispatchOutcome.SUPPRESSED_COOLDOWN

    def reset(self) -> None:
        self._last_attempt.clear()
