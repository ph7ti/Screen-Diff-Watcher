"""Gravacao de evidencias (prints da janela) para auditoria (plano, Fase 1).

O print e da **janela inteira** (sem mascara), recortado contra o desktop virtual
do backend. Falhas apenas logam (`log.warning`); nunca quebram o loop. Retencao
por `keep_per_target` (contagem) e `max_total_mb` (teto total, todos os alvos).
"""

from __future__ import annotations

import logging
import re
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from screen_watch.capture.frame import Frame, Rect
from screen_watch.capture.geometry import intersect_rect
from screen_watch.config.schema import EvidenceOptions

log = logging.getLogger(__name__)

CAPTURES_DIRNAME = "screen_watch"
CAPTURES_SUBDIR = "captures"
_BYTES_PER_MB = 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def default_captures_dir() -> Path:
    return Path(tempfile.gettempdir()) / CAPTURES_DIRNAME / CAPTURES_SUBDIR


def _resolve_dir(directory: str | Path | None) -> Path:
    return Path(directory) if directory else default_captures_dir()


def captures_dir(options: EvidenceOptions | None = None) -> Path:
    """Pasta efetiva das evidencias: `evidence.dir` quando configurado, senao a padrao."""
    return _resolve_dir(getattr(options, "dir", None))


def ensure_captures_dir(options: EvidenceOptions | None = None) -> Path:
    """Como `captures_dir`, mas cria a pasta (com os pais) se ainda nao existir."""
    directory = captures_dir(options)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _default_backend_factory() -> object:
    from screen_watch.capture.mss_backend import MssCaptureBackend  # noqa: PLC0415

    return MssCaptureBackend()


def _safe_name(value: str) -> str:
    cleaned = _SAFE_NAME.sub("_", str(value)).strip("._")
    return cleaned or "target"


class EvidenceRecorder:
    """Grava PNGs por evento (`baseline`/`change`/`action`) e aplica a retencao."""

    def __init__(
        self,
        *,
        backend_factory: Callable[[], object] | None = None,
        dir: str | Path | None = None,
        keep_per_target: int = 50,
        max_total_mb: int = 200,
        on_baseline: bool = True,
        on_change: bool = True,
        per_step: bool = False,
    ) -> None:
        self._backend_factory = backend_factory or _default_backend_factory
        self.base_dir = _resolve_dir(dir)
        self.keep_per_target = max(0, int(keep_per_target))
        self.max_total_mb = max(0, int(max_total_mb))
        self.on_baseline = bool(on_baseline)
        self.on_change = bool(on_change)
        self.per_step = bool(per_step)

    @classmethod
    def from_options(
        cls, options: EvidenceOptions | None = None, *, force_enabled: bool = False
    ) -> "EvidenceRecorder | None":
        """Recorder a partir de `EvidenceOptions`; None quando desabilitado.

        `force_enabled` existe para comandos utilitarios (`test-evidence`,
        `test-action`) que gravam mesmo com `evidence.enabled: false`.
        """
        options = options or EvidenceOptions()
        if not options.enabled and not force_enabled:
            return None
        return cls(
            dir=options.dir,
            keep_per_target=options.keep_per_target,
            max_total_mb=options.max_total_mb,
            on_baseline=options.on_baseline,
            on_change=options.on_change,
            per_step=options.per_step,
        )

    # -- ganchos do runtime ------------------------------------------------
    def record_baseline(self, frame: Frame, target_name: str) -> Path | None:
        if not self.on_baseline:
            return None
        return self.capture(frame, "baseline", target_name)

    def record_change(self, frame: Frame, target_name: str) -> Path | None:
        if not self.on_change:
            return None
        return self.capture(frame, "change", target_name)

    def record_action(self, frame: Frame, target_name: str, step: int = 0) -> Path | None:
        kind = f"action-{step}" if step else "action"
        return self.capture(frame, kind, target_name)

    # -- captura/retencao --------------------------------------------------
    def capture(self, frame: Frame, kind: str, target_name: str) -> Path | None:
        backend = None
        try:
            backend = self._backend_factory()
            rect = self._clip(backend, frame.window_rect)
            if rect is None:
                log.warning(
                    "window off-screen; evidence %r for %r ignored", kind, target_name
                )
                return None
            rgb = backend.capture(rect)
            path = self._new_path(target_name, kind)
            self._write_png(rgb, path)
        except Exception as exc:
            log.warning("failed to write evidence %r for %r: %s", kind, target_name, exc)
            return None
        finally:
            _close_backend(backend)
        self.prune()
        return path

    def _clip(self, backend: object, rect: Rect) -> Rect | None:
        bounds_getter = getattr(backend, "bounds", None)
        if not callable(bounds_getter):
            return rect
        try:
            bounds = bounds_getter()
        except Exception:
            return rect
        if bounds is None:
            return rect
        return intersect_rect(rect, bounds)

    def _new_path(self, target_name: str, kind: str) -> Path:
        directory = self.base_dir / _safe_name(target_name)
        directory.mkdir(parents=True, exist_ok=True)
        millis = int((time.time() % 1) * 1000)
        stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{millis:03d}"
        kind = _safe_name(kind)
        path = directory / f"{stamp}_{kind}.png"
        counter = 1
        while path.exists():
            path = directory / f"{stamp}_{kind}_{counter}.png"
            counter += 1
        return path

    @staticmethod
    def _write_png(rgb, path: Path) -> None:
        from PIL import Image  # noqa: PLC0415

        Image.fromarray(rgb).save(path)

    def prune(self) -> None:
        """Remove os prints mais antigos por alvo e respeita o teto total de MB."""
        try:
            directories = [path for path in self.base_dir.iterdir() if path.is_dir()]
        except OSError as exc:
            log.warning("could not list evidence in %s: %s", self.base_dir, exc)
            return

        remaining: list[Path] = []
        for directory in directories:
            pngs = _sorted_pngs(directory)
            self._prune_count(pngs)
            remaining.extend(_sorted_pngs(directory))
        self._prune_total(remaining)

    def _prune_count(self, pngs: list[Path]) -> None:
        excess = len(pngs) - self.keep_per_target
        for path in pngs[:excess]:
            _unlink(path)

    def _prune_total(self, files: list[Path]) -> None:
        if self.max_total_mb <= 0:
            return
        limit = self.max_total_mb * _BYTES_PER_MB
        sizes = {path: _size(path) for path in files}
        total = sum(sizes.values())
        for path in files:
            if total <= limit:
                break
            if _unlink(path):
                total -= sizes.get(path, 0)


def _sorted_pngs(directory: Path) -> list[Path]:
    try:
        return sorted(directory.glob("*.png"), key=_mtime)
    except OSError:
        return []


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _unlink(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError as exc:  # pragma: no cover - depende de permissao/disco
        log.warning("could not remove evidence %s: %s", path, exc)
        return False


def _close_backend(backend: object | None) -> None:
    if backend is None:
        return
    close = getattr(backend, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # pragma: no cover - depende do backend
            pass
