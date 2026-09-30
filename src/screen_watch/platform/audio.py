"""Som local atras da fronteira de plataforma (doc, secao 2.2).

`alerts/` nunca importa `winsound` nem verifica `sys.platform`: esta e a unica
porta para tocar audio. Windows usa `winsound` (stdlib); Linux/macOS usam um
player externo no `PATH` (`paplay`/`aplay`/`ffplay`/`afplay`).

Nunca levanta: devolve `False` e loga `warning` quando nao ha backend, para o
`AlertChain` nao quebrar por causa de som.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

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

# Arquivos de campainha candidatos quando nao ha `alert.wav`.
_BELL_FILES = (
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/alsa/Front_Center.wav",
)


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
            log.warning("falha ao tocar %s com %s: %s", path, command[0], exc)
            continue
        return True
    return False


def _play_windows(path: str) -> bool:
    try:
        import winsound  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depende do ambiente
        log.warning("winsound indisponivel: %s", exc)
        return False
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except (OSError, RuntimeError) as exc:
        log.warning("winsound nao conseguiu tocar %s: %s", path, exc)
        return False
    return True


def play_file(path: str | Path) -> bool:
    """Toca `path` de forma assincrona. Arquivo ausente cai no `beep()`."""
    value = str(path)
    if not Path(value).is_file():
        return beep()
    if sys.platform == "win32":
        return _play_windows(value)
    ok = _play_external(value)
    if not ok:
        log.warning("som indisponivel: nenhum player externo encontrado para %s", value)
    return ok


def beep() -> bool:
    """Aviso sonoro sem arquivo. `False` quando nao ha backend nem tema."""
    if sys.platform == "win32":
        try:
            import winsound  # noqa: PLC0415
        except Exception as exc:  # pragma: no cover - depende do ambiente
            log.warning("winsound indisponivel: %s", exc)
            return False
        try:
            winsound.MessageBeep()
        except (OSError, RuntimeError) as exc:  # pragma: no cover - depende do ambiente
            log.warning("MessageBeep falhou: %s", exc)
            return False
        return True

    bell = _candidate_bell()
    if bell is None:
        log.warning("som indisponivel: sem arquivo de campainha no tema")
        return False
    return _play_external(bell)


def backend_info() -> dict[str, object]:
    """Diagnostico do backend para o comando `features` (nao toca nada)."""
    if sys.platform == "win32":
        try:
            import winsound  # noqa: F401, PLC0415

            return {"platform": sys.platform, "backend": "winsound", "available": True}
        except Exception:
            return {"platform": sys.platform, "backend": None, "available": False}
    name = player_name()
    return {
        "platform": sys.platform,
        "backend": name,
        "players": [command[0] for command in _external_players()],
        "bell": _candidate_bell(),
        "available": name is not None,
    }
