"""Decisao/entrega das acoes depois dos alertas (plano, F2-T6).

Avaliadas so quando `result.changed`; nao alteram o desfecho nem o re-arm dos
alertas. Desarmado grava ensaio; fora do horario grava `suspended_schedule`;
armado executa e audita.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable

from screen_watch.actions.arming import ArmingController
from screen_watch.actions.protocol import ActionSpec
from screen_watch.actions.runner import ActionRunner, describe_step
from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult

log = logging.getLogger(__name__)


def _contains(text: str, token: str, case_sensitive: bool) -> bool:
    if case_sensitive:
        return token in text
    return token.lower() in text.lower()


class ActionDispatcher:
    def __init__(
        self,
        actions: tuple[ActionSpec, ...] | list[ActionSpec],
        *,
        arming: ArmingController,
        runner: ActionRunner,
        target_name: str = "",
        audit=None,
        recorder=None,
        schedule_open: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._actions = tuple(actions)
        self._arming = arming
        self._runner = runner
        self._target_name = target_name
        self._audit = audit
        self._recorder = recorder
        self._schedule_open = schedule_open
        self._clock = clock
        self._last_fire: dict[str, float] = {}

    @property
    def arming(self) -> ArmingController:
        return self._arming

    def is_schedule_open(self) -> bool:
        if self._schedule_open is None:
            return True
        try:
            return bool(self._schedule_open())
        except Exception:  # pragma: no cover - horario nunca deve derrubar o loop
            return True

    def on_result(self, result: ComparisonResult, frame: Frame) -> bool:
        """True se alguma acao executada pediu re-baseline (doc, F2-T4)."""
        if not result.changed:
            return False
        rebaseline = False
        for action in self._actions:
            if self._maybe_run(action, result, frame):
                rebaseline = True
        return rebaseline

    # -- interno -----------------------------------------------------------
    def _maybe_run(self, action: ActionSpec, result: ComparisonResult, frame: Frame) -> bool:
        if not action.enabled:
            return False
        if not self._matches(action, result):
            return False
        now = self._clock()
        if action.cooldown_s and now - self._last_fire.get(action.name, float("-inf")) < action.cooldown_s:
            return False
        self._last_fire[action.name] = now

        if self._schedule_open is not None and not self._schedule_open():
            self._record({"mode": "skipped", "reason": "suspended_schedule", "action": action.name})
            return False

        if not self._arming.is_armed():
            evidence = self._rehearsal_evidence(frame)
            self._record(
                {
                    "mode": "rehearsal",
                    "action": action.name,
                    "steps": [describe_step(step) for step in action.steps],
                    "evidence": evidence,
                }
            )
            return False

        evidence: list[str] = []
        hook = None
        if self._recorder is not None and getattr(self._recorder, "per_step", False):
            hook = lambda index: evidence.append(  # noqa: E731
                str(self._recorder.record_action(frame, self._target_name, index))
            )
        run = self._runner.run(action, frame, arming=self._arming, evidence_hook=hook)
        if self._recorder is not None and not getattr(self._recorder, "per_step", False):
            path = self._recorder.record_action(frame, self._target_name)
            if path:
                evidence.append(str(path))

        payload = {
            "mode": "armed",
            "action": action.name,
            "executed": run.executed,
            "steps": list(run.steps),
            "duration_s": round(run.duration_s, 3),
            "evidence": evidence,
        }
        if run.reason:
            payload["reason"] = run.reason
        self._record(payload)
        return bool(run.executed and action.rebaseline)

    def _matches(self, action: ActionSpec, result: ComparisonResult) -> bool:
        if result.severity < action.effective_severity_min:
            return False
        if not action.needs_ocr:
            return True
        detail = result.detail or {}
        text = str(detail.get("current_text") or "")
        case_sensitive = action.case_sensitive
        if action.text_any and not any(
            _contains(text, token, case_sensitive) for token in action.text_any
        ):
            return False
        if action.text_all and not all(
            _contains(text, token, case_sensitive) for token in action.text_all
        ):
            return False
        if action.text_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            if re.search(action.text_regex, text, flags) is None:
                return False
        return True

    def _rehearsal_evidence(self, frame: Frame) -> list[str]:
        if self._recorder is None:
            return []
        path = self._recorder.record_action(frame, self._target_name)
        return [str(path)] if path else []

    def _record(self, payload: dict) -> None:
        if self._audit is not None:
            self._audit.record(payload)


def build_dispatcher(
    target,
    *,
    recorder=None,
    audit=None,
    schedule_open: Callable[[], bool] | None = None,
    runner: ActionRunner | None = None,
    arming: ArmingController | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> ActionDispatcher | None:
    """Monta o dispatcher a partir de `TargetConfig` (None se nao ha acoes)."""
    actions = getattr(target, "actions", ())
    if not actions:
        return None
    from screen_watch.actions.audit import ActionAudit  # noqa: PLC0415
    from screen_watch.scheduler.schedule import gate  # noqa: PLC0415

    arming = arming or ArmingController()
    runner = runner or ActionRunner(humanize=getattr(target, "humanize", None))
    if schedule_open is None:
        schedule_open = gate(getattr(target, "schedule", None))
    return ActionDispatcher(
        actions,
        arming=arming,
        runner=runner,
        target_name=getattr(target, "name", ""),
        audit=audit if audit is not None else ActionAudit(),
        recorder=recorder,
        schedule_open=schedule_open,
        clock=clock,
    )
