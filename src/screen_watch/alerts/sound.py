"""Alerta sonoro local (doc, secao 11.2).

Tenta `simpleaudio` (extra opcional `sound`, sem wheel confiavel no 3.13). Sem
ele, delega a `platform/audio.py`, que concentra a fronteira de plataforma
(`winsound` no Windows; player externo no Linux/macOS). `alerts/` nao conhece
`sys.platform` nem `winsound`.
"""

from __future__ import annotations

import logging
import os

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
        from screen_watch.platform.audio import play_file  # noqa: PLC0415

        play_file(self.file)

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
