from __future__ import annotations

import sys
import threading
import types

from screen_watch.platform import audio


class _FakeWinsound:
    SND_FILENAME = 1
    SND_ASYNC = 2

    def __init__(self) -> None:
        self.played: list[tuple[str, int]] = []
        self.beeps = 0

    def PlaySound(self, path, flags) -> None:  # noqa: N802 - API do winsound
        # Como o winsound real, recusa qualquer coisa que nao seja WAV.
        if not str(path).lower().endswith(".wav"):
            raise RuntimeError("bad format")
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


def _pin_legacy(monkeypatch) -> None:
    """Desliga miniaudio explicitamente para exercitar o caminho legado."""
    monkeypatch.setattr(audio, "_miniaudio_available", lambda: False)


def test_play_file_windows_uses_winsound(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    _pin_legacy(monkeypatch)
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
    _pin_legacy(monkeypatch)
    monkeypatch.setattr(audio.shutil, "which", _which_linux({"paplay", "aplay"}))
    calls: list[list[str]] = []
    monkeypatch.setattr(audio.subprocess, "Popen", lambda args: calls.append(args))
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")

    assert audio.play_file(wav) is True
    assert calls == [["paplay", str(wav)]]


def test_play_file_linux_uses_aplay_with_quiet(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    _pin_legacy(monkeypatch)
    monkeypatch.setattr(audio.shutil, "which", _which_linux({"aplay"}))
    calls: list[list[str]] = []
    monkeypatch.setattr(audio.subprocess, "Popen", lambda args: calls.append(args))
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")

    assert audio.play_file(wav) is True
    assert calls == [["aplay", "-q", str(wav)]]


def test_play_file_linux_without_player_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    _pin_legacy(monkeypatch)
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
    _pin_legacy(monkeypatch)
    monkeypatch.setattr(audio.shutil, "which", _which_linux({"paplay", "aplay"}))
    # Sem campainha: o runner de CI tem /usr/share/sounds e o beep tentaria os
    # players de novo, mudando a contagem de chamadas.
    monkeypatch.setattr(audio, "_candidate_bell", lambda: None)
    calls: list[list[str]] = []

    def boom(args):
        calls.append(args)
        raise OSError("sem binario")

    monkeypatch.setattr(audio.subprocess, "Popen", boom)
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")

    assert audio.play_file(wav) is False
    assert len(calls) == 2  # tentou paplay e aplay antes de desistir


# -- camadas novas (Qt/miniaudio) e resolucao do caminho -------------------


def _fake_miniaudio() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        get_file_info=lambda path: object(),
        stream_file=lambda path: iter(()),
        PlaybackDevice=lambda: types.SimpleNamespace(
            start=lambda stream: None, close=lambda: None
        ),
    )


def test_install_qt_player_is_idempotent_when_already_installed(monkeypatch):
    monkeypatch.setattr(audio, "_qt_player", object())

    assert audio.install_qt_player() is True
    assert audio.qt_player_installed() is True


def test_play_file_prefers_the_qt_proxy(monkeypatch, tmp_path):
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(audio, "_qt_player", object())
    calls: list[str] = []
    monkeypatch.setattr(audio, "_invoke_qt", lambda path: calls.append(path) or True)
    monkeypatch.setattr(audio, "_miniaudio_available", lambda: True)

    assert audio.play_file(wav) is True
    assert calls == [str(wav)]


def test_play_file_falls_back_when_the_qt_invoke_fails(monkeypatch, tmp_path):
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(audio, "_qt_player", object())
    monkeypatch.setattr(audio, "_invoke_qt", lambda path: False)
    played: list[str] = []
    monkeypatch.setattr(audio, "_miniaudio_available", lambda: True)
    monkeypatch.setattr(audio, "_miniaudio_supported", lambda path: True)
    monkeypatch.setattr(audio, "_play_miniaudio", lambda path: played.append(path) or True)

    assert audio.play_file(wav) is True
    assert played == [str(wav)]


def test_play_file_uses_miniaudio_when_available(monkeypatch, tmp_path):
    mp3 = tmp_path / "alerta.mp3"
    mp3.write_bytes(b"ID3")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(audio, "_miniaudio_available", lambda: True)
    monkeypatch.setattr(audio, "_miniaudio_supported", lambda path: True)
    played: list[str] = []
    monkeypatch.setattr(audio, "_play_miniaudio", lambda path: played.append(path) or True)

    assert audio.play_file(mp3) is True
    assert played == [str(mp3)]


def test_play_file_unsupported_format_beeps(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    winsound = _install_winsound(monkeypatch)
    monkeypatch.setattr(audio, "_miniaudio_available", lambda: True)
    monkeypatch.setattr(audio, "_miniaudio_supported", lambda path: False)
    m4a = tmp_path / "alerta.m4a"
    m4a.write_bytes(b"....")

    assert audio.play_file(m4a) is True
    assert winsound.beeps == 1
    assert winsound.played == []


def test_resolve_sound_path_prefers_sounds_dir(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(home))
    sounds = home / "sounds"
    sounds.mkdir(parents=True)
    (sounds / "alerta.mp3").write_bytes(b"x")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    assert audio.resolve_sound_path("alerta.mp3") == str(sounds / "alerta.mp3")


def test_resolve_sound_path_falls_back_to_cwd(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path / "home"))
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "alerta.wav").write_bytes(b"x")
    monkeypatch.chdir(cwd)

    assert audio.resolve_sound_path("alerta.wav") == "alerta.wav"


def test_resolve_sound_path_keeps_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path / "home"))
    absolute = tmp_path / "outro" / "som.wav"

    assert audio.resolve_sound_path(absolute) == str(absolute)


def test_play_file_resolves_relative_in_sounds_dir(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(home))
    sounds = home / "sounds"
    sounds.mkdir(parents=True)
    (sounds / "alerta.wav").write_bytes(b"RIFF")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(audio, "_miniaudio_available", lambda: False)
    calls: list[list[str]] = []
    monkeypatch.setattr(audio.shutil, "which", _which_linux({"paplay"}))
    monkeypatch.setattr(audio.subprocess, "Popen", lambda args: calls.append(args))

    assert audio.play_file("alerta.wav") is True
    assert calls == [["paplay", str(sounds / "alerta.wav")]]


def test_play_miniaudio_is_non_blocking(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def worker(path: str) -> None:
        started.set()
        release.wait(2.0)

    monkeypatch.setattr(audio, "_miniaudio_worker", worker)

    assert audio._play_miniaudio("x.mp3") is True
    assert started.wait(2.0)  # a thread iniciou...
    assert not release.is_set()  # ...e `_play_miniaudio` nao esperou o fim
    release.set()


def test_miniaudio_worker_never_raises(monkeypatch):
    class Boom:
        @staticmethod
        def get_file_info(path):
            return None

        @staticmethod
        def stream_file(path):
            return iter(())

        @staticmethod
        def PlaybackDevice():
            raise RuntimeError("no audio device")

    monkeypatch.setitem(sys.modules, "miniaudio", Boom())
    audio._miniaudio_worker("x.mp3")  # nao levanta


def test_miniaudio_supported_probe(monkeypatch):
    monkeypatch.setitem(sys.modules, "miniaudio", _fake_miniaudio())
    assert audio._miniaudio_available() is True
    assert audio._miniaudio_supported("x.mp3") is True

    class Undecodable:
        @staticmethod
        def get_file_info(path):
            raise ValueError("unsupported file format")

    monkeypatch.setitem(sys.modules, "miniaudio", Undecodable())
    assert audio._miniaudio_supported("x.m4a") is False


def test_backend_info_reports_layers(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(audio.shutil, "which", _which_linux({"paplay"}))
    monkeypatch.setattr(audio, "_qt_player", None)
    monkeypatch.setitem(sys.modules, "miniaudio", None)

    info = audio.backend_info()
    assert info["qt"] is False
    assert info["miniaudio"] is False
    assert info["formats"] == ("wav",)

    monkeypatch.setitem(sys.modules, "miniaudio", _fake_miniaudio())
    info = audio.backend_info()
    assert info["miniaudio"] is True
    assert "mp3" in info["formats"]
