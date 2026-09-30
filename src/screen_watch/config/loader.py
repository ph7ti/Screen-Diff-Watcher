"""Carregamento YAML <-> dataclasses (doc, secao 12).

Tokens e segredos nunca ficam no YAML: apenas o nome da variavel de ambiente.
Toda conversao de tipo falha com `ConfigError` de mensagem clara, para o
`validate-config` nao despejar stacktrace.

O YAML v2 e global (perfis). O v1 (`targets:`) ainda carrega por uma versao, com
aviso, e pode ser convertido por `migrate-config`/`migrate_config_dict`.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from screen_watch.actions.plan import ActionError
from screen_watch.actions.plan import parse_actions as _parse_actions_raw
from screen_watch.config.schema import (
    VALID_DAYS,
    VALID_MODES,
    VALID_TIMEZONES,
    AdvancedOptions,
    AlertOptions,
    AppConfig,
    CompareOptions,
    DefaultOptions,
    EvidenceOptions,
    GlobalDefaults,
    HumanizeOptions,
    LightOptions,
    ProfileOptions,
    ScheduleOptions,
    TargetConfig,
    UiOptions,
)

log = logging.getLogger(__name__)

REQUIRED_TARGET_FIELDS = ("name", "window_handle", "roi_relative")
MIN_POLL_INTERVAL_S = 1.0
SUPPORTED_CONFIG_VERSIONS = (1, 2)
_WINDOW_RE = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")

Rect = tuple[int, int, int, int]


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


def _as_rect(value: Any, field_name: str) -> Rect:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ConfigError(f"{field_name} deve ser [x, y, w, h]")
    return tuple(_as_int(v, f"{field_name}[{i}]") for i, v in enumerate(value))  # type: ignore[return-value]


def _as_point(value: Any, field_name: str) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"{field_name} deve ser [x, y]")
    return _as_int(value[0], f"{field_name}[0]"), _as_int(value[1], f"{field_name}[1]")


def _as_mode(value: Any, field_name: str = "mode") -> str:
    mode = _as_str(value, field_name) or "advanced"
    if mode not in VALID_MODES:
        raise ConfigError(f"{field_name} invalido: {mode!r}; use um de {VALID_MODES}")
    return mode


def _as_interval(value: Any, field_name: str = "poll_interval_s") -> float:
    interval = _as_float(value, field_name)
    if interval < MIN_POLL_INTERVAL_S:
        raise ConfigError(f"{field_name} deve ser >= {MIN_POLL_INTERVAL_S} (doc, secao 1.1)")
    return interval


def parse_rects(raw: Any, field_name: str = "masks") -> tuple[Rect, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ConfigError(f"{field_name} deve ser uma lista de [x, y, w, h]")
    return tuple(_as_rect(item, f"{field_name}[]") for item in raw)


def parse_alerts(raw: Any, field_name: str = "alerts") -> tuple[AlertOptions, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ConfigError(f"{field_name} deve ser uma lista")
    return tuple(_parse_alert(item, i, field_name) for i, item in enumerate(raw))


def parse_actions(raw: Any, prefix: str = "actions", mode: str | None = None):
    """Parse de acoes convertendo `ActionError` em `ConfigError`."""
    try:
        return _parse_actions_raw(raw, prefix=prefix, mode=mode)
    except ActionError as exc:
        raise ConfigError(str(exc)) from exc


def parse_overrides(raw: Any) -> dict[str, Any]:
    """Normaliza os `overrides` de uma selecao (doc, secao 12.3).

    Valores ausentes nao entram no dicionario; os presentes sao convertidos e
    validados aqui para nao falhar em runtime. `actions` fica cru (o parse exige
    o mode resolvido, feito em `build_target`).
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("overrides deve ser um mapeamento")
    out: dict[str, Any] = {}
    if raw.get("mode") is not None:
        out["mode"] = _as_mode(raw["mode"], "overrides.mode")
    if raw.get("poll_interval_s") is not None:
        out["poll_interval_s"] = _as_interval(raw["poll_interval_s"], "overrides.poll_interval_s")
    if raw.get("rearm") is not None:
        out["rearm"] = _as_bool(raw["rearm"], "overrides.rearm")
    if raw.get("masks") is not None:
        out["masks"] = parse_rects(raw["masks"], "overrides.masks")
    if raw.get("alerts") is not None:
        out["alerts"] = parse_alerts(raw["alerts"], "overrides.alerts")
    if raw.get("actions") is not None:
        actions_raw = raw["actions"]
        if not isinstance(actions_raw, (list, tuple)):
            raise ConfigError("overrides.actions deve ser uma lista")
        out["actions"] = tuple(actions_raw)
    return out


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


def _parse_alert(raw: Any, index: int, prefix: str = "alerts") -> AlertOptions:
    field = f"{prefix}[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{field} deve ser um mapeamento")
    if "type" not in raw:
        raise ConfigError(f"{field} precisa de 'type'")
    return AlertOptions(
        type=_as_str(raw["type"], f"{field}.type"),
        enabled=_as_bool(raw.get("enabled", True), f"{field}.enabled"),
        severity_min=_as_int(raw.get("severity_min", 1), f"{field}.severity_min"),
        cooldown_s=_as_float(raw.get("cooldown_s", 30.0), f"{field}.cooldown_s"),
        file=_as_str(raw.get("file", "alert.wav"), f"{field}.file"),
        bot_token_env=_as_str(
            raw.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), f"{field}.bot_token_env"
        ),
        chat_id=_as_str(raw.get("chat_id", ""), f"{field}.chat_id"),
        attach_roi=_as_bool(raw.get("attach_roi", True), f"{field}.attach_roi"),
        path=_as_str(raw.get("path", ""), f"{field}.path"),
    )


def _parse_target(raw: Any) -> TargetConfig:
    if not isinstance(raw, dict):
        raise ConfigError("cada target deve ser um mapeamento")
    for field_name in REQUIRED_TARGET_FIELDS:
        if field_name not in raw:
            raise ConfigError(f"target sem campo obrigatorio: {field_name!r}")

    return TargetConfig(
        name=_as_str(raw["name"], "name"),
        window_handle=_as_int(raw["window_handle"], "window_handle"),
        roi_relative=_as_rect(raw["roi_relative"], "roi_relative"),
        origin_at_selection=_as_point(raw.get("origin_at_selection"), "origin_at_selection"),
        window_title_hint=_as_str(raw.get("window_title_hint", ""), "window_title_hint"),
        mode=_as_mode(raw.get("mode", "advanced")),
        poll_interval_s=_as_interval(raw.get("poll_interval_s", 2.0)),
        rearm=_as_bool(raw.get("rearm", True), "rearm"),
        masks=parse_rects(raw.get("masks")),
        compare_options=_parse_compare_options(raw.get("compare_options")),
        alerts=parse_alerts(raw.get("alerts")),
    )


def _parse_humanize(raw: Any) -> HumanizeOptions:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError("defaults.humanize deve ser um mapeamento")
    seed = raw.get("seed")
    options = HumanizeOptions(
        mouse_steps=_as_int(raw.get("mouse_steps", 24), "defaults.humanize.mouse_steps"),
        key_interval_ms=_as_int(raw.get("key_interval_ms", 60), "defaults.humanize.key_interval_ms"),
        jitter_px=_as_int(raw.get("jitter_px", 3), "defaults.humanize.jitter_px"),
        wait_jitter_ms=_as_int(raw.get("wait_jitter_ms", 150), "defaults.humanize.wait_jitter_ms"),
        seed=None if seed is None else _as_int(seed, "defaults.humanize.seed"),
    )
    if options.mouse_steps < 1:
        raise ConfigError("defaults.humanize.mouse_steps deve ser >= 1")
    if options.key_interval_ms < 0 or options.jitter_px < 0 or options.wait_jitter_ms < 0:
        raise ConfigError("defaults.humanize: key_interval_ms/jitter_px/wait_jitter_ms devem ser >= 0")
    return options


def _parse_defaults(raw: Any) -> GlobalDefaults:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError("defaults deve ser um mapeamento")
    return GlobalDefaults(
        mode=_as_mode(raw.get("mode", "advanced"), "defaults.mode"),
        poll_interval_s=_as_interval(raw.get("poll_interval_s", 2.0), "defaults.poll_interval_s"),
        rearm=_as_bool(raw.get("rearm", True), "defaults.rearm"),
        compare_options=_parse_compare_options(raw.get("compare_options")),
        humanize=_parse_humanize(raw.get("humanize")),
    )


def _parse_profile(raw: Any, name: str) -> ProfileOptions:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"profiles.{name} deve ser um mapeamento")
    defaults = _parse_defaults(raw.get("defaults"))
    return ProfileOptions(
        defaults=defaults,
        alerts=parse_alerts(raw.get("alerts"), f"profiles.{name}.alerts"),
        actions=parse_actions(raw.get("actions"), f"profiles.{name}.actions", mode=defaults.mode),
    )


def _parse_evidence(raw: Any) -> EvidenceOptions:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError("evidence deve ser um mapeamento")
    directory = raw.get("dir")
    return EvidenceOptions(
        enabled=_as_bool(raw.get("enabled", False), "evidence.enabled"),
        dir=_as_str(directory, "evidence.dir") if directory else None,
        keep_per_target=_as_int(
            raw.get("keep_per_target", 50), "evidence.keep_per_target"
        ),
        max_total_mb=_as_int(raw.get("max_total_mb", 200), "evidence.max_total_mb"),
        on_baseline=_as_bool(raw.get("on_baseline", True), "evidence.on_baseline"),
        on_change=_as_bool(raw.get("on_change", True), "evidence.on_change"),
        per_step=_as_bool(raw.get("per_step", False), "evidence.per_step"),
    )


def _parse_ui(raw: Any) -> UiOptions:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError("ui deve ser um mapeamento")
    hotkeys_raw = raw.get("hotkeys") or {}
    if not isinstance(hotkeys_raw, dict):
        raise ConfigError("ui.hotkeys deve ser um mapeamento")
    hotkeys = tuple(
        (_as_str(key, "ui.hotkeys"), _as_str(value, f"ui.hotkeys.{key}"))
        for key, value in hotkeys_raw.items()
    )
    durations_raw = raw.get("arm_durations_min", (1, 5, 15, 30))
    if not isinstance(durations_raw, (list, tuple)):
        raise ConfigError("ui.arm_durations_min deve ser uma lista de minutos")
    durations = tuple(_as_int(item, "ui.arm_durations_min[]") for item in durations_raw)
    if any(item <= 0 for item in durations):
        raise ConfigError("ui.arm_durations_min deve conter apenas minutos positivos")
    return UiOptions(hotkeys=hotkeys, arm_durations_min=durations)


def _parse_window(raw: Any, field_name: str) -> str:
    text = _as_str(raw, field_name)
    match = _WINDOW_RE.match(text)
    if match is None:
        raise ConfigError(f"{field_name} deve ser 'HH:MM-HH:MM' (recebido {text!r})")
    hours = (int(match.group(1)), int(match.group(3)))
    minutes = (int(match.group(2)), int(match.group(4)))
    if any(h > 23 for h in hours) or any(m > 59 for m in minutes):
        raise ConfigError(f"{field_name} tem hora/minuto invalido: {text!r}")
    return text


def _parse_schedule(raw: Any) -> ScheduleOptions:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError("schedule deve ser um mapeamento")
    days_raw = raw.get("days") or ()
    windows_raw = raw.get("windows") or ()
    if not isinstance(days_raw, (list, tuple)):
        raise ConfigError("schedule.days deve ser uma lista")
    if not isinstance(windows_raw, (list, tuple)):
        raise ConfigError("schedule.windows deve ser uma lista")
    days = tuple(_as_str(day, "schedule.days[]").lower() for day in days_raw)
    invalid_days = [day for day in days if day not in VALID_DAYS]
    if invalid_days:
        raise ConfigError(
            f"schedule.days invalido(s): {invalid_days}; use um de {VALID_DAYS}"
        )
    windows = tuple(_parse_window(window, "schedule.windows[]") for window in windows_raw)
    timezone = _as_str(raw.get("timezone", "local"), "schedule.timezone") or "local"
    if timezone not in VALID_TIMEZONES:
        raise ConfigError(f"schedule.timezone nao suportado: {timezone!r}")
    return ScheduleOptions(
        enabled=_as_bool(raw.get("enabled", False), "schedule.enabled"),
        days=days,
        windows=windows,
        timezone=timezone,
    )


def _config_v2_from_dict(raw: dict[str, Any]) -> AppConfig:
    profiles_raw = raw.get("profiles")
    if profiles_raw is None:
        raise ConfigError("config v2 precisa de 'profiles'")
    if not isinstance(profiles_raw, dict):
        raise ConfigError("'profiles' deve ser um mapeamento")
    profiles = {
        _as_str(name, "profiles"): _parse_profile(value, _as_str(name, "profiles"))
        for name, value in profiles_raw.items()
    }
    profile = _as_str(raw.get("profile", "default"), "profile") or "default"
    if profile not in profiles:
        raise ConfigError(f"profile inexistente no YAML: {profile!r}")
    return AppConfig(
        version=2,
        profile=profile,
        profiles=profiles,
        evidence=_parse_evidence(raw.get("evidence")),
        ui=_parse_ui(raw.get("ui")),
        schedule=_parse_schedule(raw.get("schedule")),
    )


def config_from_dict(raw: dict[str, Any]) -> AppConfig:
    if not isinstance(raw, dict):
        raise ConfigError("raiz do YAML deve ser um mapeamento")
    version_raw = raw.get("version")
    version: int | None = None
    if version_raw is not None:
        version = _as_int(version_raw, "version")
    if version is not None and version not in SUPPORTED_CONFIG_VERSIONS:
        raise ConfigError(
            f"versao de configuracao nao suportada: {version}; use 1 ou 2 (doc, secao 12)"
        )
    if version == 2:
        return _config_v2_from_dict(raw)

    # v1 legado: so `targets`.
    targets_raw = raw.get("targets")
    if targets_raw is None:
        targets_raw = []
    if not isinstance(targets_raw, (list, tuple)):
        raise ConfigError("'targets' deve ser uma lista")
    if targets_raw:
        log.warning("YAML v1 (targets) detectado; rode 'migrate-config' (doc, secao 12)")
    return AppConfig(
        version=1,
        profile="default",
        targets=tuple(_parse_target(target) for target in targets_raw),
        legacy=True,
    )


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
    """Remove o target `name` do YAML v1 e regrava (atomico, com backup).

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


def _alert_to_dict(alert: AlertOptions) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": alert.type,
        "enabled": alert.enabled,
        "severity_min": alert.severity_min,
        "cooldown_s": alert.cooldown_s,
    }
    if alert.type == "sound":
        data["file"] = alert.file
    elif alert.type == "telegram":
        data.update(
            {
                "bot_token_env": alert.bot_token_env,
                "chat_id": alert.chat_id,
                "attach_roi": alert.attach_roi,
            }
        )
    elif alert.type == "log" and alert.path:
        data["path"] = alert.path
    return data


def _compare_options_to_dict(options: CompareOptions) -> dict[str, Any]:
    return {
        "light": {"threshold": options.light.threshold},
        "default": {"hash_size": options.default.hash_size, "threshold": options.default.threshold},
        "advanced": {
            "similarity_threshold": options.advanced.similarity_threshold,
            "psm": options.advanced.psm,
            "lang": options.advanced.lang,
            "upscale": options.advanced.upscale,
            "tesseract_cmd": options.advanced.tesseract_cmd,
        },
    }


def _default_alert_dicts() -> list[dict[str, Any]]:
    return [
        {"type": "sound", "enabled": True, "severity_min": 1, "cooldown_s": 30, "file": "alert.wav"},
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
    ]


def _default_ui_dict() -> dict[str, Any]:
    return {
        "hotkeys": {
            "arm": "<ctrl>+<alt>+a",
            "disarm": "<ctrl>+<alt>+d",
            "toggle": "<ctrl>+<alt>+<space>",
            "rearm": "<ctrl>+<alt>+r",
            "abort": "<esc>",
        },
        "arm_durations_min": [1, 5, 15, 30],
    }


def _default_schedule_dict() -> dict[str, Any]:
    return {
        "enabled": False,
        "days": ["mon", "tue", "wed", "thu", "fri"],
        "windows": ["08:00-12:00", "13:30-18:00"],
        "timezone": "local",
    }


def _default_evidence_dict() -> dict[str, Any]:
    return {
        "enabled": False,
        "dir": None,
        "keep_per_target": 50,
        "max_total_mb": 200,
        "on_baseline": True,
        "on_change": True,
        "per_step": False,
    }


def _defaults_dict(defaults: GlobalDefaults) -> dict[str, Any]:
    humanize = defaults.humanize
    return {
        "mode": defaults.mode,
        "poll_interval_s": defaults.poll_interval_s,
        "rearm": defaults.rearm,
        "humanize": {
            "mouse_steps": humanize.mouse_steps,
            "key_interval_ms": humanize.key_interval_ms,
            "jitter_px": humanize.jitter_px,
            "wait_jitter_ms": humanize.wait_jitter_ms,
            "seed": humanize.seed,
        },
        "compare_options": _compare_options_to_dict(defaults.compare_options),
    }


def default_config_dict() -> dict[str, Any]:
    return {
        "version": 2,
        "profile": "default",
        "profiles": {
            "default": {
                "defaults": _defaults_dict(GlobalDefaults()),
                "alerts": _default_alert_dicts(),
                "actions": [],
            }
        },
        "ui": _default_ui_dict(),
        "schedule": _default_schedule_dict(),
        "evidence": _default_evidence_dict(),
    }


def migrate_config_dict(raw: dict[str, Any]) -> tuple[dict[str, Any], list[TargetConfig]]:
    """Converte um YAML v1 (`targets`) no dict v2 + os targets a virar selecoes.

    Nao faz I/O. Nomes duplicados abortam a migracao (o arquivo de selecao tem o
    nome do target, entao duplicaria o outro).
    """
    if not isinstance(raw, dict):
        raise ConfigError("raiz do YAML deve ser um mapeamento")
    targets_raw = raw.get("targets")
    if targets_raw is None:
        raise ConfigError("nada a migrar: YAML sem 'targets'")
    if not isinstance(targets_raw, (list, tuple)):
        raise ConfigError("'targets' deve ser uma lista")
    targets = [_parse_target(target) for target in targets_raw]
    names = [target.name for target in targets]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ConfigError(f"nomes de target duplicados: {', '.join(duplicates)}")
    if not targets:
        raise ConfigError("nada a migrar: 'targets' esta vazio")

    first = targets[0]
    new_dict = {
        "version": 2,
        "profile": "default",
        "profiles": {
            "default": {
                "defaults": _defaults_dict(
                    GlobalDefaults(
                        mode=first.mode,
                        poll_interval_s=first.poll_interval_s,
                        rearm=first.rearm,
                        compare_options=first.compare_options,
                    )
                ),
                "alerts": [_alert_to_dict(alert) for alert in first.alerts],
                "actions": [],
            }
        },
        "ui": _default_ui_dict(),
        "schedule": _default_schedule_dict(),
        "evidence": _default_evidence_dict(),
    }
    return new_dict, targets


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
