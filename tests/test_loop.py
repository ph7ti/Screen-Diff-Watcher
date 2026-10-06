from __future__ import annotations

import time

import numpy as np

from screen_watch.scheduler.loop import MonitorLoop, MonitorTarget


class FakeWindow:
    def __init__(self, minimized=False, exists=True, rect=(10, 20, 100, 50)):
        self.handle = 1
        self.title = "fake"
        self.rect = rect
        self.is_minimized = minimized
        self.exists = exists


class FakeBackend:
    def __init__(self, shape=(5, 5, 3), value=0, bounds=None):
        self.shape = shape
        self.value = value
        self._bounds = bounds
        self.calls = 0
        self.closed = False
        self.last_rect = None

    def bounds(self):
        return self._bounds

    def capture(self, rect):
        self.calls += 1
        self.last_rect = rect
        return np.full(self.shape, self.value, dtype=np.uint8)

    def close(self):
        self.closed = True


def _run(loop, seconds=0.15):
    loop.start()
    time.sleep(seconds)
    loop.stop(timeout=2.0)
    return loop


def test_emits_frames_with_resolved_rect():
    frames = []
    backend = FakeBackend()
    loop = MonitorLoop(
        frames.append,
        interval_s=0.01,
        target=MonitorTarget(window_handle=1, roi_relative=(5, 6, 5, 5)),
        backend=backend,
        window_lookup=lambda handle: FakeWindow(),
    )
    _run(loop)
    assert backend.calls >= 1
    assert backend.last_rect == (15, 26, 5, 5)
    assert frames[0].absolute_rect == (15, 26, 5, 5)
    assert frames[0].sequence == 1
    assert backend.closed is True


def test_missing_window_emits_event_and_skips_sink():
    frames = []
    events = []
    backend = FakeBackend()
    loop = MonitorLoop(
        frames.append,
        interval_s=0.01,
        target=MonitorTarget(window_handle=1, roi_relative=(0, 0, 5, 5)),
        backend=backend,
        window_lookup=lambda handle: None,
        on_event=lambda name, payload: events.append((name, payload)),
    )
    _run(loop)
    assert frames == []
    assert backend.calls == 0
    assert events and events[0][0] == "target_unavailable"
    assert events[0][1]["reason"] == "not_found"


def test_minimized_window_is_skipped():
    frames = []
    loop = MonitorLoop(
        frames.append,
        interval_s=0.01,
        target=MonitorTarget(window_handle=1, roi_relative=(0, 0, 5, 5)),
        backend=FakeBackend(),
        window_lookup=lambda handle: FakeWindow(minimized=True),
    )
    _run(loop)
    assert frames == []


def test_sink_error_does_not_kill_loop():
    errors = []

    def bad_sink(frame):
        raise RuntimeError("boom")

    loop = MonitorLoop(
        bad_sink,
        interval_s=0.01,
        target=MonitorTarget(window_handle=1, roi_relative=(0, 0, 5, 5)),
        backend=FakeBackend(),
        window_lookup=lambda handle: FakeWindow(),
        on_error=errors.append,
    )
    _run(loop)
    assert errors and isinstance(errors[0], RuntimeError)


def test_masks_are_applied_before_sink():
    frames = []
    loop = MonitorLoop(
        frames.append,
        interval_s=0.01,
        target=MonitorTarget(
            window_handle=1,
            roi_relative=(0, 0, 10, 10),
            masks=((0, 0, 5, 5),),
        ),
        backend=FakeBackend(shape=(10, 10, 3), value=255),
        window_lookup=lambda handle: FakeWindow(),
    )
    _run(loop)
    assert frames
    rgb = frames[0].rgb
    assert np.all(rgb[0:5, 0:5] == 0)  # regiao mascarada fica preta
    assert np.all(rgb[5:10, 5:10] == 255)  # o resto permanece intacto


def test_capture_is_clipped_to_virtual_bounds():
    events = []
    backend = FakeBackend(shape=(2, 2, 3), bounds=(0, 0, 22, 22))
    loop = MonitorLoop(
        lambda frame: None,
        interval_s=0.01,
        target=MonitorTarget(window_handle=1, roi_relative=(10, 10, 5, 5)),
        backend=backend,
        window_lookup=lambda handle: FakeWindow(rect=(10, 10, 100, 50)),
        on_event=lambda name, payload: events.append((name, payload)),
    )
    _run(loop)
    assert backend.last_rect == (20, 20, 2, 2)
    assert any(name == "capture_clipped" for name, _payload in events)


def test_roi_fully_off_screen_is_skipped_with_event():
    frames = []
    events = []
    backend = FakeBackend(bounds=(0, 0, 10, 10))
    loop = MonitorLoop(
        frames.append,
        interval_s=0.01,
        target=MonitorTarget(window_handle=1, roi_relative=(100, 100, 5, 5)),
        backend=backend,
        window_lookup=lambda handle: FakeWindow(rect=(0, 0, 50, 50)),
        on_event=lambda name, payload: events.append((name, payload)),
    )
    _run(loop)
    assert frames == []
    assert backend.calls == 0
    assert events and events[0][0] == "roi_off_screen"


def test_repeated_identical_errors_are_deduplicated():
    errors = []

    def bad_sink(frame):
        raise RuntimeError("mesmo erro")

    loop = MonitorLoop(
        bad_sink,
        interval_s=0.01,
        target=MonitorTarget(window_handle=1, roi_relative=(0, 0, 5, 5)),
        backend=FakeBackend(),
        window_lookup=lambda handle: FakeWindow(),
        on_error=errors.append,
    )
    _run(loop)
    assert len(errors) == 1


def test_next_wait_capped_by_deadline_provider():
    loop = MonitorLoop(lambda frame: None, interval_s=2.0)
    assert loop._next_wait(0.0) == 2.0
    assert loop._next_wait(0.5) == 1.5

    loop.deadline_provider = lambda: 0.2
    assert loop._next_wait(0.0) == 0.2
    loop.deadline_provider = lambda: 5.0
    assert loop._next_wait(0.0) == 2.0  # nunca estica alem do intervalo

    loop.deadline_provider = lambda: 0.0
    assert loop._next_wait(0.0) == 0.05  # piso do deadline


def test_next_wait_ignores_deadline_provider_errors():
    def boom():
        raise RuntimeError("deadline")

    loop = MonitorLoop(lambda frame: None, interval_s=1.0, deadline_provider=boom)
    assert loop._next_wait(0.0) == 1.0
