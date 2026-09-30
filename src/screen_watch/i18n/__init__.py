"""Internacionalizacao leve por catalogo JSON (plano GUI/UX, F1).

Modulo puro: nao importa Qt no topo. `detect_system_locale()` tenta o `QLocale`
de forma preguicosa (QtCore funciona sem `QApplication`) e cai para `locale` e
para as variaveis de ambiente quando indisponivel.

A leitura do idioma ativo acontece a cada `tr()` (nao e cacheada no import), de
modo que `set_language()` vale em runtime e nos testes. `reload()` limpa os
caches (usado por testes que trocam catalogos em disco).

Descoberta: `available_locales()` varre `screen_watch/i18n/*.json` do pacote e
usa `_meta.code`. Nenhum idioma vem de app-data (decisao do plano).
"""

from __future__ import annotations

import json
import locale as _locale
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

FALLBACK_LANGUAGE = "pt-BR"
AUTO = "auto"

_META_KEY = "_meta"
_CATALOG_DIR = Path(__file__).resolve().parent

_language: str = FALLBACK_LANGUAGE
_catalog_cache: dict[str, dict[str, str]] = {}
_missing_logged: set[str] = set()

# Nomes de idioma/regiao como o Windows os apresenta (`Portuguese_Brazil`).
_WINDOWS_LANGUAGES = {
    "portuguese": "pt",
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "japanese": "ja",
    "chinese": "zh",
    "korean": "ko",
    "russian": "ru",
}
_WINDOWS_REGIONS = {
    "brazil": "BR",
    "portugal": "PT",
    "united states": "US",
    "united kingdom": "GB",
    "spain": "ES",
    "france": "FR",
    "germany": "DE",
    "italy": "IT",
    "japan": "JP",
    "china": "CN",
    "korea": "KR",
    "russia": "RU",
}


def _read_meta(path: Path) -> dict | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("i18n catalog unreadable %s: %s", path, exc)
        return None
    if not isinstance(raw, dict):
        return None
    meta = raw.get(_META_KEY)
    return meta if isinstance(meta, dict) else None


def available_locales() -> tuple[str, ...]:
    """Tags descobertas em `screen_watch/i18n/*.json` (+ o fallback garantido)."""
    found: list[str] = []
    for path in sorted(_CATALOG_DIR.glob("*.json")):
        meta = _read_meta(path)
        code = meta.get("code") if meta else None
        if isinstance(code, str) and code:
            found.append(code)
    if FALLBACK_LANGUAGE not in found:
        found.append(FALLBACK_LANGUAGE)
    return tuple(found)


def locale_meta(language: str) -> dict:
    """`_meta` de um catalogo (ou `{}` se ausente/ invalido)."""
    path = _CATALOG_DIR / f"{language}.json"
    meta = _read_meta(path) if path.is_file() else None
    return dict(meta) if meta else {}


def _load_catalog(language: str) -> dict[str, str]:
    cached = _catalog_cache.get(language)
    if cached is not None:
        return cached
    data: dict[str, str] = {}
    path = _CATALOG_DIR / f"{language}.json"
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("i18n catalog unreadable %s: %s", path, exc)
            raw = {}
        if isinstance(raw, dict):
            data = {key: str(value) for key, value in raw.items() if not key.startswith("_")}
    _catalog_cache[language] = data
    return data


def catalog_keys(language: str) -> frozenset[str]:
    """Todas as chaves (sem `_meta`) de um catalogo; util para validacao/testes."""
    return frozenset(_load_catalog(language))


def set_language(tag: str | None) -> str:
    """Fixa o idioma ativo (com fallback se desconhecido) e devolve a tag usada."""
    global _language
    resolved = resolve_locale(None, available_locales(), tag)
    _language = resolved
    return resolved


def current_language() -> str:
    return _language


def tr(key: str, **fmt: object) -> str:
    """Traduz `key` no idioma ativo, caindo para o fallback, senao a propria chave."""
    template = _load_catalog(_language).get(key)
    if template is None:
        template = _load_catalog(FALLBACK_LANGUAGE).get(key)
    if template is None:
        if key not in _missing_logged:
            _missing_logged.add(key)
            log.warning("missing i18n key: %s", key)
        return key
    if not fmt:
        return template
    try:
        return template.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return template


def reload() -> None:
    """Limpa os caches de catalogos e o controle de chaves ausentes."""
    _catalog_cache.clear()
    _missing_logged.clear()


def normalize_locale(value: str | None) -> str:
    """Normaliza nomes variados (`pt_BR`, `Portuguese_Brazil`, `en_US.UTF-8`) -> `xx-YY`."""
    if not value:
        return ""
    text = value.strip().split(".", 1)[0].strip()
    if not text or text.upper() in {"C", "POSIX"}:
        return ""
    text = text.replace(" ", "_")
    if "_" in text:
        language_raw, _, rest = text.partition("_")
    elif "-" in text:
        language_raw, _, rest = text.partition("-")
    else:
        language_raw, rest = text, ""
    language = _WINDOWS_LANGUAGES.get(language_raw.lower(), language_raw.lower())
    region_raw = rest.strip().replace("_", " ").replace("-", " ").strip()
    if not region_raw:
        return language
    region = _WINDOWS_REGIONS.get(region_raw.lower())
    if region is None:
        region = region_raw.upper().replace(" ", "-")
    return f"{language}-{region}"


def resolve_locale(
    system_locale: str | None, available: tuple[str, ...] | list[str], override: str | None
) -> str:
    """Maior aderencia: exato (case-insensitive) -> mesmo idioma (`pt` -> `pt-BR`) -> fallback."""
    tags = [tag for tag in available if tag]
    if not tags:
        return FALLBACK_LANGUAGE
    preference = override if override and override != AUTO else system_locale
    normalized = normalize_locale(preference)
    if normalized:
        for tag in tags:
            if tag.lower() == normalized.lower():
                return tag
        language = normalized.split("-", 1)[0]
        for tag in tags:
            if tag.split("-", 1)[0].lower() == language:
                return tag
    if FALLBACK_LANGUAGE in tags:
        return FALLBACK_LANGUAGE
    return tags[0]


def detect_system_locale() -> str:
    """Locale do SO: `QLocale.system()` (QtCore, sem `QApplication`) -> `locale` -> env."""
    try:
        from PyQt6.QtCore import QLocale  # noqa: PLC0415

        name = QLocale.system().name()
        if name:
            return name
    except Exception:  # pragma: no cover - depende do ambiente
        pass
    try:
        name = _locale.getlocale()[0]
        if name:
            return name
    except (TypeError, ValueError):  # pragma: no cover - depende do ambiente
        pass
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(variable)
        if value:
            return value
    return ""


def resolve_language(*, cli: str | None = None, state: str | None = None, config: str | None = None) -> str:
    """Resolve o idioma ativo pela precedencia `--language` > state > config > auto."""
    for candidate in (cli, state, config):
        if candidate and candidate != AUTO:
            return set_language(candidate)
    return set_language(resolve_locale(detect_system_locale(), available_locales(), AUTO))
