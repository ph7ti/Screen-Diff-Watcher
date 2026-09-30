from __future__ import annotations

from screen_watch import i18n
from screen_watch.errors import ERROR_CODES, AppError, ConfigError, render_error


def test_every_error_code_is_translated_in_both_catalogs():
    for code in ERROR_CODES:
        key = f"error.{code}"
        for locale in i18n.available_locales():
            assert key in i18n.catalog_keys(locale), f"{locale}: falta {key}"


def test_str_is_english():
    exc = ConfigError(code="config.not_integer", params={"field": "version", "value": "x"})
    assert str(exc) == "version must be an integer (got 'x')"


def test_config_error_is_a_value_error():
    exc = ConfigError(code="config.not_bool", params={"field": "rearm", "value": 2})
    assert isinstance(exc, ValueError)
    assert isinstance(exc, AppError)


def test_render_error_translates_with_language():
    exc = ConfigError(code="config.not_integer", params={"field": "version", "value": "x"})
    assert "deve ser um inteiro" in render_error(exc, "pt-BR")
    assert "must be an integer" in render_error(exc, "en-US")


def test_render_error_falls_back_to_str_without_code():
    exc = RuntimeError("boom")
    assert render_error(exc) == "boom"


def test_render_error_uses_active_language():
    exc = ConfigError(code="runtime.window_minimized")
    i18n.set_language("pt-BR")
    assert render_error(exc) == "janela minimizada: não há ROI para capturar"
