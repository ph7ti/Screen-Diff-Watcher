"""Alerta sonoro local (doc, secao 11.2).

Tenta `simpleaudio` (opcional, sem wheel confiavel no 3.13). Se ele faltar, cai
para `winsound` no Windows; sem `alert.wav`, usa `MessageBeep()` — nenhum asset
e obrigatorio.
"""

from __future__ import annotations

import logging
import os
import sys

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult

log = logging.getLogger(__name__)


class SoundNotifier:
    name = "sound"

    def __init__(
        self,
        file: str = "alert.wav",
        *,
        enabled: bool = True,
        severity_min: int = 1,
        cooldown_s: float = 30.0,
    ) -> None:
        self.file = file
        self.enabled = bool(enabled)
        self.severity_min = int(severity_min)
        self.cooldown_s = float(cooldown_s)
        self._playback: object | None = None

    def notify(self, result: ComparisonResult, frame: Frame) -> None:
        if self._play_simpleaudio():
            return
        self._play_fallback()

    def _play_simpleaudio(self) -> bool:
        if not os.path.exists(self.file):
            return False
        try:
            import simpleaudio  # noqa: PLC0415
        except Exception:  # pragma: no cover - depende do ambiente
            return False
        try:
            self._playback = simpleaudio.WaveObject.from_wave_file(self.file).play()
            return True
        except Exception as exc:  # pragma: no cover - depende do ambiente
            log.warning("simpleaudio nao conseguiu tocar %s: %s", self.file, exc)
            return False

    def _play_fallback(self) -> None:
        if sys.platform != "win32":
            log.warning(
                "som indisponivel: simpleaudio ausente e sem fallback no SO %s (arquivo=%s)",
                sys.platform,
                self.file,
            )
            return
        import winsound  # noqa: PLC0415

        if os.path.exists(self.file):
            winsound.PlaySound(self.file, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            winsound.MessageBeep()
