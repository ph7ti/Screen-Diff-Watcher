"""ArmingController: ensaio (default) / armado / temporizado (plano, Fase 2).

Estado apenas em memoria (nao vai ao YAML) e comeca desarmado a cada sessao.
Thread-safe: o tray/GUI armam numa thread e o loop le na thread do monitoramento.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

DISARMED = "disarmed"
ARMED = "armed"
TIMED = "timed"


class ArmingController:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._state = DISARMED
        self._until: float | None = None
        self._armed_since: float | None = None
        self._abort = threading.Event()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == TIMED and self._until is not None and self._clock() >= self._until:
                self._state = DISARMED
                self._until = None
                self._armed_since = None
            return self._state

    @property
    def armed_since(self) -> float | None:
        """Timestamp (monotonic) do armar atual; None desarmado/expirado.

        Base da fase dos gatilhos de tempo (`every`/`after`) e do reset do
        avaliador quando o usuario rearma (doc, secao 11.4).
        """
        self.state  # normaliza a expiracao do TIMED
        with self._lock:
            return self._armed_since if self._state != DISARMED else None

    def is_armed(self) -> bool:
        return self.state != DISARMED

    def remaining_s(self) -> float | None:
        with self._lock:
            if self._state != TIMED or self._until is None:
                return None
            return max(0.0, self._until - self._clock())

    def label(self) -> str:
        """Rotulo em ingles (CLI/log); a GUI traduz `state`/`remaining_s` via i18n."""
        state = self.state
        if state == TIMED:
            remaining = self.remaining_s() or 0.0
            return f"armed for {remaining:.0f}s"
        return "armed" if state == ARMED else "disarmed (rehearsal)"

    def arm(self) -> None:
        with self._lock:
            self._state = ARMED
            self._until = None
            self._armed_since = self._clock()
            self._abort.clear()

    def disarm(self) -> None:
        with self._lock:
            self._state = DISARMED
            self._until = None
            self._armed_since = None

    def toggle(self) -> str:
        if self.is_armed():
            self.disarm()
        else:
            self.arm()
        return self.state

    def arm_for(self, minutes: float) -> None:
        seconds = max(0.0, float(minutes) * 60.0)
        with self._lock:
            self._state = TIMED
            self._until = self._clock() + seconds
            self._armed_since = self._clock()
            self._abort.clear()

    def abort(self) -> None:
        """Esc: interrompe a acao em andamento e volta ao ensaio."""
        self._abort.set()
        self.disarm()

    def abort_pending(self) -> bool:
        return self._abort.is_set()

    def clear_abort(self) -> None:
        self._abort.clear()
