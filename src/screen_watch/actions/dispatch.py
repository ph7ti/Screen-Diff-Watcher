"""Decisao/entrega das acoes depois dos alertas (plano, F2-T6).

O gatilho `change` e avaliado so quando `result.changed`; os gatilhos de tempo
(`at`/`every`/`after`, doc secao 11.4) sao avaliados em todo frame pos-baseline
via `on_tick`. Nenhum dos caminhos altera o desfecho nem o re-arm dos alertas.
Desarmado grava ensaio (apenas `change`); fora do horario grava
`suspended_schedule`; armado executa e audita.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable

from screen_watch.actions.arming import ArmingController
from screen_watch.actions.execute import run_armed_action
from screen_watch.actions.protocol import ActionSpec
from screen_watch.actions.runner import ActionRunner, describe_step
from screen_watch.actions.triggers import TriggerState, evaluate, next_delay_s
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
        on_event: Callable[[dict], None] | None = None,
        schedule_open: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._actions = tuple(actions)
        self._arming = arming
        self._runner = runner
        self._target_name = target_name
        self._audit = audit
        self._recorder = recorder
        self._on_event = on_event
        self._schedule_open = schedule_open
        self._clock = clock
        self._wall_clock = wall_clock
        self._last_fire: dict[str, float] = {}
        self._trigger_states: dict[str, TriggerState] = {}

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
        """True se alguma acao de mudanca executada pediu re-baseline (doc, F2-T4)."""
        if not result.changed:
            return False
        rebaseline = False
        for action in self._actions:
            if action.trigger != "change":
                continue
            if self._maybe_run(action, result, frame):
                rebaseline = True
        return rebaseline

    def on_tick(self, frame: Frame) -> None:
        """Avalia os gatilhos de tempo (doc, secao 11.4); sem `change` aqui.

        Chamado em todo frame pos-baseline pela sessao, mesmo sem mudanca.
        Desarmado o avaliador e apenas resetado (gatilhos de tempo nao tem
        ensaio); fora do horario a ocorrencia vencida e consumida com auditoria.
        """
        armed_since = self._arming.armed_since
        now_mono = self._clock()
        now_wall = self._wall_clock()
        for action in self._actions:
            if action.trigger == "change":
                continue
            state = self._trigger_states.setdefault(action.name, TriggerState())
            decision = evaluate(
                action,
                state,
                now_wall=now_wall,
                now_mono=now_mono,
                armed_since=armed_since,
            )
            if not action.enabled:
                continue  # o estado avancou; desabilitada nunca dispara/audita
            if decision.missed:
                self._record(
                    {
                        "mode": "skipped",
                        "reason": "missed",
                        "action": action.name,
                        "trigger": action.trigger,
                        "late_s": round(decision.late_s, 3),
                    }
                )
                continue
            if not decision.fire:
                continue
            if (
                action.cooldown_s
                and now_mono - self._last_fire.get(action.name, float("-inf"))
                < action.cooldown_s
            ):
                self._notify(
                    {
                        "mode": "skipped",
                        "reason": "cooldown",
                        "action": action.name,
                        "trigger": action.trigger,
                    }
                )
                continue
            if self._schedule_open is not None and not self._schedule_open():
                self._record(
                    {
                        "mode": "skipped",
                        "reason": "suspended_schedule",
                        "action": action.name,
                        "trigger": action.trigger,
                    }
                )
                continue
            self._last_fire[action.name] = now_mono
            self._execute(action, frame)

    def next_deadline_delay(self) -> float | None:
        """Segundos ate a proxima avaliacao de um gatilho de tempo armado.

        Consumido pelo `MonitorLoop` para encurtar a espera (doc, secao 3.5);
        chamado na mesma thread do loop.
        """
        armed_since = self._arming.armed_since
        if armed_since is None:
            return None
        now_mono = self._clock()
        now_wall = self._wall_clock()
        delays: list[float] = []
        for action in self._actions:
            if action.trigger == "change" or not action.enabled:
                continue
            state = self._trigger_states.setdefault(action.name, TriggerState())
            delay = next_delay_s(
                action,
                state,
                now_wall=now_wall,
                now_mono=now_mono,
                armed_since=armed_since,
            )
            if delay is not None:
                delays.append(delay)
        return min(delays) if delays else None

    # -- interno -----------------------------------------------------------
    def _maybe_run(self, action: ActionSpec, result: ComparisonResult, frame: Frame) -> bool:
        if not action.enabled:
            return False
        if not self._matches(action, result):
            return False
        now = self._clock()
        if action.cooldown_s and now - self._last_fire.get(action.name, float("-inf")) < action.cooldown_s:
            # Efemero (nao grava na auditoria): explica no log ao vivo por que um
            # gatilho foi ignorado, sem poluir o JSONL.
            self._notify(
                {"mode": "skipped", "reason": "cooldown", "action": action.name, "trigger": "change"}
            )
            return False
        self._last_fire[action.name] = now

        if self._schedule_open is not None and not self._schedule_open():
            self._record(
                {
                    "mode": "skipped",
                    "reason": "suspended_schedule",
                    "action": action.name,
                    "trigger": "change",
                }
            )
            return False

        if not self._arming.is_armed():
            evidence = self._rehearsal_evidence(frame)
            self._record(
                {
                    "mode": "rehearsal",
                    "action": action.name,
                    "trigger": "change",
                    "steps": [describe_step(step) for step in action.steps],
                    "evidence": evidence,
                }
            )
            return False

        return self._execute(action, frame)

    def _execute(self, action: ActionSpec, frame: Frame) -> bool:
        """Executa a acao armada e audita; True se ela pediu re-baseline."""
        run, evidence = run_armed_action(
            action,
            frame,
            runner=self._runner,
            arming=self._arming,
            recorder=self._recorder,
            target_name=self._target_name,
        )

        payload = {
            "mode": "armed",
            "action": action.name,
            "trigger": action.trigger,
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
        self._notify(payload)

    def _notify(self, payload: dict) -> None:
        """So o evento efemero (log ao vivo), sem tocar na auditoria."""
        if self._on_event is not None:
            self._on_event(dict(payload))


def build_dispatcher(
    target,
    *,
    recorder=None,
    audit=None,
    on_event: Callable[[dict], None] | None = None,
    schedule_open: Callable[[], bool] | None = None,
    runner: ActionRunner | None = None,
    arming: ArmingController | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
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
        on_event=on_event,
        schedule_open=schedule_open,
        clock=clock,
        wall_clock=wall_clock,
    )
