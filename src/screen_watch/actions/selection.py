"""Selecao por sessao do subconjunto de acoes (plano, Fase B).

Palavras reservadas no CLI: `all`/vazio = todas, `none` = nenhuma. A escolha por
selecao fica em `state.json["action_selection"][stem]`; chave ausente = todas,
lista vazia explicita = nenhuma. `None` nunca e gravado (equivale a todas).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable

from screen_watch.actions.protocol import ActionSpec

ALL = "all"
NONE = "none"
ACTION_SELECTION_KEY = "action_selection"


def parse_action_names(value: str) -> tuple[str, ...] | None:
    """Converte a lista do `--actions`: `all`/vazio -> None (todas), `none` -> ()."""
    text = (value or "").strip()
    if not text or text.lower() == ALL:
        return None
    if text.lower() == NONE:
        return ()
    return tuple(token.strip() for token in text.split(",") if token.strip())


def filter_actions(
    actions: Iterable[ActionSpec], names: Collection[str] | None
) -> tuple[ActionSpec, ...]:
    """Subconjunto de `actions`: `None` = todas, `()` = nenhuma, nomes ignorados se ausentes."""
    if names is None:
        return tuple(actions)
    allowed = set(names)
    return tuple(action for action in actions if action.name in allowed)


def load_action_selection(selection_name: str) -> tuple[str, ...] | None:
    """Nomes salvos para a selecao; `None` = nunca escolhido (todas)."""
    if not selection_name:
        return None
    from screen_watch.platform.paths import load_state  # noqa: PLC0415

    stored = load_state().get(ACTION_SELECTION_KEY)
    if not isinstance(stored, dict):
        return None
    names = stored.get(selection_name)
    if names is None:
        return None
    if not isinstance(names, (list, tuple)):
        return None
    return tuple(str(name) for name in names)


def save_action_selection(selection_name: str, names: Collection[str]) -> None:
    """Grava os nomes escolhidos em `state.json` (lista vazia = nenhuma)."""
    if not selection_name:
        return
    from screen_watch.platform.paths import load_state, update_state  # noqa: PLC0415

    state = load_state()
    stored = state.get(ACTION_SELECTION_KEY)
    mapping = dict(stored) if isinstance(stored, dict) else {}
    mapping[selection_name] = [str(name) for name in names]
    update_state(**{ACTION_SELECTION_KEY: mapping})
