"""Dump/load do JSON de selecao de ROI (doc, secao 7.3).

Gerado pela GUI; nao precisa de comentarios. `window_handle` e a chave de lookup;
`roi_relative` e a fonte de verdade para reconstruir a ROI a cada tick.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from screen_watch.config.schema import AlertOptions, CompareOptions, TargetConfig

Rect = tuple[int, int, int, int]
Point = tuple[int, int]

SELECTION_VERSION = 1


@dataclass(frozen=True)
class Selection:
    window_handle: int
    origin_at_selection: Point
    roi_relative: Rect
    version: int = SELECTION_VERSION
    window_title_hint: str = ""
    app_name: str = ""
    mode: str = "advanced"
    masks: tuple[Rect, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "window_handle": self.window_handle,
            "window_title_hint": self.window_title_hint,
            "app_name": self.app_name,
            "origin_at_selection": list(self.origin_at_selection),
            "roi_relative": list(self.roi_relative),
            "mode": self.mode,
            "masks": [list(m) for m in self.masks],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Selection":
        for field_name in ("version", "window_handle", "origin_at_selection", "roi_relative"):
            if field_name not in raw:
                raise ValueError(f"selecao sem campo obrigatorio: {field_name!r}")
        vertex = raw["version"]
        if int(vertex) != SELECTION_VERSION:
            raise ValueError(f"versao de selecao nao suportada: {vertex!r}")
        return cls(
            version=int(vertex),
            window_handle=int(raw["window_handle"]),
            window_title_hint=str(raw.get("window_title_hint", "")),
            app_name=str(raw.get("app_name", "")),
            origin_at_selection=(int(raw["origin_at_selection"][0]), int(raw["origin_at_selection"][1])),
            roi_relative=(
                int(raw["roi_relative"][0]),
                int(raw["roi_relative"][1]),
                int(raw["roi_relative"][2]),
                int(raw["roi_relative"][3]),
            ),
            mode=str(raw.get("mode", "advanced")),
            masks=tuple(
                (int(m[0]), int(m[1]), int(m[2]), int(m[3])) for m in (raw.get("masks") or [])
            ),
        )


def dump_selection(path: str | Path, selection: Selection) -> None:
    Path(path).write_text(
        json.dumps(selection.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_selection(path: str | Path) -> Selection:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("JSON de selecao deve ser um objeto")
    return Selection.from_dict(raw)


def to_target_config(
    selection: Selection,
    *,
    name: str,
    alerts: tuple[AlertOptions, ...] = (),
    poll_interval_s: float = 2.0,
    rearm: bool = True,
    compare_options: CompareOptions | None = None,
    mode: str | None = None,
) -> TargetConfig:
    """Converte a selecao gravada pelo overlay em `TargetConfig` (plano, Etapa C).

    Usado pelo `run --selection` e pela GUI. `name` vem do arquivo de selecao; o
    modo pode ser sobrescrito pelo seletor da GUI.
    """
    return TargetConfig(
        name=name,
        window_handle=selection.window_handle,
        roi_relative=selection.roi_relative,
        origin_at_selection=selection.origin_at_selection,
        window_title_hint=selection.window_title_hint,
        mode=mode or selection.mode,
        poll_interval_s=poll_interval_s,
        rearm=rearm,
        masks=selection.masks,
        compare_options=compare_options or CompareOptions(),
        alerts=alerts,
    )
