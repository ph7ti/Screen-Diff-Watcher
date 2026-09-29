"""Diagnostico P1: espaco logico vs fisico (plano, secao P1).

Rode em cada escala (100/125/150%) e registre a saida. Objetivo: decidir se o
`resolver` pode usar o conversor identidade (quando pywinctl/mss ja estao em
espaco fisico) ou se precisa de conversao por monitor.

Nao altera nada: apenas imprime. Uso:
    .\\.venv\\Scripts\\python.exe scripts\\probe_dpi.py
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from screen_watch.platform.dpi import set_dpi_awareness


def win32_rect(handle: int) -> tuple[int, int, int, int] | None:
    """Retangulo da janela via Win32 GetWindowRect (mesmo espaco do processo DPI-aware)."""
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    rect = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(handle), ctypes.byref(rect)):
        return None
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def main() -> int:
    set_dpi_awareness()

    from screen_watch.capture.mss_backend import open_mss

    print("== mss.monitors (fisico) ==")
    with open_mss() as sct:
        for index, monitor in enumerate(sct.monitors):
            print(f"  [{index}] {monitor}")

    print("== Qt (logico) ==")
    from screen_watch.platform.display import list_monitor_scales

    scales = list_monitor_scales()
    if scales is None:
        print("  PyQt6 ausente: nao foi possivel medir o espaco logico")
    else:
        for scale in scales:
            _, _, w, h = scale.rect
            physical = (round(w * scale.device_pixel_ratio), round(h * scale.device_pixel_ratio))
            print(
                f"  {scale.name!r} logico={scale.rect} dpr={scale.device_pixel_ratio} "
                f"-> fisico~{physical}"
            )

    print("== janelas: pywinctl vs Win32 GetWindowRect ==")
    from screen_watch.platform.window import list_windows

    match = 0
    checked = 0
    for info in list_windows()[:15]:
        native = win32_rect(info.handle)
        if native is None:
            continue
        checked += 1
        same = native == info.rect
        match += int(same)
        flag = "IGUAL" if same else "DIFERENTE"
        print(f"  handle={info.handle} pywinctl={info.rect} win32={native} {flag}")

    print("== veredito ==")
    if checked == 0:
        print("  sem janelas Win32 para comparar")
    elif match == checked:
        print(
            f"  pywinctl == Win32 em {match}/{checked} janelas: ambos em espaco FISICO neste "
            "processo DPI-aware. O conversor identidade e o correto."
        )
    else:
        print(
            f"  pywinctl diverge de Win32 em {checked - match}/{checked} janelas: revisar "
            "conversao logico->fisico por monitor (ver dpr acima)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
