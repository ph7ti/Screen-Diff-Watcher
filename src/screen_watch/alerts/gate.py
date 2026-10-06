"""Gate de supressao manual de alertas: snooze temporario e mute (doc, secao 11.3).

Puro e thread-safe: a GUI/tray altera o estado enquanto a thread do loop consulta
`status()` a cada dispatch. A persistencia em `state.json` e responsabilidade dos
helpers `load_gate`/`persist_gate` (best-effort), chamados fora do caminho do tick.
"""

from __future__ import annotations

import math
import threading
import time

MUTE_KEY = "alerts_muted"
SNOOZE_KEY = "alerts_snooze_until"


class AlertGate:
    """Estado de snooze/mute compartilhado entre sessoes."""

    def __init__(self, *, snooze_until: float = 0.0, muted: bool = False) -> None:
        self._lock = threading.Lock()
        self._snooze_until = float(snooze_until or 0.0)
        self._muted = bool(muted)

    # -- consulta ----------------------------------------------------------
    @property
    def snooze_until(self) -> float:
        with self._lock:
            return self._snooze_until

    @property
    def muted(self) -> bool:
        with self._lock:
            return self._muted

    def status(self, now: float | None = None) -> str | None:
        """`"muted"`, `"snoozed"` ou `None` (mute tem precedencia)."""
        with self._lock:
            if self._muted:
                return "muted"
            if self._snooze_until > (time.time() if now is None else now):
                return "snoozed"
            return None

    def active(self, now: float | None = None) -> bool:
        return self.status(now) is not None

    def snooze_remaining_s(self, now: float | None = None) -> float:
        """Segundos restantes do snooze (0 quando inativo; `inf` quando muted)."""
        with self._lock:
            if self._muted:
                return math.inf
            return max(0.0, self._snooze_until - (time.time() if now is None else now))

    # -- alteracao ---------------------------------------------------------
    def snooze(self, minutes: float, now: float | None = None) -> float:
        """Soneca por `minutes`; devolve o epoch final. Nao desfaz um mute."""
        until = (time.time() if now is None else now) + float(minutes) * 60.0
        with self._lock:
            self._snooze_until = until
        return until

    def mute(self) -> None:
        with self._lock:
            self._muted = True

    def unmute(self) -> None:
        with self._lock:
            self._muted = False

    def clear(self) -> None:
        with self._lock:
            self._muted = False
            self._snooze_until = 0.0

    # -- state.json --------------------------------------------------------
    @classmethod
    def from_state(cls, state: dict) -> "AlertGate":
        """Le `state.json` de forma tolerante (valores invalidos sao ignorados)."""
        muted = state.get(MUTE_KEY)
        raw_until = state.get(SNOOZE_KEY)
        try:
            until = float(raw_until) if raw_until is not None else 0.0
        except (TypeError, ValueError):
            until = 0.0
        return cls(snooze_until=until, muted=bool(muted))

    def to_state_fields(self) -> dict[str, float | bool]:
        with self._lock:
            return {MUTE_KEY: self._muted, SNOOZE_KEY: self._snooze_until}


def load_gate() -> AlertGate:
    from screen_watch.platform.paths import load_state  # noqa: PLC0415

    return AlertGate.from_state(load_state())


def persist_gate(gate: AlertGate) -> None:
    """Grava o estado do gate em `state.json` (best-effort, sem backup)."""
    from screen_watch.platform.paths import update_state  # noqa: PLC0415

    update_state(**gate.to_state_fields())
