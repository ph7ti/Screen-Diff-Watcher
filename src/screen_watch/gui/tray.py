"""Tray (pystray) que apenas publica acoes na fila da GUI (doc P10).

Os callbacks do tray rodam em outra thread; por isso nunca tocam em widgets:
apenas colocam um evento em `events`, tratado pela GUI na thread principal.
"""

from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)


def _icon_image():
    from PIL import Image, ImageDraw  # noqa: PLC0415

    from screen_watch.resources import icon_path  # noqa: PLC0415

    path = icon_path(32)
    if path is not None:
        try:
            with Image.open(path) as image:
                return image.copy()
        except Exception as exc:  # pragma: no cover - depende do ambiente
            log.warning("nao foi possivel carregar o icone %s: %s", path, exc)

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 56, 56), outline=(0, 82, 214, 255), width=4)
    return image


def start_tray(events) -> object | None:
    """Sobe o tray em thread separada. Devolve o Icon ou None se indisponivel."""
    try:
        import pystray  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depende do ambiente
        log.warning("pystray indisponivel, tray desabilitado: %s", exc)
        return None

    def push(action: str):
        def _callback(_icon, _item):
            events.put({"kind": "tray", "action": action})

        return _callback

    menu = pystray.Menu(
        pystray.MenuItem("Mostrar/ocultar", push("toggle")),
        pystray.MenuItem("Minimizar para o tray", push("minimize")),
        pystray.MenuItem("Iniciar", push("start")),
        pystray.MenuItem("Parar", push("stop")),
        pystray.MenuItem("Sair", push("quit")),
    )
    icon = pystray.Icon("screen_watch", _icon_image(), "Screen Diff Watcher", menu)
    thread = threading.Thread(target=icon.run, name="screen-watch-tray", daemon=True)
    thread.start()
    return icon


def stop_tray(icon: object | None) -> None:
    if icon is None:
        return
    try:
        icon.stop()
    except Exception:  # pragma: no cover - depende do ambiente
        pass
