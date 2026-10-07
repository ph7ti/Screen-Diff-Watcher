"""Checagem passiva de nova versao (doc, secao 3.8/12.1; v0.11.0).

Nunca no caminho de captura: a GUI chama `check_for_update` numa thread daemon.
A funcao nunca levanta, nunca baixa nada e faz no maximo uma tentativa de GET por
TTL no endpoint publico `/releases/latest` do GitHub (sem token e sem
identificadores). O cache vive em `state.json` (`update_check`), com TTL de 24 h
(inclusive para tentativas que falharam); o `notified_version` evita repetir o
aviso. `parse_version`/`is_newer` sao puros.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/ph7ti/Screen-Diff-Watcher/releases/latest"
RELEASES_PAGE = "https://github.com/ph7ti/Screen-Diff-Watcher/releases"
STATE_KEY = "update_check"
DEFAULT_TTL_S = 86400.0
DEFAULT_TIMEOUT_S = 5.0
_ACCEPT = "application/vnd.github+json"
_USER_AGENT = "screen-diff-watcher"
# So abrimos no navegador URLs https do GitHub (o `url` vem da API e do cache).
_TRUSTED_HOSTS = frozenset({"github.com", "www.github.com"})


@dataclass(frozen=True)
class UpdateStatus:
    """Resultado de uma checagem com versao mais nova (tag/url/momento)."""

    tag: str
    url: str
    checked_at: float


def parse_version(text: str) -> tuple[int, ...]:
    """Componentes numericos da versao; tolera `v` e sufixos (`1.2.3-rc1`, `1.2.3+build`)."""
    if not text:
        return ()
    cleaned = str(text).strip().lstrip("vV")
    release = cleaned.split("+", 1)[0].split("-", 1)[0]
    parts: list[int] = []
    for chunk in release.split("."):
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    """True quando `latest` e um release mais novo que `current` (sufixos ignorados)."""
    newer = parse_version(latest)
    older = parse_version(current)
    if not newer or not older:
        return False
    size = max(len(newer), len(older))
    newer += (0,) * (size - len(newer))
    older += (0,) * (size - len(older))
    return newer > older


def _fetch_latest(url: str = RELEASES_API) -> dict[str, Any]:
    """GET anonimo no endpoint publico; excecao em timeout/HTTP/payload invalido."""
    import httpx  # noqa: PLC0415

    response = httpx.request(
        "GET",
        url,
        headers={"Accept": _ACCEPT, "User-Agent": _USER_AGENT},
        timeout=DEFAULT_TIMEOUT_S,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("unexpected releases payload")
    return payload


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_url(value: Any) -> str:
    """So aceita https do GitHub; qualquer outro esquema/host vira string vazia."""
    url = _as_str(value)
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    if parsed.scheme != "https" or (parsed.hostname or "") not in _TRUSTED_HOSTS:
        return ""
    return url


def _cached(state: dict[str, Any] | None) -> dict[str, Any]:
    if state is not None:
        cached = state.get(STATE_KEY)
    else:
        try:
            from screen_watch.platform.paths import load_state  # noqa: PLC0415

            cached = load_state().get(STATE_KEY)
        except Exception as exc:  # pragma: no cover - cache e best-effort
            log.debug("could not read the update cache: %s", exc)
            cached = None
    return dict(cached) if isinstance(cached, dict) else {}


def _persist(entry: dict[str, Any], state: dict[str, Any] | None) -> None:
    """Grava o cache; com `state` injetado atualiza o dict, senao `update_state`."""
    if state is not None:
        state[STATE_KEY] = entry
        return
    try:
        from screen_watch.platform.paths import update_state  # noqa: PLC0415

        update_state(**{STATE_KEY: entry})
    except Exception as exc:  # pragma: no cover - cache e best-effort
        log.debug("could not persist the update cache: %s", exc)


def _persist_attempt(
    checked_at: float, latest: str, url: str, notified: str, state: dict[str, Any] | None
) -> None:
    """Registra a tentativa (mesmo sem resposta util) para respeitar o TTL de 24 h."""
    _persist(
        {
            "checked_at": checked_at,
            "latest": latest,
            "url": url,
            "notified_version": notified,
        },
        state,
    )


def _notice(
    current: str, latest: str, url: str, checked_at: float, notified: str
) -> UpdateStatus | None:
    """Status quando `latest` e mais novo e ainda nao foi avisado; senao None."""
    if not is_newer(latest, current) or latest == notified:
        return None
    return UpdateStatus(tag=latest, url=url, checked_at=checked_at)


def check_for_update(
    current: str,
    *,
    enabled: bool = True,
    ttl_s: float = DEFAULT_TTL_S,
    now: Callable[[], float] = time.time,
    fetch: Callable[[str], dict[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
) -> UpdateStatus | None:
    """Nova versao disponivel, ou None (desligado, cache fresco, sem novidade ou erro).

    `fetch`/`now`/`state` sao injetaveis (testes); sem `state` o cache vai para o
    `state.json` do usuario via `update_state` (load-modify-write). Nunca levanta.
    """
    if not enabled:
        return None
    cached = _cached(state)
    checked_at = _as_float(cached.get("checked_at"))
    latest = _as_str(cached.get("latest"))
    url = _safe_url(cached.get("url"))
    notified = _as_str(cached.get("notified_version"))
    if checked_at > 0 and now() - checked_at < ttl_s:
        status = _notice(current, latest, url, checked_at, notified)
        if status is not None:
            entry = dict(cached)
            entry["notified_version"] = status.tag
            _persist(entry, state)
        return status

    fetcher = fetch or _fetch_latest
    try:
        payload = fetcher(RELEASES_API)
    except Exception as exc:
        log.debug("update check failed: %s", exc)
        _persist_attempt(float(now()), latest, url, notified, state)
        return None
    if not isinstance(payload, dict):
        _persist_attempt(float(now()), latest, url, notified, state)
        return None
    latest = _as_str(payload.get("tag_name"))
    if not latest:
        _persist_attempt(float(now()), latest, url, notified, state)
        return None
    url = _safe_url(payload.get("html_url"))
    checked_at = float(now())
    status = _notice(current, latest, url, checked_at, notified)
    _persist_attempt(
        checked_at,
        latest,
        url,
        status.tag if status is not None else notified,
        state,
    )
    return status
