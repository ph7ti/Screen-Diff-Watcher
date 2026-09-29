"""Controlador de monitoramento para a GUI (doc P3/P10).

O loop roda em thread separada; eventos e resultados sao publicados numa
`queue.Queue` que a GUI consome com `QTimer`. Nunca se toca em widget a partir
do callback do loop.
"""

from __future__ import annotations

import queue

from screen_watch.alerts.chain import DispatchOutcome
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import TargetConfig


class MonitorController:
    def __init__(self, events: "queue.Queue[dict]") -> None:
        self.events = events
        self._session = None
        self._loop = None

    @property
    def running(self) -> bool:
        return self._loop is not None and self._loop.running

    def start(self, target: TargetConfig) -> None:
        if self.running:
            raise RuntimeError("ja existe um target em execucao")
        from screen_watch.app import MonitorSession, build_loop  # noqa: PLC0415

        self._session = MonitorSession(target, on_result=self._on_result)
        self._loop = build_loop(
            target, self._session, on_event=self._on_event, on_error=self._on_error
        )
        self.events.put({"kind": "started", "target": target.name})
        self._loop.start()

    def stop(self, timeout: float = 5.0) -> None:
        loop = self._loop
        if loop is None:
            return
        self._loop = None
        self._session = None
        loop.stop(timeout=timeout)
        self.events.put({"kind": "stopped"})

    # -- callbacks (rodam na thread do loop) -------------------------------
    def _on_result(self, result: ComparisonResult, outcome: DispatchOutcome) -> None:
        self.events.put(
            {
                "kind": "result",
                "strategy": result.strategy,
                "score": result.score,
                "severity": result.severity,
                "outcome": outcome.value,
            }
        )

    def _on_event(self, name: str, payload: dict) -> None:
        self.events.put({"kind": "event", "name": name, "payload": payload})

    def _on_error(self, exc: Exception) -> None:
        self.events.put({"kind": "error", "message": str(exc)})


def new_event_queue() -> "queue.Queue[dict]":
    return queue.Queue()
