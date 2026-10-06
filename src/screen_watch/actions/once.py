"""Execucao/ensaio avulso das acoes de um target (extraido do CLI, plano Fase C3).

Usado por `test-action` e pelo botao "Executar acao (3s)" da GUI. `countdown` e
opcional e so roda quando `armed`; cancelar (False) aborta com exit 1. Devolve
`(exit_code, linhas)` para o chamador imprimir/mostrar sem acoplar a UI.
"""

from __future__ import annotations

from collections.abc import Callable

from screen_watch.capture.frame import Frame


def run_actions(
    target,
    frame: Frame,
    *,
    armed: bool,
    recorder=None,
    audit=None,
    countdown: Callable[[], bool] | None = None,
) -> tuple[int, list[str]]:
    """Ensaia (`armed=False`) ou executa (`armed=True`) as acoes de `target`."""
    from screen_watch.actions.arming import ArmingController  # noqa: PLC0415
    from screen_watch.actions.audit import ActionAudit  # noqa: PLC0415
    from screen_watch.actions.execute import run_armed_action  # noqa: PLC0415
    from screen_watch.actions.runner import ActionRunner, describe_step  # noqa: PLC0415

    if not target.actions:
        return 1, [f"selection {target.name!r} has no actions configured"]

    lines: list[str] = []
    audit = audit if audit is not None else ActionAudit()
    arming = ArmingController()
    if armed:
        if countdown is not None and not countdown():
            return 1, ["countdown cancelled; nothing was executed"]
        arming.arm()
    runner = ActionRunner(humanize=target.humanize)

    failures = 0
    lines.append(f"target={target.name!r} mode={'armed' if armed else 'rehearsal (dry-run)'}")
    for action in target.actions:
        if not action.enabled:
            lines.append(f"[disabled] {action.name}")
            continue
        if action.trigger != "change":
            # Execucao explicita ignora o gatilho (doc, secao 11.4).
            lines.append(
                f"[trigger] {action.name}: trigger {action.trigger} ignored (explicit run)"
            )
        descriptions = [describe_step(step) for step in action.steps]
        if not arming.is_armed():
            evidence: list[str] = []
            if recorder is not None:
                path = recorder.record_action(frame, target.name)
                if path:
                    evidence.append(str(path))
            audit.record(
                {
                    "mode": "rehearsal",
                    "action": action.name,
                    "steps": descriptions,
                    "evidence": evidence,
                }
            )
            lines.append(f"[rehearsal] {action.name}: {', '.join(descriptions) or '(no steps)'}")
            continue
        run, evidence = run_armed_action(
            action,
            frame,
            runner=runner,
            arming=arming,
            recorder=recorder,
            target_name=target.name,
        )
        payload = {
            "mode": "armed",
            "action": action.name,
            "executed": run.executed,
            "steps": list(run.steps),
            "duration_s": round(run.duration_s, 3),
            "evidence": evidence,
            "reason": run.reason,
        }
        audit.record(payload)
        status = "ok" if run.executed else f"failed ({run.reason})"
        lines.append(f"[armed] {action.name}: {status}")
        if not run.executed:
            failures += 1
    lines.append(f"audit: {audit.path}")
    return (0 if not failures else 1), lines
