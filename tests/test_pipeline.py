from __future__ import annotations

import numpy as np

from screen_watch.compare.pipeline import MODE_STAGES, ComparePipeline
from screen_watch.compare.protocol import ComparisonResult


def test_advanced_mode_gates_ocr_with_phash():
    assert MODE_STAGES["advanced"] == ("default", "advanced")


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


def test_build_pipeline_keeps_the_gate_without_watch():
    from screen_watch.app import build_pipeline
    from screen_watch.config.schema import CompareOptions

    pipeline = build_pipeline("advanced", CompareOptions())
    assert [stage.name for stage in pipeline.stages] == ["default", "advanced"]


def test_build_pipeline_ignores_empty_watch_text():
    from screen_watch.app import build_pipeline
    from screen_watch.config.schema import AdvancedOptions, CompareOptions, TextWatchOptions

    options = CompareOptions(advanced=AdvancedOptions(text_watch=TextWatchOptions(text=" ")))
    pipeline = build_pipeline("advanced", options)
    assert [stage.name for stage in pipeline.stages] == ["default", "advanced"]


def test_build_pipeline_with_text_watch_bypasses_the_phash_gate(monkeypatch, make_frame):
    from screen_watch.app import build_pipeline
    from screen_watch.compare.advanced import OCRTextDiffStrategy
    from screen_watch.config.schema import AdvancedOptions, CompareOptions, TextWatchOptions

    texts = iter(["", "CONCLUIDO"])

    def fake_extract(self, rgb):
        return next(texts)

    monkeypatch.setattr(OCRTextDiffStrategy, "_extract", fake_extract)
    options = CompareOptions(
        advanced=AdvancedOptions(text_watch=TextWatchOptions(text="concluido"))
    )
    pipeline = build_pipeline("advanced", options)
    # Sem o gate phash: o OCR roda a cada tick e o veredito do watch e autoritativo.
    assert [stage.name for stage in pipeline.stages] == ["advanced"]

    pipeline.initialize(make_frame(np.zeros((4, 4, 3), dtype=np.uint8)))
    current = make_frame(np.zeros((4, 4, 3), dtype=np.uint8))  # pixels identicos
    result = pipeline.compare(current)
    assert result.changed is True
    assert result.severity == 3
    assert result.detail["text_watch"]["present_now"] is True
