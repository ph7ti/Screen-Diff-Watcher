"""Carregamento YAML <-> dataclasses (doc, secao 12).

Tokens e segredos nunca ficam no YAML: apenas o nome da variavel de ambiente.
Toda conversao de tipo falha com `ConfigError` de mensagem clara, para o
`validate-config` nao despejar stacktrace.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from screen_watch.config.schema import (
    VALID_MODES,
    AdvancedOptions,
    AlertOptions,
    AppConfig,
    CompareOptions,
    DefaultOptions,
    LightOptions,
    TargetConfig,
)

REQUIRED_TARGET_FIELDS = ("name", "window_handle", "roi_relative")
MIN_POLL_INTERVAL_S = 1.0


class ConfigError(ValueError):
    pass


def _as_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"{field_name} deve ser um inteiro (recebido {value!r})")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field_name} deve ser um inteiro (recebido {value!r})") from exc


def _as_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ConfigError(f"{field_name} deve ser um numero (recebido {value!r})")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field_name} deve ser um numero (recebido {value!r})") from exc


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ConfigError(f"{field_name} deve ser true/false (recebido {value!r})")


def _as_str(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    raise ConfigError(f"{field_name} deve ser texto (recebido {value!r})")


def _as_rect(value: Any, field_name: str) -> tuple[int, int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ConfigError(f"{field_name} deve ser [x, y, w, h]")
    return tuple(_as_int(v, f"{field_name}[{i}]") for i, v in enumerate(value))  # type: ignore[return-value]


def _as_point(value: Any, field_name: str) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"{field_name} deve ser [x, y]")
    return _as_int(value[0], f"{field_name}[0]"), _as_int(value[1], f"{field_name}[1]")


def _parse_compare_options(raw: Any) -> CompareOptions:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError("compare_options deve ser um mapeamento")
    light = raw.get("light") or {}
    default = raw.get("default") or {}
    advanced = raw.get("advanced") or {}
    for name, section in (("light", light), ("default", default), ("advanced", advanced)):
        if not isinstance(section, dict):
            raise ConfigError(f"compare_options.{name} deve ser um mapeamento")

    tesseract_cmd = advanced.get("tesseract_cmd")
    return CompareOptions(
        light=LightOptions(
            threshold=_as_float(light.get("threshold", 12.0), "compare_options.light.threshold")
        ),
        default=DefaultOptions(
            hash_size=_as_int(default.get("hash_size", 8), "compare_options.default.hash_size"),
            threshold=_as_int(default.get("threshold", 6), "compare_options.default.threshold"),
        ),
        advanced=AdvancedOptions(
            similarity_threshold=_as_float(
                advanced.get("similarity_threshold", 0.92),
                "compare_options.advanced.similarity_threshold",
            ),
            psm=_as_int(advanced.get("psm", 6), "compare_options.advanced.psm"),
            lang=_as_str(advanced.get("lang", "por+eng"), "compare_options.advanced.lang"),
            upscale=_as_int(advanced.get("upscale", 2), "compare_options.advanced.upscale"),
            tesseract_cmd=(
                _as_str(tesseract_cmd, "compare_options.advanced.tesseract_cmd")
                if tesseract_cmd
                else None
            ),
        ),
    )


def _parse_alert(raw: Any, index: int) -> AlertOptions:
    prefix = f"alerts[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{prefix} deve ser um mapeamento")
    if "type" not in raw:
        raise ConfigError(f"{prefix} precisa de 'type'")
    return AlertOptions(
        type=_as_str(raw["type"], f"{prefix}.type"),
        enabled=_as_bool(raw.get("enabled", True), f"{prefix}.enabled"),
        severity_min=_as_int(raw.get("severity_min", 1), f"{prefix}.severity_min"),
        cooldown_s=_as_float(raw.get("cooldown_s", 30.0), f"{prefix}.cooldown_s"),
        file=_as_str(raw.get("file", "alert.wav"), f"{prefix}.file"),
        bot_token_env=_as_str(
            raw.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), f"{prefix}.bot_token_env"
        ),
        chat_id=_as_str(raw.get("chat_id", ""), f"{prefix}.chat_id"),
        attach_roi=_as_bool(raw.get("attach_roi", True), f"{prefix}.attach_roi"),
        path=_as_str(raw.get("path", ""), f"{prefix}.path"),
    )


def _parse_target(raw: Any) -> TargetConfig:
    if not isinstance(raw, dict):
        raise ConfigError("cada target deve ser um mapeamento")
    for field_name in REQUIRED_TARGET_FIELDS:
        if field_name not in raw:
            raise ConfigError(f"target sem campo obrigatorio: {field_name!r}")

    mode = _as_str(raw.get("mode", "advanced"), "mode") or "advanced"
    if mode not in VALID_MODES:
        raise ConfigError(f"mode invalido: {mode!r}; use um de {VALID_MODES}")

    poll_interval_s = _as_float(raw.get("poll_interval_s", 2.0), "poll_interval_s")
    if poll_interval_s < MIN_POLL_INTERVAL_S:
        raise ConfigError(f"poll_interval_s deve ser >= {MIN_POLL_INTERVAL_S} (doc, secao 1.1)")

    masks_raw = raw.get("masks") or []
    alerts_raw = raw.get("alerts") or []
    if not isinstance(masks_raw, (list, tuple)):
        raise ConfigError("masks deve ser uma lista de [x, y, w, h]")
    if not isinstance(alerts_raw, (list, tuple)):
        raise ConfigError("alerts deve ser uma lista")

    return TargetConfig(
        name=_as_str(raw["name"], "name"),
        window_handle=_as_int(raw["window_handle"], "window_handle"),
        roi_relative=_as_rect(raw["roi_relative"], "roi_relative"),
        origin_at_selection=_as_point(raw.get("origin_at_selection"), "origin_at_selection"),
        window_title_hint=_as_str(raw.get("window_title_hint", ""), "window_title_hint"),
        mode=mode,
        poll_interval_s=poll_interval_s,
        rearm=_as_bool(raw.get("rearm", True), "rearm"),
        masks=tuple(_as_rect(m, "masks[]") for m in masks_raw),
        compare_options=_parse_compare_options(raw.get("compare_options")),
        alerts=tuple(_parse_alert(a, i) for i, a in enumerate(alerts_raw)),
    )


def config_from_dict(raw: dict[str, Any]) -> AppConfig:
    if not isinstance(raw, dict):
        raise ConfigError("raiz do YAML deve ser um mapeamento")
    targets_raw = raw.get("targets") or []
    if not isinstance(targets_raw, (list, tuple)):
        raise ConfigError("'targets' deve ser uma lista")
    return AppConfig(targets=tuple(_parse_target(t) for t in targets_raw))


def load_config_dict(path: str | Path) -> dict[str, Any]:
    """Le o YAML cru (sem validar targets), preservando as demais chaves."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"arquivo de configuracao nao encontrado: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML invalido: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("raiz do YAML deve ser um mapeamento")
    return raw


def load_config(path: str | Path) -> AppConfig:
    return config_from_dict(load_config_dict(path))


def remove_target_from_config(path: str | Path, name: str) -> bool:
    """Remove o target `name` do YAML e regrava (atomico, com backup).

    Recarrega do disco antes de regravar (doc 12.4). Devolve False se nao existir.
    """
    raw = load_config_dict(path)
    targets = raw.get("targets") or []
    if not isinstance(targets, (list, tuple)):
        raise ConfigError("'targets' deve ser uma lista")
    remaining = [
        target
        for target in targets
        if not (isinstance(target, dict) and str(target.get("name")) == name)
    ]
    if len(remaining) == len(targets):
        return False
    raw["targets"] = remaining
    save_config(path, raw)
    return True


def default_config_dict() -> dict[str, Any]:
    return {
        "targets": [
            {
                "name": "painel_estoque",
                "window_handle": 0,
                "window_title_hint": "ERP - Estoque",
                "origin_at_selection": [0, 0],
                "roi_relative": [120, 340, 400, 80],
                "mode": "advanced",
                "poll_interval_s": 2.0,
                "rearm": True,
                "masks": [],
                "compare_options": {
                    "light": {"threshold": 12.0},
                    "default": {"hash_size": 8, "threshold": 6},
                    "advanced": {
                        "similarity_threshold": 0.92,
                        "psm": 6,
                        "lang": "por+eng",
                        "upscale": 2,
                        "tesseract_cmd": None,
                    },
                },
                "alerts": [
                    {
                        "type": "sound",
                        "enabled": True,
                        "severity_min": 1,
                        "cooldown_s": 30,
                        "file": "alert.wav",
                    },
                    {"type": "popup", "enabled": True, "severity_min": 1, "cooldown_s": 30},
                    {
                        "type": "telegram",
                        "enabled": True,
                        "severity_min": 2,
                        "cooldown_s": 60,
                        "bot_token_env": "TELEGRAM_BOT_TOKEN",
                        "chat_id": "123456789",
                        "attach_roi": True,
                    },
                ],
            }
        ]
    }


def save_config(path: str | Path, raw: dict[str, Any]) -> None:
    """Grava o YAML de forma atomica, guardando um backup do arquivo anterior.

    O chamador deve recarregar do disco antes de regravar (doc, secao 12.4); isto
    apenas evita arquivo truncado se o processo morrer no meio da escrita.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))

    text = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
