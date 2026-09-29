"""Protocolo de notificador (doc, secao 11.1)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult


@runtime_checkable
class Notifier(Protocol):
    name: str
    enabled: bool
    severity_min: int
    cooldown_s: float

    def notify(self, result: ComparisonResult, frame: Frame) -> None: ...
