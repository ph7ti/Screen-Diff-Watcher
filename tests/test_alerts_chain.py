from __future__ import annotations

import numpy as np

from screen_watch.alerts.chain import AlertChain, DispatchOutcome
from screen_watch.compare.protocol import ComparisonResult


class FakeNotifier:
    def __init__(
        self,
        name="n",
        *,
        enabled=True,
        severity_min=1,
        cooldown_s=0.0,
        boom=False,
        uid=None,
    ):
        self.name = name
        self.enabled = enabled
        self.severity_min = severity_min
        self.cooldown_s = cooldown_s
        self.calls = 0
        self.boom = boom
        if uid is not None:
            self.uid = uid

    def notify(self, result, frame):
        self.calls += 1
        if self.boom:
            raise RuntimeError("boom")


def _result(make_frame, severity=3):
    return ComparisonResult(
        changed=True, score=1.0, threshold=0.5, strategy="s", severity=severity
    )


def _frame(make_frame):
    return make_frame(np.zeros((4, 4, 3), dtype=np.uint8))


def test_none_enabled(make_frame):
    chain = AlertChain([FakeNotifier(enabled=False)])
    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.NONE_ENABLED


def test_no_notifiers_is_none_enabled(make_frame):
    chain = AlertChain([])
    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.NONE_ENABLED


def test_below_min(make_frame):
    chain = AlertChain([FakeNotifier(severity_min=3)])
    outcome = chain.dispatch(_result(make_frame, severity=1), _frame(make_frame))
    assert outcome is DispatchOutcome.BELOW_MIN
    assert chain.notifiers[0].calls == 0


def test_fired_then_cooldown(make_frame):
    notifier = FakeNotifier(cooldown_s=60.0)
    chain = AlertChain([notifier])
    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.FIRED
    assert notifier.calls == 1
    outcome = chain.dispatch(_result(make_frame), _frame(make_frame))
    assert outcome is DispatchOutcome.SUPPRESSED_COOLDOWN
    assert notifier.calls == 1


def test_failure_does_not_block_other_notifiers(make_frame):
    failing = FakeNotifier(name="bad", boom=True)
    ok = FakeNotifier(name="good")
    chain = AlertChain([failing, ok])
    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.FIRED
    assert failing.calls == 1
    assert ok.calls == 1


def test_all_failing_returns_failed_and_backs_off(make_frame):
    notifier = FakeNotifier(boom=True, cooldown_s=60.0)
    chain = AlertChain([notifier])
    outcome = chain.dispatch(_result(make_frame), _frame(make_frame))
    assert outcome is DispatchOutcome.FAILED
    assert notifier.calls == 1

    # Backoff: nao re-tenta no tick seguinte enquanto o cooldown nao expira.
    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.SUPPRESSED_COOLDOWN
    assert notifier.calls == 1


def test_reset_clears_cooldown(make_frame):
    notifier = FakeNotifier(cooldown_s=60.0)
    chain = AlertChain([notifier])
    chain.dispatch(_result(make_frame), _frame(make_frame))
    chain.reset()
    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.FIRED
    assert notifier.calls == 2


def test_two_webhooks_with_distinct_ids_are_independent(make_frame):
    fast = FakeNotifier(name="webhook", uid="teams", cooldown_s=0.0)
    slow = FakeNotifier(name="webhook", uid="erp", cooldown_s=60.0)
    chain = AlertChain([fast, slow])

    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.FIRED
    assert fast.calls == 1
    assert slow.calls == 1

    # O cooldown do `slow` nao pode ser compartilhado com o `fast` (mesmo `name`).
    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.FIRED
    assert fast.calls == 2
    assert slow.calls == 1


def test_last_errors_exposes_failures_even_when_another_fires(make_frame):
    boom = FakeNotifier(name="telegram", uid="telegram", boom=True)
    ok = FakeNotifier(name="log", uid="log")
    chain = AlertChain([boom, ok])

    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.FIRED
    assert chain.last_errors == [("telegram", "boom")]

    boom.enabled = False
    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.FIRED
    assert chain.last_errors == []


def test_gate_snooze_suppresses_without_trying_notifiers(make_frame):
    from screen_watch.alerts.gate import AlertGate

    gate = AlertGate(snooze_until=9_999_999_999.0)
    notifier = FakeNotifier()
    chain = AlertChain([notifier], gate=gate)

    outcome = chain.dispatch(_result(make_frame), _frame(make_frame))
    assert outcome is DispatchOutcome.SUPPRESSED_MANUAL
    assert notifier.calls == 0
    assert chain.last_errors == []


def test_gate_expired_snooze_allows_dispatch(make_frame):
    from screen_watch.alerts.gate import AlertGate

    gate = AlertGate(snooze_until=1.0)  # epoch antigo = expirado
    notifier = FakeNotifier()
    chain = AlertChain([notifier], gate=gate)

    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.FIRED
    assert notifier.calls == 1


def test_gate_mute_suppresses_even_with_no_enabled(make_frame):
    from screen_watch.alerts.gate import AlertGate

    gate = AlertGate(muted=True)
    chain = AlertChain([FakeNotifier(enabled=False)], gate=gate)

    # O gate tem precedencia: a GUI mostra "muted" mesmo sem canal habilitado.
    assert chain.dispatch(_result(make_frame), _frame(make_frame)) is DispatchOutcome.SUPPRESSED_MANUAL
