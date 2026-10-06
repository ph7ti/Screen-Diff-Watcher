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
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from screen_watch.actions.plan import ActionError
from screen_watch.actions.plan import parse_actions as _parse_actions_raw
from screen_watch.alerts.template import validate_placeholders
from screen_watch.config.coerce import as_bool, as_float, as_int, as_str
from screen_watch.config.schema import (
    VALID_ALERT_METHODS,
    VALID_ALERT_TYPES,
    VALID_DAYS,
    VALID_MODES,
    VALID_MQTT_QOS,
    VALID_SMTP_SECURITIES,
    VALID_SYSLOG_FACILITIES,
    VALID_SYSLOG_LEVELS,
    VALID_SYSLOG_PROTOCOLS,
    VALID_TEXT_WATCH_EXPECTS,
    AdvancedOptions,
    AlertOptions,
    AppConfig,
    CompareOptions,
    DefaultOptions,
    EscalationOptions,
    EvidenceOptions,
    GlobalDefaults,
    HttpPostOptions,
    HumanizeOptions,
    LightOptions,
    MqttOptions,
    NtfyOptions,
    ProfileOptions,
    ScheduleOptions,
    SmtpOptions,
    SyslogOptions,
    TargetConfig,
    TextWatchOptions,
    UiOptions,
    WebhookOptions,
)
from screen_watch.errors import ConfigError

log = logging.getLogger(__name__)

REQUIRED_TARGET_FIELDS = ("name", "window_handle", "roi_relative")
MIN_POLL_INTERVAL_S = 1.0
SUPPORTED_CONFIG_VERSIONS = (1, 2)
_WINDOW_RE = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")

Rect = tuple[int, int, int, int]

__all__ = ["ConfigError", "load_config"]


def _as_int(value: Any, field_name: str) -> int:
    return as_int(value, field_name, error=ConfigError, prefix="config")


def _as_float(value: Any, field_name: str) -> float:
    return as_float(value, field_name, error=ConfigError, prefix="config")


def _as_bool(value: Any, field_name: str) -> bool:
    return as_bool(value, field_name, error=ConfigError, prefix="config")


def _as_str(value: Any, field_name: str) -> str:
    return as_str(value, field_name, error=ConfigError, prefix="config")


def _as_rect(value: Any, field_name: str) -> Rect:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ConfigError(code="config.not_rect", params={"field": field_name})
    return tuple(_as_int(v, f"{field_name}[{i}]") for i, v in enumerate(value))  # type: ignore[return-value]


def _as_point(value: Any, field_name: str) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(code="config.not_point", params={"field": field_name})
    return _as_int(value[0], f"{field_name}[0]"), _as_int(value[1], f"{field_name}[1]")


def _as_mode(value: Any, field_name: str = "mode") -> str:
    mode = _as_str(value, field_name) or "advanced"
    if mode not in VALID_MODES:
        raise ConfigError(
            code="config.invalid_mode",
            params={"field": field_name, "value": mode, "valid": VALID_MODES},
        )
    return mode


def _as_interval(value: Any, field_name: str = "poll_interval_s") -> float:
    interval = _as_float(value, field_name)
    if interval < MIN_POLL_INTERVAL_S:
        raise ConfigError(
            code="config.interval_too_small",
            params={"field": field_name, "minimum": MIN_POLL_INTERVAL_S},
        )
    return interval


def parse_rects(raw: Any, field_name: str = "masks") -> tuple[Rect, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ConfigError(code="config.rects_not_list", params={"field": field_name})
    return tuple(_as_rect(item, f"{field_name}[]") for item in raw)


def parse_alerts(raw: Any, field_name: str = "alerts") -> tuple[AlertOptions, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ConfigError(code="config.alerts_not_list", params={"field": field_name})
    alerts = [_parse_alert(item, i, field_name) for i, item in enumerate(raw)]
    return _finalize_alert_ids(alerts, field_name)


def _finalize_alert_ids(alerts: list[AlertOptions], field_name: str) -> tuple[AlertOptions, ...]:
    """Atribui `id` (default = tipo; `tipo#n` se repetido) e rejeita `id` explicitamente duplicado.

    Os `id` explicitos sao reservados antes da geracao dos sufixos `tipo#n`, para a
    ordem da lista nao mudar o resultado (um `tipo#n` explicito nao colide por engano).
    """
    explicit = [alert.id for alert in alerts if alert.id]
    duplicates = sorted({value for value in explicit if explicit.count(value) > 1})
    if duplicates:
        raise ConfigError(
            code="config.alert_duplicate_id",
            params={"id": duplicates[0], "field": field_name},
        )
    assigned: set[str] = set(explicit)
    counters: dict[str, int] = {}
    result: list[AlertOptions] = []
    for alert in alerts:
        base = alert.id or alert.type
        uid = base
        if uid in assigned and not alert.id:
            counters[base] = counters.get(base, 1)
            while uid in assigned:
                counters[base] += 1
                uid = f"{base}#{counters[base]}"
        assigned.add(uid)
        result.append(replace(alert, id=uid))
    return tuple(result)


def _as_headers(raw: Any, field_name: str) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ConfigError(code="config.alert_not_mapping", params={"field": field_name})
    return tuple(
        (_as_str(key, field_name), _as_str(value, f"{field_name}.{key}"))
        for key, value in raw.items()
    )


def _as_payload(raw: Any, field_name: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigError(code="config.alert_not_mapping", params={"field": field_name})
    return dict(raw)


def _as_port(value: Any, field_name: str, default: int) -> int:
    port = _as_int(value, field_name) if value is not None else default
    if not 1 <= port <= 65535:
        raise ConfigError(
            code="config.alert_invalid_port", params={"field": field_name, "value": port}
        )
    return port


def _as_timeout(value: Any, field_name: str) -> float:
    return _as_float(value, field_name) if value is not None else 5.0


def _as_url(raw: Any, field_name: str) -> str:
    url = _as_str(raw, field_name)
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        raise ConfigError(code="config.alert_invalid_url", params={"field": field_name})
    try:
        urlsplit(url).port  # valida a porta (ex.: "http://host:80x" levanta ValueError)
    except ValueError:
        raise ConfigError(
            code="config.alert_invalid_url", params={"field": field_name}
        ) from None
    return url


def _validate_payload_options(options_raw: dict[str, Any], field: str) -> None:
    payload = options_raw.get("payload")
    payload_raw = options_raw.get("payload_raw")
    if payload is not None and payload_raw is not None:
        raise ConfigError(code="config.alert_payload_conflict", params={"field": field})
    if payload is not None:
        validate_placeholders(payload, f"{field}.payload")
    if payload_raw is not None:
        validate_placeholders(_as_str(payload_raw, f"{field}.payload_raw"), f"{field}.payload_raw")
    headers = options_raw.get("headers")
    if isinstance(headers, dict):
        validate_placeholders({str(k): v for k, v in headers.items()}, f"{field}.headers")


def _as_method(raw: Any, field: str) -> str:
    method = (_as_str(raw, f"{field}.method") or "POST").upper()
    if method not in VALID_ALERT_METHODS:
        raise ConfigError(
            code="config.alert_invalid_method",
            params={"field": field, "value": method, "valid": VALID_ALERT_METHODS},
        )
    return method


def _parse_webhook_options(raw: Any, field: str) -> WebhookOptions:
    if not isinstance(raw, dict):
        raise ConfigError(code="config.alert_options_not_mapping", params={"field": field})
    url = _as_url(raw.get("url"), f"{field}.url")
    url_env = _as_str(raw.get("url_env", ""), f"{field}.url_env")
    if not url and not url_env:
        raise ConfigError(code="config.alert_missing_url", params={"field": field})
    _validate_payload_options(raw, field)
    return WebhookOptions(
        url=url,
        url_env=url_env,
        method=_as_method(raw.get("method", "POST"), field),
        headers=_as_headers(raw.get("headers"), f"{field}.headers"),
        payload=_as_payload(raw.get("payload"), f"{field}.payload"),
        payload_raw=_as_str(raw.get("payload_raw", ""), f"{field}.payload_raw"),
        timeout_s=_as_timeout(raw.get("timeout_s"), f"{field}.timeout_s"),
        verify_tls=_as_bool(raw.get("verify_tls", True), f"{field}.verify_tls"),
    )


def _parse_http_post_options(raw: Any, field: str) -> HttpPostOptions:
    if not isinstance(raw, dict):
        raise ConfigError(code="config.alert_options_not_mapping", params={"field": field})
    url = _as_url(raw.get("url"), f"{field}.url")
    url_env = _as_str(raw.get("url_env", ""), f"{field}.url_env")
    host = _as_str(raw.get("host", ""), f"{field}.host")
    port_raw = raw.get("port")
    if not url and not url_env and not host:
        raise ConfigError(code="config.alert_missing_url", params={"field": field})
    if host and port_raw is None:
        raise ConfigError(
            code="config.alert_invalid_port", params={"field": f"{field}.port", "value": None}
        )
    port = _as_port(port_raw, f"{field}.port", 0) if port_raw is not None else 0
    _validate_payload_options(raw, field)
    return HttpPostOptions(
        url=url,
        url_env=url_env,
        scheme=(_as_str(raw.get("scheme", "http"), f"{field}.scheme") or "http").lower(),
        host=host,
        port=port,
        path=_as_str(raw.get("path", ""), f"{field}.path"),
        method=_as_method(raw.get("method", "POST"), field),
        headers=_as_headers(raw.get("headers"), f"{field}.headers"),
        payload=_as_payload(raw.get("payload"), f"{field}.payload"),
        payload_raw=_as_str(raw.get("payload_raw", ""), f"{field}.payload_raw"),
        timeout_s=_as_timeout(raw.get("timeout_s"), f"{field}.timeout_s"),
        verify_tls=_as_bool(raw.get("verify_tls", True), f"{field}.verify_tls"),
    )


def _as_severity_map(raw: Any, field: str) -> tuple[tuple[int, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ConfigError(
            code="config.alert_invalid_severity_map",
            params={"field": field, "value": raw, "valid": VALID_SYSLOG_LEVELS},
        )
    items: list[tuple[int, str]] = []
    for key, value in raw.items():
        level = str(_as_str(value, f"{field}.severity_map[{key}]")).lower()
        try:
            severity = int(key)
        except (TypeError, ValueError):
            severity = -1
        if severity not in (0, 1, 2, 3) or level not in VALID_SYSLOG_LEVELS:
            raise ConfigError(
                code="config.alert_invalid_severity_map",
                params={"field": field, "value": raw, "valid": VALID_SYSLOG_LEVELS},
            )
        items.append((severity, level))
    return tuple(sorted(items))


def _parse_syslog_options(raw: Any, field: str) -> SyslogOptions:
    if not isinstance(raw, dict):
        raise ConfigError(code="config.alert_options_not_mapping", params={"field": field})
    host = _as_str(raw.get("host", ""), f"{field}.host")
    if not host:
        raise ConfigError(code="config.alert_missing_host", params={"field": field})
    protocol = (_as_str(raw.get("protocol", "udp"), f"{field}.protocol") or "udp").lower()
    if protocol not in VALID_SYSLOG_PROTOCOLS:
        raise ConfigError(
            code="config.alert_invalid_protocol",
            params={"field": field, "value": protocol, "valid": VALID_SYSLOG_PROTOCOLS},
        )
    facility = (_as_str(raw.get("facility", "local0"), f"{field}.facility") or "local0").lower()
    if facility not in VALID_SYSLOG_FACILITIES:
        raise ConfigError(
            code="config.alert_invalid_facility",
            params={"field": field, "value": facility, "valid": VALID_SYSLOG_FACILITIES},
        )
    payload_raw = raw.get("payload_raw")
    if payload_raw is not None:
        validate_placeholders(_as_str(payload_raw, f"{field}.payload_raw"), f"{field}.payload_raw")
    return SyslogOptions(
        host=host,
        port=_as_port(raw.get("port"), f"{field}.port", 514),
        protocol=protocol,
        facility=facility,
        app_name=_as_str(raw.get("app_name", "screen-diff-watcher"), f"{field}.app_name")
        or "screen-diff-watcher",
        payload_raw=_as_str(payload_raw, f"{field}.payload_raw"),
        severity_map=_as_severity_map(raw.get("severity_map"), f"{field}.severity_map"),
        timeout_s=_as_timeout(raw.get("timeout_s"), f"{field}.timeout_s"),
        append_nul=_as_bool(raw.get("append_nul", False), f"{field}.append_nul"),
    )


def _parse_channel_options(alert_type: str, raw: Any, field: str):
    if alert_type == "webhook":
        return _parse_webhook_options(raw, field)
    if alert_type == "http_post":
        return _parse_http_post_options(raw, field)
    if alert_type == "syslog":
        return _parse_syslog_options(raw, field)
    if alert_type == "ntfy":
        return _parse_ntfy_options(raw, field)
    if alert_type == "smtp":
        return _parse_smtp_options(raw, field)
    if alert_type == "mqtt":
        return _parse_mqtt_options(raw, field)
    return None


def _as_text_list(raw: Any, field: str, code: str = "config.alerts_not_list") -> tuple[str, ...]:
    """Lista de textos nao vazios (tags de ntfy, destinatarios de e-mail)."""
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ConfigError(code=code, params={"field": field, "missing": "list"})
    return tuple(
        value
        for value in (_as_str(item, f"{field}[{index}]") for index, item in enumerate(raw))
        if value
    )


def _as_priority_map(raw: Any, field: str) -> tuple[tuple[int, int], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ConfigError(
            code="config.alert_invalid_priority_map", params={"field": field, "value": raw}
        )
    items: list[tuple[int, int]] = []
    for key, value in raw.items():
        try:
            severity = int(key)
            priority = int(value)
        except (TypeError, ValueError):
            severity, priority = -1, -1
        if severity not in (0, 1, 2, 3) or not 1 <= priority <= 5:
            raise ConfigError(
                code="config.alert_invalid_priority_map", params={"field": field, "value": raw}
            )
        items.append((severity, priority))
    return tuple(sorted(items))


def _parse_ntfy_options(raw: Any, field: str) -> NtfyOptions:
    if not isinstance(raw, dict):
        raise ConfigError(code="config.alert_options_not_mapping", params={"field": field})
    server = _as_url(raw.get("server", "https://ntfy.sh"), f"{field}.server")
    topic = _as_str(raw.get("topic", ""), f"{field}.topic")
    if not topic:
        raise ConfigError(code="config.alert_missing_topic", params={"field": field})
    title = _as_str(raw.get("title", "${message}"), f"{field}.title")
    message = _as_str(raw.get("message", "${message}"), f"{field}.message")
    validate_placeholders({"title": title, "message": message}, field)
    return NtfyOptions(
        server=server.rstrip("/") or "https://ntfy.sh",
        topic=topic,
        token_env=_as_str(raw.get("token_env", ""), f"{field}.token_env"),
        title=title,
        message=message,
        priority_map=_as_priority_map(raw.get("priority_map"), f"{field}.priority_map"),
        tags=_as_text_list(raw.get("tags"), f"{field}.tags"),
        attach_roi=_as_bool(raw.get("attach_roi", False), f"{field}.attach_roi"),
        timeout_s=_as_timeout(raw.get("timeout_s"), f"{field}.timeout_s"),
    )


def _parse_smtp_options(raw: Any, field: str) -> SmtpOptions:
    if not isinstance(raw, dict):
        raise ConfigError(code="config.alert_options_not_mapping", params={"field": field})
    host = _as_str(raw.get("host", ""), f"{field}.host")
    if not host:
        raise ConfigError(code="config.alert_missing_host", params={"field": field})
    from_addr = _as_str(raw.get("from_addr", ""), f"{field}.from_addr")
    if not from_addr:
        raise ConfigError(code="config.alert_missing_from", params={"field": field})
    to = _as_text_list(raw.get("to"), field, code="config.alert_missing_to")
    if not to:
        raise ConfigError(code="config.alert_missing_to", params={"field": field})
    security = (_as_str(raw.get("security", "starttls"), f"{field}.security") or "starttls").lower()
    if security not in VALID_SMTP_SECURITIES:
        raise ConfigError(
            code="config.alert_invalid_security",
            params={"field": field, "value": security, "valid": VALID_SMTP_SECURITIES},
        )
    subject = _as_str(
        raw.get("subject", "[screen-diff-watcher] ${target} sev=${severity}"),
        f"{field}.subject",
    )
    message = _as_str(raw.get("message", "${message}"), f"{field}.message")
    validate_placeholders({"subject": subject, "message": message}, field)
    return SmtpOptions(
        host=host,
        port=_as_port(raw.get("port"), f"{field}.port", 587),
        security=security,
        from_addr=from_addr,
        to=to,
        subject=subject,
        message=message,
        username_env=_as_str(raw.get("username_env", "SMTP_USERNAME"), f"{field}.username_env"),
        password_env=_as_str(raw.get("password_env", "SMTP_PASSWORD"), f"{field}.password_env"),
        attach_roi=_as_bool(raw.get("attach_roi", True), f"{field}.attach_roi"),
        timeout_s=_as_timeout(raw.get("timeout_s"), f"{field}.timeout_s"),
    )


def _parse_mqtt_options(raw: Any, field: str) -> MqttOptions:
    if not isinstance(raw, dict):
        raise ConfigError(code="config.alert_options_not_mapping", params={"field": field})
    host = _as_str(raw.get("host", ""), f"{field}.host")
    if not host:
        raise ConfigError(code="config.alert_missing_host", params={"field": field})
    topic = _as_str(raw.get("topic", ""), f"{field}.topic")
    if not topic:
        raise ConfigError(code="config.alert_missing_topic", params={"field": field})
    tls = _as_bool(raw.get("tls", False), f"{field}.tls")
    default_port = 8883 if tls else 1883
    port_raw = raw.get("port")
    port = _as_port(port_raw, f"{field}.port", default_port) if port_raw is not None else default_port
    qos = _as_int(raw.get("qos", 0), f"{field}.qos")
    if qos not in VALID_MQTT_QOS:
        raise ConfigError(
            code="config.alert_invalid_qos",
            params={"field": field, "value": qos, "valid": VALID_MQTT_QOS},
        )
    payload_raw = raw.get("payload_raw")
    payload = raw.get("payload")
    if payload is not None and payload_raw is not None:
        raise ConfigError(code="config.alert_payload_conflict", params={"field": field})
    if payload_raw is not None:
        validate_placeholders(_as_str(payload_raw, f"{field}.payload_raw"), f"{field}.payload_raw")
    if payload is not None:
        payload = _as_payload(payload, f"{field}.payload")
        validate_placeholders(payload, f"{field}.payload")
    return MqttOptions(
        host=host,
        port=port,
        topic=topic,
        qos=qos,
        retain=_as_bool(raw.get("retain", False), f"{field}.retain"),
        client_id=_as_str(raw.get("client_id", "screen-diff-watcher"), f"{field}.client_id"),
        username_env=_as_str(raw.get("username_env", "MQTT_USERNAME"), f"{field}.username_env"),
        password_env=_as_str(raw.get("password_env", "MQTT_PASSWORD"), f"{field}.password_env"),
        tls=tls,
        payload=payload,
        payload_raw=_as_str(payload_raw, f"{field}.payload_raw"),
        timeout_s=_as_timeout(raw.get("timeout_s"), f"{field}.timeout_s"),
    )


def _parse_alert(raw: Any, index: int, prefix: str = "alerts") -> AlertOptions:
    field = f"{prefix}[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(code="config.alert_not_mapping", params={"field": field})
    if "type" not in raw:
        raise ConfigError(code="config.alert_missing_type", params={"field": field})
    alert_type = _as_str(raw["type"], f"{field}.type")
    if alert_type not in VALID_ALERT_TYPES:
        raise ConfigError(
            code="config.alert_unknown_type",
            params={"field": field, "value": alert_type, "valid": VALID_ALERT_TYPES},
        )
    return AlertOptions(
        type=alert_type,
        enabled=_as_bool(raw.get("enabled", True), f"{field}.enabled"),
        severity_min=_as_int(raw.get("severity_min", 1), f"{field}.severity_min"),
        cooldown_s=_as_float(raw.get("cooldown_s", 30.0), f"{field}.cooldown_s"),
        file=_as_str(raw.get("file", "alert.mp3"), f"{field}.file"),
        bot_token_env=_as_str(
            raw.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), f"{field}.bot_token_env"
        ),
        chat_id=_as_str(raw.get("chat_id", ""), f"{field}.chat_id"),
        attach_roi=_as_bool(raw.get("attach_roi", True), f"{field}.attach_roi"),
        path=_as_str(raw.get("path", ""), f"{field}.path"),
        id=_as_str(raw.get("id", ""), f"{field}.id"),
        options=_parse_channel_options(alert_type, raw.get("options"), field),
    )


def parse_actions(raw: Any, prefix: str = "actions", mode: str | None = None):
    """Parse de acoes convertendo `ActionError` em `ConfigError` (preserva o codigo)."""
    try:
        return _parse_actions_raw(raw, prefix=prefix, mode=mode)
    except ActionError as exc:
        code = getattr(exc, "code", "")
        if not code:
            raise ConfigError(str(exc)) from exc
        raise ConfigError(
            code=code,
            params=getattr(exc, "params", {}),
            detail=getattr(exc, "detail", ""),
        ) from exc


def parse_text_watch(
    raw: Any, field_name: str = "compare_options.advanced.text_watch"
) -> TextWatchOptions:
    """Valida um `text_watch` (YAML do perfil ou `overrides` da selecao)."""
    if not isinstance(raw, dict):
        raise ConfigError(code="config.text_watch_not_mapping", params={"field": field_name})
    text = _as_str(raw.get("text", ""), f"{field_name}.text")
    if not text.strip():
        raise ConfigError(
            code="config.text_watch_text_required", params={"field": field_name}
        )
    expect = (_as_str(raw.get("expect", "appears"), f"{field_name}.expect") or "appears").lower()
    if expect not in VALID_TEXT_WATCH_EXPECTS:
        raise ConfigError(
            code="config.text_watch_invalid_expect",
            params={
                "field": f"{field_name}.expect",
                "value": expect,
                "valid": VALID_TEXT_WATCH_EXPECTS,
            },
        )
    return TextWatchOptions(
        text=text,
        expect=expect,
        case_sensitive=_as_watch_bool(
            raw.get("case_sensitive"), f"{field_name}.case_sensitive", False
        ),
        ignore_accents=_as_watch_bool(
            raw.get("ignore_accents"), f"{field_name}.ignore_accents", True
        ),
    )


def _as_watch_bool(value: Any, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(
            code="config.text_watch_not_bool",
            params={"field": field_name, "value": value},
        )
    return value


def parse_overrides(raw: Any) -> dict[str, Any]:
    """Normaliza os `overrides` de uma selecao (doc, secao 12.3).

    Valores ausentes nao entram no dicionario; os presentes sao convertidos e
    validados aqui para nao falhar em runtime. `actions` fica cru (o parse exige
    o mode resolvido, feito em `build_target`).
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(code="config.overrides_not_mapping")
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
            raise ConfigError(code="config.overrides_actions_not_list")
        out["actions"] = tuple(actions_raw)
    if raw.get("text_watch") is not None:
        out["text_watch"] = parse_text_watch(raw["text_watch"], "overrides.text_watch")
    if raw.get("escalation") is not None:
        out["escalation"] = _parse_escalation(raw["escalation"], "overrides.escalation")
    return out


def _parse_compare_options(raw: Any) -> CompareOptions:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError(code="config.compare_options_not_mapping")
    light = raw.get("light") or {}
    default = raw.get("default") or {}
    advanced = raw.get("advanced") or {}
    for name, section in (("light", light), ("default", default), ("advanced", advanced)):
        if not isinstance(section, dict):
            raise ConfigError(code="config.compare_section_not_mapping", params={"name": name})

    tesseract_cmd = advanced.get("tesseract_cmd")
    text_watch_raw = advanced.get("text_watch")
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
            text_watch=(
                parse_text_watch(text_watch_raw, "compare_options.advanced.text_watch")
                if text_watch_raw is not None
                else None
            ),
        ),
    )


def _parse_target(raw: Any) -> TargetConfig:
    if not isinstance(raw, dict):
        raise ConfigError(code="config.target_not_mapping")
    for field_name in REQUIRED_TARGET_FIELDS:
        if field_name not in raw:
            raise ConfigError(
                code="config.target_missing_field", params={"field": field_name}
            )

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
        raise ConfigError(code="config.humanize_not_mapping")
    seed = raw.get("seed")
    options = HumanizeOptions(
        mouse_steps=_as_int(raw.get("mouse_steps", 24), "defaults.humanize.mouse_steps"),
        key_interval_ms=_as_int(raw.get("key_interval_ms", 60), "defaults.humanize.key_interval_ms"),
        jitter_px=_as_int(raw.get("jitter_px", 3), "defaults.humanize.jitter_px"),
        wait_jitter_ms=_as_int(raw.get("wait_jitter_ms", 150), "defaults.humanize.wait_jitter_ms"),
        seed=None if seed is None else _as_int(seed, "defaults.humanize.seed"),
    )
    if options.mouse_steps < 1:
        raise ConfigError(code="config.humanize_mouse_steps_min")
    if options.key_interval_ms < 0 or options.jitter_px < 0 or options.wait_jitter_ms < 0:
        raise ConfigError(code="config.humanize_non_negative")
    return options


def _parse_escalation(raw: Any, field: str = "defaults.escalation") -> EscalationOptions:
    """Escalacao por perfil/override (doc, secao 11.3); default desligada."""
    if raw is None:
        return EscalationOptions()
    if not isinstance(raw, dict):
        raise ConfigError(code="config.escalation_not_mapping")
    severity_min = _as_int(raw.get("severity_min", 2), f"{field}.severity_min")
    if severity_min < 0:
        raise ConfigError(code="config.escalation_severity_min")
    return EscalationOptions(
        enabled=_as_bool(raw.get("enabled", False), f"{field}.enabled"),
        severity_min=severity_min,
    )


def _parse_defaults(raw: Any) -> GlobalDefaults:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError(code="config.defaults_not_mapping")
    return GlobalDefaults(
        mode=_as_mode(raw.get("mode", "advanced"), "defaults.mode"),
        poll_interval_s=_as_interval(raw.get("poll_interval_s", 2.0), "defaults.poll_interval_s"),
        rearm=_as_bool(raw.get("rearm", True), "defaults.rearm"),
        compare_options=_parse_compare_options(raw.get("compare_options")),
        humanize=_parse_humanize(raw.get("humanize")),
        escalation=_parse_escalation(raw.get("escalation")),
    )


def _parse_profile(raw: Any, name: str) -> ProfileOptions:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError(code="config.profile_not_mapping", params={"name": name})
    defaults = _parse_defaults(raw.get("defaults"))
    return ProfileOptions(
        defaults=defaults,
        alerts=parse_alerts(raw.get("alerts"), f"profiles.{name}.alerts"),
        actions=parse_actions(raw.get("actions"), f"profiles.{name}.actions", mode=defaults.mode),
    )


def _parse_evidence(raw: Any) -> EvidenceOptions:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError(code="config.evidence_not_mapping")
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
        raise ConfigError(code="config.ui_not_mapping")
    hotkeys_raw = raw.get("hotkeys") or {}
    if not isinstance(hotkeys_raw, dict):
        raise ConfigError(code="config.hotkeys_not_mapping")
    hotkeys = tuple(
        (_as_str(key, "ui.hotkeys"), _as_str(value, f"ui.hotkeys.{key}"))
        for key, value in hotkeys_raw.items()
    )
    durations_raw = raw.get("arm_durations_min", (1, 5, 15, 30))
    if not isinstance(durations_raw, (list, tuple)):
        raise ConfigError(code="config.arm_durations_not_list")
    durations = tuple(_as_int(item, "ui.arm_durations_min[]") for item in durations_raw)
    if any(item <= 0 for item in durations):
        raise ConfigError(code="config.arm_durations_positive")
    snooze_raw = raw.get("snooze_minutes", (5, 15, 30, 60))
    if not isinstance(snooze_raw, (list, tuple)):
        raise ConfigError(code="config.snooze_minutes_not_list")
    snooze_minutes = tuple(_as_int(item, "ui.snooze_minutes[]") for item in snooze_raw)
    if any(item <= 0 for item in snooze_minutes):
        raise ConfigError(code="config.snooze_minutes_positive")
    max_sessions = _as_int(raw.get("max_sessions", 4), "ui.max_sessions")
    if not 1 <= max_sessions <= 16:
        raise ConfigError(
            code="config.max_sessions_range", params={"value": max_sessions}
        )
    language = _as_str(raw.get("language", "auto"), "ui.language") or "auto"
    if language != "auto":
        from screen_watch.i18n import (
            available_locales,  # noqa: PLC0415
            normalize_locale,  # noqa: PLC0415
        )

        known = {tag.lower() for tag in available_locales()}
        if normalize_locale(language).lower() not in known:
            log.warning(
                "unknown ui.language %r; falling back to 'auto' (available: %s)",
                language,
                ", ".join(available_locales()),
            )
            language = "auto"
    return UiOptions(
        hotkeys=hotkeys,
        arm_durations_min=durations,
        snooze_minutes=snooze_minutes,
        max_sessions=max_sessions,
        language=language,
    )


def _parse_window(raw: Any, field_name: str) -> str:
    text = _as_str(raw, field_name)
    match = _WINDOW_RE.match(text)
    if match is None:
        raise ConfigError(
            code="config.window_format", params={"field": field_name, "value": text}
        )
    hours = (int(match.group(1)), int(match.group(3)))
    minutes = (int(match.group(2)), int(match.group(4)))
    if any(h > 23 for h in hours) or any(m > 59 for m in minutes):
        raise ConfigError(
            code="config.window_invalid_time", params={"field": field_name, "value": text}
        )
    return text


def _parse_schedule(raw: Any) -> ScheduleOptions:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError(code="config.schedule_not_mapping")
    days_raw = raw.get("days") or ()
    windows_raw = raw.get("windows") or ()
    if not isinstance(days_raw, (list, tuple)):
        raise ConfigError(code="config.schedule_days_not_list")
    if not isinstance(windows_raw, (list, tuple)):
        raise ConfigError(code="config.schedule_windows_not_list")
    days = tuple(_as_str(day, "schedule.days[]").lower() for day in days_raw)
    invalid_days = [day for day in days if day not in VALID_DAYS]
    if invalid_days:
        raise ConfigError(
            code="config.schedule_invalid_days",
            params={"days": invalid_days, "valid": VALID_DAYS},
        )
    windows = tuple(_parse_window(window, "schedule.windows[]") for window in windows_raw)
    return ScheduleOptions(
        enabled=_as_bool(raw.get("enabled", False), "schedule.enabled"),
        days=days,
        windows=windows,
    )


def _config_v2_from_dict(raw: dict[str, Any]) -> AppConfig:
    profiles_raw = raw.get("profiles")
    if profiles_raw is None:
        raise ConfigError(code="config.v2_missing_profiles")
    if not isinstance(profiles_raw, dict):
        raise ConfigError(code="config.profiles_not_mapping")
    profiles = {
        _as_str(name, "profiles"): _parse_profile(value, _as_str(name, "profiles"))
        for name, value in profiles_raw.items()
    }
    profile = _as_str(raw.get("profile", "default"), "profile") or "default"
    if profile not in profiles:
        raise ConfigError(code="config.profile_unknown", params={"name": profile})
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
        raise ConfigError(code="config.root_not_mapping")
    version_raw = raw.get("version")
    version: int | None = None
    if version_raw is not None:
        version = _as_int(version_raw, "version")
    if version is not None and version not in SUPPORTED_CONFIG_VERSIONS:
        raise ConfigError(code="config.version_unsupported", params={"value": version})
    if version == 2:
        return _config_v2_from_dict(raw)

    # v1 legado: so `targets`.
    targets_raw = raw.get("targets")
    if targets_raw is None:
        targets_raw = []
    if not isinstance(targets_raw, (list, tuple)):
        raise ConfigError(code="config.targets_not_list")
    if targets_raw:
        log.warning("legacy v1 YAML (targets) detected; run 'migrate-config' (doc, section 12)")
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
        raise ConfigError(code="config.file_not_found", params={"path": path})
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(code="config.yaml_invalid", params={"error": exc}) from exc
    if not isinstance(raw, dict):
        raise ConfigError(code="config.root_not_mapping")
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
        raise ConfigError(code="config.targets_not_list")
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


def set_profile_sound_file(path: str | Path, profile: str, file: str) -> None:
    """Grava `file` no alerta `sound` do perfil do YAML v2 (doc, secoes 11.2/12.4).

    Cria o alerta com o shape default se o perfil ainda nao tiver um `sound`.
    Recarrega do disco antes de regravar (`save_config` e atomico e guarda
    `config.yaml.bak`), entao qualquer falha de escrita deixa o arquivo original
    intacto. Config v1 e recusada (`config.v1_not_editable`); perfil inexistente
    e `config.profile_unknown`.
    """
    raw = load_config_dict(path)
    if raw.get("version") != 2:
        raise ConfigError(code="config.v1_not_editable", params={"path": str(path)})
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict):
        raise ConfigError(code="config.v2_missing_profiles")
    profile_raw = profiles.get(profile)
    if not isinstance(profile_raw, dict):
        raise ConfigError(code="config.profile_unknown", params={"name": profile})
    alerts = profile_raw.get("alerts")
    if alerts is None:
        alerts = []
        profile_raw["alerts"] = alerts
    if not isinstance(alerts, list):
        raise ConfigError(
            code="config.alerts_not_list",
            params={"field": f"profiles.{profile}.alerts"},
        )
    sound = next(
        (
            alert
            for alert in alerts
            if isinstance(alert, dict) and alert.get("type") == "sound"
        ),
        None,
    )
    if sound is None:
        sound = {"type": "sound", "enabled": True, "severity_min": 1, "cooldown_s": 30}
        alerts.append(sound)
    sound["file"] = file
    save_config(path, raw)


def _webhook_options_to_dict(options: WebhookOptions) -> dict[str, Any]:
    data: dict[str, Any] = {"method": options.method}
    if options.url:
        data["url"] = options.url
    if options.url_env:
        data["url_env"] = options.url_env
    if options.headers:
        data["headers"] = dict(options.headers)
    if options.payload is not None:
        data["payload"] = options.payload
    if options.payload_raw:
        data["payload_raw"] = options.payload_raw
    data["timeout_s"] = options.timeout_s
    data["verify_tls"] = options.verify_tls
    return data


def _http_post_options_to_dict(options: HttpPostOptions) -> dict[str, Any]:
    data: dict[str, Any] = {"method": options.method}
    if options.url:
        data["url"] = options.url
    if options.url_env:
        data["url_env"] = options.url_env
    if options.host:
        data["scheme"] = options.scheme
        data["host"] = options.host
        data["port"] = options.port
    if options.path:
        data["path"] = options.path
    if options.headers:
        data["headers"] = dict(options.headers)
    if options.payload is not None:
        data["payload"] = options.payload
    if options.payload_raw:
        data["payload_raw"] = options.payload_raw
    data["timeout_s"] = options.timeout_s
    data["verify_tls"] = options.verify_tls
    return data


def _syslog_options_to_dict(options: SyslogOptions) -> dict[str, Any]:
    data: dict[str, Any] = {
        "host": options.host,
        "port": options.port,
        "protocol": options.protocol,
        "facility": options.facility,
        "app_name": options.app_name,
        "timeout_s": options.timeout_s,
        "append_nul": options.append_nul,
    }
    if options.payload_raw:
        data["payload_raw"] = options.payload_raw
    if options.severity_map:
        data["severity_map"] = {severity: level for severity, level in options.severity_map}
    return data


def _ntfy_options_to_dict(options: NtfyOptions) -> dict[str, Any]:
    data: dict[str, Any] = {
        "server": options.server,
        "topic": options.topic,
        "token_env": options.token_env,
        "title": options.title,
        "message": options.message,
        "attach_roi": options.attach_roi,
        "timeout_s": options.timeout_s,
    }
    if options.priority_map:
        data["priority_map"] = {severity: priority for severity, priority in options.priority_map}
    if options.tags:
        data["tags"] = list(options.tags)
    return data


def _smtp_options_to_dict(options: SmtpOptions) -> dict[str, Any]:
    return {
        "host": options.host,
        "port": options.port,
        "security": options.security,
        "from_addr": options.from_addr,
        "to": list(options.to),
        "subject": options.subject,
        "message": options.message,
        "username_env": options.username_env,
        "password_env": options.password_env,
        "attach_roi": options.attach_roi,
        "timeout_s": options.timeout_s,
    }


def _mqtt_options_to_dict(options: MqttOptions) -> dict[str, Any]:
    data: dict[str, Any] = {
        "host": options.host,
        "topic": options.topic,
        "qos": options.qos,
        "retain": options.retain,
        "client_id": options.client_id,
        "username_env": options.username_env,
        "password_env": options.password_env,
        "tls": options.tls,
        "timeout_s": options.timeout_s,
    }
    if options.port:
        data["port"] = options.port
    if options.payload is not None:
        data["payload"] = options.payload
    if options.payload_raw:
        data["payload_raw"] = options.payload_raw
    return data


def _alert_to_dict(alert: AlertOptions) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": alert.type,
        "enabled": alert.enabled,
        "severity_min": alert.severity_min,
        "cooldown_s": alert.cooldown_s,
    }
    if alert.id and alert.id != alert.type:
        data["id"] = alert.id
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
    elif alert.type == "webhook" and isinstance(alert.options, WebhookOptions):
        data["options"] = _webhook_options_to_dict(alert.options)
    elif alert.type == "http_post" and isinstance(alert.options, HttpPostOptions):
        data["options"] = _http_post_options_to_dict(alert.options)
    elif alert.type == "syslog" and isinstance(alert.options, SyslogOptions):
        data["options"] = _syslog_options_to_dict(alert.options)
    elif alert.type == "ntfy" and isinstance(alert.options, NtfyOptions):
        data["options"] = _ntfy_options_to_dict(alert.options)
    elif alert.type == "smtp" and isinstance(alert.options, SmtpOptions):
        data["options"] = _smtp_options_to_dict(alert.options)
    elif alert.type == "mqtt" and isinstance(alert.options, MqttOptions):
        data["options"] = _mqtt_options_to_dict(alert.options)
    return data


def _text_watch_to_dict(options: TextWatchOptions) -> dict[str, Any]:
    return {
        "text": options.text,
        "expect": options.expect,
        "case_sensitive": options.case_sensitive,
        "ignore_accents": options.ignore_accents,
    }


def _compare_options_to_dict(options: CompareOptions) -> dict[str, Any]:
    advanced: dict[str, Any] = {
        "similarity_threshold": options.advanced.similarity_threshold,
        "psm": options.advanced.psm,
        "lang": options.advanced.lang,
        "upscale": options.advanced.upscale,
        "tesseract_cmd": options.advanced.tesseract_cmd,
    }
    if options.advanced.text_watch is not None:
        advanced["text_watch"] = _text_watch_to_dict(options.advanced.text_watch)
    return {
        "light": {"threshold": options.light.threshold},
        "default": {"hash_size": options.default.hash_size, "threshold": options.default.threshold},
        "advanced": advanced,
    }


def _default_alert_dicts() -> list[dict[str, Any]]:
    return [
        {"type": "sound", "enabled": True, "severity_min": 1, "cooldown_s": 30, "file": "alert.mp3"},
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
        "snooze_minutes": [5, 15, 30, 60],
        "max_sessions": 4,
        "language": "auto",
    }


def _default_schedule_dict() -> dict[str, Any]:
    return {
        "enabled": False,
        "days": ["mon", "tue", "wed", "thu", "fri"],
        "windows": ["08:00-12:00", "13:30-18:00"],
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
    humanize_dict = {
        "mouse_steps": humanize.mouse_steps,
        "key_interval_ms": humanize.key_interval_ms,
        "jitter_px": humanize.jitter_px,
        "wait_jitter_ms": humanize.wait_jitter_ms,
    }
    # `seed` e apenas para testes deterministicos; omitido quando ausente para
    # nao poluir o `config.yaml` gerado por `init-config`.
    if humanize.seed is not None:
        humanize_dict["seed"] = humanize.seed
    return {
        "mode": defaults.mode,
        "poll_interval_s": defaults.poll_interval_s,
        "rearm": defaults.rearm,
        "humanize": humanize_dict,
        "compare_options": _compare_options_to_dict(defaults.compare_options),
        "escalation": {
            "enabled": defaults.escalation.enabled,
            "severity_min": defaults.escalation.severity_min,
        },
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
        raise ConfigError(code="config.root_not_mapping")
    targets_raw = raw.get("targets")
    if targets_raw is None:
        raise ConfigError(code="config.migrate_no_targets")
    if not isinstance(targets_raw, (list, tuple)):
        raise ConfigError(code="config.targets_not_list")
    targets = [_parse_target(target) for target in targets_raw]
    names = [target.name for target in targets]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ConfigError(
            code="config.migrate_duplicate_names", params={"names": ", ".join(duplicates)}
        )
    if not targets:
        raise ConfigError(code="config.migrate_empty")

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
