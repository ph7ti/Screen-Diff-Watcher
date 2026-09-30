"""Auditoria de acoes em JSON Lines (plano, F2-T8).

Ensaio e execucao armada gravam a mesma estrutura; falhas ao gravar apenas logam.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from screen_watch.platform.paths import actions_log_path

log = logging.getLogger(__name__)


class ActionAudit:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else actions_log_path()

    def record(self, payload: dict) -> None:
        record = {"ts": time.time(), **payload}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:  # pragma: no cover - depende do disco
            log.error("could not write the action audit to %s: %s", self.path, exc)
