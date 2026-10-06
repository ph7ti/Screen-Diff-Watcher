"""Canal `ntfy` (doc, secao 11.2): POST de texto ou PUT de imagem em `server/topic`.

O token e opcional (`token_env`): sem a variavel definida o topico fica anonimo;
quando a variavel esta configurada mas ausente, o notificador apenas registra um
aviso e pula (mesmo comportamento do Telegram). Erros nunca expoem a URL completa
(o token vai no header, mas o path/topico pode ser sensivel): usa-se `redact_url`.
"""

from __future__ import annotations

import io
import logging
import os

from screen_watch.alerts.http import redact_url
from screen_watch.alerts.template import context, render_string
from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import NtfyOptions
from screen_watch.errors import AppError

log = logging.getLogger(__name__)

DEFAULT_PRIORITY = 3


def _header(text: str, limit: int = 200) -> str:
    """Cabecalho HTTP seguro: sem CR/LF (evita injecao) e com tamanho limitado."""
    return " ".join(text.split())[:limit]


class NtfyNotifier:
    name = "ntfy"

    def __init__(
        self,
        options: NtfyOptions | None = None,
        *,
        enabled: bool = True,
        severity_min: int = 1,
        cooldown_s: float = 30.0,
        target_name: str = "",
    ) -> None:
        self.options = options or NtfyOptions()
        self.enabled = bool(enabled)
        self.severity_min = int(severity_min)
        self.cooldown_s = float(cooldown_s)
        self.target_name = target_name

    @property
    def _token(self) -> str | None:
        if not self.options.token_env:
            return None
        return os.environ.get(self.options.token_env) or None

    @property
    def token_present(self) -> bool:
        """False quando `token_env` esta configurado mas ausente (teste de envio reporta)."""
        if not self.options.token_env:
            return True
        return self._token is not None

    @property
    def destination(self) -> str:
        return f"{self.options.server}/{self.options.topic}"

    def _priority(self, severity: int) -> int:
        mapping = dict(self.options.priority_map)
        return mapping.get(int(severity), DEFAULT_PRIORITY)

    @staticmethod
    def _png_bytes(frame: Frame) -> bytes:
        from PIL import Image  # noqa: PLC0415

        buffer = io.BytesIO()
        Image.fromarray(frame.rgb).save(buffer, format="PNG")
        return buffer.getvalue()

    def notify(self, result: ComparisonResult, frame: Frame) -> None:
        if self.options.token_env and not self._token:
            log.warning("variable %s missing, ntfy disabled", self.options.token_env)
            return

        import httpx  # noqa: PLC0415

        values = context(result, frame, self.target_name)
        try:
            message = render_string(self.options.message or "${message}", values)
            title = render_string(self.options.title or "${message}", values)
        except (KeyError, ValueError):  # pragma: no cover - validado na config
            message = values["message"]
            title = values["message"]

        headers = {
            "Title": _header(title),
            "Priority": str(self._priority(result.severity)),
        }
        if self.options.tags:
            headers["Tags"] = _header(",".join(self.options.tags))
        token = self._token
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = self.destination
        attach = bool(self.options.attach_roi and frame is not None)
        if attach:
            headers["Filename"] = "roi.png"
            headers["Message"] = _header(message)
            content = self._png_bytes(frame)
        else:
            headers["Content-Type"] = "text/plain; charset=utf-8"
            content = message.encode("utf-8")

        try:
            response = httpx.request(
                "PUT" if attach else "POST",
                url,
                content=content,
                headers=headers,
                timeout=self.options.timeout_s,
                follow_redirects=False,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AppError(
                code="alert.ntfy_status",
                params={"status": exc.response.status_code, "url": redact_url(url)},
            ) from None
        except (httpx.RequestError, httpx.InvalidURL, ValueError):
            raise AppError(
                code="alert.ntfy_unavailable", params={"url": redact_url(url)}
            ) from None
