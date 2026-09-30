from __future__ import annotations

from screen_watch import i18n


def test_available_locales_includes_both_catalogs():
    locales = i18n.available_locales()
    assert "pt-BR" in locales
    assert "en-US" in locales


def test_normalize_locale_variants():
    assert i18n.normalize_locale("pt_BR") == "pt-BR"
    assert i18n.normalize_locale("Portuguese_Brazil") == "pt-BR"
    assert i18n.normalize_locale("en_US.UTF-8") == "en-US"
    assert i18n.normalize_locale("English_United States") == "en-US"
    assert i18n.normalize_locale("C") == ""
    assert i18n.normalize_locale(None) == ""


def test_resolve_locale_exact_language_and_fallback():
    available = ("pt-BR", "en-US")
    assert i18n.resolve_locale("en-US", available, None) == "en-US"
    assert i18n.resolve_locale("EN_us", available, None) == "en-US"
    assert i18n.resolve_locale("pt_PT", available, None) == "pt-BR"
    assert i18n.resolve_locale("de-DE", available, None) == "pt-BR"
    assert i18n.resolve_locale(None, available, None) == "pt-BR"
    assert i18n.resolve_locale("de-DE", available, "auto") == "pt-BR"
    assert i18n.resolve_locale("de-DE", available, "en-US") == "en-US"


def test_resolve_locale_without_available_returns_fallback():
    assert i18n.resolve_locale("en-US", (), None) == i18n.FALLBACK_LANGUAGE


def test_set_language_unknown_falls_back():
    assert i18n.set_language("xx-XX") == i18n.FALLBACK_LANGUAGE
    assert i18n.current_language() == i18n.FALLBACK_LANGUAGE


def test_tr_formats_and_falls_back_in_catalog(monkeypatch):
    i18n.set_language("pt-BR")
    assert i18n.tr("main.btn_start") == "Iniciar"
    assert i18n.tr("main.actions_count", checked=1, total=2) == "1 de 2 selecionados"
    assert "armado" in i18n.tr("arming.timed", remaining=5)


def test_tr_missing_key_returns_key(monkeypatch):
    i18n.set_language("pt-BR")
    assert i18n.tr("does.not.exist") == "does.not.exist"


def test_tr_uses_fallback_for_language_specific_gap(monkeypatch):
    i18n.set_language("en-US")
    # Chave so presente no pt-BR: cai no fallback por padrao (mesmo conjunto hoje).
    monkeypatch.setattr(
        i18n, "_load_catalog", lambda language: {"only.pt": "valor"} if language == "pt-BR" else {}
    )
    assert i18n.tr("only.pt") == "valor"
