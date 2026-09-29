from __future__ import annotations

from screen_watch.capture.geometry import intersect_rect


def test_rect_fully_inside():
    assert intersect_rect((5, 5, 5, 5), (0, 0, 20, 20)) == (5, 5, 5, 5)


def test_partial_intersection_is_clipped():
    assert intersect_rect((10, 10, 10, 10), (0, 0, 15, 15)) == (10, 10, 5, 5)


def test_negative_origin_is_clipped():
    assert intersect_rect((-10, -10, 15, 15), (0, 0, 20, 20)) == (0, 0, 5, 5)


def test_disjoint_returns_none():
    assert intersect_rect((100, 100, 5, 5), (0, 0, 20, 20)) is None


def test_touching_edges_returns_none():
    assert intersect_rect((20, 0, 5, 5), (0, 0, 20, 20)) is None
