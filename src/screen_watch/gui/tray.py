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
            log.warning("could not load the icon %s: %s", path, exc)

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 56, 56), outline=(0, 82, 214, 255), width=4)
    return image


def start_tray(
    events,
    arm_durations=(1, 5, 15, 30),
    profiles=("default",),
    snooze_minutes=(5, 15, 30, 60),
    selections=(),
) -> object | None:
    """Sobe o tray em thread separada. Devolve o Icon ou None se indisponivel."""
    try:
        import pystray  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depende do ambiente
        log.warning("pystray unavailable, tray disabled: %s", exc)
        return None

    from screen_watch.i18n import tr  # noqa: PLC0415

    def push_tray(action: str):
        def _callback(_icon, _item):
            events.put({"kind": "tray", "action": action})

        return _callback

    def push_action(action: str, **extra):
        def _callback(_icon, _item):
            events.put({"kind": "action", "action": action, **extra})

        return _callback

    def push_gate(action: str, **extra):
        def _callback(_icon, _item):
            events.put({"kind": "gate", "action": action, **extra})

        return _callback

    def push_target(action: str, name: str):
        def _callback(_icon, _item):
            events.put({"kind": "target", "action": action, "name": name})

        return _callback

    arm_menu = pystray.Menu(
        *[
            pystray.MenuItem(
                tr("main.arm_minutes", minutes=minutes),
                push_action("arm_for", minutes=minutes),
            )
            for minutes in arm_durations
        ]
    )

    snooze_menu = pystray.Menu(
        *[
            pystray.MenuItem(
                tr("main.snooze_minutes", minutes=minutes),
                push_gate("snooze", minutes=minutes),
            )
            for minutes in snooze_minutes
        ]
    )

    def push_profile(name: str):
        def _callback(_icon, _item):
            events.put({"kind": "profile", "name": name})

        return _callback

    profile_menu = pystray.Menu(
        *[pystray.MenuItem(name, push_profile(name)) for name in profiles]
    )
    items = [
        pystray.MenuItem(tr("tray.toggle"), push_tray("toggle")),
        pystray.MenuItem(tr("main.btn_minimize"), push_tray("minimize")),
        pystray.MenuItem(tr("main.btn_start"), push_tray("start")),
        pystray.MenuItem(tr("main.btn_stop"), push_tray("stop")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(tr("main.btn_arm"), push_action("arm")),
        pystray.MenuItem(tr("main.btn_disarm"), push_action("disarm")),
        pystray.MenuItem(tr("main.btn_arm_for"), arm_menu),
        pystray.MenuItem(tr("tray.rearm_baseline"), push_action("rearm")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(tr("tray.snooze"), snooze_menu),
        pystray.MenuItem(tr("tray.mute"), push_gate("mute")),
        pystray.MenuItem(tr("tray.unmute"), push_gate("unmute")),
        pystray.MenuItem(tr("tray.acknowledge"), push_gate("acknowledge")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(tr("tray.profile"), profile_menu),
    ]
    if selections:
        selection_menu = pystray.Menu(
            *[
                pystray.MenuItem(
                    name,
                    pystray.Menu(
                        pystray.MenuItem(tr("main.btn_start"), push_target("start", name)),
                        pystray.MenuItem(tr("main.btn_stop"), push_target("stop", name)),
                    ),
                )
                for name in selections
            ]
        )
        items.append(pystray.MenuItem(tr("tray.selection"), selection_menu))
    items.extend(
        [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("tray.update"), push_tray("open_update")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("tray.quit"), push_tray("quit")),
        ]
    )
    menu = pystray.Menu(*items)
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
