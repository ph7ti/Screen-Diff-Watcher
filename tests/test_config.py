from __future__ import annotations

import pytest
import yaml

from screen_watch.config.loader import (
    ConfigError,
    config_from_dict,
    default_config_dict,
    load_config,
    remove_target_from_config,
    save_config,
)


def _minimal(**extra):
    raw = {"targets": [{"name": "x", "window_handle": 42, "roi_relative": [1, 2, 3, 4], **extra}]}
    return config_from_dict(raw)


def test_minimal_target_parses():
    target = _minimal().get_target("x")
    assert target is not None
    assert target.window_handle == 42
    assert target.roi_relative == (1, 2, 3, 4)
    assert target.mode == "advanced"
    assert target.poll_interval_s == 2.0
    assert target.rearm is True


def test_missing_required_field_raises():
    with pytest.raises(ConfigError):
        config_from_dict({"targets": [{"name": "x", "roi_relative": [1, 2, 3, 4]}]})


def test_bad_rect_raises():
    with pytest.raises(ConfigError):
        config_from_dict({"targets": [{"name": "x", "window_handle": 1, "roi_relative": [1, 2]}]})


def test_default_config_round_trips_through_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    save_config(path, default_config_dict())
    config = load_config(path)
    target = config.get_target("painel_estoque")
    assert target is not None
    assert target.mode == "advanced"
    assert target.rearm is True
    assert len(target.alerts) == 3
    assert target.alerts[2].bot_token_env == "TELEGRAM_BOT_TOKEN"
    assert "123456789" == target.alerts[2].chat_id


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
    options = _minimal().get_target("x").compare_options.advanced
    assert options.lang == "por+eng"
    assert options.upscale == 2
    assert options.psm == 6
    assert options.tesseract_cmd is None


def test_advanced_tesseract_cmd_parsed():
    target = _minimal(
        compare_options={"advanced": {"tesseract_cmd": r"C:\Tesseract\tesseract.exe"}}
    ).get_target("x")
    assert target.compare_options.advanced.tesseract_cmd == r"C:\Tesseract\tesseract.exe"


def test_invalid_mode_raises():
    with pytest.raises(ConfigError):
        _minimal(mode="turbo")


def test_poll_interval_below_minimum_raises():
    with pytest.raises(ConfigError):
        _minimal(poll_interval_s=0.5)


def test_poll_interval_at_minimum_is_accepted():
    assert _minimal(poll_interval_s=1.0).get_target("x").poll_interval_s == 1.0


def test_rearm_false_is_parsed():
    assert _minimal(rearm=False).get_target("x").rearm is False


def test_save_config_is_atomic_and_writes_backup(tmp_path):
    path = tmp_path / "config.yaml"
    save_config(path, {"targets": [], "generation": 1})
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["generation"] == 1

    save_config(path, {"targets": [], "generation": 2})
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["generation"] == 2
    backup = path.with_name(path.name + ".bak")
    assert yaml.safe_load(backup.read_text(encoding="utf-8"))["generation"] == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_log_alert_path_parsed():
    target = _minimal(alerts=[{"type": "log", "path": "custom.jsonl"}]).get_target("x")
    assert target.alerts[0].path == "custom.jsonl"


def test_non_integer_window_handle_raises_config_error():
    with pytest.raises(ConfigError):
        config_from_dict(
            {"targets": [{"name": "x", "window_handle": "abc", "roi_relative": [1, 2, 3, 4]}]}
        )


def test_non_numeric_poll_interval_raises_config_error():
    with pytest.raises(ConfigError):
        _minimal(poll_interval_s="fast")


def test_non_boolean_rearm_raises_config_error():
    with pytest.raises(ConfigError):
        _minimal(rearm="maybe")


def test_targets_must_be_a_list():
    with pytest.raises(ConfigError):
        config_from_dict({"targets": "x"})


def test_alert_must_be_a_mapping():
    with pytest.raises(ConfigError):
        _minimal(alerts=[1])


def test_roi_values_must_be_integers():
    with pytest.raises(ConfigError):
        config_from_dict(
            {"targets": [{"name": "x", "window_handle": 1, "roi_relative": [1, 2, 3, "z"]}]}
        )


def test_remove_target_from_config(tmp_path):
    path = tmp_path / "config.yaml"
    config = default_config_dict()
    config["targets"].append({"name": "outro", "window_handle": 2, "roi_relative": [1, 2, 3, 4]})
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
