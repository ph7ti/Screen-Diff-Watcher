"""Etapa 1 da escada (doc, secao 13): ROI absoluta hardcoded, sem janela, sem GUI.

Objetivo: validar que a captura funciona e medir o Hz real.

Uso:
    python scripts/step1_absolute_roi.py --rect 100,100,320,200 --interval 1.0
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from screen_watch.platform.dpi import is_wayland, set_dpi_awareness  # noqa: E402

set_dpi_awareness()

import numpy as np  # noqa: E402

from screen_watch.capture.mss_backend import MssCaptureBackend  # noqa: E402


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
    parser = argparse.ArgumentParser(description="Etapa 1: ROI absoluta")
    parser.add_argument("--rect", type=parse_rect, default=(100, 100, 320, 200))
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    if is_wayland():
        print("Wayland detectado: mss nao captura. Abortando.")
        return 2

    backend = MssCaptureBackend()
    stop = threading.Event()
    print(f"capturando {args.rect} a cada {args.interval}s; Ctrl+C para sair")
    seq = 0
    last = None
    try:
        while not stop.is_set():
            t0 = time.perf_counter()
            rgb = backend.capture(args.rect)
            digest = frame_hash(rgb)
            mean = np.asarray(rgb, dtype=np.float32).mean(axis=(0, 1))
            now = time.perf_counter()
            delta = "" if last is None else f" dt={now - last:.3f}s ({(1.0 / (now - last)):.2f} Hz)"
            last = now
            print(
                f"seq={seq:<5} phash={digest:<18} mean={np.round(mean, 1).tolist()} "
                f"shape={rgb.shape} work={(now - t0) * 1000:.1f}ms{delta}"
            )
            seq += 1
            if stop.wait(args.interval):
                break
    except KeyboardInterrupt:
        pass
    finally:
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
