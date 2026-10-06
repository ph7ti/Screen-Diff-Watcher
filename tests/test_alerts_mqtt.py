from __future__ import annotations

import json
import sys
import types

import numpy as np
import pytest

from screen_watch.alerts.mqtt import MqttNotifier
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import MqttOptions
from screen_watch.errors import AppError


def _result():
    return ComparisonResult(
        changed=True, score=1.0, threshold=0.5, strategy="advanced", severity=2
    )


def _frame(make_frame):
    return make_frame(np.zeros((4, 4, 3), dtype=np.uint8), rect=(1, 2, 3, 4), handle=77)


class _FakeInfo:
    def __init__(self, rc: int = 0) -> None:
        self.rc = rc
        self.waited = None

    def wait_for_publish(self, timeout=None):
        self.waited = timeout


class _FakeClient:
    instances: list["_FakeClient"] = []
    connect_error: Exception | None = None

    def __init__(self, client_id=None) -> None:
        self.client_id = client_id
        self.calls: list[object] = []
        self.published: dict | None = None
        self.info = _FakeInfo()
        type(self).instances.append(self)

    def username_pw_set(self, username, password=None):
        self.calls.append(("username_pw_set", username, password))

    def tls_set(self):
        self.calls.append("tls_set")

    def connect(self, host, port):
        self.calls.append(("connect", host, port))
        if type(self).connect_error is not None:
            raise type(self).connect_error

    def publish(self, topic, payload=None, qos=0, retain=False):
        self.published = {"topic": topic, "payload": payload, "qos": qos, "retain": retain}
        self.calls.append("publish")
        return self.info

    def disconnect(self):
        self.calls.append("disconnect")


@pytest.fixture
def fake_paho(monkeypatch):
    _FakeClient.instances = []
    _FakeClient.connect_error = None
    module = types.ModuleType("paho.mqtt.client")
    module.Client = _FakeClient
    mqtt_pkg = types.ModuleType("paho.mqtt")
    mqtt_pkg.client = module
    paho = types.ModuleType("paho")
    paho.mqtt = mqtt_pkg
    monkeypatch.setitem(sys.modules, "paho", paho)
    monkeypatch.setitem(sys.modules, "paho.mqtt", mqtt_pkg)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", module)
    return _FakeClient


def _options(**overrides):
    base = dict(host="10.0.0.30", topic="screen-watch/default")
    base.update(overrides)
    return MqttOptions(**base)


def test_mqtt_publishes_default_json_payload(fake_paho, make_frame):
    notifier = MqttNotifier(_options(qos=1, retain=True), target_name="erp")

    notifier.notify(_result(), _frame(make_frame))

    client = fake_paho.instances[0]
    assert client.client_id == "screen-diff-watcher"
    assert ("connect", "10.0.0.30", 1883) in client.calls
    assert client.published["topic"] == "screen-watch/default"
    assert client.published["qos"] == 1
    assert client.published["retain"] is True
    payload = json.loads(client.published["payload"])
    assert payload["target"] == "erp"
    assert payload["severity"] == "2"
    assert "advanced" in payload["text"]
    assert client.calls[-1] == "disconnect"


def test_mqtt_payload_raw(fake_paho, make_frame):
    notifier = MqttNotifier(_options(payload_raw="alerta ${target} sev=${severity}"), target_name="x")
    notifier.notify(_result(), _frame(make_frame))
    assert fake_paho.instances[0].published["payload"] == "alerta x sev=2"


def test_mqtt_credentials_and_tls(fake_paho, monkeypatch, make_frame):
    monkeypatch.setenv("MQTT_USERNAME", "user")
    monkeypatch.setenv("MQTT_PASSWORD", "pw")
    notifier = MqttNotifier(_options(tls=True))

    notifier.notify(_result(), _frame(make_frame))

    client = fake_paho.instances[0]
    assert ("username_pw_set", "user", "pw") in client.calls
    assert "tls_set" in client.calls
    assert ("connect", "10.0.0.30", 8883) in client.calls


def test_mqtt_connect_failure(fake_paho, make_frame):
    fake_paho.connect_error = OSError("refused")
    with pytest.raises(AppError) as excinfo:
        MqttNotifier(_options()).notify(_result(), _frame(make_frame))
    assert excinfo.value.code == "alert.mqtt_unavailable"


def test_mqtt_publish_rc_failure(fake_paho, make_frame):
    original = fake_paho.__init__

    def init(self, client_id=None):
        original(self, client_id=client_id)
        self.info = _FakeInfo(rc=4)

    fake_paho.__init__ = init
    try:
        with pytest.raises(AppError) as excinfo:
            MqttNotifier(_options()).notify(_result(), _frame(make_frame))
        assert excinfo.value.code == "alert.mqtt_publish_failed"
    finally:
        fake_paho.__init__ = original


def test_mqtt_without_extra_raises(monkeypatch, make_frame):
    monkeypatch.setitem(sys.modules, "paho", None)
    monkeypatch.setitem(sys.modules, "paho.mqtt", None)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", None)
    with pytest.raises(AppError) as excinfo:
        MqttNotifier(_options()).notify(_result(), _frame(make_frame))
    assert excinfo.value.code == "alert.mqtt_missing_extra"


def test_mqtt_destination_in_target_list():
    from screen_watch.alerts.test_send import list_alert_targets
    from screen_watch.config.schema import AlertOptions, TargetConfig

    alert = AlertOptions(
        type="mqtt", id="barramento", options=MqttOptions(host="10.0.0.30", topic="topic/a")
    )
    target = TargetConfig(
        name="t", window_handle=1, roi_relative=(0, 0, 1, 1), alerts=(alert,)
    )
    rows = list_alert_targets(target)
    assert rows[0][4] == "topic/a@10.0.0.30:1883"
