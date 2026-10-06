"""Resumo legivel das acoes resolvidas (puro; doc, secao 11.4).

Reusa `runner.describe_step` para nao reimplementar a formatacao dos passos. A GUI
usa `format_action` (sem marcador) no checklist; o resumo impresso no start/troca
de contexto usa `describe_action`/`describe_actions` com `[x]`/`[ ]`.

O texto exibido (GUI) passa pelo i18n; o CLI imprime o resumo no idioma ativo.
"""

from __future__ import annotations

from collections.abc import Collection

from screen_watch.actions.protocol import STEP_KINDS, ActionSpec
from screen_watch.actions.runner import describe_step
from screen_watch.i18n import tr


def _number(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _change_trigger(action: ActionSpec) -> str:
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


def _time_trigger(action: ActionSpec) -> str:
    if action.trigger == "at":
        text = tr("summary.trigger_at", times=", ".join(action.at))
        if action.days:
            text = f"{text}, {tr('summary.trigger_at_days', days=', '.join(action.days))}"
        return text
    if action.trigger == "every":
        return tr("summary.trigger_every", seconds=_number(action.every_s))
    if action.trigger == "after":
        return tr("summary.trigger_after", seconds=_number(action.after_s))
    return ""


def format_action(action: ActionSpec) -> str:
    """Descricao da acao sem o marcador de selecao (nome, gatilho, limites, passos)."""
    if action.trigger == "change":
        detail = [f"sev>={action.effective_severity_min}", f"cooldown {_number(action.cooldown_s)}s"]
        trigger = _change_trigger(action)
    else:
        detail = [f"cooldown {_number(action.cooldown_s)}s", f"trigger {action.trigger}"]
        trigger = _time_trigger(action)
    if action.rebaseline:
        detail.append("rebaseline")
    if not action.enabled:
        detail.append(tr("summary.disabled"))
    if trigger:
        detail.append(tr("summary.when", trigger=trigger))
    steps = ", ".join(describe_step(step) for step in action.steps) or tr("summary.no_steps")
    return f"{action.name} — {', '.join(detail)} — {tr('summary.steps_prefix')} {steps}"


def describe_raw_step(step: dict) -> str:
    """Linha curta de um passo **cru** (dict), usada pelo editor de acoes da GUI."""
    if "activate" in step:
        return tr("step.activate")
    kind = next((name for name in STEP_KINDS if name in step), "?")
    params = step.get(kind) or {}
    if kind in ("click", "move"):
        if kind == "click":
            return tr(
                "step.click",
                x=params.get("x"),
                y=params.get("y"),
                ref=params.get("ref", "roi"),
                button=params.get("button", "left"),
                clicks=params.get("clicks", 1),
            )
        return tr("step.move", x=params.get("x"), y=params.get("y"), ref=params.get("ref", "roi"))
    if kind == "key":
        return tr("step.key", keys=params.get("keys", ""))
    if kind == "type":
        return tr("step.type", n=len(str(params.get("text", ""))))
    return tr("step.wait", ms=params.get("ms", 0))


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
