from __future__ import annotations

import numpy as np
import pytest

from screen_watch.alerts.template import (
    context,
    render_mapping,
    render_string,
    validate_placeholders,
)
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.errors import ConfigError


def _result(severity=2):
    return ComparisonResult(
        changed=True, score=1.0, threshold=0.5, strategy="advanced", severity=severity
    )


def _frame(make_frame):
    return make_frame(np.zeros((4, 4, 3), dtype=np.uint8), rect=(1, 2, 3, 4), handle=77)


def test_context_normalizes_values(make_frame):
    values = context(_result(), _frame(make_frame), target_name="painel")
    assert values["score"] == "1.000"
    assert values["threshold"] == "0.500"
    assert values["severity"] == "2"
    assert values["target"] == "painel"
    assert values["changed"] == "true"
    assert values["window_handle"] == "77"
    assert values["roi"] == "1,2,3,4"
    assert values["message"] == "advanced: score=1.00 (severity 2)"
    assert values["timestamp"].endswith("Z")


def test_render_string_braces_are_literal(make_frame):
    values = context(_result(), _frame(make_frame), target_name="t")
    assert render_string('{"alvo": "${target}"}', values) == '{"alvo": "t"}'


def test_render_string_dollar_escape(make_frame):
    values = context(_result(), _frame(make_frame))
    assert render_string("preco $$5", values) == "preco $5"


def test_render_string_env_is_read_at_send_time(monkeypatch, make_frame):
    values = context(_result(), _frame(make_frame))
    monkeypatch.setenv("MY_SECRET", "s3cr3t")
    assert render_string("Bearer ${env:MY_SECRET}", values) == "Bearer s3cr3t"
    monkeypatch.delenv("MY_SECRET")
    assert render_string("Bearer ${env:MY_SECRET}", values) == "Bearer "


def test_render_mapping_is_recursive(make_frame):
    values = context(_result(), _frame(make_frame), target_name="t")
    rendered = render_mapping({"a": "${target}", "b": ["${score}", 3]}, values)
    assert rendered == {"a": "t", "b": ["1.000", 3]}


def test_validate_placeholders_accepts_known_and_env():
    validate_placeholders({"text": "${target} ${env:VAR}"}, "options.payload")
    validate_placeholders("${message}", "options.payload_raw")


def test_validate_placeholders_rejects_unknown():
    with pytest.raises(ConfigError) as excinfo:
        validate_placeholders({"text": "${nope}"}, "options.payload")
    assert excinfo.value.code == "config.alert_unknown_placeholder"


def test_validate_placeholders_rejects_malformed():
    with pytest.raises(ConfigError) as excinfo:
        validate_placeholders("${bad", "options.payload_raw")
    assert excinfo.value.code == "config.alert_unknown_placeholder"


def test_env_secrets_collects_resolved_values(monkeypatch):
    from screen_watch.alerts.template import env_secrets

    monkeypatch.setenv("TOK", "abc123")
    assert env_secrets({"h": "Bearer ${env:TOK}"}) == ["abc123"]
    monkeypatch.delenv("TOK")
    assert env_secrets({"h": "Bearer ${env:TOK}"}) == []
