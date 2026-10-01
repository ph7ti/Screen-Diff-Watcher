"""Alerta sonoro local (doc, secao 11.2).

Tenta `simpleaudio` (extra opcional `sound`, sem wheel confiavel no 3.13). Sem
ele, delega a `platform/audio.py`, que concentra a fronteira de plataforma
(player Qt na GUI; `miniaudio` no CLI; `winsound`/player externo no legado).
`alerts/` nao conhece `sys.platform`, `winsound`, Qt nem miniaudio.

O `file` relativo e resolvido por `platform/audio.py` (``app_home()/sounds``,
depois os sons empacotados e o CWD), de modo que o caminho vale para o app
instalado. Sem `file` explicito vale o `alert.mp3` empacotado.
"""

from __future__ import annotations

import logging
from pathlib import Path

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult

log = logging.getLogger(__name__)


class SoundNotifier:
    name = "sound"

    def __init__(
        self,
        file: str = "alert.mp3",
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
        from screen_watch.platform.audio import play_file, resolve_sound_path  # noqa: PLC0415

        path = resolve_sound_path(self.file)
        if self._play_simpleaudio(path):
            return
        play_file(path)

    def _play_simpleaudio(self, path: str) -> bool:
        # `simpleaudio` so decodifica WAV; para os demais formatos o despacho de
        # `play_file` (Qt/miniaudio) e o caminho certo.
        if Path(path).suffix.lower() != ".wav":
            return False
        if not Path(path).is_file():
            return False
        try:
            import simpleaudio  # noqa: PLC0415
        except Exception:  # pragma: no cover - depende do ambiente
            return False
        try:
            self._playback = simpleaudio.WaveObject.from_wave_file(path).play()
            return True
        except Exception as exc:  # pragma: no cover - depende do ambiente
            log.warning("simpleaudio could not play %s: %s", path, exc)
            return False
