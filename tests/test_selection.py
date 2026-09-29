from __future__ import annotations

import pytest

from screen_watch.config.schema import AlertOptions
from screen_watch.persistence.selection import (
    Selection,
    dump_selection,
    load_selection,
    to_target_config,
)


def test_round_trip(tmp_path):
    selection = Selection(
        window_handle=123456,
        origin_at_selection=(100, 200),
        roi_relative=(120, 340, 400, 80),
        window_title_hint="ERP - Estoque",
        mode="default",
        masks=((1, 2, 3, 4),),
    )
    path = tmp_path / "selection.json"
    dump_selection(path, selection)
    loaded = load_selection(path)
    assert loaded == selection


def test_defaults_applied(tmp_path):
    path = tmp_path / "selection.json"
    path.write_text(
        '{"version": 1, "window_handle": 9, "origin_at_selection": [0, 0],'
        ' "roi_relative": [1, 2, 3, 4]}',
        encoding="utf-8",
    )
    loaded = load_selection(path)
    assert loaded.mode == "advanced"
    assert loaded.masks == ()
    assert loaded.window_title_hint == ""


def test_missing_required_field_raises(tmp_path):
    path = tmp_path / "selection.json"
    path.write_text('{"version": 1, "window_handle": 9}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_selection(path)


def test_unsupported_version_raises(tmp_path):
    path = tmp_path / "selection.json"
    path.write_text(
        '{"version": 99, "window_handle": 9, "origin_at_selection": [0, 0],'
        ' "roi_relative": [1, 2, 3, 4]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_selection(path)


def test_to_target_config_maps_selection_fields():
    selection = Selection(
        window_handle=4242,
        origin_at_selection=(10, 20),
        roi_relative=(1, 2, 30, 40),
        window_title_hint="janela",
        mode="advanced",
        masks=((5, 5, 10, 10),),
    )
    alerts = (AlertOptions(type="log"),)

    target = to_target_config(
        selection, name="demo", alerts=alerts, poll_interval_s=3.0, rearm=False
    )

    assert target.name == "demo"
    assert target.window_handle == 4242
    assert target.roi_relative == (1, 2, 30, 40)
    assert target.origin_at_selection == (10, 20)
    assert target.window_title_hint == "janela"
    assert target.mode == "advanced"
    assert target.masks == ((5, 5, 10, 10),)
    assert target.alerts == alerts
    assert target.poll_interval_s == 3.0
    assert target.rearm is False
    assert target.compare_options.advanced.lang == "por+eng"


def test_to_target_config_mode_override():
    selection = Selection(
        window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4), mode="light"
    )
    assert to_target_config(selection, name="x", mode="advanced").mode == "advanced"


def test_selection_app_name_round_trips(tmp_path):
    path = tmp_path / "s.json"
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        window_title_hint="WhatsApp Beta",
        app_name="WhatsApp",
        mode="light",
    )
    dump_selection(path, selection)

    loaded = load_selection(path)
    assert loaded.app_name == "WhatsApp"
    assert loaded.window_title_hint == "WhatsApp Beta"
    assert loaded.mode == "light"


def test_selection_without_app_name_defaults_empty(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(
        '{"version": 1, "window_handle": 9, "origin_at_selection": [0, 0],'
        ' "roi_relative": [1, 2, 3, 4]}',
        encoding="utf-8",
    )
    loaded = load_selection(path)
    assert loaded.app_name == ""
    assert loaded.mode == "advanced"
