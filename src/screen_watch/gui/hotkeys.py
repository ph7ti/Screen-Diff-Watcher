"""Hotkeys globais via `pynput` (plano, F2-T7) — extra opcional `input`.

Os callbacks rodam na thread do listener; por isso apenas publicam um evento na
fila da GUI (mesma regra do tray). Sem `pynput`, devolve None e a GUI cai para
tray-only com um aviso.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def start_hotkeys(events, hotkeys: dict[str, str]) -> object | None:
    """Registra `nome -> combo` (ex.: `arm -> '<ctrl>+<alt>+a'`)."""
    if not hotkeys:
        return None
    try:
        from pynput import keyboard  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depende do ambiente
        log.warning("pynput unavailable, global hotkeys disabled: %s", exc)
        return None

    def callback(name: str):
        def _callback(_listener=None):
            events.put({"kind": "action", "action": name})

        return _callback

    # Valida combo a combo: um combo invalido (ex.: `space` sem `<...>`) nao pode
    # derrubar a registracao das demais hotkeys.
    hot_key = getattr(keyboard, "HotKey", None)
    mapping: dict[str, object] = {}
    for name, combo in hotkeys.items():
        if not combo:
            continue
        if hot_key is not None:
            try:
                hot_key.parse(combo)
            except Exception as exc:  # noqa: BLE001 - pynput levanta tipos variados
                log.warning("invalid hotkey ignored (%s=%r): %s", name, combo, exc)
                continue
        mapping[combo] = callback(name)
    if not mapping:
        return None
    try:
        listener = keyboard.GlobalHotKeys(mapping)
        listener.daemon = True
        listener.start()
        return listener
    except Exception as exc:  # pragma: no cover - depende do ambiente
        log.warning("could not register global hotkeys: %s", exc)
        return None


def stop_hotkeys(listener: object | None) -> None:
    if listener is None:
        return
    try:
        listener.stop()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - depende do ambiente
        pass
