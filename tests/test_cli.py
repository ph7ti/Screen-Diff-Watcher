from __future__ import annotations

import argparse

import numpy as np
import pytest

from screen_watch import __main__ as cli
from screen_watch.config.loader import ConfigError, load_config, save_config
from screen_watch.persistence.selection import Selection, dump_selection, load_selection


class _FakeWindow:
    handle = 7
    title = "janela fake"
    rect = (10, 20, 100, 50)
    is_minimized = False
    exists = True


class _FakeCapturedWindow:
    handle = 55
    title = "capturada"
    rect = (0, 0, 100, 100)


def test_select_manual_writes_selection_with_real_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    monkeypatch.setattr(
        "screen_watch.platform.window.find_window_by_handle", lambda handle: _FakeWindow()
    )
    args = argparse.Namespace(roi=[1, 2, 30, 40], handle=7, title="", mode="advanced", name="demo")

    assert cli._cmd_select_manual(args) == 0

    selection = load_selection(tmp_path / "selections" / "demo.json")
    assert selection.window_handle == 7
    assert selection.origin_at_selection == (10, 20)
    assert selection.roi_relative == (1, 2, 30, 40)
    assert selection.window_title_hint == "janela fake"


def test_select_manual_rejects_small_roi(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    args = argparse.Namespace(roi=[1, 2, 5, 5], handle=7, title="", mode="advanced", name="demo")
    assert cli._cmd_select_manual(args) == 1


def test_select_manual_warns_when_window_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    monkeypatch.setattr(
        "screen_watch.platform.window.find_window_by_handle", lambda handle: None
    )
    args = argparse.Namespace(roi=[1, 2, 30, 40], handle=7, title="x", mode="advanced", name="demo")

    assert cli._cmd_select_manual(args) == 0
    assert "nao encontrada" in capsys.readouterr().out


def test_check_monitor_scales_handles_missing_qt(monkeypatch, capsys):
    monkeypatch.setattr("screen_watch.platform.display.list_monitor_scales", lambda: None)
    cli._check_monitor_scales((0, 0, 10, 10))
    assert "PyQt6" in capsys.readouterr().out


def test_check_monitor_scales_warns_on_unsuitable_monitor(monkeypatch, capsys):
    from screen_watch.platform.display import MonitorScale

    scales = [
        MonitorScale("A", (0, 0, 100, 100), 1.25, True),
        MonitorScale("B", (100, 0, 100, 100), 1.0),
    ]
    monkeypatch.setattr("screen_watch.platform.display.list_monitor_scales", lambda: scales)

    cli._check_monitor_scales((10, 10, 20, 20))

    out = capsys.readouterr().out
    assert "ATENCAO" in out
    assert "'B'" in out


def _write_selection(path, **extra):
    dump_selection(
        path,
        Selection(
            window_handle=9,
            origin_at_selection=(0, 0),
            roi_relative=(1, 2, 30, 40),
            mode="light",
            **extra,
        ),
    )


# -- resolucao de selecao --------------------------------------------------


def test_resolve_selection_path_by_name(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    _write_selection(tmp_path / "selections" / "demo.json")

    assert cli._resolve_selection_path("demo") == tmp_path / "selections" / "demo.json"


def test_resolve_selection_path_by_explicit_path(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    path = tmp_path / "outro.json"
    _write_selection(path)
    assert cli._resolve_selection_path(str(path)) == path


def test_resolve_selection_path_uses_state(monkeypatch, tmp_path):
    from screen_watch.platform.paths import update_state

    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    _write_selection(tmp_path / "selections" / "demo.json")
    update_state(last_selection="demo.json")

    assert cli._resolve_selection_path(None) == tmp_path / "selections" / "demo.json"


def test_resolve_selection_path_without_any_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    with pytest.raises(ConfigError):
        cli._resolve_selection_path(None)


def test_resolve_run_target_from_selection_uses_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    selection_path = tmp_path / "demo.json"
    _write_selection(selection_path)
    args = argparse.Namespace(
        selection=str(selection_path),
        target=None,
        config=str(tmp_path / "absent.yaml"),
        profile=None,
    )

    target = cli._resolve_run_target(args)

    assert target.name == "demo"
    assert target.window_handle == 9
    assert target.mode == "light"
    assert [a.type for a in target.alerts] == ["sound", "popup", "log"]


def test_resolve_run_target_uses_legacy_yaml_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    save_config(
        config_path,
        {
            "targets": [
                {
                    "name": "demo",
                    "window_handle": 1,
                    "roi_relative": [1, 2, 3, 4],
                    "alerts": [{"type": "sound"}, {"type": "popup"}, {"type": "telegram"}],
                }
            ]
        },
    )
    selection_path = tmp_path / "demo.json"
    _write_selection(selection_path)

    args = argparse.Namespace(
        selection=str(selection_path), target=None, config=str(config_path), profile=None
    )
    target = cli._resolve_run_target(args)

    assert target.window_handle == 9
    assert [a.type for a in target.alerts] == ["sound", "popup", "telegram"]


def test_resolve_run_target_uses_v2_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    save_config(
        config_path,
        {
            "version": 2,
            "profile": "default",
            "profiles": {
                "default": {
                    "defaults": {"poll_interval_s": 3.0, "rearm": False},
                    "alerts": [{"type": "popup"}],
                }
            },
        },
    )
    selection_path = tmp_path / "demo.json"
    _write_selection(selection_path)

    args = argparse.Namespace(
        selection=str(selection_path), target=None, config=str(config_path), profile=None
    )
    target = cli._resolve_run_target(args)

    assert target.poll_interval_s == 3.0
    assert target.rearm is False
    assert [a.type for a in target.alerts] == ["popup"]


# -- comandos --------------------------------------------------------------


def test_parser_accepts_compare_modes():
    args = cli.build_parser().parse_args(["compare-modes", "--target", "x"])
    assert args.func is cli._cmd_compare_modes
    assert args.modes == "light,default,advanced"


def test_parser_accepts_gui_and_show_paths():
    parser = cli.build_parser()
    assert parser.parse_args(["gui"]).func is cli._cmd_gui
    assert parser.parse_args(["show-paths"]).func is cli._cmd_show_paths


def test_parser_accepts_list_selections_and_migrate():
    parser = cli.build_parser()
    assert parser.parse_args(["list-selections"]).func is cli._cmd_list_selections
    assert parser.parse_args(["migrate-config", "--dry-run"]).func is cli._cmd_migrate_config


def test_slugify():
    assert cli._slugify("WhatsApp.Root") == "whatsapp-root"
    assert cli._slugify("Visual Studio Code - Insiders") == "visual-studio-code-insiders"
    assert cli._slugify("!!!") == "target"


def test_list_selections_marks_last(monkeypatch, tmp_path, capsys):
    from screen_watch.platform.paths import update_state

    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    _write_selection(tmp_path / "selections" / "demo.json")
    update_state(last_selection="demo.json")

    assert cli._cmd_list_selections(argparse.Namespace()) == 0
    out = capsys.readouterr().out
    assert "demo.json" in out
    assert "(ultima)" in out


def test_migrate_config_command(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    save_config(
        config_path,
        {
            "targets": [
                {
                    "name": "demo",
                    "window_handle": 9,
                    "roi_relative": [1, 2, 3, 4],
                    "mode": "default",
                    "alerts": [{"type": "log"}],
                }
            ]
        },
    )

    assert cli._cmd_migrate_config(argparse.Namespace(path=str(config_path), dry_run=False)) == 0

    selection = load_selection(tmp_path / "selections" / "demo.json")
    assert selection.window_handle == 9
    assert selection.mode == "default"
    config = load_config(config_path)
    assert config.version == 2
    assert config.resolve().defaults.mode == "default"
    assert (tmp_path / "config.yaml.bak").exists()


def test_migrate_config_dry_run_writes_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    save_config(
        config_path,
        {"targets": [{"name": "demo", "window_handle": 9, "roi_relative": [1, 2, 3, 4]}]},
    )

    assert cli._cmd_migrate_config(argparse.Namespace(path=str(config_path), dry_run=True)) == 0
    assert "dry-run" in capsys.readouterr().out
    assert not list((tmp_path / "selections").glob("*.json"))
    assert load_config(config_path).version == 1


def test_migrate_config_aborts_on_existing_selection(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    _write_selection(tmp_path / "selections" / "demo.json")
    config_path = tmp_path / "config.yaml"
    save_config(
        config_path,
        {"targets": [{"name": "demo", "window_handle": 9, "roi_relative": [1, 2, 3, 4]}]},
    )

    assert cli._cmd_migrate_config(argparse.Namespace(path=str(config_path), dry_run=False)) == 1
    assert "ja existem" in capsys.readouterr().out


def test_validate_config_v2_reports_profiles(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    save_config(config_path, _v2())
    args = argparse.Namespace(config=str(config_path), selections=False)
    assert cli._cmd_validate_config(args) == 0
    assert "perfil" in capsys.readouterr().out


def _v2():
    from screen_watch.config.loader import default_config_dict

    return default_config_dict()


def test_validate_config_with_selections(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    _write_selection(tmp_path / "selections" / "demo.json", overrides={"poll_interval_s": 1.5})
    config_path = tmp_path / "config.yaml"
    save_config(config_path, _v2())

    args = argparse.Namespace(config=str(config_path), selections=True)
    assert cli._cmd_validate_config(args) == 0
    out = capsys.readouterr().out
    assert "1/1" in out


def test_compare_modes_rejects_invalid_mode(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    selection_path = tmp_path / "demo.json"
    _write_selection(selection_path)
    args = argparse.Namespace(
        selection=str(selection_path),
        target=None,
        config=str(tmp_path / "absent.yaml"),
        profile=None,
        modes="turbo",
        delay=0.0,
        repeat=1,
    )

    assert cli._cmd_compare_modes(args) == 1
    assert "modos invalidos" in capsys.readouterr().out


def _fake_capture(target):
    rgb = np.full((10, 10, 3), 7, dtype=np.uint8)
    return rgb, (0, 0, 10, 10), _FakeCapturedWindow()


def test_compare_modes_runs_with_mocked_capture(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    selection_path = tmp_path / "demo.json"
    _write_selection(selection_path)
    monkeypatch.setattr(cli, "_capture_target_roi", _fake_capture)
    args = argparse.Namespace(
        selection=str(selection_path),
        target=None,
        config=str(tmp_path / "absent.yaml"),
        profile=None,
        modes="light",
        delay=0.0,
        repeat=1,
    )

    assert cli._cmd_compare_modes(args) == 0
    assert "light" in capsys.readouterr().out


def test_test_alert_runs_with_mocked_capture(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    (tmp_path / "selections").mkdir()
    _write_selection(tmp_path / "selections" / "demo.json")
    config_path = tmp_path / "config.yaml"
    save_config(
        config_path,
        {
            "version": 2,
            "profile": "default",
            "profiles": {
                "default": {"defaults": {}, "alerts": [{"type": "log"}]},
            },
        },
    )
    monkeypatch.setattr(cli, "_capture_target_roi", _fake_capture)

    args = argparse.Namespace(
        config=str(config_path), selection="demo", target=None, profile=None
    )

    assert cli._cmd_test_alert(args) == 0
    log_path = tmp_path / "logs" / "alerts.jsonl"
    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8").strip()
