from __future__ import annotations

import os

import numpy as np

from screen_watch.alerts.chain import DispatchOutcome
from screen_watch.app import MonitorSession
from screen_watch.config.schema import EvidenceOptions, TargetConfig
from screen_watch.evidence.recorder import EvidenceRecorder


class _FakeBackend:
    def __init__(self, bounds=(0, 0, 1000, 1000)):
        self._bounds = bounds
        self.captured: list[tuple[int, int, int, int]] = []
        self.closed = False

    def bounds(self):
        return self._bounds

    def capture(self, rect):
        self.captured.append(rect)
        return np.zeros((rect[3], rect[2], 3), dtype=np.uint8)

    def close(self):
        self.closed = True


def _target(**extra) -> TargetConfig:
    return TargetConfig(
        name="t", window_handle=1, roi_relative=(0, 0, 10, 10), mode="light", **extra
    )


def test_disabled_by_default_returns_none():
    assert EvidenceRecorder.from_options(EvidenceOptions()) is None
    assert EvidenceRecorder.from_options(None) is None


def test_force_enabled_builds_recorder():
    recorder = EvidenceRecorder.from_options(EvidenceOptions(), force_enabled=True)
    assert recorder is not None
    assert recorder.on_baseline is True


def test_capture_writes_full_window(tmp_path, make_frame, solid):
    backend = _FakeBackend()
    recorder = EvidenceRecorder(backend_factory=lambda: backend, dir=tmp_path)
    frame = make_frame(solid(10), rect=(10, 20, 50, 30))

    path = recorder.capture(frame, "change", "alvo")

    assert path is not None and path.exists()
    assert path.parent.name == "alvo"
    assert path.name.endswith("_change.png")
    assert backend.captured == [(10, 20, 50, 30)]
    assert backend.closed is True


def test_capture_records_action_kind(tmp_path, make_frame, solid):
    backend = _FakeBackend()
    recorder = EvidenceRecorder(backend_factory=lambda: backend, dir=tmp_path)
    frame = make_frame(solid(10), rect=(0, 0, 20, 20))

    path = recorder.record_action(frame, "alvo", step=3)

    assert path is not None
    assert path.name.endswith("_action-3.png")


def test_capture_skips_window_offscreen(tmp_path, make_frame, solid):
    backend = _FakeBackend(bounds=(0, 0, 100, 100))
    recorder = EvidenceRecorder(backend_factory=lambda: backend, dir=tmp_path)
    frame = make_frame(solid(10), rect=(500, 500, 10, 10))

    assert recorder.capture(frame, "change", "alvo") is None
    assert not list(tmp_path.rglob("*.png"))


def test_capture_clips_partial_window(tmp_path, make_frame, solid):
    backend = _FakeBackend(bounds=(0, 0, 100, 100))
    recorder = EvidenceRecorder(backend_factory=lambda: backend, dir=tmp_path)
    frame = make_frame(solid(10), rect=(90, 90, 40, 40))

    assert recorder.capture(frame, "change", "alvo") is not None
    assert backend.captured == [(90, 90, 10, 10)]


def test_capture_failure_only_logs(tmp_path, make_frame, solid):
    class _Boom:
        def capture(self, rect):
            raise RuntimeError("boom")

        def close(self):
            pass

    recorder = EvidenceRecorder(backend_factory=_Boom, dir=tmp_path)
    frame = make_frame(solid(10), rect=(0, 0, 20, 20))
    assert recorder.capture(frame, "change", "alvo") is None


def test_prune_by_count(tmp_path):
    directory = tmp_path / "alvo"
    directory.mkdir()
    for index in range(5):
        path = directory / f"{index}_change.png"
        path.write_bytes(b"x")
        os.utime(path, (1000 + index, 1000 + index))

    recorder = EvidenceRecorder(backend_factory=_FakeBackend, dir=tmp_path, keep_per_target=2)
    recorder.prune()

    assert sorted(p.name for p in directory.glob("*.png")) == ["3_change.png", "4_change.png"]


def test_prune_by_total_mb(tmp_path):
    directory = tmp_path / "alvo"
    directory.mkdir()
    for index in range(4):
        path = directory / f"{index}_change.png"
        path.write_bytes(b"x" * (1024 * 1024))
        os.utime(path, (1000 + index, 1000 + index))

    recorder = EvidenceRecorder(
        backend_factory=_FakeBackend, dir=tmp_path, keep_per_target=50, max_total_mb=2
    )
    recorder.prune()

    assert len(list(directory.glob("*.png"))) == 2


def test_prune_is_per_target(tmp_path):
    for name in ("a", "b"):
        directory = tmp_path / name
        directory.mkdir()
        for index in range(3):
            path = directory / f"{index}_change.png"
            path.write_bytes(b"x")
            os.utime(path, (1000 + index, 1000 + index))

    recorder = EvidenceRecorder(backend_factory=_FakeBackend, dir=tmp_path, keep_per_target=1)
    recorder.prune()

    for name in ("a", "b"):
        assert len(list((tmp_path / name).glob("*.png"))) == 1


def test_session_records_baseline_then_change(make_frame, solid):
    class _Recorder:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        def record_baseline(self, frame, name):
            self.calls.append(("baseline", name))

        def record_change(self, frame, name):
            self.calls.append(("change", name))

    recorder = _Recorder()
    session = MonitorSession(_target(), recorder=recorder)
    session.chain.dispatch = lambda result, frame: DispatchOutcome.FIRED

    session(make_frame(solid(10), sequence=1))
    session(make_frame(solid(10), sequence=2))
    session(make_frame(solid(200), sequence=3))

    assert recorder.calls == [("baseline", "t"), ("change", "t")]


def test_record_hooks_honor_flags(tmp_path, make_frame, solid):
    recorder = EvidenceRecorder(
        backend_factory=_FakeBackend, dir=tmp_path, on_baseline=False, on_change=False
    )
    frame = make_frame(solid(10), rect=(0, 0, 20, 20))
    assert recorder.record_baseline(frame, "alvo") is None
    assert recorder.record_change(frame, "alvo") is None
    assert not list(tmp_path.rglob("*.png"))


def test_capture_without_bounds_on_backend(tmp_path, make_frame, solid):
    class _NoBounds:
        def __init__(self):
            self.captured = []

        def capture(self, rect):
            self.captured.append(rect)
            return np.zeros((max(1, rect[3]), max(1, rect[2]), 3), dtype=np.uint8)

        def close(self):
            pass

    recorder = EvidenceRecorder(backend_factory=_NoBounds, dir=tmp_path)
    frame = make_frame(solid(10), rect=(5, 6, 20, 20))
    assert recorder.capture(frame, "change", "alvo") is not None


def test_from_options_enabled_builds_recorder(tmp_path):
    recorder = EvidenceRecorder.from_options(EvidenceOptions(enabled=True, dir=str(tmp_path)))
    assert recorder is not None
    assert recorder.base_dir == tmp_path


def test_captures_dir_prefers_options_dir(tmp_path):
    from screen_watch.evidence.recorder import captures_dir, default_captures_dir

    assert captures_dir(EvidenceOptions(dir=str(tmp_path))) == tmp_path
    assert captures_dir(None) == default_captures_dir()
    assert captures_dir(EvidenceOptions()) == default_captures_dir()


def test_ensure_captures_dir_creates_missing_parents(tmp_path):
    from screen_watch.evidence.recorder import ensure_captures_dir

    target = tmp_path / "a" / "b"
    created = ensure_captures_dir(EvidenceOptions(dir=str(target)))

    assert created == target
    assert target.is_dir()


def test_target_name_is_sanitized(tmp_path, make_frame, solid):
    recorder = EvidenceRecorder(backend_factory=_FakeBackend, dir=tmp_path)
    frame = make_frame(solid(10), rect=(0, 0, 20, 20))
    path = recorder.record_action(frame, "al vo/1", step=2)
    assert path is not None
    assert path.parent.name == "al_vo_1"
    assert path.name.endswith("_action-2.png")

