from __future__ import annotations

from screen_watch.naming import MAX_SLUG_LENGTH, slugify


def test_slugify_normalizes_case_and_symbols():
    assert slugify("WhatsApp.Root") == "whatsapp-root"
    assert slugify("Visual Studio Code - Insiders") == "visual-studio-code-insiders"


def test_slugify_strips_accents():
    assert slugify("Seleção Verificando") == "selecao-verificando"
    assert slugify("AÇÃO Concluída") == "acao-concluida"


def test_slugify_empty_when_no_letters_or_digits():
    assert slugify("!!!") == ""
    assert slugify("   ...   ") == ""


def test_slugify_truncates_at_max_length():
    assert len(slugify("a" * 200)) == MAX_SLUG_LENGTH
    assert slugify("a" * 200, max_len=None) == "a" * 200


def test_slugify_truncation_does_not_leave_trailing_dash():
    assert slugify("abc-" + "de" * 40, max_len=4) == "abc"
