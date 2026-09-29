"""Resumo legivel das acoes resolvidas (puro; doc, secao 11.4).

Reusa `runner.describe_step` para nao reimplementar a formatacao dos passos. A GUI
usa `format_action` (sem marcador) no checklist; o resumo impresso no start/troca
de contexto usa `describe_action`/`describe_actions` com `[x]`/`[ ]`.
"""

from __future__ import annotations

from collections.abc import Collection

from screen_watch.actions.protocol import STEP_KINDS, ActionSpec
from screen_watch.actions.runner import describe_step


def _number(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _trigger(action: ActionSpec) -> str:
    parts: list[str] = []
    if action.text_any:
        parts.append(f"text_any={list(action.text_any)}")
    if action.text_all:
        parts.append(f"text_all={list(action.text_all)}")
    if action.text_regex:
        parts.append(f"text_regex={action.text_regex!r}")
    if action.case_sensitive:
        parts.append("case_sensitive")
    return ", ".join(parts)


def format_action(action: ActionSpec) -> str:
    """Descricao da acao sem o marcador de selecao (nome, gatilho, limites, passos)."""
    detail = [f"sev>={action.effective_severity_min}", f"cooldown {_number(action.cooldown_s)}s"]
    if action.rebaseline:
        detail.append("rebaseline")
    if not action.enabled:
        detail.append("desabilitada")
    trigger = _trigger(action)
    if trigger:
        detail.append(f"quando: {trigger}")
    steps = ", ".join(describe_step(step) for step in action.steps) or "(sem passos)"
    return f"{action.name} — {', '.join(detail)} — passos: {steps}"


def describe_raw_step(step: dict) -> str:
    """Linha curta de um passo **cru** (dict), usada pelo editor de acoes da GUI."""
    if "activate" in step:
        return "activate"
    kind = next((name for name in STEP_KINDS if name in step), "?")
    params = step.get(kind) or {}
    if kind in ("click", "move"):
        suffix = (
            f" {params.get('button', 'left')}x{params.get('clicks', 1)}"
            if kind == "click"
            else ""
        )
        return (
            f"{kind}: ({params.get('x')},{params.get('y')}) "
            f"ref={params.get('ref', 'roi')}{suffix}"
        )
    if kind == "key":
        return f"key: {params.get('keys', '')}"
    if kind == "type":
        return f"type: {len(str(params.get('text', '')))} char(s)"
    return f"wait: {params.get('ms', 0)}ms"


def describe_action(action: ActionSpec, selected: bool = True) -> str:
    """Uma linha por acao, marcando `[x]`/`[ ]` conforme a selecao da sessao."""
    return f"[{'x' if selected else ' '}] {format_action(action)}"


def describe_actions(
    actions: Collection[ActionSpec], selected_names: Collection[str] | None = None
) -> list[str]:
    """Resumo de todas as acoes; `selected_names=None` marca todas como selecionadas."""
    return [
        describe_action(action, selected_names is None or action.name in selected_names)
        for action in actions
    ]
