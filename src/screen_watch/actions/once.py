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
    from screen_watch.actions.runner import ActionRunner, describe_step  # noqa: PLC0415

    if not target.actions:
        return 1, [f"selecao {target.name!r} nao tem acoes configuradas"]

    lines: list[str] = []
    audit = audit if audit is not None else ActionAudit()
    arming = ArmingController()
    if armed:
        if countdown is not None and not countdown():
            return 1, ["contagem cancelada; nada foi executado"]
        arming.arm()
    runner = ActionRunner(humanize=target.humanize)

    failures = 0
    lines.append(f"alvo={target.name!r} modo={'armado' if armed else 'ensaio (dry-run)'}")
    for action in target.actions:
        if not action.enabled:
            lines.append(f"[desabilitada] {action.name}")
            continue
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
            lines.append(f"[ensaio] {action.name}: {', '.join(descriptions) or '(sem passos)'}")
            continue
        run = runner.run(action, frame, arming=arming)
        payload = {
            "mode": "armed",
            "action": action.name,
            "executed": run.executed,
            "steps": list(run.steps),
            "duration_s": round(run.duration_s, 3),
            "reason": run.reason,
        }
        audit.record(payload)
        status = "ok" if run.executed else f"falhou ({run.reason})"
        lines.append(f"[armado] {action.name}: {status}")
        if not run.executed:
            failures += 1
    lines.append(f"auditoria: {audit.path}")
    return (0 if not failures else 1), lines
