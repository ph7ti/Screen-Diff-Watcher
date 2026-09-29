from __future__ import annotations

import numpy as np

from screen_watch.capture.mask import apply_mask


def test_masked_region_becomes_black():
    rgb = np.full((20, 20, 3), 255, dtype=np.uint8)
    out = apply_mask(rgb, [(5, 5, 10, 10)])
    assert np.all(out[5:15, 5:15] == 0)
    assert np.all(out[0:5, 0:5] == 255)


def test_mask_clamps_out_of_bounds():
    rgb = np.full((10, 10, 3), 255, dtype=np.uint8)
    out = apply_mask(rgb, [(-5, -5, 8, 8)])
    assert np.all(out[0:3, 0:3] == 0)
    assert out.shape == rgb.shape


def test_empty_mask_returns_equal_copy():
    rgb = np.full((4, 4, 3), 7, dtype=np.uint8)
    out = apply_mask(rgb, [])
    assert np.array_equal(out, rgb)
    assert out is not rgb
