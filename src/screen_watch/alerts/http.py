"""Canais `webhook` e `http_post` (doc, secao 11).

Ambos fazem POST JSON para uma URL configuravel, com **modelo de payload**
configuravel (`payload:` mapping ou `payload_raw:` string). O segredo da URL fica
fora do YAML (`url_env: VAR`) e nunca aparece em erros/logs: a URL e redigida
(`scheme://host/…`) e valores de `${env:VAR}` sao mascarados.

`httpx` e core (usado pelo Telegram). Redirects nao sao seguidos; `verify_tls`
default `true` (aviso em log a cada envio quando `false`).
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlsplit

from screen_watch.alerts.template import context, render_mapping, render_string
from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import HttpPostOptions, WebhookOptions
from screen_watch.errors import AppError

log = logging.getLogger(__name__)

DEFAULT_PAYLOAD: dict[str, str] = {"text": "${message}"}


def redact_url(url: str) -> str:
    """Forma segura de logar uma URL (sem path/query/userinfo, que podem ter segredos)."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return "<url>"
    if not parts.scheme or not host:
        return "<url>"
    suffix = f":{port}" if port else ""
    return f"{parts.scheme}://{host}{suffix}/…"


def build_http_url(options: WebhookOptions | HttpPostOptions) -> str:
    """URL efetiva (`url` > `url_env` > `scheme://host:port/path`); vazia se ausente."""
    if options.url:
        return options.url
    if options.url_env:
        return os.environ.get(options.url_env) or ""
    host = getattr(options, "host", "")
    if host:
        path = options.path or ""
        if path and not path.startswith("/"):
            path = f"/{path}"
        return f"{options.scheme}://{host}:{options.port}{path}"
    return ""


def post_json(
    url: str,
    *,
    payload: Any = None,
    body: str | None = None,
    headers: dict[str, str] | None = None,
    method: str = "POST",
    timeout_s: float = 5.0,
    verify: bool = True,
) -> None:
    """POST JSON para `url`; nao-2xx -> `alert.http_status`, rede -> `alert.http_unreachable`.

    Todas as falhas viram `AppError` com a URL **redigida** — inclusive URLs malformadas
    (`InvalidURL`/`ValueError`), para nao vazar o valor em erros/logs.
    """
    import httpx  # noqa: PLC0415

    request_headers = dict(headers or {})
    if body is not None:
        request_headers.setdefault("Content-Type", "application/json")
    safe_url = redact_url(url)
    try:
        response = httpx.request(
            method,
            url,
            json=None if body is not None else payload,
            content=body,
            headers=request_headers or None,
            timeout=timeout_s,
            follow_redirects=False,
            verify=verify,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AppError(
            code="alert.http_status",
            params={"status": exc.response.status_code, "url": safe_url},
        ) from None
    except (httpx.RequestError, httpx.InvalidURL, ValueError):
        raise AppError(
            code="alert.http_unreachable",
            params={"url": safe_url},
        ) from None


def _render_payload(options, values: dict[str, str]):
    """`payload` (mapping) ou `payload_raw` (string) -> `(payload, body)`; nunca ambos."""
    if options.payload_raw:
        return None, render_string(options.payload_raw, values)
    payload = options.payload if options.payload is not None else DEFAULT_PAYLOAD
    return render_mapping(payload, values), None


def _send(url: str, options, values: dict[str, str]) -> None:
    """Renderiza headers/payload e faz o POST (logica compartilhada pelos dois canais)."""
    headers = {key: render_string(value, values) for key, value in options.headers}
    payload, body = _render_payload(options, values)
    post_json(
        url,
        payload=payload,
        body=body,
        headers=headers,
        method=options.method,
        timeout_s=options.timeout_s,
        verify=options.verify_tls,
    )


class WebhookNotifier:
    name = "webhook"

    def __init__(
        self,
        options: WebhookOptions | None = None,
        *,
        enabled: bool = True,
        severity_min: int = 1,
        cooldown_s: float = 30.0,
        target_name: str = "",
    ) -> None:
        self.options = options or WebhookOptions()
        self.enabled = bool(enabled)
        self.severity_min = int(severity_min)
        self.cooldown_s = float(cooldown_s)
        self.target_name = target_name

    @property
    def _url(self) -> str:
        return build_http_url(self.options)

    @property
    def destination(self) -> str:
        """URL resolvida (vazia quando `url_env` nao esta no ambiente)."""
        return self._url

    def notify(self, result: ComparisonResult, frame: Frame) -> None:
        url = self._url
        if not url:
            log.warning(
                "webhook url missing (%s); alert skipped", self.options.url_env or "<empty>"
            )
            return
        if not self.options.verify_tls:
            log.warning("TLS verification disabled for webhook %s", redact_url(url))
        _send(url, self.options, context(result, frame, self.target_name))


class HttpPostNotifier:
    name = "http_post"

    def __init__(
        self,
        options: HttpPostOptions | None = None,
        *,
        enabled: bool = True,
        severity_min: int = 1,
        cooldown_s: float = 30.0,
        target_name: str = "",
    ) -> None:
        self.options = options or HttpPostOptions()
        self.enabled = bool(enabled)
        self.severity_min = int(severity_min)
        self.cooldown_s = float(cooldown_s)
        self.target_name = target_name

    @property
    def _url(self) -> str:
        return build_http_url(self.options)

    @property
    def destination(self) -> str:
        """URL resolvida (vazia quando `url_env` nao esta no ambiente)."""
        return self._url

    def notify(self, result: ComparisonResult, frame: Frame) -> None:
        url = self._url
        if not url:
            log.warning(
                "http_post url missing (%s); alert skipped",
                self.options.url_env or "<empty>",
            )
            return
        if not self.options.verify_tls:
            log.warning("TLS verification disabled for http_post %s", redact_url(url))
        _send(url, self.options, context(result, frame, self.target_name))
