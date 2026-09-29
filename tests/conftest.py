from __future__ import annotations

import numpy as np
import pytest

from screen_watch.capture.frame import Frame


@pytest.fixture
def make_frame():
    def _make(
        rgb: np.ndarray,
        *,
        sequence: int = 0,
        rect: tuple[int, int, int, int] = (0, 0, 0, 0),
        handle: int = 1,
    ) -> Frame:
        return Frame(
            rgb=rgb,
            timestamp=0.0,
            absolute_rect=rect,
            window_rect=rect,
            window_handle=handle,
            sequence=sequence,
        )

    return _make


@pytest.fixture
def solid():
    def _solid(value: int, shape: tuple[int, int, int] = (64, 64, 3)) -> np.ndarray:
        return np.full(shape, value, dtype=np.uint8)

    return _solid
