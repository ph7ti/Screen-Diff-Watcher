"""Notificador de log em JSON Lines (plano, §4/P7 e Etapa A.9).

Cada alerta vira uma linha JSON com o desfecho e o retangulo capturado, para
auditar falsos positivos e o disparo deterministico do `test-alert`.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult

log = logging.getLogger(__name__)


def default_log_path() -> Path:
    from screen_watch.platform.paths import logs_dir  # noqa: PLC0415

    return logs_dir() / "alerts.jsonl"


class JsonlNotifier:
    name = "log"

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        enabled: bool = True,
        severity_min: int = 1,
        cooldown_s: float = 0.0,
    ) -> None:
        self.path = Path(path) if path else default_log_path()
        self.enabled = bool(enabled)
        self.severity_min = int(severity_min)
        self.cooldown_s = float(cooldown_s)

    def notify(self, result: ComparisonResult, frame: Frame) -> None:
        record = {
            "ts": time.time(),
            "strategy": result.strategy,
            "changed": result.changed,
            "score": result.score,
            "threshold": result.threshold,
            "severity": result.severity,
            "window_handle": frame.window_handle,
            "absolute_rect": list(frame.absolute_rect),
            "sequence": frame.sequence,
            "detail": result.detail,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:  # pragma: no cover - depende do disco
            log.error("nao foi possivel escrever o log jsonl em %s: %s", self.path, exc)
