"""Etapa 2 da escada (doc, secao 13): ancoragem via pywinctl (Modelo B).

Move a janela e confirme que a ROI segue. Valida DPI e multi-monitor.

Uso:
    python scripts/step2_anchored_roi.py --list
    python scripts/step2_anchored_roi.py --handle 123456 --roi 120,340,400,80
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from screen_watch.platform.dpi import is_wayland, set_dpi_awareness  # noqa: E402

set_dpi_awareness()

import numpy as np  # noqa: E402

from screen_watch.capture.mss_backend import MssCaptureBackend  # noqa: E402
from screen_watch.capture.resolver import resolve  # noqa: E402
from screen_watch.platform.window import find_window_by_handle, list_windows  # noqa: E402


def parse_rect(value: str) -> tuple[int, int, int, int]:
    parts = [int(p) for p in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("use o formato x,y,w,h")
    return (parts[0], parts[1], parts[2], parts[3])


def frame_hash(rgb: np.ndarray) -> str:
    import imagehash
    from PIL import Image

    return str(imagehash.phash(Image.fromarray(rgb), hash_size=8))


def main() -> int:
    parser = argparse.ArgumentParser(description="Etapa 2: ROI ancorada na janela")
    parser.add_argument("--handle", type=int, default=None)
    parser.add_argument("--roi", type=parse_rect, default=(0, 0, 320, 200),
                        help="ROI relativa a origem da janela (x,y,w,h)")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--list", action="store_true", help="apenas lista as janelas e sai")
    args = parser.parse_args()

    if args.list or args.handle is None:
        for info in list_windows():
            x, y, w, h = info.rect
            print(f"{info.handle!s:>12}  {'min' if info.is_minimized else 'ok '}  {x},{y} {w}x{h}  {info.title!r}")
        if args.handle is None:
            print("\ninforme --handle <id> para monitorar")
            return 0

    if is_wayland():
        print("Wayland detectado: mss nao captura. Abortando.")
        return 2

    backend = MssCaptureBackend()
    stop = threading.Event()
    print(f"ancorando ROI {args.roi} na janela {args.handle}; Ctrl+C para sair")
    try:
        while not stop.is_set():
            info = find_window_by_handle(args.handle)
            if info is None:
                print("janela nao encontrada")
                if stop.wait(args.interval):
                    break
                continue
            if info.is_minimized:
                print("janela minimizada (rect e lixo); aguardando")
                if stop.wait(args.interval):
                    break
                continue
            abs_rect = resolve(info, args.roi)
            if abs_rect is None:
                print("ROI degenerada; aguardando")
                if stop.wait(args.interval):
                    break
                continue
            rgb = backend.capture(abs_rect)
            print(
                f"window={info.rect} abs={abs_rect} phash={frame_hash(rgb)} shape={rgb.shape}"
            )
            if stop.wait(args.interval):
                break
    except KeyboardInterrupt:
        pass
    finally:
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
