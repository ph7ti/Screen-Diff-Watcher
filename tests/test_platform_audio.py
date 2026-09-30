from __future__ import annotations

import sys

from screen_watch.platform import audio


class _FakeWinsound:
    SND_FILENAME = 1
    SND_ASYNC = 2

    def __init__(self) -> None:
        self.played: list[tuple[str, int]] = []
        self.beeps = 0

    def PlaySound(self, path, flags) -> None:  # noqa: N802 - API do winsound
        self.played.append((path, flags))

    def MessageBeep(self) -> None:  # noqa: N802 - API do winsound
        self.beeps += 1


def _install_winsound(monkeypatch) -> _FakeWinsound:
    fake = _FakeWinsound()
    monkeypatch.setitem(sys.modules, "winsound", fake)
    return fake


def _which_linux(available: set[str]):
    def fake(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in available else None

    return fake


def test_play_file_windows_uses_winsound(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    winsound = _install_winsound(monkeypatch)
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")

    assert audio.play_file(wav) is True
    assert winsound.played == [(str(wav), _FakeWinsound.SND_FILENAME | _FakeWinsound.SND_ASYNC)]
    assert winsound.beeps == 0


def test_play_file_windows_missing_file_beeps(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    winsound = _install_winsound(monkeypatch)

    assert audio.play_file(tmp_path / "absent.wav") is True
    assert winsound.beeps == 1
    assert winsound.played == []


def test_play_file_linux_prefers_paplay(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(audio.shutil, "which", _which_linux({"paplay", "aplay"}))
    calls: list[list[str]] = []
    monkeypatch.setattr(audio.subprocess, "Popen", lambda args: calls.append(args))
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")

    assert audio.play_file(wav) is True
    assert calls == [["paplay", str(wav)]]


def test_play_file_linux_uses_aplay_with_quiet(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(audio.shutil, "which", _which_linux({"aplay"}))
    calls: list[list[str]] = []
    monkeypatch.setattr(audio.subprocess, "Popen", lambda args: calls.append(args))
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")

    assert audio.play_file(wav) is True
    assert calls == [["aplay", "-q", str(wav)]]


def test_play_file_linux_without_player_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(audio.shutil, "which", _which_linux(set()))
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")

    assert audio.play_file(wav) is False


def test_beep_linux_without_bell_returns_false(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(audio.shutil, "which", _which_linux(set()))

    assert audio.beep() is False


def test_backend_info_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    _install_winsound(monkeypatch)

    info = audio.backend_info()
    assert info["backend"] == "winsound"
    assert info["available"] is True


def test_backend_info_linux_reports_player(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(audio.shutil, "which", _which_linux({"paplay"}))

    info = audio.backend_info()
    assert info["backend"] == "paplay"
    assert info["available"] is True
    assert "paplay" in info["players"]


def test_play_file_never_raises_when_popen_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(audio.shutil, "which", _which_linux({"paplay", "aplay"}))
    calls: list[list[str]] = []

    def boom(args):
        calls.append(args)
        raise OSError("sem binario")

    monkeypatch.setattr(audio.subprocess, "Popen", boom)
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")

    assert audio.play_file(wav) is False
    assert len(calls) == 2  # tentou paplay e aplay antes de desistir
