"""Execucao sincrona de uma acao na thread do loop (plano, F2-T5).

Captura/comparacao pausam durante a sequencia (sem re-entrancia). Antes de cada
passo re-checa `arming`/aborto e, no primeiro passo `activate`, verifica se o foco
continua na janela-alvo (aborta se mudou).
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from screen_watch.actions.arming import ArmingController
from screen_watch.actions.protocol import ActionSpec, ActionStep
from screen_watch.capture.frame import Frame
from screen_watch.config.schema import HumanizeOptions
from screen_watch.platform.input import (
    InputBackend,
    InputUnavailable,
    interpolate_points,
    make_rng,
)

log = logging.getLogger(__name__)

_DEFAULT_HUMANIZE = HumanizeOptions()


class FocusChanged(RuntimeError):
    """O foco saiu da janela-alvo entre o `activate` e o clique."""


@dataclass(frozen=True)
class ActionRunResult:
    action: str
    executed: bool
    steps: tuple[str, ...] = field(default_factory=tuple)
    duration_s: float = 0.0
    reason: str = ""


def describe_step(step: ActionStep) -> str:
    if step.kind == "activate":
        return "activate"
    if step.kind in ("click", "move"):
        suffix = f" {step.button}x{step.clicks}" if step.kind == "click" else ""
        return f"{step.kind}: ({step.x},{step.y}) ref={step.ref}{suffix}"
    if step.kind == "key":
        return f"key: {step.keys}"
    if step.kind == "type":
        return f"type: {len(step.text)} char(s)"
    return f"wait: {step.ms}ms"


def _default_activate(handle: int) -> bool:
    from screen_watch.platform.window import activate_window  # noqa: PLC0415

    return activate_window(handle)


def _default_is_active(handle: int) -> bool:
    from screen_watch.platform.window import is_window_active  # noqa: PLC0415

    return is_window_active(handle)


class ActionRunner:
    def __init__(
        self,
        *,
        backend_factory: Callable[[], InputBackend] | None = None,
        humanize: HumanizeOptions | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        activate: Callable[[int], bool] | None = None,
        is_active: Callable[[int], bool] | None = None,
    ) -> None:
        self._backend_factory = backend_factory
        self.humanize = humanize or _DEFAULT_HUMANIZE
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or make_rng(self.humanize)
        self._activate = activate or _default_activate
        self._is_active = is_active or _default_is_active
        self._backend: InputBackend | None = None
        self._cursor: tuple[int, int] | None = None
        self._fired: dict[str, list[float]] = {}
        self._session_counts: dict[str, int] = {}

    # -- API ---------------------------------------------------------------
    def run(
        self,
        action: ActionSpec,
        frame: Frame,
        *,
        arming: ArmingController,
        evidence_hook: Callable[[int], None] | None = None,
    ) -> ActionRunResult:
        now = self._clock()
        if not self._allow(action, now):
            return ActionRunResult(action.name, False, reason="rate_limited")
        try:
            backend = self._get_backend()
        except InputUnavailable as exc:
            return ActionRunResult(action.name, False, reason=str(exc))

        started = self._clock()
        descriptions: list[str] = []
        reason = ""
        for index, step in enumerate(action.steps):
            if arming.abort_pending():
                reason = "aborted"
                break
            if not arming.is_armed():
                reason = "disarmed_during_run"
                break
            try:
                descriptions.append(self._execute(backend, step, frame))
            except FocusChanged:
                reason = "focus_changed"
                break
            except InputUnavailable as exc:
                reason = str(exc)
                break
            if evidence_hook is not None:
                evidence_hook(index)

        if action.settle_s > 0:
            self._pause(action.settle_s)
        duration = self._clock() - started
        if reason:
            return ActionRunResult(action.name, False, tuple(descriptions), duration, reason)
        self._record_fire(action, self._clock())
        return ActionRunResult(action.name, True, tuple(descriptions), duration)

    # -- passos ------------------------------------------------------------
    def _execute(self, backend: InputBackend, step: ActionStep, frame: Frame) -> str:
        if step.kind == "activate":
            handle = frame.window_handle
            if not self._activate(handle):
                raise FocusChanged(f"nao foi possivel ativar a janela {handle}")
            if not self._is_active(handle):
                raise FocusChanged(f"foco mudou apos ativar a janela {handle}")
            return describe_step(step)
        if step.kind in ("click", "move"):
            point = self._resolve(step, frame)
            self._move(backend, point)
            if step.kind == "click":
                backend.click(point[0], point[1], button=step.button, clicks=step.clicks)
            return describe_step(step)
        if step.kind == "key":
            backend.press(step.keys)
            return describe_step(step)
        if step.kind == "type":
            interval = (
                self.humanize.key_interval_ms if step.interval_ms is None else step.interval_ms
            )
            backend.type_text(step.text, interval_ms=interval)
            return describe_step(step)
        self._pause(step.ms / 1000.0)
        return describe_step(step)

    def _resolve(self, step: ActionStep, frame: Frame) -> tuple[int, int]:
        if step.ref == "roi":
            base = frame.absolute_rect
        elif step.ref == "window":
            base = frame.window_rect
        else:
            base = (0, 0, 0, 0)
        return base[0] + int(step.x or 0), base[1] + int(step.y or 0)

    def _move(self, backend: InputBackend, point: tuple[int, int]) -> None:
        steps = max(1, int(self.humanize.mouse_steps))
        start = self._cursor if self._cursor is not None else point
        for target in interpolate_points(
            start, point, steps, jitter_px=self.humanize.jitter_px, rng=self._rng
        ):
            backend.move(target[0], target[1])
        self._cursor = point

    def _pause(self, seconds: float) -> None:
        jitter = 0.0
        if self.humanize.wait_jitter_ms:
            jitter = self._rng.randint(
                -self.humanize.wait_jitter_ms, self.humanize.wait_jitter_ms
            ) / 1000.0
        self._sleep(max(0.0, seconds + jitter))

    # -- limites -----------------------------------------------------------
    def _get_backend(self) -> InputBackend:
        if self._backend is None:
            factory = self._backend_factory
            if factory is None:
                from screen_watch.platform.input import default_backend  # noqa: PLC0415

                factory = default_backend
            self._backend = factory()
        return self._backend

    def _allow(self, action: ActionSpec, now: float) -> bool:
        if action.max_per_min:
            recent = [t for t in self._fired.get(action.name, []) if now - t < 60.0]
            self._fired[action.name] = recent
            if len(recent) >= action.max_per_min:
                return False
        if action.max_per_session and self._session_counts.get(action.name, 0) >= action.max_per_session:
            return False
        return True

    def _record_fire(self, action: ActionSpec, now: float) -> None:
        recent = [t for t in self._fired.get(action.name, []) if now - t < 60.0]
        recent.append(now)
        self._fired[action.name] = recent
        self._session_counts[action.name] = self._session_counts.get(action.name, 0) + 1
