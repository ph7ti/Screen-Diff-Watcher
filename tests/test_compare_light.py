from __future__ import annotations

import numpy as np

from screen_watch.compare.light import MeanColorStrategy


def test_identical_frames_are_not_changed(make_frame, solid):
    strategy = MeanColorStrategy(threshold=12.0)
    strategy.initialize(make_frame(solid(100)))
    result = strategy.compare(make_frame(solid(100)))
    assert result.changed is False
    assert result.score == 0.0
    assert result.strategy == "light"


def test_dramatic_change_is_detected(make_frame, solid):
    strategy = MeanColorStrategy(threshold=12.0)
    strategy.initialize(make_frame(solid(100)))
    result = strategy.compare(make_frame(solid(200)))
    assert result.changed is True
    assert result.score > 12.0


def test_mean_ignores_layout_of_uniform_frame(make_frame, solid):
    strategy = MeanColorStrategy(threshold=1.0)
    noise = np.zeros((32, 40, 3), dtype=np.uint8)
    noise[:16, :, :] = 100
    strategy.initialize(make_frame(noise))
    assert strategy.compare(make_frame(noise)).changed is False
