from __future__ import annotations

import sys
import types

import numpy as np

from screen_watch.alerts.sound import SoundNotifier
from screen_watch.compare.protocol import ComparisonResult


def _result():
    return ComparisonResult(changed=True, score=1.0, threshold=0.5, strategy="s", severity=3)


def _frame(make_frame):
    return make_frame(np.zeros((4, 4, 3), dtype=np.uint8))


class FakeWaveObject:
    @staticmethod
    def from_wave_file(path):
        return FakeWaveObject()

    def play(self):
        return object()


def _install_simpleaudio(monkeypatch):
    module = types.SimpleNamespace(WaveObject=FakeWaveObject)
    monkeypatch.setitem(sys.modules, "simpleaudio", module)


def _install_winsound(monkeypatch):
    class FakeWinsound:
        SND_FILENAME = 1
        SND_ASYNC = 2

        def __init__(self):
            self.played = []
            self.beeps = 0

        def PlaySound(self, file, flags):
            self.played.append((file, flags))

        def MessageBeep(self):
            self.beeps += 1

    fake = FakeWinsound()
    monkeypatch.setitem(sys.modules, "winsound", fake)
    return fake


def test_simpleaudio_is_preferred(monkeypatch, make_frame, tmp_path):
    monkeypatch.setitem(sys.modules, "simpleaudio", None)  # force ImportError
    _install_simpleaudio(monkeypatch)
    winsound = _install_winsound(monkeypatch)
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")

    SoundNotifier(file=str(wav)).notify(_result(), _frame(make_frame))
    assert winsound.played == []


def test_falls_back_to_winsound_when_simpleaudio_missing(monkeypatch, make_frame, tmp_path):
    monkeypatch.setitem(sys.modules, "simpleaudio", None)
    monkeypatch.setattr(sys, "platform", "win32")
    winsound = _install_winsound(monkeypatch)
    wav = tmp_path / "alert.wav"
    wav.write_bytes(b"RIFF")

    SoundNotifier(file=str(wav)).notify(_result(), _frame(make_frame))
    assert winsound.played == [(str(wav), FakeWinsoundFlags.FILENAME_ASYNC)]
    assert winsound.beeps == 0


def test_missing_wav_uses_message_beep(monkeypatch, make_frame, tmp_path):
    monkeypatch.setitem(sys.modules, "simpleaudio", None)
    monkeypatch.setattr(sys, "platform", "win32")
    winsound = _install_winsound(monkeypatch)

    SoundNotifier(file=str(tmp_path / "absent.wav")).notify(_result(), _frame(make_frame))
    assert winsound.beeps == 1
    assert winsound.played == []


def test_non_windows_without_simpleaudio_does_not_raise(monkeypatch, make_frame, tmp_path):
    monkeypatch.setitem(sys.modules, "simpleaudio", None)
    monkeypatch.setattr(sys, "platform", "linux")
    SoundNotifier(file=str(tmp_path / "absent.wav")).notify(_result(), _frame(make_frame))


class FakeWinsoundFlags:
    FILENAME_ASYNC = 1 | 2
