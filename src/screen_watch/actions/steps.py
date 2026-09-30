"""Manipulacao pura da lista de passos crus do editor de acoes (F5).

Opera sobre `list[dict]` (os passos como aparecem em `overrides.actions`) e
devolve sempre uma lista **nova**; nenhuma funcao muta a lista recebida. Nao
depende de Qt nem de I/O: a GUI importa so estas funcoes e reassina
`self._steps`, mantendo o modelo como fonte unica da verdade.
"""

from __future__ import annotations

import copy


def move_step(steps: list[dict], index: int, delta: int) -> list[dict]:
    """Copia de `steps` com o item em `index` deslocado `delta` posicoes.

    O destino fica preso a `[0, len(steps) - 1]`. Indice fora da faixa ou
    `delta == 0` devolve apenas uma copia inalterada.
    """
    result = list(steps)
    if not 0 <= index < len(result) or delta == 0:
        return result
    target = min(max(index + delta, 0), len(result) - 1)
    if target == index:
        return result
    item = result.pop(index)
    result.insert(target, item)
    return result


def duplicate_step(steps: list[dict], index: int) -> list[dict]:
    """Copia de `steps` com um deep-copy do item em `index` logo depois dele."""
    result = list(steps)
    if not 0 <= index < len(result):
        return result
    result.insert(index + 1, copy.deepcopy(result[index]))
    return result


def replace_step(steps: list[dict], index: int, step: dict) -> list[dict]:
    """Copia de `steps` trocando o item em `index` por um deep-copy de `step`."""
    result = list(steps)
    if not 0 <= index < len(result):
        return result
    result[index] = copy.deepcopy(step)
    return result


def remove_step(steps: list[dict], index: int) -> list[dict]:
    """Copia de `steps` sem o item em `index` (inalterada se fora da faixa)."""
    result = list(steps)
    if not 0 <= index < len(result):
        return result
    del result[index]
    return result
