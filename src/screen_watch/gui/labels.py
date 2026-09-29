"""Rotulos de exibicao da GUI (puros, sem Qt).

Mostram o nome do aplicativo/selecao e a ROI monitorada, no formato
`[origem] nome — ROI x,y LxA — modo`.
"""

from __future__ import annotations

from screen_watch.config.schema import TargetConfig
from screen_watch.persistence.selection import Selection


def target_label(target: TargetConfig) -> str:
    x, y, w, h = target.roi_relative
    hint = f" — {target.window_title_hint}" if target.window_title_hint else ""
    return f"[YAML] {target.name}{hint} — Região {x},{y} {w}x{h} — {target.mode}"


def selection_label(selection: Selection, stem: str = "") -> str:
    x, y, w, h = selection.roi_relative
    name = selection.app_name or selection.window_title_hint or stem or "selecao"
    return f"Seleção {name} — Região {x},{y} {w}x{h} — {selection.mode}"
