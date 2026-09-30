from __future__ import annotations

import socket

import numpy as np
import pytest

from screen_watch.alerts.syslog import SyslogNotifier
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import SyslogOptions
from screen_watch.errors import AppError


def _result(severity=3):
    return ComparisonResult(
        changed=True, score=1.0, threshold=0.5, strategy="advanced", severity=severity
    )


def _frame(make_frame):
    return make_frame(np.zeros((4, 4, 3), dtype=np.uint8), rect=(1, 2, 3, 4), handle=77)


def _udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(3.0)
    return sock, sock.getsockname()[1]


def test_udp_default_is_informational_local0(make_frame):
    sock, port = _udp_listener()
    try:
        options = SyslogOptions(
            host="127.0.0.1", port=port, app_name="sdw", payload_raw="${target} sev=${severity}"
        )
        notifier = SyslogNotifier(options, target_name="painel")
        notifier.notify(_result(), _frame(make_frame))
        data, _addr = sock.recvfrom(4096)
    finally:
        sock.close()

    assert data.startswith(b"<134>")  # local0 (16)*8 + informational (6) = 134
    text = data.decode("utf-8")
    assert text.startswith("<134>sdw: painel sev=3")
    assert not text.endswith("\x00")


def test_severity_map_overrides_priority(make_frame):
    sock, port = _udp_listener()
    try:
        options = SyslogOptions(
            host="127.0.0.1",
            port=port,
            payload_raw="${message}",
            severity_map=((3, "error"),),
        )
        notifier = SyslogNotifier(options)
        notifier.notify(_result(severity=3), _frame(make_frame))
        data, _addr = sock.recvfrom(4096)
    finally:
        sock.close()

    assert data.startswith(b"<131>")  # local0 (16)*8 + error (3) = 131


def test_tcp_protocol_delivers(make_frame):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(3.0)
    port = server.getsockname()[1]
    try:
        options = SyslogOptions(
            host="127.0.0.1", port=port, protocol="tcp", payload_raw="${message}"
        )
        SyslogNotifier(options).notify(_result(), _frame(make_frame))
        conn, _addr = server.accept()
        try:
            data = conn.recv(4096)
        finally:
            conn.close()
    finally:
        server.close()

    assert data.startswith(b"<134>")
    assert b"severity 3" in data


def test_unavailable_host_raises(make_frame):
    options = SyslogOptions(host="127.0.0.1", port=1, protocol="tcp", payload_raw="${message}")
    with pytest.raises(AppError) as excinfo:
        SyslogNotifier(options).notify(_result(), _frame(make_frame))
    assert excinfo.value.code == "alert.syslog_unavailable"


def test_message_control_chars_are_sanitized(make_frame):
    sock, port = _udp_listener()
    try:
        options = SyslogOptions(
            host="127.0.0.1", port=port, app_name="sdw", payload_raw="line1\nline2\rFORGED"
        )
        SyslogNotifier(options).notify(_result(), _frame(make_frame))
        data, _addr = sock.recvfrom(4096)
    finally:
        sock.close()

    text = data.decode("utf-8")
    assert "\n" not in text
    assert "\r" not in text
    assert "line1 line2 FORGED" in text
