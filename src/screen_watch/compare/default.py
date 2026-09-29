"""Estrategia Default — hash perceptual phash (doc, secao 10.3)."""

from __future__ import annotations

import imagehash
from PIL import Image

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult


class PerceptualHashStrategy:
    name = "default"

    def __init__(self, hash_size: int = 8, threshold: int = 6) -> None:
        self.hash_size = int(hash_size)
        self.threshold = float(threshold)
        self._baseline_hash: imagehash.ImageHash | None = None

    def initialize(self, baseline: Frame) -> None:
        img = Image.fromarray(baseline.rgb)
        self._baseline_hash = imagehash.phash(img, hash_size=self.hash_size)

    def compare(self, current: Frame) -> ComparisonResult:
        if self._baseline_hash is None:
            raise RuntimeError("initialize() deve ser chamado com o baseline antes de compare()")
        img = Image.fromarray(current.rgb)
        current_hash = imagehash.phash(img, hash_size=self.hash_size)
        dist = float(self._baseline_hash - current_hash)
        return ComparisonResult(
            changed=dist > self.threshold,
            score=dist,
            threshold=self.threshold,
            strategy=self.name,
        )
