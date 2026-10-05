from __future__ import annotations

from screen_watch.gui.calibration import severity_counts, to_csv


def test_to_csv_has_header_and_rows():
    text = to_csv(
        [
            (1.5, "default", 3.25, 6.0, 2),
            (2.0, "light", 0.5, 12.0, 0),
        ]
    )
    lines = text.splitlines()
    assert lines[0] == "timestamp,strategy,score,threshold,severity"
    assert lines[1] == "1.500,default,3.250000,6.000000,2"
    assert lines[2] == "2.000,light,0.500000,12.000000,0"
    assert text.endswith("\n")


def test_to_csv_empty_has_only_header():
    assert to_csv([]) == "timestamp,strategy,score,threshold,severity\n"


def test_severity_counts():
    samples = [
        (1.0, "light", 0.0, 1.0, 0),
        (2.0, "light", 0.0, 1.0, 3),
        (3.0, "light", 0.0, 1.0, 3),
    ]
    assert severity_counts(samples) == {0: 1, 3: 2}
    assert severity_counts([]) == {}
