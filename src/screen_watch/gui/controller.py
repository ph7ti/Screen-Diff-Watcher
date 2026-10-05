"""Controlador de monitoramento para a GUI (doc P3/P10).

O loop roda em thread separada; eventos e resultados sao publicados numa
`queue.Queue` que a GUI consome com `QTimer`. Nunca se toca em widget a partir
do callback do loop: o preview e o ring buffer de calibracao sao copias
pequenas/limitadas, protegidas por lock, e a GUI monta o `QImage` na propria
thread (doc, secao 3.7).
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from typing import TYPE_CHECKING

from screen_watch.alerts.chain import DispatchOutcome
from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import TargetConfig

if TYPE_CHECKING:
    import numpy as np

PREVIEW_MAX_SIDE = 240
CALIBRATION_MAX = 600

# (ts, strategy, score, threshold, severity)
CalibrationSample = tuple[float, str, float, float, int]
PreviewFrames = tuple["np.ndarray | None", "np.ndarray | None"]


class MonitorController:
    def __init__(self, events: "queue.Queue[dict]") -> None:
        self.events = events
        self._session = None
        self._loop = None
        self._preview_lock = threading.Lock()
        self._preview_latest: "np.ndarray | None" = None
        self._preview_baseline: "np.ndarray | None" = None
        self._calibration_lock = threading.Lock()
        self._calibration: deque[CalibrationSample] = deque(maxlen=CALIBRATION_MAX)

    @property
    def running(self) -> bool:
        return self._loop is not None and self._loop.running

    @property
    def actions(self):
        return getattr(self._session, "actions", None)

    def rebaseline(self) -> None:
        if self._session is not None:
            self._session.request_rebaseline()

    def start(self, target: TargetConfig, recorder: object | None = None) -> None:
        if self.running:
            from screen_watch.errors import AppError  # noqa: PLC0415

            raise AppError(code="runtime.already_running")
        from screen_watch.app import MonitorSession, build_loop  # noqa: PLC0415

        self._session = MonitorSession(
            target,
            on_result=self._on_result,
            recorder=recorder,
            on_action=self._on_action,
            on_frame=self._on_frame,
            on_compare=self._on_compare,
        )
        self._loop = build_loop(
            target, self._session, on_event=self._on_event, on_error=self._on_error
        )
        self.events.put({"kind": "started", "target": target.label or target.name})
        self._loop.start()

    def stop(self, timeout: float = 5.0) -> None:
        loop = self._loop
        if loop is None:
            return
        self._loop = None
        self._session = None
        loop.stop(timeout=timeout)
        self.clear_preview()
        with self._calibration_lock:
            self._calibration.clear()
        self.events.put({"kind": "stopped"})

    # -- preview/calibracao (lidos pela GUI thread) -------------------------
    def preview(self) -> PreviewFrames:
        with self._preview_lock:
            return self._preview_latest, self._preview_baseline

    def clear_preview(self) -> None:
        with self._preview_lock:
            self._preview_latest = None
            self._preview_baseline = None

    def calibration(self) -> list[CalibrationSample]:
        with self._calibration_lock:
            return list(self._calibration)

    # -- callbacks (rodam na thread do loop) -------------------------------
    def _on_frame(self, frame: Frame, is_baseline: bool) -> None:
        from screen_watch.gui.preview_geometry import downsample  # noqa: PLC0415

        thumbnail = downsample(frame.rgb, PREVIEW_MAX_SIDE)
        with self._preview_lock:
            self._preview_latest = thumbnail
            if is_baseline:
                self._preview_baseline = thumbnail

    def _on_compare(self, result: ComparisonResult) -> None:
        with self._calibration_lock:
            self._calibration.append(
                (
                    time.time(),
                    result.strategy,
                    float(result.score),
                    float(result.threshold),
                    int(result.severity),
                )
            )

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

    def _on_action(self, payload: dict) -> None:
        # `action_event` e proprio das acoes; `kind == "action"` sao comandos de
        # tray/hotkey (evita eco/loop entre os dois canais).
        self.events.put({"kind": "action_event", "payload": payload})

    def _on_error(self, exc: Exception) -> None:
        self.events.put({"kind": "error", "message": str(exc)})


def new_event_queue() -> "queue.Queue[dict]":
    return queue.Queue()
