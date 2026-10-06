from __future__ import annotations

import pytest
import yaml

from screen_watch.config.loader import (
    ConfigError,
    config_from_dict,
    default_config_dict,
    load_config,
    migrate_config_dict,
    remove_target_from_config,
    save_config,
    set_profile_sound_file,
)


def _legacy(**extra):
    raw = {"targets": [{"name": "x", "window_handle": 42, "roi_relative": [1, 2, 3, 4], **extra}]}
    return config_from_dict(raw)


def _v2_dict(**profile_extra):
    profile = {
        "defaults": {"mode": "advanced", "poll_interval_s": 2.0, "rearm": True},
        "alerts": [{"type": "log"}],
    }
    profile.update(profile_extra)
    return {"version": 2, "profile": "default", "profiles": {"default": profile}}


# -- v1 legado -------------------------------------------------------------


def test_minimal_target_parses():
    target = _legacy().get_target("x")
    assert target is not None
    assert target.window_handle == 42
    assert target.roi_relative == (1, 2, 3, 4)
    assert target.mode == "advanced"
    assert target.poll_interval_s == 2.0
    assert target.rearm is True


def test_legacy_yaml_sets_legacy_flag():
    config = _legacy()
    assert config.legacy is True
    assert config.version == 1
    assert config.profiles == {}


def test_missing_required_field_raises():
    with pytest.raises(ConfigError):
        config_from_dict({"targets": [{"name": "x", "roi_relative": [1, 2, 3, 4]}]})


def test_bad_rect_raises():
    with pytest.raises(ConfigError):
        config_from_dict({"targets": [{"name": "x", "window_handle": 1, "roi_relative": [1, 2]}]})


def test_alerts_require_type():
    with pytest.raises(ConfigError):
        config_from_dict(
            {
                "targets": [
                    {
                        "name": "x",
                        "window_handle": 1,
                        "roi_relative": [1, 2, 3, 4],
                        "alerts": [{"enabled": True}],
                    }
                ]
            }
        )


def test_advanced_defaults():
    options = _legacy().get_target("x").compare_options.advanced
    assert options.lang == "por+eng"
    assert options.upscale == 2
    assert options.psm == 6
    assert options.tesseract_cmd is None


def test_advanced_tesseract_cmd_parsed():
    target = _legacy(
        compare_options={"advanced": {"tesseract_cmd": r"C:\Tesseract\tesseract.exe"}}
    ).get_target("x")
    assert target.compare_options.advanced.tesseract_cmd == r"C:\Tesseract\tesseract.exe"


def test_invalid_mode_raises():
    with pytest.raises(ConfigError):
        _legacy(mode="turbo")


def test_poll_interval_below_minimum_raises():
    with pytest.raises(ConfigError):
        _legacy(poll_interval_s=0.5)


def test_poll_interval_at_minimum_is_accepted():
    assert _legacy(poll_interval_s=1.0).get_target("x").poll_interval_s == 1.0


def test_rearm_false_is_parsed():
    assert _legacy(rearm=False).get_target("x").rearm is False


def test_log_alert_path_parsed():
    target = _legacy(alerts=[{"type": "log", "path": "custom.jsonl"}]).get_target("x")
    assert target.alerts[0].path == "custom.jsonl"


def test_non_integer_window_handle_raises_config_error():
    with pytest.raises(ConfigError):
        config_from_dict(
            {"targets": [{"name": "x", "window_handle": "abc", "roi_relative": [1, 2, 3, 4]}]}
        )


def test_non_numeric_poll_interval_raises_config_error():
    with pytest.raises(ConfigError):
        _legacy(poll_interval_s="fast")


def test_non_boolean_rearm_raises_config_error():
    with pytest.raises(ConfigError):
        _legacy(rearm="maybe")


def test_targets_must_be_a_list():
    with pytest.raises(ConfigError):
        config_from_dict({"targets": "x"})


def test_alert_must_be_a_mapping():
    with pytest.raises(ConfigError):
        _legacy(alerts=[1])


def test_roi_values_must_be_integers():
    with pytest.raises(ConfigError):
        config_from_dict(
            {"targets": [{"name": "x", "window_handle": 1, "roi_relative": [1, 2, 3, "z"]}]}
        )


# -- v2 (perfis) -----------------------------------------------------------


def test_default_sound_file_is_alert_mp3():
    config = config_from_dict(default_config_dict())
    profile = config.resolve()
    assert profile.alerts[0].type == "sound"
    assert profile.alerts[0].file == "alert.mp3"


def test_parse_sound_alert_defaults_to_alert_mp3():
    from screen_watch.config.loader import parse_alerts

    alert = parse_alerts([{"type": "sound"}], "alerts")[0]
    assert alert.file == "alert.mp3"


def test_default_config_is_v2_and_round_trips(tmp_path):
    path = tmp_path / "config.yaml"
    save_config(path, default_config_dict())
    config = load_config(path)
    assert config.version == 2
    assert config.legacy is False
    assert config.profile == "default"
    profile = config.resolve()
    assert profile.defaults.mode == "advanced"
    assert profile.defaults.rearm is True
    assert len(profile.alerts) == 3
    assert profile.alerts[2].bot_token_env == "TELEGRAM_BOT_TOKEN"
    assert profile.alerts[2].chat_id == "123456789"


def test_v2_default_config_disables_evidence():
    config = config_from_dict(default_config_dict())
    assert config.evidence.enabled is False
    assert config.schedule.enabled is False
    assert config.ui.arm_durations_min == (1, 5, 15, 30)


def test_v2_resolve_unknown_profile_raises_key_error():
    config = config_from_dict(_v2_dict())
    with pytest.raises(KeyError):
        config.resolve("inexistente")


def test_v2_active_profile_must_exist():
    raw = _v2_dict()
    raw["profile"] = "trabalho"
    with pytest.raises(ConfigError):
        config_from_dict(raw)


def test_v2_requires_profiles_section():
    with pytest.raises(ConfigError):
        config_from_dict({"version": 2, "profile": "default"})


def test_v2_parses_second_profile():
    raw = _v2_dict()
    raw["profiles"]["trabalho"] = {
        "defaults": {"mode": "default", "poll_interval_s": 1.0},
        "alerts": [],
    }
    config = config_from_dict(raw)
    assert config.resolve("trabalho").defaults.mode == "default"
    assert config.resolve("trabalho").defaults.poll_interval_s == 1.0


def test_v2_parses_evidence_ui_and_schedule():
    raw = _v2_dict()
    raw["evidence"] = {"enabled": True, "keep_per_target": 7, "max_total_mb": 10, "per_step": True}
    raw["ui"] = {"hotkeys": {"arm": "<ctrl>+a"}, "arm_durations_min": [1, 2]}
    raw["schedule"] = {
        "enabled": True,
        "days": ["sat", "sun"],
        "windows": ["09:00-10:30"],
    }
    config = config_from_dict(raw)
    assert config.evidence.enabled is True
    assert config.evidence.keep_per_target == 7
    assert config.evidence.per_step is True
    assert config.ui.hotkey("arm") == "<ctrl>+a"
    assert config.ui.hotkey("rearm", "fallback") == "fallback"
    assert config.ui.arm_durations_min == (1, 2)
    assert config.schedule.days == ("sat", "sun")
    assert config.schedule.windows == ("09:00-10:30",)


def test_v2_invalid_schedule_day_raises():
    raw = _v2_dict()
    raw["schedule"] = {"enabled": True, "days": ["funday"]}
    with pytest.raises(ConfigError):
        config_from_dict(raw)


def test_v2_invalid_schedule_window_raises():
    raw = _v2_dict()
    raw["schedule"] = {"enabled": True, "days": ["mon"], "windows": ["9:00-10:00"]}
    with pytest.raises(ConfigError):
        config_from_dict(raw)


def test_v2_negative_arm_duration_raises():
    raw = _v2_dict()
    raw["ui"] = {"arm_durations_min": [0, 5]}
    with pytest.raises(ConfigError):
        config_from_dict(raw)


def test_v2_bad_defaults_poll_interval_raises():
    raw = _v2_dict(defaults={"poll_interval_s": 0.2})
    with pytest.raises(ConfigError):
        config_from_dict(raw)


def test_v2_parses_humanize():
    raw = _v2_dict()
    raw["profiles"]["default"]["defaults"]["humanize"] = {
        "mouse_steps": 5,
        "jitter_px": 1,
        "seed": 7,
    }
    humanize = config_from_dict(raw).resolve().defaults.humanize
    assert humanize.mouse_steps == 5
    assert humanize.jitter_px == 1
    assert humanize.seed == 7


def test_v2_bad_humanize_mouse_steps_raises():
    raw = _v2_dict(defaults={"humanize": {"mouse_steps": 0}})
    with pytest.raises(ConfigError):
        config_from_dict(raw)


def test_unsupported_version_raises():
    with pytest.raises(ConfigError):
        config_from_dict({"version": 3, "profiles": {}})


# -- migracao --------------------------------------------------------------


def test_migrate_config_dict_builds_v2_from_first_target():
    raw = {
        "targets": [
            {
                "name": "a",
                "window_handle": 1,
                "roi_relative": [1, 2, 3, 4],
                "mode": "default",
                "poll_interval_s": 1.5,
                "rearm": False,
                "alerts": [{"type": "sound", "cooldown_s": 5}],
            },
            {"name": "b", "window_handle": 2, "roi_relative": [5, 6, 7, 8]},
        ]
    }
    new_dict, targets = migrate_config_dict(raw)
    assert [target.name for target in targets] == ["a", "b"]
    assert new_dict["version"] == 2
    defaults = new_dict["profiles"]["default"]["defaults"]
    assert defaults["mode"] == "default"
    assert defaults["poll_interval_s"] == 1.5
    assert defaults["rearm"] is False
    assert new_dict["profiles"]["default"]["alerts"][0]["type"] == "sound"

    config = config_from_dict(new_dict)
    assert config.profile == "default"
    assert config.resolve().defaults.mode == "default"


def test_migrate_config_dict_rejects_duplicate_names():
    raw = {
        "targets": [
            {"name": "x", "window_handle": 1, "roi_relative": [1, 2, 3, 4]},
            {"name": "x", "window_handle": 2, "roi_relative": [1, 2, 3, 4]},
        ]
    }
    with pytest.raises(ConfigError):
        migrate_config_dict(raw)


def test_migrate_config_dict_without_targets_raises():
    with pytest.raises(ConfigError):
        migrate_config_dict({"version": 2, "profiles": {}})


# -- gravacao --------------------------------------------------------------


def test_save_config_is_atomic_and_writes_backup(tmp_path):
    path = tmp_path / "config.yaml"
    save_config(path, {"targets": [], "generation": 1})
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["generation"] == 1

    save_config(path, {"targets": [], "generation": 2})
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["generation"] == 2
    backup = path.with_name(path.name + ".bak")
    assert yaml.safe_load(backup.read_text(encoding="utf-8"))["generation"] == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_remove_target_from_config(tmp_path):
    path = tmp_path / "config.yaml"
    config = {
        "targets": [
            {"name": "painel_estoque", "window_handle": 1, "roi_relative": [1, 2, 3, 4]},
            {"name": "outro", "window_handle": 2, "roi_relative": [1, 2, 3, 4]},
        ]
    }
    save_config(path, config)

    assert remove_target_from_config(path, "outro") is True
    assert [t.name for t in load_config(path).targets] == ["painel_estoque"]

    assert remove_target_from_config(path, "inexistente") is False
    assert path.with_name(path.name + ".bak").exists()


def test_remove_target_keeps_other_top_level_keys(tmp_path):
    path = tmp_path / "config.yaml"
    save_config(
        path,
        {"generation": 7, "targets": [{"name": "a", "window_handle": 1, "roi_relative": [1, 2, 3, 4]}]},
    )

    remove_target_from_config(path, "a")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["generation"] == 7
    assert raw["targets"] == []


def test_set_profile_sound_file_updates_existing_alert(tmp_path):
    path = tmp_path / "config.yaml"
    raw = _v2_dict()
    raw["profiles"]["default"]["alerts"] = [
        {"type": "log"},
        {"type": "sound", "file": "alert.mp3", "severity_min": 2},
    ]
    save_config(path, raw)

    set_profile_sound_file(path, "default", "C:/sons/meu.mp3")

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    sound = [
        alert for alert in loaded["profiles"]["default"]["alerts"] if alert["type"] == "sound"
    ]
    assert len(sound) == 1
    assert sound[0]["file"] == "C:/sons/meu.mp3"
    assert sound[0]["severity_min"] == 2
    assert path.with_name(path.name + ".bak").exists()


def test_set_profile_sound_file_creates_alert_when_missing(tmp_path):
    path = tmp_path / "config.yaml"
    save_config(path, _v2_dict())

    set_profile_sound_file(path, "default", "novo.mp3")

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    alerts = loaded["profiles"]["default"]["alerts"]
    sound = [alert for alert in alerts if alert["type"] == "sound"]
    assert len(sound) == 1
    assert sound[0] == {
        "type": "sound",
        "enabled": True,
        "severity_min": 1,
        "cooldown_s": 30,
        "file": "novo.mp3",
    }
    assert [alert["type"] for alert in alerts] == ["log", "sound"]


def test_set_profile_sound_file_rejects_v1(tmp_path):
    path = tmp_path / "config.yaml"
    save_config(path, {"targets": []})

    with pytest.raises(ConfigError) as excinfo:
        set_profile_sound_file(path, "default", "x.mp3")

    assert excinfo.value.code == "config.v1_not_editable"


def test_set_profile_sound_file_rejects_unknown_profile(tmp_path):
    path = tmp_path / "config.yaml"
    save_config(path, _v2_dict())

    with pytest.raises(ConfigError) as excinfo:
        set_profile_sound_file(path, "outro", "x.mp3")

    assert excinfo.value.code == "config.profile_unknown"


def test_set_profile_sound_file_rejects_non_list_alerts(tmp_path):
    path = tmp_path / "config.yaml"
    raw = _v2_dict()
    raw["profiles"]["default"]["alerts"] = "nope"
    save_config(path, raw)

    with pytest.raises(ConfigError) as excinfo:
        set_profile_sound_file(path, "default", "x.mp3")

    assert excinfo.value.code == "config.alerts_not_list"


def test_set_profile_sound_file_rollback_keeps_original(tmp_path, monkeypatch):
    import os

    path = tmp_path / "config.yaml"
    save_config(path, _v2_dict())
    original = path.read_text(encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        set_profile_sound_file(path, "default", "x.mp3")

    assert path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("*.tmp"))


def test_default_config_has_humanize_and_no_actions():
    config = config_from_dict(default_config_dict())
    profile = config.resolve()
    assert profile.defaults.humanize.mouse_steps == 24
    assert profile.actions == ()


def test_override_parser_error_branches():
    from screen_watch.config.loader import parse_alerts, parse_overrides, parse_rects

    for bad in (
        3,
        {"mode": "turbo"},
        {"poll_interval_s": 0.1},
        {"rearm": "x"},
        {"masks": "x"},
        {"alerts": 1},
        {"actions": 1},
    ):
        with pytest.raises(ConfigError):
            parse_overrides(bad)
    with pytest.raises(ConfigError):
        parse_rects(3)
    with pytest.raises(ConfigError):
        parse_alerts(3)


def test_v2_top_level_section_error_branches():
    with pytest.raises(ConfigError):
        config_from_dict({"version": 2, "profile": "default"})
    with pytest.raises(ConfigError):
        config_from_dict({"version": 2, "profile": "default", "profiles": []})
    with pytest.raises(ConfigError):
        config_from_dict({"version": 2, "profile": "x", "profiles": {"default": {}}})
    with pytest.raises(ConfigError):
        config_from_dict({"version": 2, "profiles": {"default": 3}})
    with pytest.raises(ConfigError):
        config_from_dict({"version": "x"})
    with pytest.raises(ConfigError):
        config_from_dict({"targets": 3})


def test_v2_nested_section_error_branches():
    def raw(**top):
        data = {"version": 2, "profile": "default", "profiles": {"default": {}}}
        data.update(top)
        return data

    with pytest.raises(ConfigError):
        config_from_dict(raw(evidence=3))
    with pytest.raises(ConfigError):
        config_from_dict(raw(ui=3))
    with pytest.raises(ConfigError):
        config_from_dict(raw(ui={"hotkeys": 3}))
    with pytest.raises(ConfigError):
        config_from_dict(raw(ui={"arm_durations_min": [0]}))
    with pytest.raises(ConfigError):
        config_from_dict(raw(schedule=3))
    with pytest.raises(ConfigError):
        config_from_dict(raw(schedule={"windows": ["25:00-10:00"]}))
    with pytest.raises(ConfigError):
        config_from_dict(raw(schedule={"windows": ["10:00"]}))
    with pytest.raises(ConfigError):
        config_from_dict(_v2_dict(defaults={"humanize": 3}))


# -- canais novos (webhook/http_post/syslog) -------------------------------


def _parse_one(alert: dict):
    from screen_watch.config.loader import parse_alerts

    return parse_alerts([alert], "alerts")[0]


def test_webhook_parses_and_round_trips():
    from screen_watch.config.loader import _alert_to_dict

    alert = _parse_one(
        {
            "type": "webhook",
            "id": "teams",
            "severity_min": 2,
            "options": {
                "url_env": "TEAMS_WEBHOOK",
                "method": "PUT",
                "headers": {"Content-Type": "application/json"},
                "payload": {"text": "Mudanca em ${target} sev=${severity}"},
                "timeout_s": 7,
                "verify_tls": False,
            },
        }
    )
    assert alert.id == "teams"
    assert alert.options.url_env == "TEAMS_WEBHOOK"
    assert alert.options.method == "PUT"
    assert alert.options.verify_tls is False
    assert alert.options.timeout_s == 7.0
    assert alert.options.headers == (("Content-Type", "application/json"),)

    again = _parse_one(_alert_to_dict(alert))
    assert again == alert


def test_http_post_parses_host_and_port():
    from screen_watch.config.loader import _alert_to_dict

    alert = _parse_one(
        {
            "type": "http_post",
            "options": {"host": "10.0.0.20", "port": 8080, "path": "/alerta"},
        }
    )
    assert alert.options.host == "10.0.0.20"
    assert alert.options.port == 8080
    assert alert.options.path == "/alerta"
    assert alert.options.scheme == "http"

    again = _parse_one(_alert_to_dict(alert))
    assert again == alert


def test_syslog_parses_defaults_and_round_trips():
    from screen_watch.config.loader import _alert_to_dict

    alert = _parse_one(
        {
            "type": "syslog",
            "options": {
                "host": "10.0.0.9",
                "severity_map": {3: "error"},
                "payload_raw": "${timestamp} ${target}",
            },
        }
    )
    assert alert.options.port == 514
    assert alert.options.protocol == "udp"
    assert alert.options.facility == "local0"
    assert alert.options.app_name == "screen-diff-watcher"
    assert alert.options.severity_map == ((3, "error"),)

    again = _parse_one(_alert_to_dict(alert))
    assert again == alert


def test_ntfy_parses_and_round_trips():
    from screen_watch.config.loader import _alert_to_dict

    alert = _parse_one(
        {
            "type": "ntfy",
            "id": "celular",
            "options": {
                "server": "https://ntfy.example",
                "topic": "meu-topico",
                "priority_map": {1: 1, 3: 5},
                "tags": ["eye"],
                "attach_roi": True,
            },
        }
    )
    assert alert.options.server == "https://ntfy.example"
    assert alert.options.priority_map == ((1, 1), (3, 5))
    assert alert.options.tags == ("eye",)
    assert alert.options.attach_roi is True

    again = _parse_one(_alert_to_dict(alert))
    assert again == alert


def test_smtp_parses_and_round_trips():
    from screen_watch.config.loader import _alert_to_dict

    alert = _parse_one(
        {
            "type": "smtp",
            "options": {
                "host": "smtp.example.com",
                "from_addr": "watch@example.com",
                "to": ["oncall@example.com", "boss@example.com"],
                "security": "ssl",
            },
        }
    )
    assert alert.options.to == ("oncall@example.com", "boss@example.com")
    assert alert.options.security == "ssl"
    assert alert.options.attach_roi is True

    again = _parse_one(_alert_to_dict(alert))
    assert again == alert


def test_mqtt_parses_defaults_and_round_trips():
    from screen_watch.config.loader import _alert_to_dict

    alert = _parse_one({"type": "mqtt", "options": {"host": "10.0.0.30", "topic": "t"}})
    assert alert.options.port == 1883
    assert alert.options.qos == 0
    assert alert.options.tls is False

    again = _parse_one(_alert_to_dict(alert))
    assert again == alert


def test_mqtt_tls_defaults_port_8883():
    alert = _parse_one(
        {"type": "mqtt", "options": {"host": "10.0.0.30", "topic": "t", "tls": True}}
    )
    assert alert.options.port == 8883


def test_alert_id_defaults_and_suffix_on_repeat():
    from screen_watch.config.loader import parse_alerts

    alerts = parse_alerts(
        [
            {"type": "log"},
            {"type": "webhook", "options": {"url": "https://a"}},
            {"type": "webhook", "options": {"url": "https://b"}},
        ],
        "alerts",
    )
    assert [a.id for a in alerts] == ["log", "webhook", "webhook#2"]


def test_alert_id_suffix_reserves_explicit_ids_regardless_of_order():
    from screen_watch.config.loader import parse_alerts

    alerts = parse_alerts(
        [
            {"type": "log"},
            {"type": "log"},
            {"type": "log", "id": "log#2"},
        ],
        "alerts",
    )
    assert [a.id for a in alerts] == ["log", "log#3", "log#2"]


def test_duplicate_explicit_id_raises():
    from screen_watch.config.loader import parse_alerts

    with pytest.raises(ConfigError) as excinfo:
        parse_alerts([{"type": "log", "id": "x"}, {"type": "popup", "id": "x"}], "alerts")
    assert excinfo.value.code == "config.alert_duplicate_id"


def test_alert_error_branches_by_code():
    from screen_watch.config.loader import parse_alerts

    cases = [
        ({"type": "carrier-pigeon"}, "config.alert_unknown_type"),
        ({"type": "webhook"}, "config.alert_options_not_mapping"),
        ({"type": "webhook", "options": {}}, "config.alert_missing_url"),
        ({"type": "webhook", "options": {"url": "ftp://x"}}, "config.alert_invalid_url"),
        (
            {"type": "webhook", "options": {"url": "http://host:80x/hook"}},
            "config.alert_invalid_url",
        ),
        (
            {"type": "webhook", "options": {"url": "https://x", "method": "DELETE"}},
            "config.alert_invalid_method",
        ),
        (
            {
                "type": "webhook",
                "options": {"url": "https://x", "payload": {}, "payload_raw": "y"},
            },
            "config.alert_payload_conflict",
        ),
        (
            {"type": "webhook", "options": {"url": "https://x", "payload": {"a": "${nope}"}}},
            "config.alert_unknown_placeholder",
        ),
        (
            {"type": "http_post", "options": {"host": "h", "port": 0}},
            "config.alert_invalid_port",
        ),
        (
            {"type": "syslog", "options": {"host": "h", "protocol": "sctp"}},
            "config.alert_invalid_protocol",
        ),
        ({"type": "syslog", "options": {}}, "config.alert_missing_host"),
        (
            {"type": "syslog", "options": {"host": "h", "facility": "nope"}},
            "config.alert_invalid_facility",
        ),
        (
            {"type": "syslog", "options": {"host": "h", "severity_map": {9: "error"}}},
            "config.alert_invalid_severity_map",
        ),
        ({"type": "ntfy"}, "config.alert_options_not_mapping"),
        ({"type": "ntfy", "options": {}}, "config.alert_missing_topic"),
        (
            {"type": "ntfy", "options": {"topic": "t", "priority_map": {1: 9}}},
            "config.alert_invalid_priority_map",
        ),
        ({"type": "smtp", "options": {}}, "config.alert_missing_host"),
        ({"type": "smtp", "options": {"host": "h"}}, "config.alert_missing_from"),
        (
            {"type": "smtp", "options": {"host": "h", "from_addr": "a@x"}},
            "config.alert_missing_to",
        ),
        (
            {
                "type": "smtp",
                "options": {
                    "host": "h",
                    "from_addr": "a@x",
                    "to": ["b@x"],
                    "security": "tls",
                },
            },
            "config.alert_invalid_security",
        ),
        ({"type": "mqtt", "options": {}}, "config.alert_missing_host"),
        ({"type": "mqtt", "options": {"host": "h"}}, "config.alert_missing_topic"),
        (
            {"type": "mqtt", "options": {"host": "h", "topic": "t", "qos": 5}},
            "config.alert_invalid_qos",
        ),
        (
            {
                "type": "mqtt",
                "options": {"host": "h", "topic": "t", "payload": {}, "payload_raw": "x"},
            },
            "config.alert_payload_conflict",
        ),
        (
            {"type": "mqtt", "options": {"host": "h", "topic": "t", "payload": {"a": "${nope}"}}},
            "config.alert_unknown_placeholder",
        ),
    ]
    for alert, code in cases:
        with pytest.raises(ConfigError) as excinfo:
            parse_alerts([alert], "alerts")
        assert excinfo.value.code == code, (alert, excinfo.value.code)


# -- escalation e snooze (v0.9.0) ------------------------------------------


def test_escalation_parsed_in_defaults():
    from screen_watch.config.schema import EscalationOptions

    config = config_from_dict(
        _v2_dict(defaults={"mode": "advanced", "escalation": {"enabled": True, "severity_min": 3}})
    )
    assert config.profiles["default"].defaults.escalation == EscalationOptions(
        enabled=True, severity_min=3
    )


def test_escalation_defaults_are_disabled():
    config = config_from_dict(_v2_dict())
    escalation = config.profiles["default"].defaults.escalation
    assert escalation.enabled is False
    assert escalation.severity_min == 2


def test_escalation_parsed_in_overrides():
    from screen_watch.config.loader import parse_overrides
    from screen_watch.config.schema import EscalationOptions

    out = parse_overrides({"escalation": {"enabled": True}})
    assert out["escalation"] == EscalationOptions(enabled=True, severity_min=2)


def test_escalation_invalid_raises():
    with pytest.raises(ConfigError) as excinfo:
        config_from_dict(_v2_dict(defaults={"escalation": 3}))
    assert excinfo.value.code == "config.escalation_not_mapping"

    with pytest.raises(ConfigError) as excinfo:
        config_from_dict(_v2_dict(defaults={"escalation": {"severity_min": -1}}))
    assert excinfo.value.code == "config.escalation_severity_min"


def test_ui_snooze_minutes_parsed_and_validated():
    raw = _v2_dict()
    raw["ui"] = {"snooze_minutes": [10, 20]}
    assert config_from_dict(raw).ui.snooze_minutes == (10, 20)

    raw["ui"] = {"snooze_minutes": "10"}
    with pytest.raises(ConfigError) as excinfo:
        config_from_dict(raw)
    assert excinfo.value.code == "config.snooze_minutes_not_list"

    raw["ui"] = {"snooze_minutes": [0]}
    with pytest.raises(ConfigError) as excinfo:
        config_from_dict(raw)
    assert excinfo.value.code == "config.snooze_minutes_positive"


def test_default_config_round_trips_with_escalation_and_snooze():
    config = config_from_dict(default_config_dict())
    defaults = config.profiles["default"].defaults
    assert defaults.escalation.enabled is False
    assert config.ui.snooze_minutes == (5, 15, 30, 60)
    assert config.ui.max_sessions == 4


def test_ui_max_sessions_parsed_and_validated():
    raw = _v2_dict()
    raw["ui"] = {"max_sessions": 2}
    assert config_from_dict(raw).ui.max_sessions == 2

    raw["ui"] = {"max_sessions": 0}
    with pytest.raises(ConfigError) as excinfo:
        config_from_dict(raw)
    assert excinfo.value.code == "config.max_sessions_range"

    raw["ui"] = {"max_sessions": 99}
    with pytest.raises(ConfigError) as excinfo:
        config_from_dict(raw)
    assert excinfo.value.code == "config.max_sessions_range"


# -- text_watch (compare_options.advanced) ---------------------------------


def _text_watch_config(watch) -> dict:
    raw = _v2_dict()
    raw["profiles"]["default"]["defaults"] = {
        "mode": "advanced",
        "compare_options": {"advanced": {"text_watch": watch}},
    }
    return raw


def test_v2_parses_text_watch():
    config = config_from_dict(_text_watch_config({"text": "CONCLUÍDO", "expect": "appears"}))
    watch = config.resolve().defaults.compare_options.advanced.text_watch
    assert watch.text == "CONCLUÍDO"
    assert watch.expect == "appears"
    assert watch.case_sensitive is False
    assert watch.ignore_accents is True


def test_v2_text_watch_is_optional():
    config = config_from_dict(_v2_dict())
    assert config.resolve().defaults.compare_options.advanced.text_watch is None


def test_text_watch_error_branches_by_code():
    cases = [
        (3, "config.text_watch_not_mapping"),
        ({}, "config.text_watch_text_required"),
        ({"text": "   "}, "config.text_watch_text_required"),
        ({"text": "x", "expect": "blink"}, "config.text_watch_invalid_expect"),
        ({"text": "x", "case_sensitive": "yes"}, "config.text_watch_not_bool"),
        ({"text": "x", "ignore_accents": "no"}, "config.text_watch_not_bool"),
    ]
    for watch, code in cases:
        with pytest.raises(ConfigError) as excinfo:
            config_from_dict(_text_watch_config(watch))
        assert excinfo.value.code == code, (watch, excinfo.value.code)


def test_parse_overrides_accepts_text_watch():
    from screen_watch.config.loader import parse_overrides

    parsed = parse_overrides({"text_watch": {"text": "ok", "expect": "disappears"}})
    assert parsed["text_watch"].text == "ok"
    assert parsed["text_watch"].expect == "disappears"

    with pytest.raises(ConfigError):
        parse_overrides({"text_watch": {"text": ""}})


def test_compare_options_dict_includes_text_watch_only_when_set():
    from screen_watch.config.loader import _compare_options_to_dict
    from screen_watch.config.schema import AdvancedOptions, CompareOptions, TextWatchOptions

    without = _compare_options_to_dict(CompareOptions())
    assert "text_watch" not in without["advanced"]

    with_watch = _compare_options_to_dict(
        CompareOptions(advanced=AdvancedOptions(text_watch=TextWatchOptions(text="ok")))
    )
    assert with_watch["advanced"]["text_watch"] == {
        "text": "ok",
        "expect": "appears",
        "case_sensitive": False,
        "ignore_accents": True,
    }

    raw = _v2_dict()
    raw["profiles"]["default"]["defaults"] = {
        "mode": "advanced",
        "compare_options": with_watch,
    }
    assert config_from_dict(raw).resolve().defaults.compare_options.advanced.text_watch.text == "ok"
