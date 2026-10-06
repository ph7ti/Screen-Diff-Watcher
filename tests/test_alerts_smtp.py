from __future__ import annotations

import smtplib

import numpy as np
import pytest

from screen_watch.alerts.smtp import SmtpNotifier
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import SmtpOptions
from screen_watch.errors import AppError


def _result():
    return ComparisonResult(
        changed=True, score=1.0, threshold=0.5, strategy="advanced", severity=2
    )


def _frame(make_frame):
    return make_frame(np.zeros((4, 4, 3), dtype=np.uint8), rect=(1, 2, 3, 4), handle=77)


class _FakeServer:
    instances: list["_FakeServer"] = []
    connect_error: Exception | None = None
    login_error: Exception | None = None
    send_error: Exception | None = None

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.actions: list[object] = []
        type(self).instances.append(self)

    def ehlo(self):
        self.actions.append("ehlo")

    def starttls(self, context=None):
        self.actions.append(("starttls", context))

    def login(self, user, password):
        self.actions.append(("login", user, password))
        if type(self).login_error is not None:
            raise type(self).login_error

    def send_message(self, message):
        self.actions.append(("send", message))
        if type(self).send_error is not None:
            raise type(self).send_error

    def quit(self):
        self.actions.append("quit")


@pytest.fixture
def fake_smtp(monkeypatch):
    _FakeServer.instances = []
    _FakeServer.connect_error = None
    _FakeServer.login_error = None
    _FakeServer.send_error = None
    monkeypatch.setattr(smtplib, "SMTP", _FakeServer)

    class _FakeSSL(_FakeServer):
        pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSSL)
    return _FakeServer


def _options(**overrides):
    base = dict(
        host="smtp.example.com",
        from_addr="watch@example.com",
        to=("oncall@example.com",),
    )
    base.update(overrides)
    return SmtpOptions(**base)


def test_smtp_starttls_login_and_send(fake_smtp, monkeypatch, make_frame):
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    notifier = SmtpNotifier(_options(), target_name="erp")

    notifier.notify(_result(), _frame(make_frame))

    server = fake_smtp.instances[0]
    assert server.args == ("smtp.example.com", 587)
    assert "ehlo" in server.actions
    assert any(isinstance(action, tuple) and action[0] == "starttls" for action in server.actions)
    assert ("login", "user", "pw") in server.actions
    sent = next(action[1] for action in server.actions if isinstance(action, tuple) and action[0] == "send")
    assert sent["To"] == "oncall@example.com"
    assert sent["From"] == "watch@example.com"
    assert "erp" in sent["Subject"]
    assert list(sent.iter_attachments())  # attach_roi default True
    assert server.actions[-1] == "quit"


def test_smtp_no_login_without_username(fake_smtp, monkeypatch, make_frame):
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    SmtpNotifier(_options()).notify(_result(), _frame(make_frame))
    server = fake_smtp.instances[0]
    assert not any(isinstance(action, tuple) and action[0] == "login" for action in server.actions)


def test_smtp_none_security_skips_starttls(fake_smtp, monkeypatch, make_frame):
    SmtpNotifier(_options(security="none", attach_roi=False)).notify(_result(), _frame(make_frame))
    server = fake_smtp.instances[0]
    assert not any(isinstance(action, tuple) and action[0] == "starttls" for action in server.actions)
    sent = next(action[1] for action in server.actions if isinstance(action, tuple) and action[0] == "send")
    assert list(sent.iter_attachments()) == []


def test_smtp_ssl_uses_smtp_ssl(fake_smtp, monkeypatch, make_frame):
    SmtpNotifier(_options(security="ssl"), target_name="").notify(_result(), _frame(make_frame))
    assert isinstance(fake_smtp.instances[0], fake_smtp)


def test_smtp_connect_failure(fake_smtp, monkeypatch, make_frame):
    def boom(*args, **kwargs):
        raise OSError("refused")

    monkeypatch.setattr(smtplib, "SMTP", boom)
    with pytest.raises(AppError) as excinfo:
        SmtpNotifier(_options()).notify(_result(), _frame(make_frame))
    assert excinfo.value.code == "alert.smtp_unavailable"


def test_smtp_auth_failure_sanitizes_credentials(fake_smtp, monkeypatch, make_frame):
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "s3cr3t")
    fake_smtp.login_error = smtplib.SMTPAuthenticationError(535, b"bad user")
    with pytest.raises(AppError) as excinfo:
        SmtpNotifier(_options()).notify(_result(), _frame(make_frame))
    assert excinfo.value.code == "alert.smtp_auth_failed"
    assert "s3cr3t" not in str(excinfo.value)


def test_smtp_send_failure_sanitizes_password(fake_smtp, monkeypatch, make_frame):
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "sup3r")
    fake_smtp.send_error = smtplib.SMTPException("rejected sup3r")
    with pytest.raises(AppError) as excinfo:
        SmtpNotifier(_options()).notify(_result(), _frame(make_frame))
    assert excinfo.value.code == "alert.smtp_send_failed"
    assert "sup3r" not in str(excinfo.value)
    assert "<SECRET>" in excinfo.value.params["error"]


def test_smtp_destination_in_target_list():
    from screen_watch.alerts.test_send import list_alert_targets
    from screen_watch.config.schema import AlertOptions, TargetConfig

    alert = AlertOptions(
        type="smtp",
        id="email",
        options=SmtpOptions(
            host="smtp.example.com", from_addr="a@x", to=("oncall@example.com",)
        ),
    )
    target = TargetConfig(
        name="t", window_handle=1, roi_relative=(0, 0, 1, 1), alerts=(alert,)
    )
    rows = list_alert_targets(target)
    assert rows[0][4] == "oncall@example.com@smtp.example.com"
