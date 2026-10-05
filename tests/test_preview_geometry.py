from __future__ import annotations

import numpy as np

from screen_watch.gui.preview_geometry import downsample


def test_downsample_small_frame_is_copied_unchanged():
    rgb = np.zeros((10, 20, 3), dtype=np.uint8)
    out = downsample(rgb, 240)
    assert out.shape == (10, 20, 3)
    assert out is not rgb
    out[0, 0, 0] = 255
    assert rgb[0, 0, 0] == 0


def test_downsample_limits_the_longest_side():
    rgb = np.zeros((1080, 1920, 3), dtype=np.uint8)
    out = downsample(rgb, 240)
    assert max(out.shape[:2]) <= 240
    assert out.shape[2] == 3


def test_downsample_landscape_and_portrait_steps():
    landscape = downsample(np.zeros((100, 1000, 3), dtype=np.uint8), 100)
    portrait = downsample(np.zeros((1000, 100, 3), dtype=np.uint8), 100)
    assert landscape.shape[:2] == (10, 100)
    assert portrait.shape[:2] == (100, 10)


def test_downsample_preserves_pixel_values_on_grid():
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    rgb[2, 2] = (10, 20, 30)
    out = downsample(rgb, 2)
    assert out.shape == (2, 2, 3)
    assert tuple(out[1, 1]) == (10, 20, 30)
