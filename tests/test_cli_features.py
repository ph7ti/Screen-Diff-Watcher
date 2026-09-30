from __future__ import annotations

import argparse
import json

from screen_watch.cli import commands as cli
from screen_watch.cli.parser import build_parser


def test_parser_accepts_features():
    args = build_parser().parse_args(["features", "--json"])
    assert args.func is cli._cmd_features
    assert args.json is True


def test_features_json_degrades_without_display(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    monkeypatch.setattr(
        cli,
        "_tesseract_info",
        lambda: {"path": None, "languages": [], "error": "nao encontrado"},
    )
    monkeypatch.setattr(cli, "_monitors_info", lambda: None)

    assert cli._cmd_features(argparse.Namespace(json=True)) == 0
    info = json.loads(capsys.readouterr().out)

    assert info["version"]
    assert info["monitors"] is None
    assert info["tesseract"]["path"] is None
    assert info["selections"] == 0


def test_features_text_prints_sections(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    monkeypatch.setattr(
        cli,
        "_tesseract_info",
        lambda: {"path": "/usr/bin/tesseract", "languages": ["eng", "por"], "error": None},
    )
    monkeypatch.setattr(
        cli,
        "_monitors_info",
        lambda: [{"name": "D1", "scale_percent": 100, "primary": True}],
    )

    assert cli._cmd_features(argparse.Namespace(json=False)) == 0
    out = capsys.readouterr().out
    assert "screen-watch" in out
    assert "eng, por" in out
    assert "monitors: 1" in out


def test_tesseract_info_without_binary(monkeypatch):
    monkeypatch.setattr(
        "screen_watch.platform.tesseract.resolve_tesseract_cmd", lambda configured=None: None
    )

    info = cli._tesseract_info()
    assert info["path"] is None
    assert info["error"]


def test_tesseract_info_lists_languages(monkeypatch):
    monkeypatch.setattr(
        "screen_watch.platform.tesseract.resolve_tesseract_cmd",
        lambda configured=None: "tesseract",
    )

    class FakeCompleted:
        returncode = 0
        stdout = "List of available languages (2):\neng\npor\n"
        stderr = ""

    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: FakeCompleted())

    info = cli._tesseract_info()
    assert info["languages"] == ["eng", "por"]
    assert info["error"] is None


def test_tesseract_info_reports_run_failure(monkeypatch):
    monkeypatch.setattr(
        "screen_watch.platform.tesseract.resolve_tesseract_cmd",
        lambda configured=None: "tesseract",
    )

    def boom(*args, **kwargs):
        raise OSError("sem permissao")

    monkeypatch.setattr(cli.subprocess, "run", boom)

    info = cli._tesseract_info()
    assert info["languages"] == []
    assert "sem permissao" in str(info["error"])
