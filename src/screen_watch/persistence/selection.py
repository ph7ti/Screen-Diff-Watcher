"""Dump/load do JSON de selecao de ROI (doc, secao 7.3 e 12.3).

Gerado pela GUI; nao precisa de comentarios. `window_handle` e a chave de lookup;
`roi_relative` e a fonte de verdade para reconstruir a ROI a cada tick.

v2 acrescenta `overrides` opcional: valores que substituem (nao somam) os do
perfil para este alvo. Selecoes v1 continuam carregando sem overrides.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from screen_watch.config.schema import (
    AlertOptions,
    CompareOptions,
    ProfileOptions,
    ScheduleOptions,
    TargetConfig,
)

Rect = tuple[int, int, int, int]
Point = tuple[int, int]

SELECTION_VERSION = 2
SUPPORTED_SELECTION_VERSIONS = (1, 2)


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
    overrides: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "version": self.version,
            "window_handle": self.window_handle,
            "window_title_hint": self.window_title_hint,
            "app_name": self.app_name,
            "origin_at_selection": list(self.origin_at_selection),
            "roi_relative": list(self.roi_relative),
            "mode": self.mode,
            "masks": [list(m) for m in self.masks],
        }
        if self.overrides is not None:
            data["overrides"] = self.overrides
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Selection":
        for field_name in ("version", "window_handle", "origin_at_selection", "roi_relative"):
            if field_name not in raw:
                raise ValueError(f"selecao sem campo obrigatorio: {field_name!r}")
        vertex = int(raw["version"])
        if vertex not in SUPPORTED_SELECTION_VERSIONS:
            raise ValueError(f"versao de selecao nao suportada: {vertex!r}")
        overrides = raw.get("overrides")
        if overrides is not None and not isinstance(overrides, dict):
            raise ValueError("'overrides' deve ser um objeto JSON")
        return cls(
            version=vertex,
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
            overrides=overrides,
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


def from_target_config(target: TargetConfig) -> Selection:
    """Converte um `TargetConfig` v1 (YAML `targets`) em selecao v2."""
    return Selection(
        window_handle=target.window_handle,
        origin_at_selection=target.origin_at_selection or (0, 0),
        roi_relative=target.roi_relative,
        window_title_hint=target.window_title_hint,
        mode=target.mode,
        masks=target.masks,
    )


def build_target(
    selection: Selection,
    profile: ProfileOptions,
    *,
    name: str,
    mode: str | None = None,
    schedule=None,
) -> TargetConfig:
    """Resolve selecao + perfil (+ overrides) em `TargetConfig` (doc, secao 12.3).

    `overrides` da selecao **substituem** os valores do perfil, nao somam.
    `mode` explicito (seletor da GUI) ganha precedencia sobre ambos.
    """
    from screen_watch.config.loader import (  # noqa: PLC0415
        ConfigError,
        parse_actions,
        parse_overrides,
    )
    from screen_watch.config.schema import VALID_MODES  # noqa: PLC0415

    defaults = profile.defaults
    overrides = parse_overrides(selection.overrides)
    resolved_mode = mode or overrides.get("mode") or selection.mode
    if resolved_mode not in VALID_MODES:
        raise ConfigError(f"mode invalido: {resolved_mode!r}; use um de {VALID_MODES}")

    actions_raw = overrides.get("actions")
    actions = (
        parse_actions(actions_raw, "overrides.actions", mode=resolved_mode)
        if actions_raw is not None
        else profile.actions
    )
    for action in actions:
        if action.needs_ocr and resolved_mode != "advanced":
            raise ConfigError(
                f"acao {action.name!r}: filtros text_* exigem mode 'advanced' (OCR); "
                f"selecao esta em {resolved_mode!r}"
            )
    return TargetConfig(
        name=name,
        window_handle=selection.window_handle,
        roi_relative=selection.roi_relative,
        origin_at_selection=selection.origin_at_selection,
        window_title_hint=selection.window_title_hint,
        mode=resolved_mode,
        poll_interval_s=overrides.get("poll_interval_s", defaults.poll_interval_s),
        rearm=overrides.get("rearm", defaults.rearm),
        masks=overrides.get("masks", selection.masks),
        compare_options=defaults.compare_options,
        alerts=overrides.get("alerts", profile.alerts),
        actions=actions,
        humanize=defaults.humanize,
        schedule=schedule or ScheduleOptions(),
    )


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
    """Converte a selecao gravada pelo overlay em `TargetConfig`.

    Atalho de baixo nivel; o caminho com perfis/overrides e `build_target`.
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
