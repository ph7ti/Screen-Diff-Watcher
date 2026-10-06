"""Gerenciador de N sessoes de monitoramento (doc, secao 3.5/3.7/16, v0.9.0).

Cada sessao tem seu proprio `MonitorSession` + `MonitorLoop` (thread e backend
`mss` isolados por thread) e buffers de preview/calibracao com os mesmos limites
da v0.8. O gate de snooze/mute e **compartilhado** por todas as sessoes.

A fila de eventos carrega `session` (nome da selecao) em `started`/`stopped`/
`result`/`event`/`error`/`action_event`, para a GUI separar as linhas de log e o
status agregado. Nenhum widget e tocado daqui: a GUI consome a fila com `QTimer`.
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from screen_watch.alerts.chain import DispatchOutcome
from screen_watch.alerts.gate import AlertGate, persist_gate
from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import TargetConfig
from screen_watch.errors import AppError

if TYPE_CHECKING:
    import numpy as np

PREVIEW_MAX_SIDE = 240
CALIBRATION_MAX = 600
DEFAULT_MAX_SESSIONS = 4

# (ts, strategy, score, threshold, severity)
CalibrationSample = tuple[float, str, float, float, int]
PreviewFrames = tuple["np.ndarray | None", "np.ndarray | None"]


@dataclass
class _ManagedSession:
    target: TargetConfig
    session: object
    loop: object
    preview_lock: threading.Lock = field(default_factory=threading.Lock)
    preview_latest: "np.ndarray | None" = None
    preview_baseline: "np.ndarray | None" = None
    calibration_lock: threading.Lock = field(default_factory=threading.Lock)
    calibration: deque[CalibrationSample] = field(
        default_factory=lambda: deque(maxlen=CALIBRATION_MAX)
    )


class SessionManager:
    def __init__(
        self,
        events: "queue.Queue[dict]",
        *,
        gate: AlertGate | None = None,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        session_factory: Callable[..., object] | None = None,
        loop_factory: Callable[..., object] | None = None,
    ) -> None:
        self.events = events
        # Gate de snooze/mute (doc, secao 11.3): unico para todas as sessoes e
        # persistido em state.json a cada mudanca feita pela GUI/tray.
        self.gate = gate if gate is not None else AlertGate()
        self.max_sessions = max(1, int(max_sessions))
        self._session_factory = session_factory
        self._loop_factory = loop_factory
        self._sessions: dict[str, _ManagedSession] = {}
        self._order: list[str] = []

    # -- consulta ----------------------------------------------------------
    def set_max_sessions(self, value: int) -> None:
        """Ajusta o limite depois que a config foi carregada pela janela."""
        self.max_sessions = max(1, int(value))

    @property
    def running(self) -> bool:
        return any(self._is_alive(item.loop) for item in self._sessions.values())

    def names(self) -> list[str]:
        return [name for name in self._order if name in self._sessions]

    def is_running(self, name: str) -> bool:
        item = self._sessions.get(name)
        return item is not None and self._is_alive(item.loop)

    def actions(self, name: str | None = None):
        item = self._managed(name)
        return getattr(item.session, "actions", None) if item is not None else None

    def escalating(self, name: str | None = None) -> bool:
        if name is not None:
            item = self._sessions.get(name)
            return bool(item is not None and getattr(item.session, "awaiting_ack", False))
        return any(
            bool(getattr(item.session, "awaiting_ack", False))
            for item in self._sessions.values()
        )

    # -- preview/calibracao (lidos pela GUI thread) ------------------------
    def preview(self, name: str | None = None) -> PreviewFrames:
        item = self._managed(name)
        if item is None:
            return None, None
        with item.preview_lock:
            return item.preview_latest, item.preview_baseline

    def clear_preview(self, name: str | None = None) -> None:
        item = self._managed(name)
        if item is None:
            return
        with item.preview_lock:
            item.preview_latest = None
            item.preview_baseline = None

    def calibration(self, name: str | None = None) -> list[CalibrationSample]:
        item = self._managed(name)
        if item is None:
            return []
        with item.calibration_lock:
            return list(item.calibration)

    # -- snooze/mute/escalation (doc, secao 11.3) --------------------------
    def snooze(self, minutes: float) -> None:
        self.gate.snooze(minutes)
        self._persist_gate()

    def mute(self) -> None:
        self.gate.mute()
        self._persist_gate()

    def unmute(self) -> None:
        self.gate.unmute()
        self._persist_gate()

    def acknowledge(self, name: str | None = None) -> None:
        for item in self._affected(name):
            item.session.acknowledge()

    def rebaseline(self, name: str | None = None) -> None:
        for item in self._affected(name):
            item.session.request_rebaseline()

    def gate_status(self) -> str | None:
        return self.gate.status()

    def gate_remaining_s(self) -> float:
        return self.gate.snooze_remaining_s()

    def _persist_gate(self) -> None:
        try:
            persist_gate(self.gate)
        except OSError:
            pass

    # -- ciclo de vida -----------------------------------------------------
    def start(self, target: TargetConfig, recorder: object | None = None) -> str:
        name = target.name
        if self.is_running(name):
            raise AppError(code="runtime.session_already_running", params={"name": name})
        if len(self._sessions) >= self.max_sessions:
            raise AppError(
                code="runtime.session_limit",
                params={"max": self.max_sessions, "name": name},
            )

        session = self._build_session(target, name=name, recorder=recorder)
        loop = self._build_loop(target, session, name=name)
        self._sessions[name] = _ManagedSession(target=target, session=session, loop=loop)
        if name in self._order:
            self._order.remove(name)
        self._order.append(name)
        self.events.put({"kind": "started", "session": name, "target": target.label or name})
        loop.start()
        return name

    def stop(self, name: str | None = None, timeout: float = 5.0) -> None:
        for key in ([name] if name is not None else list(self._sessions)):
            item = self._sessions.pop(key, None)
            if item is None:
                continue
            if key in self._order:
                self._order.remove(key)
            item.loop.stop(timeout=timeout)
            with item.preview_lock:
                item.preview_latest = None
                item.preview_baseline = None
            with item.calibration_lock:
                item.calibration.clear()
            self.events.put({"kind": "stopped", "session": key})

    def stop_all(self, timeout: float = 5.0) -> None:
        self.stop(None, timeout=timeout)

    # -- interno -----------------------------------------------------------
    def _affected(self, name: str | None) -> list[_ManagedSession]:
        if name is not None:
            item = self._sessions.get(name)
            return [item] if item is not None else []
        return list(self._sessions.values())

    def _managed(self, name: str | None) -> _ManagedSession | None:
        """Item pedido; sem nome, a ultima sessao ativa (foco da GUI)."""
        if name is not None:
            return self._sessions.get(name)
        for key in reversed(self._order):
            if key in self._sessions:
                return self._sessions[key]
        return None

    @staticmethod
    def _is_alive(loop: object) -> bool:
        return bool(getattr(loop, "running", False))

    def _build_session(self, target: TargetConfig, *, name: str, recorder: object | None):
        if self._session_factory is not None:
            return self._session_factory(
                target,
                name=name,
                recorder=recorder,
                gate=self.gate,
                on_result=lambda result, outcome: self._on_result(name, result, outcome),
                on_action=lambda payload: self._on_action(name, payload),
                on_frame=lambda frame, baseline: self._on_frame(name, frame, baseline),
                on_compare=lambda result: self._on_compare(name, result),
            )
        from screen_watch.app import MonitorSession  # noqa: PLC0415

        return MonitorSession(
            target,
            on_result=lambda result, outcome: self._on_result(name, result, outcome),
            recorder=recorder,
            on_action=lambda payload: self._on_action(name, payload),
            on_frame=lambda frame, baseline: self._on_frame(name, frame, baseline),
            on_compare=lambda result: self._on_compare(name, result),
            gate=self.gate,
        )

    def _build_loop(self, target: TargetConfig, session: object, *, name: str):
        if self._loop_factory is not None:
            return self._loop_factory(
                target,
                session,
                name=name,
                on_event=lambda event, payload: self._on_event(name, event, payload),
                on_error=lambda exc: self._on_error(name, exc),
            )
        from screen_watch.app import build_loop  # noqa: PLC0415

        return build_loop(
            target,
            session,
            on_event=lambda event, payload: self._on_event(name, event, payload),
            on_error=lambda exc: self._on_error(name, exc),
        )

    # -- callbacks (rodam na thread do loop) -------------------------------
    def _on_frame(self, name: str, frame: Frame, is_baseline: bool) -> None:
        from screen_watch.gui.preview_geometry import downsample  # noqa: PLC0415

        item = self._sessions.get(name)
        if item is None:
            return
        thumbnail = downsample(frame.rgb, PREVIEW_MAX_SIDE)
        with item.preview_lock:
            item.preview_latest = thumbnail
            if is_baseline:
                item.preview_baseline = thumbnail

    def _on_compare(self, name: str, result: ComparisonResult) -> None:
        item = self._sessions.get(name)
        if item is None:
            return
        with item.calibration_lock:
            item.calibration.append(
                (
                    time.time(),
                    result.strategy,
                    float(result.score),
                    float(result.threshold),
                    int(result.severity),
                )
            )

    def _on_result(
        self, name: str, result: ComparisonResult, outcome: DispatchOutcome
    ) -> None:
        self.events.put(
            {
                "kind": "result",
                "session": name,
                "strategy": result.strategy,
                "score": result.score,
                "severity": result.severity,
                "outcome": outcome.value,
                "escalating": self.escalating(name),
            }
        )

    def _on_event(self, name: str, event: str, payload: dict) -> None:
        self.events.put({"kind": "event", "name": event, "payload": payload, "session": name})

    def _on_action(self, name: str, payload: dict) -> None:
        self.events.put({"kind": "action_event", "payload": payload, "session": name})

    def _on_error(self, name: str, exc: Exception) -> None:
        self.events.put({"kind": "error", "message": str(exc), "session": name})


def new_event_queue() -> "queue.Queue[dict]":
    return queue.Queue()
