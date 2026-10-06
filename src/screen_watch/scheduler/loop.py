"""Loop de monitoramento cancelavel (doc, secoes 3.5, 7.4, 16).

`threading.Thread` + `Event.wait(timeout)`. O tempo de trabalho e subtraido do
intervalo, garantindo cadencia estavel. Nenhum `time.sleep` no loop.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from screen_watch.capture.frame import Frame, Rect
from screen_watch.capture.geometry import intersect_rect
from screen_watch.capture.mask import apply_mask
from screen_watch.capture.resolver import LogicalToPhysical, resolve

log = logging.getLogger(__name__)

WindowLookup = Callable[[int], object]
Sink = Callable[[Frame], None]
EventSink = Callable[[str, dict], None]
DeadlineProvider = Callable[[], float | None]


@dataclass(frozen=True)
class MonitorTarget:
    window_handle: int
    roi_relative: Rect
    masks: tuple[Rect, ...] = ()
    logical_to_physical: LogicalToPhysical | None = None


def _default_window_lookup(handle: int) -> object:
    from screen_watch.platform.window import find_window_by_handle  # noqa: PLC0415

    return find_window_by_handle(handle)


def _default_backend_factory() -> object:
    from screen_watch.capture.mss_backend import MssCaptureBackend  # noqa: PLC0415

    return MssCaptureBackend()


@dataclass
class MonitorLoop:
    sink: Sink
    interval_s: float = 2.0
    target: MonitorTarget | None = None
    backend: object | None = None
    window_lookup: WindowLookup = field(default=_default_window_lookup)
    on_event: EventSink | None = None
    on_error: Callable[[Exception], None] | None = None
    backend_factory: Callable[[], object] = _default_backend_factory
    deadline_provider: DeadlineProvider | None = None

    def __post_init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sequence = 0
        self._last_event: str | None = None
        self._last_error: str | None = None

    # -- ciclo de vida -----------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="monitor-loop", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def join(self, timeout: float | None = None) -> None:
        """Bloqueia ate a thread encerrar (ou ate `timeout`)."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # -- interno -----------------------------------------------------------
    def _next_wait(self, elapsed: float = 0.0) -> float:
        """Espera do proximo tick, encurtada pelo proximo deadline armado.

        O intervalo normal subtrai o tempo de trabalho; se houver um gatilho de
        tempo armado mais proximo (doc, secao 3.5/11.4), a espera e reduzida
        (piso de 50 ms) para o disparo ser pontual. Excecao do provider nunca
        derruba o loop.
        """
        wait = max(0.0, self.interval_s - elapsed)
        if self.deadline_provider is not None:
            try:
                delay = self.deadline_provider()
            except Exception:  # pragma: no cover - defesa, deadline nunca quebra
                delay = None
            if delay is not None:
                wait = min(wait, max(0.05, float(delay)))
        return wait

    def _run(self) -> None:
        backend = self.backend or self.backend_factory()
        try:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                frame = None
                try:
                    frame = self._tick(backend)
                except Exception as exc:
                    self._error(exc)
                # O sink (comparacao) fica FORA do try de captura (doc, secao 7.4/14.5).
                if frame is not None:
                    try:
                        self.sink(frame)
                    except Exception as exc:
                        self._error(exc)
                elapsed = time.perf_counter() - t0
                self._stop.wait(self._next_wait(elapsed))
        finally:
            try:
                backend.close()
            except Exception:
                pass

    def _tick(self, backend: object) -> Frame | None:
        target = self.target
        if target is None:
            self._emit("target_unavailable", {"reason": "no_target"})
            return None

        info = self.window_lookup(target.window_handle)
        if info is None or not getattr(info, "exists", False):
            self._emit("target_unavailable", {"reason": "not_found"})
            return None
        if getattr(info, "is_minimized", False):
            self._emit("target_unavailable", {"reason": "minimized"})
            return None

        abs_rect = resolve(
            info, target.roi_relative, logical_to_physical=target.logical_to_physical
        )
        if abs_rect is None:
            self._emit("target_unavailable", {"reason": "roi_out_of_bounds"})
            return None

        abs_rect = self._clip_to_bounds(abs_rect, backend)
        if abs_rect is None:
            return None

        rgb = self._normalize(backend.capture(abs_rect))
        rgb = apply_mask(rgb, target.masks)
        self._sequence += 1
        return Frame(
            rgb=rgb,
            timestamp=time.time(),
            absolute_rect=abs_rect,
            window_rect=info.rect,
            window_handle=info.handle,
            sequence=self._sequence,
        )

    def _clip_to_bounds(self, rect: Rect, backend: object) -> Rect | None:
        """Recorta a ROI contra o desktop virtual do backend (doc 7.2, P5).

        Sem `bounds()` no backend, nao recorta. Emite eventos deduplicados
        (`capture_clipped`/`roi_off_screen`) sem quebrar o loop.
        """
        bounds_getter = getattr(backend, "bounds", None)
        if not callable(bounds_getter):
            return rect
        try:
            bounds = bounds_getter()
        except Exception:
            return rect
        if bounds is None:
            return rect

        clipped = intersect_rect(rect, bounds)
        if clipped is None:
            self._emit("roi_off_screen", {"rect": rect, "bounds": bounds})
            return None
        if clipped != rect:
            self._emit("capture_clipped", {"rect": rect, "clipped": clipped})
        return clipped

    @staticmethod
    def _normalize(rgb: np.ndarray) -> np.ndarray:
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError(f"shape inesperado do frame: {rgb.shape}")
        if rgb.dtype != np.uint8:
            rgb = rgb.astype(np.uint8, copy=False)
        return np.ascontiguousarray(rgb)

    def _emit(self, name: str, payload: dict) -> None:
        if name == self._last_event:
            return
        self._last_event = name
        if self.on_event is not None:
            self.on_event(name, payload)

    def _error(self, exc: Exception) -> None:
        # Deduplica falhas consecutivas identicas (ex.: Tesseract ausente) para
        # nao inundar o log a cada tick; reaparece se o erro mudar.
        message = f"{type(exc).__name__}: {exc}"
        if message == self._last_error:
            return
        self._last_error = message
        if self.on_error is not None:
            self.on_error(exc)
        else:
            log.error("monitoring loop failure: %s", exc)
