"""Recursos empacotados (icones e sons do projeto).

Os PNGs ficam em `screen_watch/assets/icons/`, o som default em
`screen_watch/assets/sounds/`, e ambos sao declarados em
`[tool.setuptools.package-data]` para irem junto no wheel/instalacao.

Este modulo nao importa Qt nem PIL: devolve caminhos de arquivo e cada
consumidor monta o formato que precisa (QIcon, PIL.Image, etc.).
"""

from __future__ import annotations

from pathlib import Path

_ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"
_BASE_ICON = _ICON_DIR / "ScreenDiffWatcher.png"
_SOUND_DIR = Path(__file__).resolve().parent / "assets" / "sounds"
_DEFAULT_SOUND = _SOUND_DIR / "alert.mp3"

# Arquivos pequenos, indexados pelo lado do quadrado em pixels.
_SMALL_ICONS: dict[int, Path] = {
    32: _ICON_DIR / "ScreenDiffWatcher_32px.png",
    48: _ICON_DIR / "ScreenDiffWatcher_48px.png",
    64: _ICON_DIR / "ScreenDiffWatcher_64px.png",
}


def icon_paths() -> list[Path]:
    """Todos os icones existentes, do menor para o maior (base por ultimo)."""
    ordered = [*_SMALL_ICONS.values(), _BASE_ICON]
    return [path for path in ordered if path.is_file()]


def icon_path(size: int | None = None) -> Path | None:
    """Melhor icone para `size`; cai no arquivo base quando nao ha tamanho exato."""
    if size is not None:
        exact = _SMALL_ICONS.get(size)
        if exact is not None and exact.is_file():
            return exact
    if _BASE_ICON.is_file():
        return _BASE_ICON
    remaining = icon_paths()
    return remaining[-1] if remaining else None


def bundled_sounds_dir() -> Path:
    """Diretorio dos sons empacotados (``screen_watch/assets/sounds``).

    Distinto de `platform.paths.sounds_dir()` (``app_home()/sounds``, do usuario).
    """
    return _SOUND_DIR


def default_sound_path() -> Path | None:
    """Caminho do som default empacotado (`alert.mp3`); None se ausente."""
    return _DEFAULT_SOUND if _DEFAULT_SOUND.is_file() else None
