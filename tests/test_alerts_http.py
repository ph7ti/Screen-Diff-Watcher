from __future__ import annotations

import re

import httpx
import numpy as np
import pytest

from screen_watch.alerts.http import (
    HttpPostNotifier,
    WebhookNotifier,
    post_json,
    redact_url,
)
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import HttpPostOptions, WebhookOptions
from screen_watch.errors import AppError


def _result():
    return ComparisonResult(
        changed=True, score=1.0, threshold=0.5, strategy="advanced", severity=2
    )


def _frame(make_frame):
    return make_frame(np.zeros((4, 4, 3), dtype=np.uint8), rect=(1, 2, 3, 4), handle=77)


def _patch_request(monkeypatch, handler):
    seen: list[dict] = []
    transport = httpx.MockTransport(handler)

    def fake_request(method, url, **kwargs):
        seen.append({"method": method, "url": str(url), **kwargs})
        client_verify = kwargs.pop("verify", True)
        with httpx.Client(transport=transport, verify=client_verify) as client:
            return client.request(method, url, **kwargs)

    monkeypatch.setattr(httpx, "request", fake_request)
    return seen


def test_webhook_uses_default_payload(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200, json={"ok": True}))
    notifier = WebhookNotifier(WebhookOptions(url="https://example.com/hook"), target_name="painel")

    notifier.notify(_result(), _frame(make_frame))

    assert len(seen) == 1
    assert seen[0]["method"] == "POST"
    assert seen[0]["json"] == {"text": "advanced: score=1.00 (severity 2)"}


def test_webhook_payload_raw_and_env_header(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    monkeypatch.setenv("ERP_TOKEN", "s3cr3t")
    options = WebhookOptions(
        url_env="HOOK_URL",
        headers=(("Authorization", "Bearer ${env:ERP_TOKEN}"),),
        payload_raw="${timestamp} ${target} sev=${severity}",
    )
    monkeypatch.setenv("HOOK_URL", "https://example.com/hook")
    notifier = WebhookNotifier(options, target_name="painel")

    notifier.notify(_result(), _frame(make_frame))

    assert seen[0]["headers"]["Authorization"] == "Bearer s3cr3t"
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z painel sev=2", seen[0]["content"]
    )


def test_webhook_missing_url_is_skipped(monkeypatch, make_frame, caplog):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    notifier = WebhookNotifier(WebhookOptions(url_env="ABSENT_URL"))
    monkeypatch.delenv("ABSENT_URL", raising=False)

    with caplog.at_level("WARNING"):
        notifier.notify(_result(), _frame(make_frame))

    assert seen == []
    assert "ABSENT_URL" in caplog.text


def test_non_2xx_raises_redacted_status_error(monkeypatch, make_frame):
    _patch_request(monkeypatch, lambda request: httpx.Response(500, text="boom"))
    url = "https://example.com/hook/SECRETTOKEN"
    with pytest.raises(AppError) as excinfo:
        WebhookNotifier(WebhookOptions(url=url)).notify(_result(), _frame(make_frame))

    assert excinfo.value.code == "alert.http_status"
    assert excinfo.value.params["status"] == 500
    assert "SECRETTOKEN" not in str(excinfo.value)
    assert "example.com" in str(excinfo.value)


def test_network_error_raises_unreachable(monkeypatch, make_frame):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    _patch_request(monkeypatch, handler)
    with pytest.raises(AppError) as excinfo:
        WebhookNotifier(WebhookOptions(url="https://example.com/hook")).notify(
            _result(), _frame(make_frame)
        )

    assert excinfo.value.code == "alert.http_unreachable"


def test_verify_tls_false_is_passed_and_logged(monkeypatch, make_frame, caplog):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    notifier = WebhookNotifier(
        WebhookOptions(url="https://example.com/hook", verify_tls=False)
    )

    with caplog.at_level("WARNING"):
        notifier.notify(_result(), _frame(make_frame))

    assert seen[0]["verify"] is False
    assert "TLS verification disabled" in caplog.text


def test_http_post_builds_url_from_host_port_path(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(204))
    options = HttpPostOptions(
        scheme="http", host="10.0.0.20", port=8080, path="alerta", payload={"evento": "${target}"}
    )
    notifier = HttpPostNotifier(options, target_name="erp")

    notifier.notify(_result(), _frame(make_frame))

    assert seen[0]["url"] == "http://10.0.0.20:8080/alerta"
    assert seen[0]["json"] == {"evento": "erp"}


def test_http_post_payload_raw_sets_json_content_type(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    notifier = HttpPostNotifier(HttpPostOptions(url="https://x/y", payload_raw="ok"))

    notifier.notify(_result(), _frame(make_frame))

    assert seen[0]["headers"]["Content-Type"] == "application/json"
    assert seen[0]["content"] == "ok"


def test_redact_url_hides_path_and_query():
    assert redact_url("https://host:8443/secret/path?token=abc") == "https://host:8443/…"
    assert redact_url("not a url") == "<url>"


def test_redact_url_handles_malformed_port():
    assert redact_url("http://host:80x/hook") == "<url>"


def test_post_json_maps_invalid_url_to_unreachable(monkeypatch):
    with pytest.raises(AppError) as excinfo:
        post_json("http://[::1", payload={"a": 1})
    assert excinfo.value.code == "alert.http_unreachable"
    assert "::1" not in str(excinfo.value)


def test_list_alert_targets_redacts_and_normalizes_http_post():
    from screen_watch.alerts.test_send import list_alert_targets
    from screen_watch.config.schema import AlertOptions, TargetConfig

    alert = AlertOptions(
        type="http_post",
        id="erp",
        options=HttpPostOptions(host="10.0.0.20", port=8080, path="alerta"),
    )
    target = TargetConfig(
        name="t", window_handle=1, roi_relative=(0, 0, 1, 1), alerts=(alert,)
    )
    rows = list_alert_targets(target)
    assert rows[0][0] == "erp"
    assert rows[0][4] == "http://10.0.0.20:8080/…"


def test_post_json_returns_none_on_2xx(monkeypatch):
    _patch_request(monkeypatch, lambda request: httpx.Response(201))
    assert post_json("https://example.com/hook", payload={"a": 1}) is None
