"""Som local atras da fronteira de plataforma (doc, secao 2.2 e 11.2).

`alerts/` nunca importa `winsound`, Qt nem verifica `sys.platform`: esta e a unica
porta para tocar audio. Camadas, em ordem:

1. **Qt** (`QMediaPlayer`, quando `install_qt_player()` rodou na thread da GUI):
   toca WAV/MP3/M4A/AAC/FLAC/... via Media Foundation/GStreamer/AVFoundation.
   Reproduz de forma enfileirada (`QueuedConnection`), interrompendo o som anterior.
2. **miniaudio** (CLI/`run`, sem aplicacao Qt): WAV/MP3/OGG/FLAC; toca numa thread
   daemon para nao bloquear o loop de monitoramento. Sem suporte a AAC/M4A.
3. **Legado**: `winsound` (somente WAV) no Windows; player externo no `PATH`
   (`paplay`/`aplay`/`ffplay`/`afplay`) no Linux/macOS.

`file` relativo procura primeiro em `platform.paths.sounds_dir()`
(``app_home()/sounds``), depois no diretorio empacotado
(`resources.bundled_sounds_dir()`, onde mora o `alert.mp3` default) e por fim no
CWD (compatibilidade com o comportamento antigo). Arquivo ausente ou formato sem
backend cai no `beep()`.

Nunca levanta: devolve `False` e loga `warning` quando nao ha backend, para o
`AlertChain` nao quebrar por causa de som.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from screen_watch.platform.paths import sounds_dir
from screen_watch.resources import bundled_sounds_dir

log = logging.getLogger(__name__)

# Players externos por SO, em ordem de preferencia. `ffplay` precisa de flags
# para nao abrir janela, sair ao fim e nao poluir o stderr.
_PLAYERS: dict[str, tuple[tuple[str, ...], ...]] = {
    "linux": (
        ("paplay",),
        ("aplay", "-q"),
        ("ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"),
    ),
    "darwin": (("afplay",),),
}

# Arquivos de campainha candidatos quando o som configurado nao existe (o
# default `alert.mp3` vem no pacote, entao isto e so o ultimo recurso).
_BELL_FILES = (
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/alsa/Front_Center.wav",
)

# Formatos esperados por camada (diagnostico do `features`; o backend real do Qt
# depende dos codecs do SO — no Linux, dos plugins do GStreamer instalados).
_MINIAUDIO_FORMATS = ("wav", "mp3", "ogg", "oga", "flac")
_QT_FORMATS = ("wav", "mp3", "m4a", "aac", "ogg", "oga", "flac", "wma")

# Player Qt criado no thread da GUI por `install_qt_player()`. O CLI nunca toca
# em Qt: sem aplicacao Qt o proxy fica None e vale o miniaudio/legado.
_qt_player: Any = None


def _external_players() -> tuple[tuple[str, ...], ...]:
    return _PLAYERS.get(sys.platform, ())


def _candidate_bell() -> str | None:
    for candidate in _BELL_FILES:
        if Path(candidate).is_file():
            return candidate
    return None


def player_name() -> str | None:
    """Primeiro player externo presente no `PATH` (None no Windows ou sem player)."""
    for command in _external_players():
        if shutil.which(command[0]):
            return command[0]
    return None


def _play_external(path: str) -> bool:
    for command in _external_players():
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.Popen([*command, path])
        except OSError as exc:  # pragma: no cover - depende do ambiente
            log.warning("failed to play %s with %s: %s", path, command[0], exc)
            continue
        return True
    return False


def _play_windows(path: str) -> bool:
    try:
        import winsound  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depende do ambiente
        log.warning("winsound unavailable: %s", exc)
        return False
    try:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)  # type: ignore[attr-defined]
    except (OSError, RuntimeError) as exc:
        log.warning("winsound could not play %s: %s", path, exc)
        return False
    return True


def resolve_sound_path(path: str | Path) -> str:
    """Resolve o caminho do som sem I/O extra.

    Absoluto usa como esta; relativo procura em ``sounds_dir()`` (arquivo do
    usuario), depois no diretorio empacotado (``bundled_sounds_dir()``) e, se
    nao existir, devolve o valor original (leitura relativa ao CWD, como antes).
    """
    value = Path(path)
    if value.is_absolute():
        return str(value)
    candidate = sounds_dir() / value
    if candidate.is_file():
        return str(candidate)
    bundled = bundled_sounds_dir() / value
    if bundled.is_file():
        return str(bundled)
    return str(value)


def _build_qt_proxy():
    """Cria o `QObject` dono do `QMediaPlayer` (import de Qt preguicoso)."""
    from PyQt6.QtCore import QObject, QUrl, pyqtSlot
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

    class QtSoundPlayer(QObject):
        def __init__(self) -> None:
            super().__init__()
            self._output = QAudioOutput(self)
            self._output.setVolume(1.0)
            self._player = QMediaPlayer(self)
            self._player.setAudioOutput(self._output)

        @pyqtSlot(str)
        def _play(self, path: str) -> None:
            # Uma instancia so: tocar de novo interrompe o som anterior.
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.play()

    return QtSoundPlayer()


def install_qt_player() -> bool:
    """Instala o player Qt no thread atual (deve ser o da GUI). Idempotente.

    `QMediaPlayer` exige um `QCoreApplication` e sera usado pela thread da GUI
    (o `AlertChain` despacha na thread do loop); sem aplicacao Qt, devolve False
    e o audio segue por miniaudio/legado.
    """
    global _qt_player
    if _qt_player is not None:
        return True
    try:
        from PyQt6.QtCore import QCoreApplication  # noqa: PLC0415
    except Exception as exc:
        log.debug("PyQt6 unavailable for the Qt sound player: %s", exc)
        return False
    if QCoreApplication.instance() is None:
        log.debug("no QCoreApplication; Qt sound player not installed")
        return False
    try:
        _qt_player = _build_qt_proxy()
    except Exception as exc:
        log.warning("QtMultimedia player unavailable: %s", exc)
        return False
    return True


def uninstall_qt_player() -> None:
    """Descarta o player Qt (uso em testes e no encerramento da GUI)."""
    global _qt_player
    _qt_player = None


def qt_player_installed() -> bool:
    return _qt_player is not None


def _invoke_qt(path: str) -> bool:
    """Enfileira `_play` no thread da GUI (o proxy foi criado la)."""
    player = _qt_player
    if player is None:
        return False
    try:
        from PyQt6.QtCore import Q_ARG, QMetaObject, Qt  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depende do ambiente
        log.warning("QtCore unavailable to play %s: %s", path, exc)
        return False
    try:
        QMetaObject.invokeMethod(
            player, "_play", Qt.ConnectionType.QueuedConnection, Q_ARG(str, path)
        )
    except Exception as exc:  # pragma: no cover - depende do ambiente
        log.warning("Qt player could not play %s: %s", path, exc)
        return False
    return True


def _miniaudio_available() -> bool:
    try:
        import miniaudio  # noqa: F401, PLC0415
    except Exception:
        return False
    return True


def _miniaudio_supported(path: str) -> bool:
    """Sonda rapida (so o cabecalho): o miniaudio tem decoder para `path`?

    Ex.: M4A/AAC nao tem; a sonda falha e o despacho segue para o legado/beep.
    """
    try:
        import miniaudio  # noqa: PLC0415
    except Exception:  # pragma: no cover - corrida com o import check
        return False
    try:
        miniaudio.get_file_info(path)
    except Exception as exc:
        log.debug("miniaudio cannot decode %s: %s", path, exc)
        return False
    return True


def _tracked_stream(stream, done: threading.Event):
    """Envolve o gerador do miniaudio para sinalizar o fim da reproducao."""
    try:
        yield from stream
    finally:
        done.set()


def _miniaudio_worker(path: str) -> None:
    try:
        import miniaudio  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - corrida com o import check
        log.warning("miniaudio unavailable: %s", exc)
        return
    done = threading.Event()
    try:
        device = miniaudio.PlaybackDevice()
        device.start(_tracked_stream(miniaudio.stream_file(path), done))
        # `start` retorna na hora (a reproducao roda no device); manter o device
        # vivo ate o fim do stream. O teto evita thread presa se o decoder parar
        # sem esgotar o gerador.
        done.wait(300.0)
        device.close()
    except Exception as exc:
        log.warning("miniaudio could not play %s: %s", path, exc)


def _play_miniaudio(path: str) -> bool:
    """Toca numa thread daemon para nao bloquear o loop (WAV/MP3/OGG/FLAC)."""
    thread = threading.Thread(
        target=_miniaudio_worker, args=(path,), name="screen-watch-sound", daemon=True
    )
    thread.start()
    return True


def _play_legacy(path: str) -> bool:
    if sys.platform == "win32":
        return _play_windows(path)
    return _play_external(path)


def play_file(path: str | Path) -> bool:
    """Toca `path` de forma assincrona (Qt -> miniaudio -> legado -> beep)."""
    value = resolve_sound_path(path)
    if not Path(value).is_file():
        log.warning("sound file not found: %s", value)
        return beep()
    if _qt_player is not None and _invoke_qt(value):
        return True
    if _miniaudio_available():
        if _miniaudio_supported(value):
            return _play_miniaudio(value)
        log.warning("miniaudio has no decoder for %s; trying the legacy backend", value)
    if _play_legacy(value):
        return True
    log.warning("no backend could play %s; falling back to beep", value)
    return beep()


def beep() -> bool:
    """Aviso sonoro sem arquivo. `False` quando nao ha backend nem tema."""
    if sys.platform == "win32":
        try:
            import winsound  # noqa: PLC0415
        except Exception as exc:  # pragma: no cover - depende do ambiente
            log.warning("winsound unavailable: %s", exc)
            return False
        try:
            winsound.MessageBeep()
        except (OSError, RuntimeError) as exc:  # pragma: no cover - depende do ambiente
            log.warning("MessageBeep failed: %s", exc)
            return False
        return True

    bell = _candidate_bell()
    if bell is None:
        log.warning("sound unavailable: no bell file in the theme")
        return False
    return _play_external(bell)


def supported_formats() -> tuple[str, ...]:
    """Formatos que a camada efetiva tende a tocar (sem tocar nada)."""
    if _qt_player is not None:
        return _QT_FORMATS
    if _miniaudio_available():
        return _MINIAUDIO_FORMATS
    return ("wav",)


def backend_info() -> dict[str, object]:
    """Diagnostico do backend para o comando `features` (nao toca nada)."""
    # Anotacao fora dos ramos: no mypy/Linux o ramo `win32` e inalcancavel e a
    # inferencia do dict do ramo `else` ficaria estreita demais.
    info: dict[str, object]
    if sys.platform == "win32":
        try:
            import winsound  # noqa: F401, PLC0415

            info = {
                "platform": sys.platform,
                "backend": "winsound",
                "available": True,
            }
        except Exception:
            info = {"platform": sys.platform, "backend": None, "available": False}
    else:
        name = player_name()
        info = {
            "platform": sys.platform,
            "backend": name,
            "players": [command[0] for command in _external_players()],
            "bell": _candidate_bell(),
            "available": name is not None,
        }
    info["qt"] = _qt_player is not None
    info["miniaudio"] = _miniaudio_available()
    info["formats"] = supported_formats()
    return info
