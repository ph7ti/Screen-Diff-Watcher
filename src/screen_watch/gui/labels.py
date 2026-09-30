"""Rotulos de exibicao da GUI (puros, sem Qt; texto via i18n).

Mostram o nome do aplicativo/selecao e a ROI monitorada, no formato
`[origem] nome — ROI x,y LxA — modo`.
"""

from __future__ import annotations

from screen_watch.config.schema import TargetConfig
from screen_watch.i18n import tr
from screen_watch.persistence.selection import Selection


def target_label(target: TargetConfig) -> str:
    x, y, w, h = target.roi_relative
    hint = f" — {target.window_title_hint}" if target.window_title_hint else ""
    return tr(
        "label.target",
        name=target.name,
        hint=hint,
        x=x,
        y=y,
        w=w,
        h=h,
        mode=target.mode,
    )


def selection_label(selection: Selection, stem: str = "") -> str:
    x, y, w, h = selection.roi_relative
    name = (
        selection.app_name
        or selection.window_title_hint
        or stem
        or tr("label.default_name")
    )
    return tr("label.selection", name=name, x=x, y=y, w=w, h=h, mode=selection.mode)
