from __future__ import annotations

import os

from screen_watch.alerts.history import filter_records, find_evidence, read_records


def test_read_records_skips_invalid_and_blank_lines(tmp_path):
    path = tmp_path / "alerts.jsonl"
    path.write_text(
        '{"ts": 1.0, "severity": 1}\n'
        "\n"
        "not json\n"
        "[1, 2]\n"
        '{"ts": 2.0, "severity": 2}\n',
        encoding="utf-8",
    )

    records, invalid = read_records(path)

    assert [record["ts"] for record in records] == [1.0, 2.0]
    assert invalid == 2


def test_read_records_missing_file(tmp_path):
    records, invalid = read_records(tmp_path / "nope.jsonl")
    assert records == [] and invalid == 0


def test_filter_records_by_window_severity_and_strategy():
    records = [
        {"ts": 100.0, "severity": 0, "strategy": "light"},
        {"ts": 200.0, "severity": 2, "strategy": "default"},
        {"ts": 300.0, "severity": 3, "strategy": "advanced"},
        {"severity": 3, "strategy": "advanced"},
    ]

    assert [r.get("ts") for r in filter_records(records, since=150.0, until=250.0)] == [200.0]
    assert [r.get("ts") for r in filter_records(records, severity_min=2)] == [
        200.0,
        300.0,
        None,
    ]
    assert [r.get("ts") for r in filter_records(records, strategy="advanced")] == [
        300.0,
        None,
    ]
    assert len(filter_records(records)) == 4


def test_find_evidence_picks_nearest_within_tolerance(tmp_path):
    target = tmp_path / "painel"
    target.mkdir()
    near = target / "20261005-120000-000_change.png"
    far = target / "20261005-130000-000_change.png"
    near.write_bytes(b"")
    far.write_bytes(b"")
    timestamp = 1_000_000.0
    os.utime(near, (timestamp + 1.0, timestamp + 1.0))
    os.utime(far, (timestamp + 3600.0, timestamp + 3600.0))

    assert find_evidence(timestamp, tmp_path) == near
    assert find_evidence(timestamp + 30.0, tmp_path) is None


def test_find_evidence_missing_dir(tmp_path):
    assert find_evidence(1.0, tmp_path / "nope") is None


def test_filter_records_ignores_bad_types():
    records = [{"ts": "x", "severity": "high", "strategy": "light"}]
    assert filter_records(records, since=0.0) == []
    assert filter_records(records, severity_min=1) == []
    assert len(filter_records(records, strategy="light")) == 1
