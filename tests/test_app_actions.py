from __future__ import annotations

from screen_watch.alerts.chain import DispatchOutcome
from screen_watch.app import MonitorSession, evidence_recorder, profile_from_config
from screen_watch.config.loader import ConfigError
from screen_watch.config.schema import (
    AppConfig,
    EvidenceOptions,
    ProfileOptions,
    TargetConfig,
)


def _target(**extra) -> TargetConfig:
    return TargetConfig(
        name="t",
        window_handle=1,
        roi_relative=(0, 0, 10, 10),
        mode="light",
        rearm=False,
        **extra,
    )


def test_profile_from_config_none_uses_default_alerts():
    profile = profile_from_config(None)
    assert [alert.type for alert in profile.alerts] == ["sound", "popup", "log"]


def test_profile_from_config_legacy_uses_matching_target():
    config = AppConfig(
        version=1,
        legacy=True,
        targets=(
            TargetConfig(name="painel", window_handle=1, roi_relative=(0, 0, 10, 10), mode="light"),
        ),
    )
    profile = profile_from_config(config, None, "painel")
    assert profile.defaults.mode == "light"


def test_profile_from_config_missing_raises_config_error():
    config = AppConfig(profile="default", profiles={"default": ProfileOptions()})
    try:
        profile_from_config(config, "inexistente")
    except ConfigError as exc:
        assert "unknown profile" in str(exc)
        assert exc.code == "config.profile_unknown"
    else:  # pragma: no cover - so falha se o comportamento regredir
        raise AssertionError("profile invalido deveria levantar ConfigError")


def test_profile_from_config_resolves_requested_profile():
    config = AppConfig(
        profile="default",
        profiles={
            "default": ProfileOptions(),
            "trabalho": ProfileOptions(),
        },
    )
    assert profile_from_config(config, "trabalho") is config.profiles["trabalho"]


def test_evidence_recorder_helper(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path / "home"))
    assert evidence_recorder(None) is None
    config = AppConfig(
        profiles={"default": ProfileOptions()},
        evidence=EvidenceOptions(enabled=True, dir=str(tmp_path)),
    )
    recorder = evidence_recorder(config)
    assert recorder is not None
    assert recorder.base_dir == tmp_path


def test_evidence_recorder_honors_state_toggle(monkeypatch, tmp_path):
    from screen_watch.evidence.recorder import default_captures_dir
    from screen_watch.platform.paths import update_state

    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path / "home"))

    # Config v1/legado: `evidence.enabled` fica desligado por default.
    config = AppConfig(version=1, legacy=True)
    assert evidence_recorder(config) is None

    update_state(evidence_enabled=True)
    recorder = evidence_recorder(config)
    assert recorder is not None
    assert recorder.base_dir == default_captures_dir()

    update_state(evidence_enabled=False)
    assert evidence_recorder(config) is None


def test_monitor_session_action_rebaseline_plumbing(make_frame, solid):
    class FakeActions:
        def __init__(self, request):
            self.request = request
            self.calls = 0
            self.ticks = 0

        def on_result(self, result, frame):
            self.calls += 1
            return self.request

        def on_tick(self, frame):
            self.ticks += 1

        def next_deadline_delay(self):
            return None

    rebaselining = FakeActions(True)
    session = MonitorSession(_target(), actions=rebaselining)
    session.chain.dispatch = lambda result, frame: DispatchOutcome.FIRED
    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))
    assert rebaselining.calls == 1
    session(make_frame(solid(250), sequence=3))
    assert rebaselining.calls == 1  # baseline avancou apos a acao

    persistent = FakeActions(False)
    session2 = MonitorSession(_target(), actions=persistent)
    session2.chain.dispatch = lambda result, frame: DispatchOutcome.NONE_ENABLED
    session2(make_frame(solid(100), sequence=1))
    session2(make_frame(solid(250), sequence=2))
    session2(make_frame(solid(250), sequence=3))
    assert persistent.calls == 2  # sem rebaseline, a mudanca persiste


def test_monitor_session_request_rebaseline_next_frame(make_frame, solid):
    session = MonitorSession(_target())
    session(make_frame(solid(100), sequence=1))
    session.request_rebaseline()
    assert session._pending_rebaseline is True

    session(make_frame(solid(250), sequence=2))
    assert session._pending_rebaseline is False
    dispatched = []
    session.chain.dispatch = lambda result, frame: dispatched.append(result)
    session(make_frame(solid(250), sequence=3))
    assert dispatched == []  # o frame anterior virou baseline


def test_monitor_session_without_actions_has_none(make_frame, solid):
    session = MonitorSession(_target())
    assert session.actions is None


def test_monitor_session_action_event_plumbing(monkeypatch, tmp_path, make_frame, solid):
    from screen_watch.actions.protocol import ActionSpec, ActionStep

    monkeypatch.setenv("SCREEN_WATCH_HOME", str(tmp_path))
    events: list[dict] = []
    target = _target(
        actions=(
            ActionSpec(name="a", settle_s=0.0, steps=(ActionStep(kind="key", keys="a"),)),
        )
    )
    session = MonitorSession(target, on_action=events.append)
    session.chain.dispatch = lambda result, frame: DispatchOutcome.FIRED

    session(make_frame(solid(100), sequence=1))
    session(make_frame(solid(250), sequence=2))

    assert events and events[0]["mode"] == "rehearsal"
    assert events[0]["action"] == "a"


class _FakeTickActions:
    def __init__(self, delay=None):
        self.ticks = 0
        self._delay = delay

    def on_result(self, result, frame):
        return False

    def on_tick(self, frame):
        self.ticks += 1

    def next_deadline_delay(self):
        return self._delay


def test_monitor_session_calls_on_tick_only_after_baseline(make_frame, solid):
    actions = _FakeTickActions()
    session = MonitorSession(_target(), actions=actions)

    session(make_frame(solid(100), sequence=1))  # baseline: nao avalia
    assert actions.ticks == 0

    session(make_frame(solid(100), sequence=2))
    session(make_frame(solid(100), sequence=3))
    assert actions.ticks == 2

    session.request_rebaseline()
    session(make_frame(solid(100), sequence=4))
    assert actions.ticks == 2  # frame de re-baseline tambem nao avalia


def test_monitor_session_next_deadline_delay_delegates():
    session = MonitorSession(_target(), actions=_FakeTickActions(delay=12.5))
    assert session.next_deadline_delay() == 12.5

    without = MonitorSession(_target())
    assert without.actions is None
    assert without.next_deadline_delay() is None


def test_build_loop_wires_deadline_provider():
    from screen_watch.app import build_loop

    session = MonitorSession(_target())
    loop = build_loop(_target(), session)
    assert loop.deadline_provider is not None
    assert loop.deadline_provider() is None

    explicit = build_loop(_target(), session, deadline_provider=None)
    assert explicit.deadline_provider is None
