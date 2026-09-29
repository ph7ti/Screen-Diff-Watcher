"""Gravador de acoes do usuario (plano, F3-T4).

As partes puras (`convert_point`, `StepRecorder`) sao testaveis sem display; o
listener (`record_interactively`) usa `pynput` (extra `input`) e so e chamado pelo
CLI `record-actions`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import yaml

log = logging.getLogger(__name__)

Rect = tuple[int, int, int, int]
Point = tuple[int, int]


class RecordingCancelled(RuntimeError):
    """A contagem/confirmacao que antecede a gravacao foi cancelada."""

_MODIFIER_NAMES = {
    "ctrl": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "shift": "shift",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt": "alt",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "cmd": "cmd",
    "cmd_l": "cmd",
    "cmd_r": "cmd",
}


def point_in_rect(point: Point, rect: Rect) -> bool:
    x, y = point
    rx, ry, rw, rh = rect
    return rx <= x < rx + rw and ry <= y < ry + rh


def convert_point(x: int, y: int, *, roi_rect: Rect, window_rect: Rect) -> dict:
    """Converte um ponto absoluto para `ref` roi/window/screen (plano, F3-T4)."""
    if point_in_rect((x, y), roi_rect):
        return {"x": x - roi_rect[0], "y": y - roi_rect[1], "ref": "roi"}
    if point_in_rect((x, y), window_rect):
        return {"x": x - window_rect[0], "y": y - window_rect[1], "ref": "window"}
    return {"x": x, "y": y, "ref": "screen"}


class StepRecorder:
    def __init__(self, *, roi_rect: Rect | None = None, window_rect: Rect | None = None) -> None:
        self.roi_rect = roi_rect
        self.window_rect = window_rect
        self._steps: list[dict] = []

    def add_click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> dict:
        if self.roi_rect is not None and self.window_rect is not None:
            params = convert_point(x, y, roi_rect=self.roi_rect, window_rect=self.window_rect)
        else:
            params = {"x": int(x), "y": int(y), "ref": "screen"}
        params.update({"button": button, "clicks": int(clicks)})
        step = {"click": params}
        self._steps.append(step)
        return step

    def add_move(self, x: int, y: int) -> dict:
        if self.roi_rect is not None and self.window_rect is not None:
            params = convert_point(x, y, roi_rect=self.roi_rect, window_rect=self.window_rect)
        else:
            params = {"x": int(x), "y": int(y), "ref": "screen"}
        step = {"move": params}
        self._steps.append(step)
        return step

    def add_key(self, keys: str) -> dict:
        step = {"key": {"keys": keys}}
        self._steps.append(step)
        return step

    def add_wait(self, ms: int) -> dict:
        step = {"wait": {"ms": int(ms)}}
        self._steps.append(step)
        return step

    def raw_steps(self) -> list[dict]:
        return list(self._steps)

    def to_yaml(self, name: str = "gravada", *, with_activate: bool = True) -> str:
        """Snippet pronto para colar sob `actions:` (com `when` comentado)."""
        steps = self.raw_steps()
        if with_activate and not any("activate" in step for step in steps):
            steps = [{"activate": True}, *steps]
        action = {
            "name": name,
            "enabled": True,
            "severity_min": 1,
            "cooldown_s": 30,
            "settle_s": 1.5,
            "rebaseline": False,
            "steps": steps,
        }
        text = yaml.safe_dump({"actions": [action]}, allow_unicode=True, sort_keys=False)
        comment = (
            "  # when:                        # descomente para refinar o gatilho\n"
            "  #   changed: true\n"
            '  #   text_any: ["erro", "falha"]\n'
        )
        lines: list[str] = []
        for line in text.splitlines():
            if line.strip().startswith("steps:"):
                lines.append(comment.rstrip("\n"))
            lines.append(line)
        return "\n".join(lines) + "\n"


def record_interactively(
    *,
    roi_rect: Rect,
    window_rect: Rect,
    start_key: str = "f9",
    stop_key: str = "f10",
    status=print,
    before_start: Callable[[], None] | None = None,
    auto_start: bool = False,
) -> StepRecorder:
    """Escuta o usuario ate `stop_key` (Inicio/Fim explicitos). Requer `pynput`.

    Com `auto_start=True`, `before_start()` roda na thread principal **antes** de
    criar os listeners (nunca no callback do `pynput`) e a gravacao ja comeca sem
    exigir `start_key`. Com `auto_start=False`, mantem o `F9` explicito.
    """
    from screen_watch.platform.input import InputUnavailable  # noqa: PLC0415

    try:
        from pynput import keyboard, mouse  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depende do ambiente
        raise InputUnavailable(
            "pynput indisponivel. Instale o extra de entrada: pip install -e \".[input]\""
        ) from exc

    recorder = StepRecorder(roi_rect=roi_rect, window_rect=window_rect)
    if auto_start and before_start is not None:
        before_start()
    state = {"active": bool(auto_start), "done": False}
    held: list[str] = []

    def _key_name(key) -> str:
        name = getattr(key, "name", None)
        if name:
            return _MODIFIER_NAMES.get(name, name)
        char = getattr(key, "char", None)
        return char or str(key)

    def on_click(x, y, button, pressed):
        if not state["active"] or not pressed:
            return
        recorder.add_click(int(x), int(y), button=getattr(button, "name", "left"))
        status(f"click {int(x)},{int(y)} ({getattr(button, 'name', 'left')})")

    def on_press(key):
        name = _key_name(key)
        if name == start_key and not state["active"]:
            state["active"] = True
            status(f"gravando... pressione {stop_key} para finalizar")
            return
        if name == stop_key:
            state["done"] = True
            return False
        if not state["active"]:
            return
        base = getattr(key, "name", None)
        if base in _MODIFIER_NAMES:
            mapped = _MODIFIER_NAMES[base]
            if mapped not in held:
                held.append(mapped)
            return
        chord = "+".join([*held, name])
        recorder.add_key(chord)
        status(f"key {chord}")

    def on_release(key):
        base = getattr(key, "name", None)
        if base in _MODIFIER_NAMES:
            mapped = _MODIFIER_NAMES[base]
            if mapped in held:
                held.remove(mapped)

    mouse_listener = mouse.Listener(on_click=on_click)
    key_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    mouse_listener.start()
    key_listener.start()
    if auto_start:
        status(f"gravando... pressione {stop_key} para finalizar")
    else:
        status(f"pressione {start_key} para iniciar a gravacao")
    key_listener.join()
    mouse_listener.stop()
    return recorder
