"""Canal `mqtt` (doc, secao 11.2): publish em broker MQTT (extra `paho-mqtt`).

O import do `paho.mqtt.client` e tardio: sem o extra, o canal configurado falha
com `alert.mqtt_missing_extra` (erro visivel no `AlertChain`, nunca skip mudo).
Credenciais apenas por variavel de ambiente; o payload e um template mapping
(default com texto/severidade/alvo) ou `payload_raw`. Sem imagem.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from screen_watch.alerts.template import context, render_mapping, render_string
from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import MqttOptions
from screen_watch.errors import AppError

log = logging.getLogger(__name__)

DEFAULT_PAYLOAD: dict[str, str] = {
    "text": "${message}",
    "target": "${target}",
    "severity": "${severity}",
    "strategy": "${strategy}",
    "score": "${score}",
    "threshold": "${threshold}",
    "timestamp": "${timestamp}",
}


class MqttNotifier:
    name = "mqtt"

    def __init__(
        self,
        options: MqttOptions | None = None,
        *,
        enabled: bool = True,
        severity_min: int = 1,
        cooldown_s: float = 30.0,
        target_name: str = "",
    ) -> None:
        self.options = options or MqttOptions()
        self.enabled = bool(enabled)
        self.severity_min = int(severity_min)
        self.cooldown_s = float(cooldown_s)
        self.target_name = target_name

    @property
    def destination(self) -> str:
        return f"{self.options.host}:{self._port}/{self.options.topic}"

    @property
    def _port(self) -> int:
        return self.options.port or (8883 if self.options.tls else 1883)

    def _credentials(self) -> tuple[str | None, str | None]:
        username = (
            os.environ.get(self.options.username_env) if self.options.username_env else None
        )
        password = (
            os.environ.get(self.options.password_env) if self.options.password_env else None
        )
        return username or None, password or None

    def _body(self, values: dict[str, str]) -> str:
        if self.options.payload_raw:
            return render_string(self.options.payload_raw, values)
        payload: Any = self.options.payload if self.options.payload is not None else DEFAULT_PAYLOAD
        return json.dumps(render_mapping(payload, values), ensure_ascii=False)

    def notify(self, result: ComparisonResult, frame: Frame) -> None:
        try:
            from paho.mqtt import client as mqtt_client  # noqa: PLC0415
        except ImportError:
            raise AppError(code="alert.mqtt_missing_extra") from None

        values = context(result, frame, self.target_name)
        try:
            body = self._body(values)
        except (KeyError, ValueError):  # pragma: no cover - validado na config
            body = json.dumps({"text": values["message"]}, ensure_ascii=False)

        client = mqtt_client.Client(client_id=self.options.client_id or "screen-diff-watcher")
        username, password = self._credentials()
        if username:
            client.username_pw_set(username, password)
        if self.options.tls:
            try:
                client.tls_set()
            except Exception:
                raise AppError(
                    code="alert.mqtt_unavailable",
                    params={"host": self.options.host, "port": self._port},
                ) from None

        try:
            client.connect(self.options.host, self._port)
        except Exception:
            raise AppError(
                code="alert.mqtt_unavailable",
                params={"host": self.options.host, "port": self._port},
            ) from None
        try:
            info = client.publish(
                self.options.topic,
                payload=body,
                qos=self.options.qos,
                retain=self.options.retain,
            )
            wait = getattr(info, "wait_for_publish", None)
            if callable(wait):
                wait(timeout=self.options.timeout_s)
            rc = getattr(info, "rc", 0)
            if rc not in (0, None):
                raise AppError(
                    code="alert.mqtt_publish_failed",
                    params={"host": self.options.host, "error": f"rc={rc}"},
                )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                code="alert.mqtt_publish_failed",
                params={"host": self.options.host, "error": type(exc).__name__},
            ) from None
        finally:
            try:
                client.disconnect()
            except Exception:  # pragma: no cover - best-effort
                pass
