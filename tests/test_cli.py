from __future__ import annotations

import argparse

import numpy as np

from screen_watch import __main__ as cli
from screen_watch.persistence.selection import load_selection


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


def _write_selection(path):
    from screen_watch.persistence.selection import Selection, dump_selection

    dump_selection(
        path,
        Selection(
            window_handle=9,
            origin_at_selection=(0, 0),
            roi_relative=(1, 2, 30, 40),
            mode="light",
        ),
    )


def test_resolve_run_target_from_selection_uses_defaults(tmp_path):
    selection_path = tmp_path / "demo.json"
    _write_selection(selection_path)
    args = argparse.Namespace(
        selection=str(selection_path), target=None, config=str(tmp_path / "absent.yaml")
    )

    target = cli._resolve_run_target(args)

    assert target.name == "demo"
    assert target.window_handle == 9
    assert target.mode == "light"
    assert [a.type for a in target.alerts] == ["sound", "popup", "log"]


def test_resolve_run_target_inherits_matching_yaml_target(tmp_path):
    from screen_watch.config.loader import default_config_dict, save_config

    config = default_config_dict()
    config["targets"][0]["name"] = "demo"
    config_path = tmp_path / "config.yaml"
    save_config(config_path, config)

    selection_path = tmp_path / "demo.json"
    _write_selection(selection_path)

    args = argparse.Namespace(
        selection=str(selection_path), target=None, config=str(config_path)
    )
    target = cli._resolve_run_target(args)

    assert target.window_handle == 9
    assert [a.type for a in target.alerts] == ["sound", "popup", "telegram"]


def test_parser_accepts_compare_modes():
    args = cli.build_parser().parse_args(["compare-modes", "--target", "x"])
    assert args.func is cli._cmd_compare_modes
    assert args.modes == "light,default,advanced"


def test_parser_accepts_gui_and_show_paths():
    parser = cli.build_parser()
    assert parser.parse_args(["gui"]).func is cli._cmd_gui
    assert parser.parse_args(["show-paths"]).func is cli._cmd_show_paths


def test_slugify():
    assert cli._slugify("WhatsApp.Root") == "whatsapp-root"
    assert cli._slugify("Visual Studio Code - Insiders") == "visual-studio-code-insiders"
    assert cli._slugify("!!!") == "target"


def test_compare_modes_rejects_invalid_mode(tmp_path, capsys):
    selection_path = tmp_path / "demo.json"
    _write_selection(selection_path)
    args = argparse.Namespace(
        selection=str(selection_path),
        target=None,
        config=str(tmp_path / "absent.yaml"),
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
    selection_path = tmp_path / "demo.json"
    _write_selection(selection_path)
    monkeypatch.setattr(cli, "_capture_target_roi", _fake_capture)
    args = argparse.Namespace(
        selection=str(selection_path),
        target=None,
        config=str(tmp_path / "absent.yaml"),
        modes="light",
        delay=0.0,
        repeat=1,
    )

    assert cli._cmd_compare_modes(args) == 0
    assert "light" in capsys.readouterr().out


def test_test_alert_runs_with_mocked_capture(monkeypatch, tmp_path):
    from screen_watch.config.loader import save_config

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
                    "alerts": [{"type": "log"}],
                }
            ]
        },
    )
    monkeypatch.setattr(cli, "_capture_target_roi", _fake_capture)

    args = argparse.Namespace(config=str(config_path), target="demo")

    assert cli._cmd_test_alert(args) == 0
    log_path = tmp_path / "logs" / "alerts.jsonl"
    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8").strip()
