from __future__ import annotations

import numpy as np

from screen_watch.compare.pipeline import MODE_STAGES, ComparePipeline
from screen_watch.compare.protocol import ComparisonResult


def test_advanced_mode_is_ocr_only():
    assert MODE_STAGES["advanced"] == ("advanced",)


class RecordingStage:
    def __init__(self, name, changed):
        self.name = name
        self.changed = changed
        self.calls = 0
        self.initialized_with = None

    def initialize(self, baseline):
        self.initialized_with = baseline

    def compare(self, current):
        self.calls += 1
        return ComparisonResult(
            changed=self.changed, score=1.0, threshold=1.0, strategy=self.name
        )


def test_short_circuits_on_first_false(make_frame):
    first = RecordingStage("a", changed=False)
    second = RecordingStage("b", changed=True)
    pipeline = ComparePipeline([first, second])
    pipeline.initialize(make_frame(np.zeros((4, 4, 3), dtype=np.uint8)))
    result = pipeline.compare(make_frame(np.zeros((4, 4, 3), dtype=np.uint8)))
    assert result.strategy == "a"
    assert first.calls == 1
    assert second.calls == 0


def test_runs_all_when_all_true(make_frame):
    stages = [RecordingStage(n, changed=True) for n in ("a", "b", "c")]
    pipeline = ComparePipeline(stages)
    pipeline.initialize(make_frame(np.zeros((4, 4, 3), dtype=np.uint8)))
    result = pipeline.compare(make_frame(np.zeros((4, 4, 3), dtype=np.uint8)))
    assert result.strategy == "c"
    assert all(s.calls == 1 for s in stages)


def test_severity_is_enriched_on_final_result(make_frame):
    stage = RecordingStage("a", changed=True)
    stage.compare = lambda current: ComparisonResult(
        changed=True, score=3.0, threshold=1.0, strategy="a"
    )
    pipeline = ComparePipeline([stage])
    pipeline.initialize(make_frame(np.zeros((4, 4, 3), dtype=np.uint8)))
    result = pipeline.compare(make_frame(np.zeros((4, 4, 3), dtype=np.uint8)))
    assert result.severity == 3
