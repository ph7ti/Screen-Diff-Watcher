"""Teste de envio a um destino especifico (CLI e GUI).

`list_alert_targets` monta as linhas para listar os alertas de um alvo;
`send_test` dispara um resultado sintetico (severity 3) **apenas** ao destino
escolhido e nunca levanta — devolve `TestOutcome(ok, message)`.

Diferente do `test-alert` sem flags (que respeita `enabled` via `AlertChain`), o
teste explicito ignora `enabled` e avisa no resultado quando o alerta esta
desligado. Sem `frame` (sem ROI), envia em modo texto (forca `attach_roi=False`
no Telegram) para nao depender de captura.
"""

from __future__ import annotations

import time
from typing import NamedTuple

import numpy as np

from screen_watch.alerts.http import build_http_url, redact_url
from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult


class TestOutcome(NamedTuple):
    ok: bool
    message: str


def _describe_destination(alert) -> str:
    options = getattr(alert, "options", None)
    if alert.type == "webhook":
        if getattr(options, "url_env", ""):
            return f"url_env={options.url_env}"
        return redact_url(getattr(options, "url", "")) if getattr(options, "url", "") else "<url>"
    if alert.type == "http_post":
        if getattr(options, "url_env", ""):
            return f"url_env={options.url_env}"
        url = build_http_url(options) if options is not None else ""
        return redact_url(url) if url else "<url>"
    if alert.type == "syslog":
        host = getattr(options, "host", "") or "<host>"
        port = getattr(options, "port", 514)
        protocol = getattr(options, "protocol", "udp")
        return f"{protocol}://{host}:{port}"
    if alert.type == "ntfy":
        server = getattr(options, "server", "") or "https://ntfy.sh"
        topic = getattr(options, "topic", "") or "<topic>"
        return f"{server}/{topic}"
    if alert.type == "smtp":
        host = getattr(options, "host", "") or "<host>"
        to = ", ".join(getattr(options, "to", ()) or ()) or "<to>"
        return f"{to}@{host}"
    if alert.type == "mqtt":
        host = getattr(options, "host", "") or "<host>"
        topic = getattr(options, "topic", "") or "<topic>"
        port = getattr(options, "port", 0) or (8883 if getattr(options, "tls", False) else 1883)
        return f"{topic}@{host}:{port}"
    if alert.type == "telegram":
        if alert.chat_id:
            return f"chat_id={alert.chat_id}"
        return f"env={alert.bot_token_env}"
    if alert.type == "sound":
        return alert.file
    if alert.type == "log":
        return alert.path or "<default jsonl>"
    if alert.type == "popup":
        return "desktop notification"
    return "-"


def list_alert_targets(target) -> list[tuple[str, str, bool, int, str]]:
    """Linhas `(id, type, enabled, severity_min, destination)` dos alertas do alvo."""
    return [
        (
            alert.id or alert.type,
            alert.type,
            bool(alert.enabled),
            int(alert.severity_min),
            _describe_destination(alert),
        )
        for alert in target.alerts
    ]


def _synthetic_frame(target) -> Frame:
    rect = getattr(target, "roi_relative", (0, 0, 0, 0))
    return Frame(
        rgb=np.zeros((2, 2, 3), dtype=np.uint8),
        timestamp=time.time(),
        absolute_rect=rect,
        window_rect=rect,
        window_handle=int(getattr(target, "window_handle", 0)),
        sequence=0,
    )


def _redact_failure(exc: BaseException, notifier, alert) -> str:
    """Texto do erro sem a URL resolvida nem valores de `${env:VAR}` (nunca vaza segredo)."""
    from screen_watch.alerts.template import env_secrets  # noqa: PLC0415

    text = str(exc)
    secrets: list[str] = [getattr(notifier, "destination", None) or ""]
    options = getattr(alert, "options", None)
    if options is not None:
        secrets += env_secrets(getattr(options, "payload", None))
        secrets += env_secrets(getattr(options, "payload_raw", None))
        secrets += env_secrets(dict(getattr(options, "headers", ()) or ()))
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<SECRET>")
    return text


def send_test(target, alert_id: str, frame: Frame | None = None) -> TestOutcome:
    """Envia um alerta sintetico ao destino `alert_id`; nunca levanta."""
    from screen_watch.app import build_notifier  # noqa: PLC0415

    alert = next(
        (item for item in target.alerts if (item.id or item.type) == alert_id), None
    )
    if alert is None:
        available = ", ".join(item.id or item.type for item in target.alerts) or "none"
        return TestOutcome(False, f"alert {alert_id!r} not found; available: {available}")

    notes: list[str] = []
    if not alert.enabled:
        notes.append("alert is disabled (enabled=false)")

    notifier = build_notifier(alert, getattr(target, "name", ""))
    if notifier is None:
        return TestOutcome(False, f"alert type {alert.type!r} has no notifier")

    # URL vazia (ex.: `url_env` sem ambiente) faz o notificador pular em silencio; aqui isso
    # e um teste explicito, entao reportamos falha em vez de "sent".
    destination = getattr(notifier, "destination", None)
    if destination is not None and not destination:
        url_env = getattr(getattr(alert, "options", None), "url_env", "")
        return TestOutcome(
            False,
            f"alert {alert_id!r} ({alert.type}): no url resolved"
            + (f" (check {url_env})" if url_env else " (check url/url_env)"),
        )

    if alert.type == "telegram" and not getattr(notifier, "token_present", True):
        return TestOutcome(
            False, f"alert {alert_id!r} (telegram): {alert.bot_token_env} not set"
        )

    if alert.type == "ntfy" and not getattr(notifier, "token_present", True):
        token_env = getattr(getattr(alert, "options", None), "token_env", "NTFY_TOKEN")
        return TestOutcome(False, f"alert {alert_id!r} (ntfy): {token_env} not set")

    if frame is None:
        frame = _synthetic_frame(target)
        if getattr(notifier, "attach_roi", False):
            notifier.attach_roi = False
            notes.append("no ROI available; text mode (attach_roi=False)")

    result = ComparisonResult(
        changed=True,
        score=1.0,
        threshold=0.5,
        strategy="test-alert",
        severity=3,
        detail={"synthetic": True},
    )
    suffix = f" [{'; '.join(notes)}]" if notes else ""
    try:
        notifier.notify(result, frame)
    except Exception as exc:
        detail = _redact_failure(exc, notifier, alert)
        return TestOutcome(False, f"alert {alert_id!r} ({alert.type}) failed: {detail}{suffix}")
    return TestOutcome(True, f"alert {alert_id!r} ({alert.type}) sent{suffix}")
