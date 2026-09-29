from __future__ import annotations

from screen_watch.actions.protocol import ActionSpec
from screen_watch.actions.selection import (
    filter_actions,
    load_action_selection,
    parse_action_names,
    save_action_selection,
)


def _actions(*names: str) -> tuple[ActionSpec, ...]:
    return tuple(ActionSpec(name=name) for name in names)


def test_parse_action_names_reserved_words():
    assert parse_action_names("all") is None
    assert parse_action_names("ALL") is None
    assert parse_action_names("") is None
    assert parse_action_names("   ") is None
    assert parse_action_names("none") == ()
    assert parse_action_names("None") == ()


def test_parse_action_names_list():
    assert parse_action_names("a, b ,c") == ("a", "b", "c")
    assert parse_action_names("a") == ("a",)
    assert parse_action_names("a,,b,") == ("a", "b")


def test_filter_actions():
    actions = _actions("a", "b", "c")

    assert [item.name for item in filter_actions(actions, None)] == ["a", "b", "c"]
    assert filter_actions(actions, ()) == ()
    assert [item.name for item in filter_actions(actions, ("c", "a"))] == ["a", "c"]
    assert [item.name for item in filter_actions(actions, ("desconhecida",))] == []


def test_selection_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))

    assert load_action_selection("painel") is None

    save_action_selection("painel", ["reprocessar", "confirmar"])
    assert load_action_selection("painel") == ("reprocessar", "confirmar")

    save_action_selection("painel", [])
    assert load_action_selection("painel") == ()
    assert load_action_selection("outra") is None


def test_load_action_selection_ignores_corrupt(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    (tmp_path / "state.json").write_text('{"action_selection": 3}', encoding="utf-8")
    assert load_action_selection("painel") is None

    (tmp_path / "state.json").write_text(
        '{"action_selection": {"painel": 5}}', encoding="utf-8"
    )
    assert load_action_selection("painel") is None

    assert load_action_selection("") is None
