"""Testes de integracao opt-in (fora do CI).

Marcados com `integration`; por padrao sao pulados. Para rodar:

    $env:TEST_REAL_CAPTURE="1"; python -m pytest -m integration
    $env:TEST_REAL_TELEGRAM="1"; $env:TELEGRAM_BOT_TOKEN="...";
    $env:TELEGRAM_TEST_CHAT_ID="..."; python -m pytest -m integration
"""

from __future__ import annotations

import os
import time

import numpy as np
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("TEST_REAL_CAPTURE") != "1",
    reason="defina TEST_REAL_CAPTURE=1 para rodar",
)
def test_real_capture_primary_monitor():
    from screen_watch.capture.mss_backend import MssCaptureBackend

    backend = MssCaptureBackend()
    try:
        x, y, w, h = backend.bounds()
        assert w > 0 and h > 0

        rect = (x, y, min(320, w), min(200, h))
        started = time.perf_counter()
        rgb = backend.capture(rect)
        elapsed = time.perf_counter() - started

        assert rgb.shape == (rect[3], rect[2], 3)
        assert rgb.dtype == np.uint8
        assert elapsed < 2.0
    finally:
        backend.close()


@pytest.mark.skipif(
    os.environ.get("TEST_REAL_TELEGRAM") != "1"
    or not os.environ.get("TELEGRAM_BOT_TOKEN")
    or not os.environ.get("TELEGRAM_TEST_CHAT_ID"),
    reason="defina TEST_REAL_TELEGRAM=1, TELEGRAM_BOT_TOKEN e TELEGRAM_TEST_CHAT_ID",
)
def test_real_telegram_send_photo():
    from screen_watch.alerts.telegram import TelegramNotifier
    from screen_watch.capture.frame import Frame
    from screen_watch.compare.protocol import ComparisonResult

    notifier = TelegramNotifier(chat_id=os.environ["TELEGRAM_TEST_CHAT_ID"], attach_roi=True)
    rgb = np.full((40, 60, 3), 120, dtype=np.uint8)
    frame = Frame(
        rgb=rgb,
        timestamp=time.time(),
        absolute_rect=(0, 0, 60, 40),
        window_rect=(0, 0, 60, 40),
        window_handle=0,
        sequence=1,
    )
    result = ComparisonResult(
        changed=True,
        score=1.0,
        threshold=0.1,
        strategy="integration",
        severity=3,
        detail={"synthetic": True},
    )

    # Levanta excecao se o HTTP nao for 2xx (sendPhoto).
    notifier.notify(result, frame)
