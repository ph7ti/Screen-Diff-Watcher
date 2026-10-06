"""Canal `smtp` (doc, secao 11.2): e-mail via stdlib, credenciais apenas em env.

`security`: `starttls` (default), `ssl` ou `none`. Login so acontece quando a
variavel de usuario esta definida; a senha nunca aparece em erros/logs (o texto
do servidor e saneado). `attach_roi` anexa o PNG da ROI, como no Telegram.
"""

from __future__ import annotations

import io
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from screen_watch.alerts.template import context, render_string
from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import SmtpOptions
from screen_watch.errors import AppError

log = logging.getLogger(__name__)


def _sanitize_header(text: str) -> str:
    return " ".join(text.split())


class SmtpNotifier:
    name = "smtp"

    def __init__(
        self,
        options: SmtpOptions | None = None,
        *,
        enabled: bool = True,
        severity_min: int = 1,
        cooldown_s: float = 30.0,
        target_name: str = "",
    ) -> None:
        self.options = options or SmtpOptions()
        self.enabled = bool(enabled)
        self.severity_min = int(severity_min)
        self.cooldown_s = float(cooldown_s)
        self.target_name = target_name

    @property
    def destination(self) -> str:
        return f"{self.options.host}:{self.options.port}"

    @property
    def auth_user(self) -> str | None:
        if not self.options.username_env:
            return None
        return os.environ.get(self.options.username_env) or None

    @property
    def _password(self) -> str | None:
        if not self.options.password_env:
            return None
        return os.environ.get(self.options.password_env) or None

    @property
    def credentials_present(self) -> bool:
        """True quando o login configurado tem a variavel de usuario no ambiente."""
        if not self.options.username_env:
            return True
        return self.auth_user is not None

    def _sanitize(self, text: str) -> str:
        for secret in (self.auth_user, self._password):
            if secret:
                text = text.replace(secret, "<SECRET>")
        return text

    @staticmethod
    def _png_bytes(frame: Frame) -> bytes:
        from PIL import Image  # noqa: PLC0415

        buffer = io.BytesIO()
        Image.fromarray(frame.rgb).save(buffer, format="PNG")
        return buffer.getvalue()

    def _build_message(self, result: ComparisonResult, frame: Frame) -> EmailMessage:
        values = context(result, frame, self.target_name)
        try:
            subject = render_string(self.options.subject, values)
            body = render_string(self.options.message or "${message}", values)
        except (KeyError, ValueError):  # pragma: no cover - validado na config
            subject = values["message"]
            body = values["message"]
        message = EmailMessage()
        message["Subject"] = _sanitize_header(subject)
        message["From"] = self.options.from_addr
        message["To"] = ", ".join(self.options.to)
        message.set_content(body)
        if self.options.attach_roi and frame is not None:
            message.add_attachment(
                self._png_bytes(frame), maintype="image", subtype="png", filename="roi.png"
            )
        return message

    def _connect(self) -> smtplib.SMTP:
        if self.options.security == "ssl":
            return smtplib.SMTP_SSL(
                self.options.host,
                self.options.port,
                timeout=self.options.timeout_s,
                context=ssl.create_default_context(),
            )
        return smtplib.SMTP(
            self.options.host, self.options.port, timeout=self.options.timeout_s
        )

    def notify(self, result: ComparisonResult, frame: Frame) -> None:
        message = self._build_message(result, frame)
        username = self.auth_user
        password = self._password

        try:
            server = self._connect()
        except (OSError, smtplib.SMTPException, TimeoutError, ssl.SSLError):
            raise AppError(
                code="alert.smtp_unavailable",
                params={"host": self.options.host, "port": self.options.port},
            ) from None

        try:
            if self.options.security == "starttls":
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if username:
                try:
                    server.login(username, password or "")
                except smtplib.SMTPAuthenticationError:
                    raise AppError(
                        code="alert.smtp_auth_failed",
                        params={"user": username, "host": self.options.host},
                    ) from None
            try:
                server.send_message(message)
            except smtplib.SMTPException as exc:
                raise AppError(
                    code="alert.smtp_send_failed",
                    params={"host": self.options.host, "error": self._sanitize(str(exc))},
                ) from None
        except AppError:
            raise
        except (OSError, smtplib.SMTPException, TimeoutError, ssl.SSLError) as exc:
            raise AppError(
                code="alert.smtp_unavailable",
                params={"host": self.options.host, "port": self.options.port},
            ) from exc
        finally:
            try:
                server.quit()
            except Exception:  # pragma: no cover - best-effort
                pass
