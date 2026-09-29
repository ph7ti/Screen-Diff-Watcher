from __future__ import annotations

from screen_watch.gui.overlay_geometry import (
    fits_in_window,
    global_from_local,
    is_valid_selection,
    local_from_global,
    normalize_corners,
    resolve_ref_point,
    to_physical,
    to_relative,
)


def test_normalize_corners_orders_points():
    assert normalize_corners((30, 40), (10, 5)) == (10, 5, 20, 35)


def test_global_local_round_trip():
    origin = (100, 200)
    local = (5, 6, 30, 40)
    g = global_from_local(local, origin)
    assert g == (105, 206, 30, 40)
    assert local_from_global(g, origin) == local


def test_to_physical_identity_at_100_percent():
    assert to_physical((10, 20, 30, 40), screen_origin=(0, 0), device_pixel_ratio=1.0) == (
        10,
        20,
        30,
        40,
    )


def test_to_physical_scales_size_at_125_percent():
    # Usa int() (truncamento), como o doc 9.5.
    assert to_physical((10, 20, 30, 40), screen_origin=(0, 0), device_pixel_ratio=1.25) == (
        12,
        25,
        37,
        50,
    )


def test_to_physical_anchors_on_screen_origin():
    physical = to_physical(
        (1920, 428, 100, 50), screen_origin=(1920, 428), device_pixel_ratio=1.0
    )
    assert physical == (1920, 428, 100, 50)


def test_to_relative_subtracts_window_origin():
    assert to_relative((200, 300, 30, 40), (120, 340)) == (80, -40, 30, 40)


def test_is_valid_selection_min_side():
    assert is_valid_selection((0, 0, 10, 10)) is True
    assert is_valid_selection((0, 0, 9, 10)) is False


def test_fits_in_window():
    assert fits_in_window((0, 0, 10, 10), (100, 100)) is True
    assert fits_in_window((95, 0, 10, 10), (100, 100)) is False
    assert fits_in_window((-1, 0, 10, 10), (100, 100)) is False


def test_resolve_ref_point_roi_and_window():
    roi = (100, 50, 400, 80)
    window = (0, 0, 800, 600)

    assert resolve_ref_point((110, 60), "roi", roi_rect=roi, window_rect=window) == (
        "roi",
        (10, 10),
    )
    assert resolve_ref_point((10, 10), "window", roi_rect=roi, window_rect=window) == (
        "window",
        (10, 10),
    )
    assert resolve_ref_point((5, 7), "screen", roi_rect=roi, window_rect=window) == (
        "screen",
        (5, 7),
    )


def test_resolve_ref_point_falls_back_to_screen_without_base():
    assert resolve_ref_point((5, 7), "roi") == ("screen", (5, 7))
    assert resolve_ref_point((5, 7), "window", roi_rect=(1, 2, 3, 4)) == ("screen", (5, 7))


def test_primary_screen_matches_doc_formula():
    # Para a tela primaria (origem 0,0) a conversao ancorada equivale a `x * dpr`.
    rect = (100, 50, 20, 10)
    anchored = to_physical(rect, screen_origin=(0, 0), device_pixel_ratio=1.25)
    doc = (int(100 * 1.25), int(50 * 1.25), int(20 * 1.25), int(10 * 1.25))
    assert anchored == doc
