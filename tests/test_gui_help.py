from __future__ import annotations

from screen_watch import i18n
from screen_watch.gui.help import HELP_KEYS, build_help_html


def test_every_help_key_has_title_purpose_example_in_all_catalogs():
    for key in HELP_KEYS:
        for suffix in ("titulo", "proposito", "exemplo"):
            for locale in i18n.available_locales():
                assert f"help.{key}.{suffix}" in i18n.catalog_keys(locale)


def test_build_help_html_has_all_three_parts():
    i18n.set_language("pt-BR")
    html = build_help_html("editor.severity_min")
    assert html.startswith("<b>")
    assert "<br>" in html
    assert "<i>" in html


def test_build_help_html_with_explicit_catalog():
    catalog = {"help.x.titulo": "T", "help.x.proposito": "P", "help.x.exemplo": "E"}
    assert build_help_html("x", catalog=catalog) == "<b>T</b><br>P<br><i>E</i>"


def test_build_help_html_unknown_key_is_empty_with_catalog():
    assert build_help_html("nope.nope", catalog={}) == ""


def test_all_help_keys_resolve_in_active_language():
    i18n.set_language("en-US")
    for key in HELP_KEYS:
        assert build_help_html(key), f"{key} sem ajuda"
