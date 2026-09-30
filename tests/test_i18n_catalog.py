from __future__ import annotations

from screen_watch import i18n


def test_catalogs_have_the_same_keys():
    fallback = i18n.catalog_keys(i18n.FALLBACK_LANGUAGE)
    for locale in i18n.available_locales():
        keys = i18n.catalog_keys(locale)
        assert keys == fallback, f"{locale} difere do fallback"


def test_catalogs_have_no_empty_values():
    for locale in i18n.available_locales():
        catalog = i18n._load_catalog(locale)  # noqa: SLF001 - inspecao de teste
        for key, value in catalog.items():
            assert value.strip(), f"{locale}:{key} vazio"


def test_meta_is_valid_for_each_catalog():
    for locale in i18n.available_locales():
        meta = i18n.locale_meta(locale)
        assert meta, f"{locale}: _meta ausente"
        assert meta["code"] == locale
        assert meta["name"]
        assert isinstance(meta["version"], int)
        assert meta["fallback"] == i18n.FALLBACK_LANGUAGE
