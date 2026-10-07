"""Checagem passiva de nova versao (doc 3.8; v0.11.0).

Rede sempre mockada (`httpx.MockTransport`, como em `tests/test_alerts_ntfy.py`);
nenhum socket real e aberto.
"""

from __future__ import annotations

import httpx
import pytest

from screen_watch import updates
from screen_watch.updates import (
    RELEASES_API,
    UpdateStatus,
    check_for_update,
    is_newer,
    parse_version,
)


def _patch_request(monkeypatch, handler):
    seen: list[dict] = []
    transport = httpx.MockTransport(handler)

    def fake_request(method, url, **kwargs):
        seen.append({"method": method, "url": str(url), **kwargs})
        with httpx.Client(transport=transport) as client:
            return client.request(method, url, **kwargs)

    monkeypatch.setattr(httpx, "request", fake_request)
    return seen


def _release(monkeypatch, tag="v0.11.0"):
    url = f"https://github.com/ph7ti/Screen-Diff-Watcher/releases/tag/{tag}"
    return _patch_request(
        monkeypatch,
        lambda request: httpx.Response(200, json={"tag_name": tag, "html_url": url}),
    )


# -- parse_version / is_newer ------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("v0.11.0", (0, 11, 0)),
        ("0.11.0", (0, 11, 0)),
        ("V1.2.3-rc1", (1, 2, 3)),
        ("1.2.3+build.7", (1, 2, 3)),
        ("0.11", (0, 11)),
        ("", ()),
        ("release", ()),
    ],
)
def test_parse_version(text, expected):
    assert parse_version(text) == expected


def test_is_newer_compares_release_components():
    assert is_newer("v0.11.0", "0.10.1") is True
    assert is_newer("0.11", "0.10.1") is True
    assert is_newer("v0.10.1", "0.10.1") is False
    assert is_newer("1.0.0-beta.2", "1.0.0") is False
    assert is_newer("0.9.9", "0.10.0") is False
    assert is_newer("", "0.10.1") is False
    assert is_newer("v0.11.0", "") is False


# -- check_for_update --------------------------------------------------------


def test_newer_release_returns_status(monkeypatch):
    seen = _release(monkeypatch)
    state: dict = {}

    status = check_for_update("0.10.1", now=lambda: 1000.0, state=state)

    assert status == UpdateStatus(
        tag="v0.11.0",
        url="https://github.com/ph7ti/Screen-Diff-Watcher/releases/tag/v0.11.0",
        checked_at=1000.0,
    )
    assert seen[0]["method"] == "GET"
    assert seen[0]["url"] == RELEASES_API
    assert seen[0]["headers"]["Accept"] == "application/vnd.github+json"
    assert seen[0]["timeout"] == updates.DEFAULT_TIMEOUT_S
    assert state["update_check"]["latest"] == "v0.11.0"
    assert state["update_check"]["notified_version"] == "v0.11.0"


def test_same_or_older_release_returns_none(monkeypatch):
    seen = _release(monkeypatch, tag="v0.10.1")
    state: dict = {}

    assert check_for_update("0.10.1", now=lambda: 1000.0, state=state) is None
    assert len(seen) == 1
    assert state["update_check"]["notified_version"] == ""


def test_cache_fresh_does_not_hit_network(monkeypatch):
    seen = _release(monkeypatch)
    release_url = "https://github.com/ph7ti/Screen-Diff-Watcher/releases/tag/v0.11.0"
    state = {
        "update_check": {
            "checked_at": 1000.0,
            "latest": "v0.11.0",
            "url": release_url,
            "notified_version": "",
        }
    }

    status = check_for_update("0.10.1", now=lambda: 1000.0 + 3600, state=state)

    assert seen == []
    assert status is not None
    assert status.url == release_url
    assert state["update_check"]["notified_version"] == "v0.11.0"


def test_cache_fresh_and_already_notified_returns_none(monkeypatch):
    seen = _release(monkeypatch)
    state = {
        "update_check": {
            "checked_at": 1000.0,
            "latest": "v0.11.0",
            "url": "https://github.com/ph7ti/Screen-Diff-Watcher/releases/tag/v0.11.0",
            "notified_version": "v0.11.0",
        }
    }

    assert check_for_update("0.10.1", now=lambda: 1000.0 + 3600, state=state) is None
    assert seen == []


def test_expired_cache_fetches_once(monkeypatch):
    seen = _release(monkeypatch, tag="v0.10.1")
    state = {
        "update_check": {
            "checked_at": 1000.0,
            "latest": "v0.10.1",
            "url": "",
            "notified_version": "",
        }
    }

    status = check_for_update("0.10.1", now=lambda: 1000.0 + 86401, state=state)

    assert len(seen) == 1
    assert status is None
    assert state["update_check"]["checked_at"] == 1000.0 + 86401


def test_opt_out_never_hits_network(monkeypatch):
    seen = _release(monkeypatch)

    assert check_for_update("0.10.1", enabled=False, state={}) is None
    assert seen == []


def test_network_error_is_silent_and_caches_the_attempt(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    seen = _patch_request(monkeypatch, handler)
    state: dict = {}

    assert check_for_update("0.10.1", now=lambda: 1000.0, state=state) is None
    assert len(seen) == 1
    assert state["update_check"]["checked_at"] == 1000.0
    assert state["update_check"]["latest"] == ""

    # Dentro do TTL a tentativa falha nao e repetida (no maximo 1 GET/dia).
    assert check_for_update("0.10.1", now=lambda: 1000.0 + 3600, state=state) is None
    assert len(seen) == 1


def test_http_error_is_silent(monkeypatch):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(503))
    state: dict = {}

    assert check_for_update("0.10.1", now=lambda: 1000.0, state=state) is None
    assert len(seen) == 1
    assert state["update_check"]["checked_at"] == 1000.0


def test_malformed_payload_is_silent(monkeypatch):
    seen = _patch_request(monkeypatch, lambda request: httpx.Response(200, json=[]))
    state: dict = {}

    assert check_for_update("0.10.1", now=lambda: 1000.0, state=state) is None
    assert len(seen) == 1
    assert state["update_check"]["checked_at"] == 1000.0


def test_injected_fetch_avoids_httpx(monkeypatch):
    seen = _release(monkeypatch)
    payload = {
        "tag_name": "v1.0.0",
        "html_url": "https://github.com/ph7ti/Screen-Diff-Watcher/releases/tag/v1.0.0",
    }

    status = check_for_update("0.10.1", fetch=lambda url: payload, state={})

    assert seen == []
    assert status is not None
    assert status.tag == "v1.0.0"


def test_corrupt_cache_is_ignored(monkeypatch):
    seen = _release(monkeypatch)
    state = {"update_check": "garbage"}

    status = check_for_update("0.10.1", state=state)

    assert len(seen) == 1
    assert status is not None
    assert isinstance(state["update_check"], dict)


def test_untrusted_payload_url_is_dropped(monkeypatch):
    _patch_request(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={"tag_name": "v0.11.0", "html_url": "file:///etc/passwd"},
        ),
    )
    state: dict = {}

    status = check_for_update("0.10.1", now=lambda: 1000.0, state=state)

    assert status is not None
    assert status.url == ""
    assert state["update_check"]["url"] == ""


def test_poisoned_cached_url_is_dropped(monkeypatch):
    seen = _release(monkeypatch)
    state = {
        "update_check": {
            "checked_at": 1000.0,
            "latest": "v0.11.0",
            "url": "https://evil.example/release",
            "notified_version": "",
        }
    }

    status = check_for_update("0.10.1", now=lambda: 1000.0 + 3600, state=state)

    assert seen == []
    assert status is not None
    assert status.url == ""
