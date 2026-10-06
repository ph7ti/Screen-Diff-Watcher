from __future__ import annotations

import httpx
import numpy as np
import pytest

from screen_watch.alerts.ntfy import NtfyNotifier
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import NtfyOptions
from screen_watch.errors import AppError


def _result(severity: int = 2):
    return ComparisonResult(
        changed=True, score=1.0, threshold=0.5, strategy="advanced", severity=severity
    )


def _frame(make_frame):
    return make_frame(np.zeros((4, 4, 3), dtype=np.uint8), rect=(1, 2, 3, 4), handle=77)


def _patch_request(monkeypatch, handler):
    seen: list[dict] = []
    transport = httpx.MockTransport(handler)

    def fake_request(method, url, **kwargs):
        seen.append({"method": method, "url": str(url), **kwargs})
        with httpx.Client(transport=transport) as client:
            return client.request(method, url, **kwargs)

    monkeypatch.setattr(httpx, "request", fake_request)
    return seen


def test_ntfy_posts_text_with_headers(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    notifier = NtfyNotifier(NtfyOptions(topic="meu-topico"), target_name="painel")

    notifier.notify(_result(severity=2), _frame(make_frame))

    assert seen[0]["method"] == "POST"
    assert seen[0]["url"] == "https://ntfy.sh/meu-topico"
    assert seen[0]["headers"]["Priority"] == "4"  # default 2 -> 4
    assert seen[0]["headers"]["Title"] == "advanced: score=1.00 (severity 2)"
    assert seen[0]["content"] == b"advanced: score=1.00 (severity 2)"


def test_ntfy_priority_map_and_tags(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    options = NtfyOptions(
        topic="t", priority_map=((3, 5),), tags=("warning", "eye"), title="alerta ${target}"
    )
    NtfyNotifier(options, target_name="erp").notify(_result(severity=3), _frame(make_frame))

    assert seen[0]["headers"]["Priority"] == "5"
    assert seen[0]["headers"]["Title"] == "alerta erp"
    assert seen[0]["headers"]["Tags"] == "warning,eye"


def test_ntfy_unknown_priority_falls_back(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    options = NtfyOptions(topic="t", priority_map=((1, 1),))
    NtfyNotifier(options).notify(_result(severity=3), _frame(make_frame))
    assert seen[0]["headers"]["Priority"] == "3"


def test_ntfy_token_from_env(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    monkeypatch.setenv("NTFY_TOKEN", "tk_123")
    NtfyNotifier(NtfyOptions(topic="t", token_env="NTFY_TOKEN")).notify(
        _result(), _frame(make_frame)
    )
    assert seen[0]["headers"]["Authorization"] == "Bearer tk_123"


def test_ntfy_configured_token_missing_is_skipped(monkeypatch, make_frame, caplog):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    notifier = NtfyNotifier(NtfyOptions(topic="t", token_env="NTFY_TOKEN"))
    assert notifier.token_present is False
    with caplog.at_level("WARNING"):
        notifier.notify(_result(), _frame(make_frame))
    assert seen == []
    assert "NTFY_TOKEN" in caplog.text


def test_ntfy_anonymous_when_token_env_empty(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    NtfyNotifier(NtfyOptions(topic="t", token_env="")).notify(_result(), _frame(make_frame))
    assert "Authorization" not in seen[0]["headers"]


def test_ntfy_attach_roi_uses_put(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    notifier = NtfyNotifier(NtfyOptions(topic="t", attach_roi=True))

    notifier.notify(_result(), _frame(make_frame))

    assert seen[0]["method"] == "PUT"
    assert seen[0]["headers"]["Filename"] == "roi.png"
    assert "Message" in seen[0]["headers"]
    assert seen[0]["content"].startswith(b"\x89PNG")


def test_ntfy_attach_roi_without_frame_posts_text(monkeypatch, make_frame):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200))
    NtfyNotifier(NtfyOptions(topic="t", attach_roi=True)).notify(_result(), None)
    assert seen[0]["method"] == "POST"


def test_ntfy_status_error_is_redacted(monkeypatch, make_frame):
    _patch_request(monkeypatch, lambda request: httpx.Response(500, text="boom"))
    notifier = NtfyNotifier(NtfyOptions(topic="topico-secreto"))
    with pytest.raises(AppError) as excinfo:
        notifier.notify(_result(), _frame(make_frame))
    assert excinfo.value.code == "alert.ntfy_status"
    assert excinfo.value.params["status"] == 500
    assert "topico-secreto" not in str(excinfo.value)
    assert "ntfy.sh" in str(excinfo.value)


def test_ntfy_network_error(monkeypatch, make_frame):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    _patch_request(monkeypatch, handler)
    with pytest.raises(AppError) as excinfo:
        NtfyNotifier(NtfyOptions(topic="t")).notify(_result(), _frame(make_frame))
    assert excinfo.value.code == "alert.ntfy_unavailable"
    assert "topico" not in str(excinfo.value)


def test_ntfy_destination_in_target_list():
    from screen_watch.alerts.test_send import list_alert_targets
    from screen_watch.config.schema import AlertOptions, TargetConfig

    alert = AlertOptions(
        type="ntfy", id="celular", options=NtfyOptions(server="https://ntfy.example", topic="t")
    )
    target = TargetConfig(
        name="t", window_handle=1, roi_relative=(0, 0, 1, 1), alerts=(alert,)
    )
    rows = list_alert_targets(target)
    assert rows[0][0] == "celular"
    assert rows[0][4] == "https://ntfy.example/t"
