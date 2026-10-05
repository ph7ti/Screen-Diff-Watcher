from __future__ import annotations

import pytest

from screen_watch.config.schema import (
    AdvancedOptions,
    AlertOptions,
    CompareOptions,
    GlobalDefaults,
    LightOptions,
    ProfileOptions,
    TargetConfig,
    TextWatchOptions,
)
from screen_watch.errors import ConfigError
from screen_watch.persistence.selection import (
    Selection,
    build_target,
    dump_selection,
    effective_masks,
    from_target_config,
    load_selection,
    override_actions,
    override_text_watch,
    plan_rename,
    rename_selection,
    resolve_actions,
    set_masks,
    set_override_actions,
    set_override_text_watch,
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
    with pytest.raises(ConfigError):
        load_selection(path)


def test_unsupported_version_raises(tmp_path):
    path = tmp_path / "selection.json"
    path.write_text(
        '{"version": 99, "window_handle": 9, "origin_at_selection": [0, 0],'
        ' "roi_relative": [1, 2, 3, 4]}',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
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
    with pytest.raises(ConfigError):
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
    with pytest.raises(ConfigError):
        build_target(selection, _profile(), name="x")


def test_build_target_rejects_invalid_mode():
    selection = Selection(
        window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4), mode="turbo"
    )
    with pytest.raises(ConfigError):
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
    with pytest.raises(ConfigError):
        build_target(selection, _profile(mode="default"), name="x")


def _actions_selection() -> Selection:
    return Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        mode="advanced",
        overrides={
            "actions": [
                {"name": "a", "steps": [{"activate": True}]},
                {"name": "b", "steps": [{"activate": True}]},
            ]
        },
    )


def test_resolve_actions_uses_overrides():
    actions = resolve_actions(_actions_selection(), _profile(mode="advanced"))
    assert [action.name for action in actions] == ["a", "b"]


def test_resolve_actions_rejects_text_in_non_advanced():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        mode="default",
        overrides={"actions": [{"name": "a", "when": {"text_any": ["x"]}}]},
    )
    with pytest.raises(ConfigError):
        resolve_actions(selection, _profile(mode="default"))


def test_override_actions_round_trip_and_resolve():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        mode="advanced",
        overrides={"poll_interval_s": 1.5},
    )
    assert override_actions(selection) == []

    raw = {
        "name": "nova",
        "steps": [{"activate": True}, {"click": {"x": 1, "y": 2, "ref": "roi"}}],
    }
    updated = set_override_actions(selection, [raw])

    assert updated.overrides["poll_interval_s"] == 1.5
    assert override_actions(updated)[0]["name"] == "nova"
    # resolve_actions enxerga a acao sem depender de perfis/config v2
    assert [action.name for action in resolve_actions(updated, _profile(mode="advanced"))] == [
        "nova"
    ]


def test_set_override_actions_empty_removes_key():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        overrides={"actions": [{"name": "a", "steps": []}], "rearm": False},
    )
    updated = set_override_actions(selection, [])
    assert "actions" not in updated.overrides
    assert updated.overrides["rearm"] is False

    only_actions = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        overrides={"actions": [{"name": "a", "steps": []}]},
    )
    assert set_override_actions(only_actions, []).overrides is None


def test_override_actions_ignores_corrupt():
    base = {"window_handle": 1, "origin_at_selection": (0, 0), "roi_relative": (1, 2, 3, 4)}
    assert override_actions(Selection(**base, overrides=None)) == []
    assert override_actions(Selection(**base, overrides={"actions": 3})) == []
    assert override_actions(Selection(**base, overrides={"actions": ["x", {"name": "a"}]})) == [
        {"name": "a"}
    ]


def test_build_target_applies_action_filter():
    selection = _actions_selection()

    filtered = build_target(
        selection, _profile(mode="advanced"), name="x", action_filter=("b",)
    )
    assert [action.name for action in filtered.actions] == ["b"]

    none_selected = build_target(
        selection, _profile(mode="advanced"), name="x", action_filter=()
    )
    assert none_selected.actions == ()

    unfiltered = build_target(selection, _profile(mode="advanced"), name="x")
    assert [action.name for action in unfiltered.actions] == ["a", "b"]


# -- nome da selecao -------------------------------------------------------


def _named_selection(**extra) -> Selection:
    fields = {
        "window_handle": 1,
        "origin_at_selection": (0, 0),
        "roi_relative": (1, 2, 3, 4),
        "mode": "advanced",
    }
    fields.update(extra)
    return Selection(**fields)


def test_name_round_trips(tmp_path):
    selection = _named_selection(name="Verificando Download")
    path = tmp_path / "s.json"
    dump_selection(path, selection)
    assert load_selection(path) == selection
    assert load_selection(path).name == "Verificando Download"


def test_name_defaults_to_empty_when_absent(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        '{"version": 2, "window_handle": 9, "origin_at_selection": [0, 0],'
        ' "roi_relative": [1, 2, 3, 4]}',
        encoding="utf-8",
    )
    assert load_selection(path).name == ""


def test_build_target_carries_label_from_name():
    target = build_target(_named_selection(name="Painel"), _profile(), name="demo")
    assert target.name == "demo"
    assert target.label == "Painel"


def test_build_target_label_empty_without_name():
    target = build_target(_named_selection(), _profile(), name="demo")
    assert target.label == ""


def test_to_target_config_carries_label():
    target = to_target_config(_named_selection(name="Painel"), name="demo")
    assert target.label == "Painel"


def test_plan_rename_builds_slug_path(tmp_path):
    old = tmp_path / "demo.json"
    assert plan_rename(tmp_path, old, "Verificando Download") == (
        tmp_path / "verificando-download.json"
    )
    assert plan_rename(tmp_path, old, "Seleção Ação") == tmp_path / "selecao-acao.json"


def test_plan_rename_same_slug_is_noop(tmp_path):
    old = tmp_path / "verificando-download.json"
    assert plan_rename(tmp_path, old, "Verificando Download") == old
    assert plan_rename(tmp_path, old, "VERIFICANDO DOWNLOAD") == old


def test_plan_rename_rejects_conflict_case_insensitive(tmp_path):
    old = tmp_path / "demo.json"
    (tmp_path / "Outra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        plan_rename(tmp_path, old, "outra")
    assert excinfo.value.code == "selection.name_conflict"


def test_plan_rename_rejects_empty_slug(tmp_path):
    with pytest.raises(ConfigError) as excinfo:
        plan_rename(tmp_path, tmp_path / "demo.json", "###")
    assert excinfo.value.code == "selection.name_invalid"


def test_plan_rename_rejects_long_slug(tmp_path):
    with pytest.raises(ConfigError) as excinfo:
        plan_rename(tmp_path, tmp_path / "demo.json", "a" * 61)
    assert excinfo.value.code == "selection.name_too_long"


def test_rename_selection_moves_file_and_writes_name(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    old = tmp_path / "selections" / "demo.json"
    dump_selection(old, _named_selection(name="antigo"))
    new = tmp_path / "selections" / "novo.json"

    updated = rename_selection(old, new, name="Novo")

    assert not old.exists()
    assert new.exists()
    assert updated.name == "Novo"
    assert load_selection(new).name == "Novo"
    assert load_selection(new).window_handle == 1


def test_rename_selection_same_file_writes_only_name(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    path = tmp_path / "selections" / "demo.json"
    dump_selection(path, _named_selection())

    updated = rename_selection(path, path, name="Novo")

    assert path.exists()
    assert updated.name == "Novo"
    assert load_selection(path).name == "Novo"


def test_rename_selection_never_overwrites(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    old = tmp_path / "selections" / "demo.json"
    new = tmp_path / "selections" / "outra.json"
    dump_selection(old, _named_selection(name="demo"))
    dump_selection(new, _named_selection(name="outra"))

    with pytest.raises(ConfigError) as excinfo:
        rename_selection(old, new, name="Outra")

    assert excinfo.value.code == "selection.name_conflict"
    assert old.exists() and new.exists()
    assert load_selection(old).name == "demo"
    assert load_selection(new).name == "outra"


def test_rename_selection_rolls_back_on_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    old = tmp_path / "selections" / "demo.json"
    dump_selection(old, _named_selection())
    new = tmp_path / "selections" / "novo.json"

    import screen_watch.persistence.selection as selection_module

    def boom(path, selection):
        raise OSError("disco cheio")

    monkeypatch.setattr(selection_module, "dump_selection", boom)

    with pytest.raises(ConfigError) as excinfo:
        rename_selection(old, new, name="Novo")

    assert excinfo.value.code == "selection.rename_failed"
    assert old.exists()
    assert not new.exists()


def test_rename_selection_updates_last_selection(monkeypatch, tmp_path):
    from screen_watch.platform.paths import load_state, update_state

    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    old = tmp_path / "selections" / "demo.json"
    dump_selection(old, _named_selection())
    update_state(last_selection="demo.json")
    new = tmp_path / "selections" / "novo.json"

    rename_selection(old, new, name="Novo")

    assert load_state()["last_selection"] == "novo.json"


def test_rename_selection_keeps_unrelated_last_selection(monkeypatch, tmp_path):
    from screen_watch.platform.paths import load_state, update_state

    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    old = tmp_path / "selections" / "demo.json"
    dump_selection(old, _named_selection())
    update_state(last_selection="outra.json")
    new = tmp_path / "selections" / "novo.json"

    rename_selection(old, new, name="Novo")

    assert load_state()["last_selection"] == "outra.json"


# -- text_watch (override da selecao > perfil) -----------------------------


def test_override_text_watch_round_trip(tmp_path):
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        mode="advanced",
        overrides={"poll_interval_s": 1.5},
    )
    assert override_text_watch(selection) is None

    watch = TextWatchOptions(
        text="CONCLUÍDO", expect="disappears", case_sensitive=True, ignore_accents=False
    )
    updated = set_override_text_watch(selection, watch)

    assert updated.overrides["poll_interval_s"] == 1.5
    assert override_text_watch(updated) == watch

    path = tmp_path / "s.json"
    dump_selection(path, updated)
    assert override_text_watch(load_selection(path)) == watch


def test_set_override_text_watch_none_removes_key():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        overrides={"text_watch": {"text": "ok"}, "rearm": False},
    )
    updated = set_override_text_watch(selection, None)
    assert "text_watch" not in updated.overrides
    assert updated.overrides["rearm"] is False

    only_watch = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        overrides={"text_watch": {"text": "ok"}},
    )
    assert set_override_text_watch(only_watch, None).overrides is None


def test_override_text_watch_rejects_invalid_raw():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        overrides={"text_watch": {"text": "  "}},
    )
    with pytest.raises(ConfigError):
        override_text_watch(selection)


def test_build_target_applies_text_watch_override():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        mode="advanced",
        overrides={"text_watch": {"text": "ok", "expect": "disappears"}},
    )
    target = build_target(selection, _profile(mode="advanced"), name="x")
    assert target.compare_options.advanced.text_watch == TextWatchOptions(
        text="ok", expect="disappears"
    )


def test_build_target_override_text_watch_wins_over_profile():
    profile = ProfileOptions(
        defaults=GlobalDefaults(
            compare_options=CompareOptions(
                advanced=AdvancedOptions(text_watch=TextWatchOptions(text="perfil"))
            )
        )
    )
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        mode="advanced",
        overrides={"text_watch": {"text": "selecao"}},
    )
    target = build_target(selection, profile, name="x")
    assert target.compare_options.advanced.text_watch.text == "selecao"


def test_build_target_uses_profile_text_watch_without_override():
    profile = ProfileOptions(
        defaults=GlobalDefaults(
            compare_options=CompareOptions(
                advanced=AdvancedOptions(text_watch=TextWatchOptions(text="perfil"))
            )
        )
    )
    selection = Selection(
        window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4), mode="advanced"
    )
    target = build_target(selection, profile, name="x")
    assert target.compare_options.advanced.text_watch.text == "perfil"


def test_build_target_rejects_text_watch_outside_advanced():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        mode="default",
        overrides={"text_watch": {"text": "ok"}},
    )
    with pytest.raises(ConfigError) as excinfo:
        build_target(selection, _profile(mode="default"), name="x")
    assert excinfo.value.code == "config.text_watch_needs_advanced"


def test_build_target_rejects_profile_text_watch_outside_advanced():
    profile = ProfileOptions(
        defaults=GlobalDefaults(
            mode="light",
            compare_options=CompareOptions(
                advanced=AdvancedOptions(text_watch=TextWatchOptions(text="perfil"))
            ),
        )
    )
    selection = Selection(
        window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4), mode="light"
    )
    with pytest.raises(ConfigError) as excinfo:
        build_target(selection, profile, name="x")
    assert excinfo.value.code == "config.text_watch_needs_advanced"


def test_dump_selection_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "s.json"
    dump_selection(path, Selection(window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4)))
    assert load_selection(path).window_handle == 1
    assert list(tmp_path.glob("*.tmp")) == []


def test_dump_selection_failure_keeps_previous_content(tmp_path, monkeypatch):
    import os

    path = tmp_path / "s.json"
    path.write_text("original", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        dump_selection(path, Selection(window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4)))
    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob("*.tmp")) == []


def test_effective_masks_prefers_override():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        masks=((1, 1, 1, 1),),
        overrides={"masks": [[2, 2, 2, 2]]},
    )
    assert effective_masks(selection) == ((2, 2, 2, 2),)


def test_effective_masks_falls_back_to_selection():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        masks=((1, 1, 1, 1),),
    )
    assert effective_masks(selection) == ((1, 1, 1, 1),)


def test_set_masks_updates_existing_override_and_keeps_other_keys():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        masks=((9, 9, 9, 9),),
        overrides={"masks": [[1, 1, 1, 1]], "rearm": False},
    )
    updated = set_masks(selection, ((2, 2, 3, 3),))
    assert updated.overrides == {"masks": [[2, 2, 3, 3]], "rearm": False}
    assert updated.masks == ((9, 9, 9, 9),)


def test_set_masks_updates_selection_field_when_not_empty():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(1, 2, 3, 4),
        masks=((1, 1, 1, 1),),
    )
    updated = set_masks(selection, ((4, 4, 5, 5),))
    assert updated.masks == ((4, 4, 5, 5),)
    assert updated.overrides is None


def test_set_masks_creates_override_when_no_field_exists():
    selection = Selection(window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4))
    updated = set_masks(selection, ((3, 3, 3, 3),))
    assert updated.masks == ()
    assert updated.overrides == {"masks": [[3, 3, 3, 3]]}


def test_set_masks_empty_without_existing_field_is_noop():
    selection = Selection(window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4))
    updated = set_masks(selection, ())
    assert updated == selection
    assert updated.overrides is None
