from __future__ import annotations

import numpy as np
import pytest

imagehash = pytest.importorskip("imagehash")
pytest.importorskip("PIL")

from screen_watch.compare.default import PerceptualHashStrategy  # noqa: E402


def gradient(offset: int) -> np.ndarray:
    base = np.linspace(0, 255, 64, dtype=np.float32)
    image = np.tile(base, (64, 1))
    image = np.clip(image + offset, 0, 255)
    return np.dstack([image, image, image]).astype(np.uint8)


def test_identical_frames_are_not_changed(make_frame):
    strategy = PerceptualHashStrategy(hash_size=8, threshold=6)
    frame = make_frame(gradient(0))
    strategy.initialize(frame)
    result = strategy.compare(frame)
    assert result.changed is False
    assert result.score == 0.0


def test_structural_change_is_detected(make_frame):
    strategy = PerceptualHashStrategy(hash_size=8, threshold=6)
    baseline = make_frame(np.zeros((64, 64, 3), dtype=np.uint8))
    strategy.initialize(baseline)
    checker = np.zeros((64, 64, 3), dtype=np.uint8)
    checker[::8, :] = 255
    checker[:, ::8] = 255
    result = strategy.compare(make_frame(checker))
    assert result.changed is True
    assert result.score > 6
