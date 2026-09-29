"""Entrada (mouse/teclado) com humanizacao — extra opcional `input` (doc, secao 12.2).

`pynput` nunca e importado no topo: o CI coleta e roda testes sem o extra. Os
helpers puros (`interpolate_points`, `make_rng`) sao testaveis sem display; o
backend real (`PynputBackend`) so e instanciado quando uma acao vai executar.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Sequence
from typing import Protocol

from screen_watch.config.schema import HumanizeOptions

log = logging.getLogger(__name__)

_KEY_ALIASES = {
    "escape": "esc",
    "return": "enter",
    "control": "ctrl",
    "windows": "cmd",
    "super": "cmd",
    "page_up": "pageup",
    "page_down": "pagedown",
}


class InputUnavailable(RuntimeError):
    """`pynput` ausente ou ambiente sem entrada (ex.: Wayland)."""


class InputBackend(Protocol):
    def move(self, x: int, y: int) -> None: ...

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> None: ...

    def press(self, keys: str) -> None: ...

    def type_text(self, text: str, *, interval_ms: int = 60) -> None: ...


def available() -> bool:
    """True se o extra `input` (pynput) pode ser importado."""
    try:
        import pynput  # noqa: F401, PLC0415

        return True
    except Exception:
        return False


def make_rng(humanize: HumanizeOptions) -> random.Random:
    return random.Random(humanize.seed)


def interpolate_points(
    start: tuple[int, int],
    end: tuple[int, int],
    steps: int,
    *,
    jitter_px: int = 0,
    rng: random.Random | None = None,
) -> list[tuple[int, int]]:
    """Pontos intermediarios de `start` ate `end` (inclusive o final), com jitter."""
    count = max(1, int(steps))
    points: list[tuple[int, int]] = []
    for index in range(1, count + 1):
        ratio = index / count
        x = round(start[0] + (end[0] - start[0]) * ratio)
        y = round(start[1] + (end[1] - start[1]) * ratio)
        if jitter_px and rng is not None:
            x += rng.randint(-jitter_px, jitter_px)
            y += rng.randint(-jitter_px, jitter_px)
        points.append((x, y))
    return points


class PynputBackend:
    """Backend real, importado sob demanda (extra `input`)."""

    name = "pynput"

    def __init__(self) -> None:
        try:
            from pynput import keyboard, mouse  # noqa: PLC0415
        except Exception as exc:  # pragma: no cover - depende do ambiente
            raise InputUnavailable(
                "pynput indisponivel. Instale o extra de entrada: pip install -e \".[input]\""
            ) from exc
        self._keyboard = keyboard
        self._mouse = mouse
        self._mouse_ctl = mouse.Controller()
        self._key_ctl = keyboard.Controller()

    def move(self, x: int, y: int) -> None:
        self._mouse_ctl.position = (int(x), int(y))

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> None:
        self.move(x, y)
        btn = getattr(self._mouse.Button, button, self._mouse.Button.left)
        for _ in range(max(1, int(clicks))):
            self._mouse_ctl.click(btn, 1)

    def press(self, keys: str) -> None:
        tokens = [token.strip().lower() for token in str(keys).split("+") if token.strip()]
        if not tokens:
            raise InputUnavailable("chord de teclas vazio")
        resolved = [self._resolve_key(token) for token in tokens]
        for key in resolved:
            self._key_ctl.press(key)
        for key in reversed(resolved):
            self._key_ctl.release(key)

    def type_text(self, text: str, *, interval_ms: int = 60) -> None:
        interval = max(0, int(interval_ms)) / 1000.0
        for char in str(text):
            self._key_ctl.type(char)
            if interval:
                time.sleep(interval)

    def _resolve_key(self, token: str):
        kb = self._keyboard
        name = _KEY_ALIASES.get(token, token)
        special = getattr(kb.Key, name, None)
        if special is not None:
            return special
        if len(token) == 1:
            return token
        raise InputUnavailable(f"tecla desconhecida: {token!r}")


def default_backend() -> InputBackend:
    return PynputBackend()


def format_keys(keys: Sequence[str] | str) -> str:
    """Normaliza um chord para o formato `ctrl+s` (usado em mensagens/auditoria)."""
    if isinstance(keys, str):
        return keys
    return "+".join(keys)
