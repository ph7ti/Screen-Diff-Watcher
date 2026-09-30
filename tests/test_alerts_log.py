from __future__ import annotations

import json

import numpy as np

from screen_watch.alerts.log import JsonlNotifier
from screen_watch.compare.protocol import ComparisonResult


def _result():
    return ComparisonResult(
        changed=True,
        score=0.42,
        threshold=0.08,
        strategy="advanced",
        severity=2,
        detail={"baseline_text": "a", "current_text": "b"},
    )


def test_writes_one_jsonl_line_with_expected_fields(make_frame, tmp_path):
    path = tmp_path / "nested" / "alerts.jsonl"
    notifier = JsonlNotifier(path=path)
    notifier.notify(_result(), make_frame(np.zeros((3, 3, 3), dtype=np.uint8), sequence=7))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["strategy"] == "advanced"
    assert record["severity"] == 2
    assert record["sequence"] == 7
    assert record["absolute_rect"] == [0, 0, 0, 0]
    assert record["detail"]["current_text"] == "b"


def test_appends_multiple_lines(make_frame, tmp_path):
    path = tmp_path / "alerts.jsonl"
    notifier = JsonlNotifier(path=path)
    notifier.notify(_result(), make_frame(np.zeros((3, 3, 3), dtype=np.uint8)))
    notifier.notify(_result(), make_frame(np.zeros((3, 3, 3), dtype=np.uint8)))
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_default_path_uses_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    from screen_watch.platform.paths import alerts_log_path

    assert alerts_log_path() == tmp_path / "logs" / "alerts.jsonl"
