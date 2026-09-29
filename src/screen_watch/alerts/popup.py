"""Popup local via `plyer.notification` (doc, secao 11.2).

Fallbacks documentados (nao implementados no prototipo): `windows-toasts` (Windows),
`pync` (macOS), `notify-send` via DBus (Linux).
"""

from __future__ import annotations

import logging

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult

log = logging.getLogger(__name__)


class PopupNotifier:
    name = "popup"

    def __init__(
        self,
        *,
        enabled: bool = True,
        severity_min: int = 1,
        cooldown_s: float = 30.0,
        title: str = "Screen Diff Watcher",
    ) -> None:
        self.enabled = bool(enabled)
        self.severity_min = int(severity_min)
        self.cooldown_s = float(cooldown_s)
        self.title = title

    def notify(self, result: ComparisonResult, frame: Frame) -> None:
        try:
            from plyer import notification  # noqa: PLC0415
        except Exception as exc:  # pragma: no cover - depende do ambiente
            log.warning("plyer indisponivel, popup desabilitado: %s", exc)
            return
        message = f"{result.strategy}: mudanca (score={result.score:.2f})"
        notification.notify(title=self.title, message=message, timeout=5)
