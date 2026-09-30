"""Webhook Telegram Bot (doc, secao 11.2).

O token nunca fica no YAML: ele e lido de uma variavel de ambiente. A imagem do ROI
e anexada sempre que `attach_roi` estiver ligado, para validar falsos positivos.
Timeout curto (5 s) para nao travar o loop.

Falhas HTTP viram `TelegramAPIError` com a descricao do Telegram (ex.: "chat not
found", "the bot can't send messages to the bot"), sem expor o token: o httpx
inclui a URL completa na mensagem de erro, e a URL carrega o token.
"""

from __future__ import annotations

import io
import logging
import os

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
REQUEST_TIMEOUT_S = 5.0


class TelegramAPIError(RuntimeError):
    """Falha ao falar com a API do Telegram, sem expor token/URL."""

    def __init__(self, status_code: int | None, description: str) -> None:
        self.status_code = status_code
        self.description = description
        detail = f"HTTP {status_code}: {description}" if status_code else description
        super().__init__(detail)


class TelegramNotifier:
    name = "telegram"

    def __init__(
        self,
        chat_id: str,
        *,
        bot_token_env: str = "TELEGRAM_BOT_TOKEN",
        enabled: bool = True,
        severity_min: int = 2,
        cooldown_s: float = 60.0,
        attach_roi: bool = True,
    ) -> None:
        self.chat_id = str(chat_id)
        self.bot_token_env = bot_token_env
        self.enabled = bool(enabled)
        self.severity_min = int(severity_min)
        self.cooldown_s = float(cooldown_s)
        self.attach_roi = bool(attach_roi)

    @property
    def _token(self) -> str | None:
        return os.environ.get(self.bot_token_env) or None

    @property
    def token_present(self) -> bool:
        """True se a variavel de ambiente do token esta definida (para o teste de envio)."""
        return self._token is not None

    @staticmethod
    def _png_bytes(frame: Frame) -> bytes:
        from PIL import Image  # noqa: PLC0415

        buffer = io.BytesIO()
        Image.fromarray(frame.rgb).save(buffer, format="PNG")
        return buffer.getvalue()

    def notify(self, result: ComparisonResult, frame: Frame) -> None:
        token = self._token
        if not token:
            log.warning("variable %s missing, Telegram disabled", self.bot_token_env)
            return

        import httpx  # noqa: PLC0415

        caption = f"{result.strategy}: score={result.score:.2f} (severidade {result.severity})"
        url = f"{API_BASE}/bot{token}"

        try:
            if self.attach_roi:
                files = {"photo": ("roi.png", self._png_bytes(frame), "image/png")}
                data = {"chat_id": self.chat_id, "caption": caption}
                response = httpx.post(
                    f"{url}/sendPhoto", data=data, files=files, timeout=REQUEST_TIMEOUT_S
                )
            else:
                data = {"chat_id": self.chat_id, "text": caption}
                response = httpx.post(
                    f"{url}/sendMessage", data=data, timeout=REQUEST_TIMEOUT_S
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TelegramAPIError(
                exc.response.status_code, self._error_text(exc.response)
            ) from None
        except httpx.RequestError as exc:
            raise TelegramAPIError(None, self._sanitize(str(exc))) from None

    def _sanitize(self, message: str) -> str:
        """Remove o token de qualquer mensagem antes de ela chegar ao log."""
        token = self._token
        return message.replace(token, "<TOKEN>") if token else message

    def _error_text(self, response) -> str:
        """Descricao do Telegram (JSON) ou a razao HTTP, sempre sem o token."""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            description = payload.get("description")
            if isinstance(description, str) and description.strip():
                return self._sanitize(description.strip())
        return self._sanitize(response.reason_phrase or "request failed")
