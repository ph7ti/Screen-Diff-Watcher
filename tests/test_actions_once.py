from __future__ import annotations

import numpy as np

from screen_watch.actions.audit import ActionAudit
from screen_watch.actions.once import run_actions
from screen_watch.actions.protocol import ActionSpec, ActionStep
from screen_watch.capture.frame import Frame
from screen_watch.config.schema import TargetConfig


class FakeBackend:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def press(self, keys: str) -> None:
        self.keys.append(keys)


def _frame() -> Frame:
    rgb = np.zeros((10, 10, 3), dtype=np.uint8)
    return Frame(
        rgb=rgb,
        timestamp=0.0,
        absolute_rect=(0, 0, 10, 10),
        window_rect=(0, 0, 10, 10),
        window_handle=1,
        sequence=1,
    )


def _key_action() -> ActionSpec:
    return ActionSpec(name="a", settle_s=0.0, steps=(ActionStep(kind="key", keys="a"),))


def _target(actions: tuple[ActionSpec, ...]) -> TargetConfig:
    return TargetConfig(name="t", window_handle=1, roi_relative=(0, 0, 10, 10), actions=actions)


def test_run_actions_rehearsal_does_not_press(monkeypatch, tmp_path):
    backend = FakeBackend()
    monkeypatch.setattr("screen_watch.platform.input.default_backend", lambda: backend)
    audit = ActionAudit(tmp_path / "a.jsonl")

    code, lines = run_actions(_target((_key_action(),)), _frame(), armed=False, audit=audit)

    assert code == 0
    assert backend.keys == []
    assert any("rehearsal" in line for line in lines)


def test_run_actions_armed_executes(monkeypatch, tmp_path):
    backend = FakeBackend()
    monkeypatch.setattr("screen_watch.platform.input.default_backend", lambda: backend)
    audit = ActionAudit(tmp_path / "a.jsonl")

    code, lines = run_actions(
        _target((_key_action(),)),
        _frame(),
        armed=True,
        audit=audit,
        countdown=lambda: True,
    )

    assert code == 0
    assert backend.keys == ["a"]
    assert any("armed" in line for line in lines)


def test_run_actions_countdown_cancel_aborts(monkeypatch, tmp_path):
    backend = FakeBackend()
    monkeypatch.setattr("screen_watch.platform.input.default_backend", lambda: backend)
    audit = ActionAudit(tmp_path / "a.jsonl")

    code, lines = run_actions(
        _target((_key_action(),)),
        _frame(),
        armed=True,
        audit=audit,
        countdown=lambda: False,
    )

    assert code == 1
    assert backend.keys == []
    assert any("cancelled" in line for line in lines)
    assert not audit.path.exists()


def test_run_actions_disabled_action_is_skipped(monkeypatch, tmp_path):
    backend = FakeBackend()
    monkeypatch.setattr("screen_watch.platform.input.default_backend", lambda: backend)
    action = ActionSpec(
        name="a",
        enabled=False,
        settle_s=0.0,
        steps=(ActionStep(kind="key", keys="a"),),
    )

    code, lines = run_actions(
        _target((action,)), _frame(), armed=True, audit=ActionAudit(tmp_path / "a.jsonl")
    )

    assert code == 0
    assert backend.keys == []
    assert any("disabled" in line for line in lines)


def test_run_actions_without_actions():
    code, lines = run_actions(_target(()), _frame(), armed=False)
    assert code == 1
    assert any("has no actions" in line for line in lines)


def test_run_actions_armed_records_evidence(monkeypatch, tmp_path):
    import json

    backend = FakeBackend()
    monkeypatch.setattr("screen_watch.platform.input.default_backend", lambda: backend)
    audit = ActionAudit(tmp_path / "a.jsonl")

    class FakeRecorder:
        per_step = False

        def __init__(self):
            self.calls: list[tuple[str, int]] = []

        def record_action(self, frame, name, step=0):
            self.calls.append((name, step))
            return f"/x/{name}-{step}.png"

    recorder = FakeRecorder()
    code, _ = run_actions(
        _target((_key_action(),)),
        _frame(),
        armed=True,
        recorder=recorder,
        audit=audit,
        countdown=lambda: True,
    )

    assert code == 0
    assert recorder.calls == [("t", 0)]
    record = json.loads(audit.path.read_text(encoding="utf-8").splitlines()[0])
    assert record["evidence"] == ["/x/t-0.png"]


def test_run_actions_armed_records_evidence_per_step(monkeypatch, tmp_path):
    backend = FakeBackend()
    monkeypatch.setattr("screen_watch.platform.input.default_backend", lambda: backend)
    action = ActionSpec(
        name="a",
        settle_s=0.0,
        steps=(ActionStep(kind="key", keys="a"), ActionStep(kind="key", keys="b")),
    )

    class FakeRecorder:
        per_step = True

        def __init__(self):
            self.calls: list[tuple[str, int]] = []

        def record_action(self, frame, name, step=0):
            self.calls.append((name, step))
            return f"/x/{name}-{step}.png"

    recorder = FakeRecorder()
    code, _ = run_actions(
        _target((action,)),
        _frame(),
        armed=True,
        recorder=recorder,
        audit=ActionAudit(tmp_path / "a.jsonl"),
        countdown=lambda: True,
    )

    assert code == 0
    assert recorder.calls == [("t", 0), ("t", 1)]


def test_run_actions_reports_failure(monkeypatch, tmp_path):
    class BoomBackend(FakeBackend):
        def press(self, keys: str) -> None:
            from screen_watch.platform.input import InputUnavailable

            raise InputUnavailable("sem entrada")

    monkeypatch.setattr("screen_watch.platform.input.default_backend", lambda: BoomBackend())

    code, lines = run_actions(
        _target((_key_action(),)), _frame(), armed=True, audit=ActionAudit(tmp_path / "a.jsonl")
    )

    assert code == 1
    assert any("failed" in line for line in lines)
