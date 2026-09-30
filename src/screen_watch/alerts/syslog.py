"""Canal `syslog` (doc, secao 11): informacional, sem imagem.

`logging.handlers.SysLogHandler` envia `<PRI>` + `ident` (tag) + mensagem para
host/porta configurados. UDP e o default (fire-and-forget, sem confirmacao de
entrega); TCP fica disponivel quando a entrega precisa ser confirmada.

`timeout=` no `SysLogHandler` so existe no Python 3.14; aqui o `createSocket` e
sobrescrito para aplicar `settimeout` no socket (3.11/3.13 do CI). O nivel syslog
por severidade e configuravel (`severity_map`, chaves 0..3); default: tudo
`informational`, com a severidade real no texto via `${severity}`.
"""

from __future__ import annotations

import logging
import socket
from logging.handlers import SysLogHandler

from screen_watch.alerts.template import context, render_string
from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import SyslogOptions
from screen_watch.errors import AppError

log = logging.getLogger(__name__)

DEFAULT_PAYLOAD = "${message}"


def _sanitize(text: str) -> str:
    """Remove CR/LF e demais controles (evita forjar linhas syslog no coletor)."""
    return "".join(ch if ch == "\t" or ord(ch) >= 0x20 else " " for ch in text)

# Nome do nivel (RFC 5424) -> codigo numerico usado pelo SysLogHandler.
SYSLOG_LEVELS: dict[str, int] = {
    "emergency": 0,
    "alert": 1,
    "critical": 2,
    "error": 3,
    "warning": 4,
    "notice": 5,
    "informational": 6,
    "debug": 7,
}


class _AlertSysLogHandler(SysLogHandler):
    """`SysLogHandler` com timeout no socket (3.11/3.13 nao tem `timeout=`).

    O timeout e aplicado **antes** do `connect`, senao um host TCP que engole o SYN
    bloquearia a thread do loop pelo timeout do SO (`createSocket` da stdlib faz o
    `connect` sem timeout).
    """

    def __init__(self, *args, alert_timeout: float = 5.0, **kwargs) -> None:
        self._alert_timeout = alert_timeout
        super().__init__(*args, **kwargs)

    def createSocket(self) -> None:
        address = self.address
        if isinstance(address, str):  # UNIX socket (nao usado) - delega para a stdlib
            super().createSocket()
            return
        self.unixsocket = False
        socktype = self.socktype or socket.SOCK_DGRAM
        host, port = address
        results = socket.getaddrinfo(host, port, 0, socktype)
        if not results:
            raise OSError("getaddrinfo returns an empty list")
        error: OSError | None = None
        sock = None
        for af, res_socktype, proto, _canon, sa in results:
            error = sock = None
            try:
                sock = socket.socket(af, res_socktype, proto)
                sock.settimeout(self._alert_timeout)
                if res_socktype == socket.SOCK_STREAM:
                    sock.connect(sa)
                break
            except OSError as exc:
                error = exc
                if sock is not None:
                    sock.close()
        if error is not None:
            raise error
        self.socket = sock
        self.socktype = socktype

    def mapPriority(self, levelName: str) -> int:
        return SYSLOG_LEVELS.get(str(levelName).lower(), SYSLOG_LEVELS["informational"])


class SyslogNotifier:
    name = "syslog"

    def __init__(
        self,
        options: SyslogOptions | None = None,
        *,
        enabled: bool = True,
        severity_min: int = 1,
        cooldown_s: float = 30.0,
        target_name: str = "",
    ) -> None:
        self.options = options or SyslogOptions()
        self.enabled = bool(enabled)
        self.severity_min = int(severity_min)
        self.cooldown_s = float(cooldown_s)
        self.target_name = target_name

    def _level_for(self, severity: int) -> str:
        mapping = dict(self.options.severity_map)
        return mapping.get(int(severity), "informational")

    def notify(self, result: ComparisonResult, frame: Frame) -> None:
        values = context(result, frame, self.target_name)
        template = self.options.payload_raw or DEFAULT_PAYLOAD
        try:
            message = render_string(template, values)
        except (KeyError, ValueError):  # pragma: no cover - validado na config
            message = values["message"]
        message = _sanitize(message)

        socktype = (
            socket.SOCK_STREAM if self.options.protocol == "tcp" else socket.SOCK_DGRAM
        )
        try:
            handler = _AlertSysLogHandler(
                address=(self.options.host, self.options.port),
                facility=self.options.facility,
                socktype=socktype,
                alert_timeout=self.options.timeout_s,
            )
        except OSError:
            raise AppError(
                code="alert.syslog_unavailable",
                params={"host": self.options.host, "port": self.options.port},
            ) from None

        try:
            app_name = _sanitize(self.options.app_name) if self.options.app_name else ""
            handler.ident = f"{app_name}: " if app_name else ""
            handler.append_nul = bool(self.options.append_nul)
            record = logging.LogRecord(
                name="screen_watch.alert",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg=message,
                args=(),
                exc_info=None,
            )
            record.levelname = self._level_for(result.severity)
            handler.handle(record)
        finally:
            handler.close()
