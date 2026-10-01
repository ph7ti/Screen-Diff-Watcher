"""Dump/load do JSON de selecao de ROI (doc, secao 7.3 e 12.3).

Gerado pela GUI; nao precisa de comentarios. `window_handle` e a chave de lookup;
`roi_relative` e a fonte de verdade para reconstruir a ROI a cada tick.

v2 acrescenta `overrides` opcional: valores que substituem (nao somam) os do
perfil para este alvo. Selecoes v1 continuam carregando sem overrides.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from screen_watch.actions.protocol import ActionSpec
from screen_watch.config.schema import (
    AlertOptions,
    CompareOptions,
    ProfileOptions,
    ScheduleOptions,
    TargetConfig,
    TextWatchOptions,
)
from screen_watch.errors import ConfigError
from screen_watch.naming import MAX_SLUG_LENGTH, slugify

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
    # Nome de exibicao digitado na GUI; o arquivo usa o slug dele (v2 aceita).
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "version": self.version,
            "window_handle": self.window_handle,
            "window_title_hint": self.window_title_hint,
            "app_name": self.app_name,
            "name": self.name,
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
                raise ConfigError(
                    code="selection.missing_field", params={"field": field_name}
                )
        vertex = int(raw["version"])
        if vertex not in SUPPORTED_SELECTION_VERSIONS:
            raise ConfigError(
                code="selection.version_unsupported", params={"value": vertex}
            )
        overrides = raw.get("overrides")
        if overrides is not None and not isinstance(overrides, dict):
            raise ConfigError(code="selection.overrides_not_object")
        return cls(
            version=vertex,
            window_handle=int(raw["window_handle"]),
            window_title_hint=str(raw.get("window_title_hint", "")),
            app_name=str(raw.get("app_name", "")),
            name=str(raw.get("name", "")),
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
        raise ConfigError(code="selection.not_object")
    return Selection.from_dict(raw)


def plan_rename(selections_dir: str | Path, old_path: str | Path, name: str) -> Path:
    """Valida `name` e devolve o destino em `selections_dir` (nao move nada).

    O slug igual ao stem atual devolve o proprio `old_path`: e um no-op em que o
    chamador apenas regrava o `name`. Erros: `selection.name_invalid` (nome sem
    letras/numeros), `selection.name_too_long` (> `MAX_SLUG_LENGTH`) e
    `selection.name_conflict` (ja existe outra selecao com o mesmo slug).
    """
    old = Path(old_path)
    slug = slugify(name, max_len=None)
    if not slug:
        raise ConfigError(code="selection.name_invalid")
    if len(slug) > MAX_SLUG_LENGTH:
        raise ConfigError(
            code="selection.name_too_long", params={"max": MAX_SLUG_LENGTH}
        )
    if slug.casefold() == old.stem.casefold():
        return old
    # Comparacao sem caixa: no Windows o nome do arquivo e case-insensitive e no
    # Linux nao queremos dois arquivos que so diferem por caixa.
    for existing in Path(selections_dir).glob("*.json"):
        if existing.stem.casefold() == slug.casefold():
            raise ConfigError(code="selection.name_conflict", params={"name": slug})
    return Path(selections_dir) / f"{slug}.json"


def rename_selection(
    old_path: str | Path, new_path: str | Path, *, name: str = ""
) -> Selection:
    """Move a selecao para `new_path` gravando `name` (rollback em falha).

    Nunca sobrescreve um arquivo existente. Quando `old_path` e `new_path` sao o
    mesmo arquivo (slug igual, inclusive so caixa), apenas regrava o JSON no
    lugar. Ao final atualiza `state.json:last_selection` se ele apontava para o
    nome antigo.
    """
    old = Path(old_path)
    new = Path(new_path)
    selection = load_selection(old)
    if name:
        selection = replace(selection, name=name)
    same = old.parent == new.parent and old.name.casefold() == new.name.casefold()
    if same:
        dump_selection(old, selection)
        return selection
    if new.exists():
        raise ConfigError(code="selection.name_conflict", params={"name": new.stem})
    try:
        dump_selection(new, selection)
    except OSError as exc:
        raise ConfigError(
            code="selection.rename_failed", params={"error": exc}
        ) from exc
    try:
        old.unlink()
    except OSError as exc:
        try:
            new.unlink(missing_ok=True)  # rollback: nunca deixar dois arquivos
        except OSError:
            pass
        raise ConfigError(
            code="selection.rename_failed", params={"error": exc}
        ) from exc
    _update_last_selection(old.name, new.name)
    return selection


def _update_last_selection(old_file_name: str, new_file_name: str) -> None:
    """Aponta `state.json:last_selection` para o arquivo novo (best-effort)."""
    from screen_watch.platform.paths import load_state, update_state  # noqa: PLC0415

    try:
        current = str(load_state().get("last_selection") or "")
        if current and current.casefold() == old_file_name.casefold():
            update_state(last_selection=new_file_name)
    except OSError:
        pass


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


def override_actions(selection: Selection) -> list[dict[str, Any]]:
    """Acoes cruas definidas em `overrides.actions` (copia; lista vazia se ausente).

    Sao as unicas que a GUI pode editar sem tocar no perfil/YAML; funcionam tambem
    com config v1 (o parse exige apenas o `mode` resolvido).
    """
    overrides = selection.overrides
    if not isinstance(overrides, dict):
        return []
    raw = overrides.get("actions")
    if not isinstance(raw, (list, tuple)):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def set_override_actions(
    selection: Selection, actions: Collection[dict[str, Any]]
) -> Selection:
    """Devolve uma copia da selecao com `overrides.actions` substituido.

    Lista vazia remove a chave (volta a herdar as acoes do perfil). Os demais
    campos de `overrides` sao preservados; sem nenhum, `overrides` volta a None.
    """
    overrides = dict(selection.overrides or {})
    items = list(actions)
    if items:
        overrides["actions"] = items
    else:
        overrides.pop("actions", None)
    return replace(selection, overrides=overrides or None)


def override_text_watch(selection: Selection) -> TextWatchOptions | None:
    """`overrides.text_watch` normalizado (None se ausente).

    `ConfigError` se o texto estiver vazio/invalido (quem chama decide tratar).
    """
    overrides = selection.overrides
    if not isinstance(overrides, dict):
        return None
    raw = overrides.get("text_watch")
    if raw is None:
        return None
    from screen_watch.config.loader import parse_text_watch  # noqa: PLC0415

    return parse_text_watch(raw, "overrides.text_watch")


def set_override_text_watch(
    selection: Selection, watch: TextWatchOptions | None
) -> Selection:
    """Devolve uma copia da selecao com `overrides.text_watch` substituido.

    `None` remove a chave (volta a herdar o `text_watch` do perfil, se houver).
    """
    overrides = dict(selection.overrides or {})
    if watch is None:
        overrides.pop("text_watch", None)
    else:
        overrides["text_watch"] = {
            "text": watch.text,
            "expect": watch.expect,
            "case_sensitive": watch.case_sensitive,
            "ignore_accents": watch.ignore_accents,
        }
    return replace(selection, overrides=overrides or None)


def _resolve_mode(selection: Selection, overrides: dict[str, Any], mode: str | None) -> str:
    from screen_watch.config.schema import VALID_MODES  # noqa: PLC0415

    resolved = mode or overrides.get("mode") or selection.mode
    if resolved not in VALID_MODES:
        raise ConfigError(
            code="config.invalid_mode",
            params={"field": "mode", "value": resolved, "valid": VALID_MODES},
        )
    return resolved


def _actions_for_overrides(overrides: dict[str, Any], profile: ProfileOptions, mode: str):
    """Overrides > perfil, mantendo a validacao OCR/mode (doc, secao 12.3)."""
    from screen_watch.config.loader import parse_actions  # noqa: PLC0415

    actions_raw = overrides.get("actions")
    actions = (
        parse_actions(actions_raw, "overrides.actions", mode=mode)
        if actions_raw is not None
        else profile.actions
    )
    for action in actions:
        if action.needs_ocr and mode != "advanced":
            raise ConfigError(
                code="config.action_text_needs_advanced",
                params={"name": action.name, "mode": mode},
            )
    return actions


def resolve_actions(
    selection: Selection, profile: ProfileOptions, mode: str | None = None
) -> tuple[ActionSpec, ...]:
    """Acoes resolvidas (overrides > perfil) sem aplicar o filtro de sessao."""
    from screen_watch.config.loader import parse_overrides  # noqa: PLC0415

    overrides = parse_overrides(selection.overrides)
    resolved_mode = _resolve_mode(selection, overrides, mode)
    return _actions_for_overrides(overrides, profile, resolved_mode)


def build_target(
    selection: Selection,
    profile: ProfileOptions,
    *,
    name: str,
    mode: str | None = None,
    schedule=None,
    action_filter: Collection[str] | None = None,
) -> TargetConfig:
    """Resolve selecao + perfil (+ overrides) em `TargetConfig` (doc, secao 12.3).

    `overrides` da selecao **substituem** os valores do perfil, nao somam.
    `mode` explicito (seletor da GUI) ganha precedencia sobre ambos.
    `action_filter` (nomes escolhidos na sessao) so reduz a lista; `None` = todas.
    """
    from screen_watch.actions.selection import filter_actions  # noqa: PLC0415
    from screen_watch.config.loader import parse_overrides  # noqa: PLC0415

    defaults = profile.defaults
    overrides = parse_overrides(selection.overrides)
    resolved_mode = _resolve_mode(selection, overrides, mode)
    actions = _actions_for_overrides(overrides, profile, resolved_mode)
    if action_filter is not None:
        actions = filter_actions(actions, action_filter)
    compare_options = _compare_options_with_watch(defaults.compare_options, overrides, resolved_mode)
    return TargetConfig(
        name=name,
        label=selection.name,
        window_handle=selection.window_handle,
        roi_relative=selection.roi_relative,
        origin_at_selection=selection.origin_at_selection,
        window_title_hint=selection.window_title_hint,
        mode=resolved_mode,
        poll_interval_s=overrides.get("poll_interval_s", defaults.poll_interval_s),
        rearm=overrides.get("rearm", defaults.rearm),
        masks=overrides.get("masks", selection.masks),
        compare_options=compare_options,
        alerts=overrides.get("alerts", profile.alerts),
        actions=actions,
        humanize=defaults.humanize,
        schedule=schedule or ScheduleOptions(),
    )


def _compare_options_with_watch(
    compare_options: CompareOptions, overrides: dict[str, Any], mode: str
) -> CompareOptions:
    """Aplica o `text_watch` (override > perfil) ao `advanced` do `CompareOptions`.

    Fora do modo `advanced` o filtro e invalido (`config.text_watch_needs_advanced`);
    o OCR nao roda nos demais modos.
    """
    watch = overrides.get("text_watch")
    if watch is None:
        watch = compare_options.advanced.text_watch
    if watch is None:
        return compare_options
    if mode != "advanced":
        raise ConfigError(
            code="config.text_watch_needs_advanced", params={"mode": mode}
        )
    return replace(
        compare_options, advanced=replace(compare_options.advanced, text_watch=watch)
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
        label=selection.name,
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
