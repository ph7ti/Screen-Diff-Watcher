from __future__ import annotations

import pytest

from screen_watch.config.schema import (
    AlertOptions,
    CompareOptions,
    GlobalDefaults,
    LightOptions,
    ProfileOptions,
    TargetConfig,
)
from screen_watch.persistence.selection import (
    Selection,
    build_target,
    dump_selection,
    from_target_config,
    load_selection,
    to_target_config,
)


def _profile(**defaults) -> ProfileOptions:
    return ProfileOptions(
        defaults=GlobalDefaults(**defaults),
        alerts=(AlertOptions(type="sound"),),
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
    assert loaded.version == 1
    assert loaded.mode == "advanced"
    assert loaded.masks == ()
    assert loaded.window_title_hint == ""
    assert loaded.overrides is None


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


def test_v1_selection_loads_without_overrides(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(
        '{"version": 1, "window_handle": 9, "origin_at_selection": [0, 0],'
        ' "roi_relative": [1, 2, 3, 4], "mode": "light"}',
        encoding="utf-8",
    )
    loaded = load_selection(path)
    assert loaded.overrides is None
    assert loaded.mode == "light"


def test_overrides_round_trip(tmp_path):
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        overrides={"poll_interval_s": 1.5, "rearm": False, "masks": [[1, 1, 2, 2]]},
    )
    path = tmp_path / "s.json"
    dump_selection(path, selection)
    loaded = load_selection(path)
    assert loaded.overrides == {"poll_interval_s": 1.5, "rearm": False, "masks": [[1, 1, 2, 2]]}


def test_overrides_must_be_object(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        '{"version": 2, "window_handle": 9, "origin_at_selection": [0, 0],'
        ' "roi_relative": [1, 2, 3, 4], "overrides": 3}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_selection(path)


def test_build_target_applies_overrides():
    selection = Selection(
        window_handle=4242,
        origin_at_selection=(10, 20),
        roi_relative=(1, 2, 30, 40),
        window_title_hint="janela",
        mode="light",
        masks=((5, 5, 10, 10),),
        overrides={
            "poll_interval_s": 1.5,
            "rearm": False,
            "alerts": [{"type": "log"}],
        },
    )
    target = build_target(selection, _profile(mode="advanced"), name="demo")

    assert target.name == "demo"
    assert target.window_handle == 4242
    assert target.mode == "light"
    assert target.poll_interval_s == 1.5
    assert target.rearm is False
    assert target.masks == ((5, 5, 10, 10),)
    assert [a.type for a in target.alerts] == ["log"]


def test_build_target_uses_profile_when_no_overrides():
    selection = Selection(
        window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4), mode="advanced"
    )
    target = build_target(selection, _profile(mode="light", poll_interval_s=3.0), name="x")
    assert target.mode == "advanced"
    assert target.poll_interval_s == 3.0
    assert [a.type for a in target.alerts] == ["sound"]


def test_build_target_mode_argument_wins():
    selection = Selection(
        window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4), mode="light"
    )
    assert build_target(selection, _profile(), name="x", mode="default").mode == "default"


def test_build_target_mode_override_wins_over_selection():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        mode="light",
        overrides={"mode": "default"},
    )
    assert build_target(selection, _profile(), name="x").mode == "default"


def test_build_target_rejects_bad_override():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        overrides={"poll_interval_s": 0.1},
    )
    with pytest.raises(ValueError):
        build_target(selection, _profile(), name="x")


def test_build_target_rejects_invalid_mode():
    selection = Selection(
        window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4), mode="turbo"
    )
    with pytest.raises(ValueError):
        build_target(selection, _profile(), name="x")


def test_build_target_keeps_compare_options_from_profile():
    profile = ProfileOptions(
        defaults=GlobalDefaults(compare_options=CompareOptions(light=LightOptions(threshold=3.0)))
    )
    selection = Selection(
        window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4)
    )
    assert build_target(selection, profile, name="x").compare_options.light.threshold == 3.0


def test_build_target_carries_schedule():
    from screen_watch.config.schema import ScheduleOptions

    schedule = ScheduleOptions(enabled=True, days=("mon",), windows=("08:00-12:00",))
    selection = Selection(window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4))
    target = build_target(selection, _profile(), name="x", schedule=schedule)
    assert target.schedule is schedule


def test_from_target_config_copies_fields():
    target = TargetConfig(
        name="painel",
        window_handle=7,
        roi_relative=(1, 2, 3, 4),
        origin_at_selection=(5, 6),
        window_title_hint="ERP",
        mode="default",
        masks=((9, 9, 1, 1),),
    )
    selection = from_target_config(target)
    assert selection.window_handle == 7
    assert selection.origin_at_selection == (5, 6)
    assert selection.roi_relative == (1, 2, 3, 4)
    assert selection.mode == "default"
    assert selection.masks == ((9, 9, 1, 1),)


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
    assert target.alerts == alerts
    assert target.poll_interval_s == 3.0
    assert target.rearm is False


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


def test_build_target_override_actions_and_masks():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        mode="advanced",
        overrides={
            "actions": [{"name": "a", "steps": [{"activate": True}, {"click": {"x": 1, "y": 1}}]}],
            "masks": [[1, 1, 2, 2]],
            "rearm": False,
        },
    )
    target = build_target(
        selection, _profile(mode="advanced"), name="x"
    )
    assert target.rearm is False
    assert target.masks == ((1, 1, 2, 2),)
    assert target.actions[0].name == "a"


def test_build_target_rejects_text_action_in_non_advanced():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        mode="default",
        overrides={"actions": [{"name": "a", "when": {"text_any": ["x"]}}]},
    )
    with pytest.raises(ValueError):
        build_target(selection, _profile(mode="default"), name="x")
