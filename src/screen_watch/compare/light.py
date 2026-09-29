"""Estrategia Leve — cor media RGB + distancia euclidiana (doc, secao 10.2)."""

from __future__ import annotations

import numpy as np

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult


class MeanColorStrategy:
    name = "light"

    def __init__(self, threshold: float = 12.0) -> None:
        self.threshold = float(threshold)
        self._baseline_mean: np.ndarray | None = None

    def initialize(self, baseline: Frame) -> None:
        self._baseline_mean = baseline.rgb.mean(axis=(0, 1))

    def compare(self, current: Frame) -> ComparisonResult:
        if self._baseline_mean is None:
            raise RuntimeError("initialize() deve ser chamado com o baseline antes de compare()")
        current_mean = current.rgb.mean(axis=(0, 1))
        delta = float(np.linalg.norm(current_mean - self._baseline_mean))
        return ComparisonResult(
            changed=delta > self.threshold,
            score=delta,
            threshold=self.threshold,
            strategy=self.name,
        )
