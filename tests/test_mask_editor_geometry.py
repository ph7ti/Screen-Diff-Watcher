from __future__ import annotations

from screen_watch.gui.mask_editor_geometry import (
    clamp_mask_to_roi,
    hit_test_masks,
    mask_from_drag,
    mask_local_logical,
    point_in_roi,
    remove_mask_at,
    roi_global_physical,
    roi_local_logical,
    to_global_physical,
)


def test_to_global_physical_anchors_at_screen_origin():
    assert to_global_physical(
        (150, 250), screen_origin=(100, 100), device_pixel_ratio=1.0
    ) == (150, 250)
    assert to_global_physical(
        (150, 250), screen_origin=(100, 100), device_pixel_ratio=2.0
    ) == (200, 400)


def test_roi_global_physical_is_window_plus_relative():
    window = (1000, 500, 800, 600)
    roi = (20, 30, 200, 40)
    assert roi_global_physical(window, roi) == (1020, 530, 200, 40)


def test_roi_local_logical_inverts_physical_for_dpr_one():
    roi = roi_local_logical((1020, 530, 200, 40), screen_origin=(1000, 500), device_pixel_ratio=1.0)
    assert roi == (20, 30, 200, 40)


def test_roi_local_logical_scales_for_dpr():
    roi = roi_local_logical((1250, 750, 250, 50), screen_origin=(1000, 500), device_pixel_ratio=1.25)
    assert roi == (200, 200, 200, 40)


def test_mask_from_drag_relative_to_roi_dpr_one():
    mask = mask_from_drag(
        (40, 60),
        (140, 100),
        screen_origin=(0, 0),
        device_pixel_ratio=1.0,
        roi_global=(20, 30, 300, 300),
    )
    assert mask == (20, 30, 100, 40)


def test_mask_from_drag_normalizes_reversed_corners():
    forward = mask_from_drag(
        (40, 60), (140, 100), screen_origin=(0, 0), device_pixel_ratio=1.0, roi_global=(0, 0, 300, 300)
    )
    backward = mask_from_drag(
        (140, 100), (40, 60), screen_origin=(0, 0), device_pixel_ratio=1.0, roi_global=(0, 0, 300, 300)
    )
    assert forward == backward == (40, 60, 100, 40)


def test_mask_from_drag_scales_by_dpr():
    mask = mask_from_drag(
        (20, 20),
        (60, 40),
        screen_origin=(0, 0),
        device_pixel_ratio=1.5,
        roi_global=(0, 0, 300, 300),
    )
    assert mask == (30, 30, 60, 30)


def test_clamp_mask_to_roi_keeps_fully_inside_mask():
    assert clamp_mask_to_roi((10, 10, 50, 40), (200, 100)) == (10, 10, 50, 40)


def test_clamp_mask_to_roi_intersects_partial_overlap():
    assert clamp_mask_to_roi((-10, -10, 50, 50), (200, 100)) == (0, 0, 40, 40)


def test_clamp_mask_to_roi_rejects_outside_or_too_small():
    assert clamp_mask_to_roi((-50, -50, 20, 20), (200, 100)) is None
    assert clamp_mask_to_roi((10, 10, 3, 40), (200, 100)) is None


def test_hit_test_prefers_topmost_and_detects_miss():
    masks = ((0, 0, 100, 100), (20, 20, 50, 50))
    assert hit_test_masks(masks, (30, 30)) == 1
    assert hit_test_masks(masks, (5, 5)) == 0
    assert hit_test_masks(masks, (500, 500)) is None


def test_remove_mask_at_drops_only_the_index():
    masks = ((0, 0, 10, 10), (20, 20, 10, 10))
    assert remove_mask_at(masks, 0) == ((20, 20, 10, 10),)
    assert remove_mask_at(masks, 9) == masks


def test_mask_local_logical_maps_back_for_painting():
    local = mask_local_logical((30, 30, 60, 30), (20, 40, 200, 100), 1.5)
    assert local == (40, 60, 40, 20)


def test_point_in_roi():
    assert point_in_roi((0, 0), (200, 100))
    assert point_in_roi((199, 99), (200, 100))
    assert not point_in_roi((200, 99), (200, 100))
    assert not point_in_roi((-1, 0), (200, 100))
