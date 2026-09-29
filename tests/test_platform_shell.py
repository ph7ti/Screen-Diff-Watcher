from __future__ import annotations

from pathlib import Path

from screen_watch.platform import shell


def test_open_path_accepts_path_objects(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(shell.sys, "platform", "win32")
    monkeypatch.setattr(shell.os, "startfile", lambda path: calls.append(path), raising=False)

    assert shell.open_path(Path("C:/tmp/x")) is True
    assert calls == [str(Path("C:/tmp/x"))]


def test_open_path_uses_startfile_on_windows(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(shell.sys, "platform", "win32")
    monkeypatch.setattr(shell.os, "startfile", lambda path: calls.append(path), raising=False)

    assert shell.open_path("C:/tmp/x") is True
    assert calls == ["C:/tmp/x"]


def test_open_path_uses_open_on_macos(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(shell.sys, "platform", "darwin")
    monkeypatch.setattr(shell.subprocess, "Popen", lambda args: calls.append(args))

    assert shell.open_path("/tmp/x") is True
    assert calls == [["open", "/tmp/x"]]


def test_open_path_uses_xdg_open_on_linux(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(shell.sys, "platform", "linux")
    monkeypatch.setattr(shell.subprocess, "Popen", lambda args: calls.append(args))

    assert shell.open_path("/tmp/x") is True
    assert calls == [["xdg-open", "/tmp/x"]]


def test_open_path_returns_false_on_failure(monkeypatch):
    def boom(path):
        raise OSError("sem associacao")

    monkeypatch.setattr(shell.sys, "platform", "win32")
    monkeypatch.setattr(shell.os, "startfile", boom, raising=False)

    assert shell.open_path("C:/tmp/x") is False
