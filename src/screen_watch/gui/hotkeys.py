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
        log.warning("pynput indisponivel, hotkeys globais desabilitadas: %s", exc)
        return None

    def callback(name: str):
        def _callback(_listener=None):
            events.put({"kind": "action", "action": name})

        return _callback

    mapping = {combo: callback(name) for name, combo in hotkeys.items() if combo}
    if not mapping:
        return None
    try:
        listener = keyboard.GlobalHotKeys(mapping)
        listener.daemon = True
        listener.start()
        return listener
    except Exception as exc:  # pragma: no cover - depende do ambiente
        log.warning("nao foi possivel registrar hotkeys globais: %s", exc)
        return None


def stop_hotkeys(listener: object | None) -> None:
    if listener is None:
        return
    try:
        listener.stop()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - depende do ambiente
        pass
