from __future__ import annotations

import httpx
import numpy as np

from screen_watch.alerts.telegram import TelegramNotifier
from screen_watch.compare.protocol import ComparisonResult


def _result():
    return ComparisonResult(
        changed=True, score=0.5, threshold=0.1, strategy="advanced", severity=2
    )


def _frame(make_frame):
    return make_frame(np.full((4, 4, 3), 128, dtype=np.uint8))


def _patch_post(monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    def fake_post(url, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", fake_post)
    return requests


def test_send_photo_with_roi(monkeypatch, make_frame):
    requests = _patch_post(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOKEN123")
    notifier = TelegramNotifier(chat_id="999", attach_roi=True)

    notifier.notify(_result(), _frame(make_frame))

    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/botTOKEN123/sendPhoto"
    body = request.content
    assert b'name="chat_id"' in body
    assert b"999" in body
    assert b'filename="roi.png"' in body


def test_send_message_without_roi(monkeypatch, make_frame):
    requests = _patch_post(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOKEN123")
    notifier = TelegramNotifier(chat_id="999", attach_roi=False)

    notifier.notify(_result(), _frame(make_frame))

    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/botTOKEN123/sendMessage"
    assert b"chat_id" in request.content
    assert b'filename="roi.png"' not in request.content


def test_missing_token_logs_and_returns(monkeypatch, make_frame, caplog):
    requests = _patch_post(monkeypatch)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with caplog.at_level("WARNING"):
        TelegramNotifier(chat_id="999").notify(_result(), _frame(make_frame))

    assert requests == []
    assert "TELEGRAM_BOT_TOKEN" in caplog.text


def test_custom_token_env(monkeypatch, make_frame):
    requests = _patch_post(monkeypatch)
    monkeypatch.setenv("MY_BOT_TOKEN", "CUSTOM")
    notifier = TelegramNotifier(chat_id="1", bot_token_env="MY_BOT_TOKEN", attach_roi=False)

    notifier.notify(_result(), _frame(make_frame))

    assert requests[0].url.path == "/botCUSTOM/sendMessage"
