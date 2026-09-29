"""DPI awareness e deteccao de Wayland.

`set_dpi_awareness()` deve ser a primeira coisa executada no processo, antes de
qualquer backend de captura, janela Qt ou chamada a `pywinctl` (ver doc, secao 5.1).
"""

from __future__ import annotations

import ctypes
import os
import sys


def set_dpi_awareness() -> None:
    """Fixa o processo como per-monitor DPI aware (no-op fora do Windows)."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def is_wayland() -> bool:
    """True se a sessao atual for Wayland. `mss` nao captura nesse caso."""
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
