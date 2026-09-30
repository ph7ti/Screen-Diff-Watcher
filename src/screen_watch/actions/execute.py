"""Execucao compartilhada de uma acao armada (reusada pelo dispatcher e pelo CLI/GUI).

Extrai o padrao "rodar uma acao + coletar evidencias" usado tanto pelo
`ActionDispatcher` (sessao de monitoramento) quanto pelo `once.run_actions`
(`test-action` e botao da GUI), evitando divergencia na estrutura da auditoria.
"""

from __future__ import annotations

from screen_watch.actions.arming import ArmingController
from screen_watch.actions.protocol import ActionSpec
from screen_watch.actions.runner import ActionRunner, ActionRunResult
from screen_watch.capture.frame import Frame


def run_armed_action(
    action: ActionSpec,
    frame: Frame,
    *,
    runner: ActionRunner,
    arming: ArmingController,
    recorder: object | None,
    target_name: str,
) -> tuple[ActionRunResult, list[str]]:
    """Executa `action` armada e coleta as evidencias (caminhos de PNG).

    Com `recorder.per_step`, grava uma evidencia por passo; senao, uma unica ao
    final. Devolve o `ActionRunResult` e a lista de caminhos gravados.
    """
    evidence: list[str] = []
    hook = None
    if recorder is not None and getattr(recorder, "per_step", False):
        hook = lambda index: evidence.append(  # noqa: E731
            str(recorder.record_action(frame, target_name, index))
        )
    run = runner.run(action, frame, arming=arming, evidence_hook=hook)
    if recorder is not None and not getattr(recorder, "per_step", False):
        path = recorder.record_action(frame, target_name)
        if path:
            evidence.append(str(path))
    return run, evidence
