from __future__ import annotations

import os

from screen_watch.platform import paths


def test_app_home_override(monkeypatch, tmp_path):
    target = tmp_path / "sw-home"
    monkeypatch.setenv(paths.ENV_HOME, str(target))
    assert paths.app_home() == target
    assert paths.config_path() == target / "config.yaml"
    assert paths.selections_dir() == target / "selections"
    assert paths.logs_dir() == target / "logs"


def test_app_home_falls_back_per_platform(monkeypatch):
    monkeypatch.delenv(paths.ENV_HOME, raising=False)
    home = paths.app_home()
    assert home.name == "screen_watch"


def test_ensure_dirs_creates_structure(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    root = paths.ensure_dirs()
    assert root == tmp_path / "home"
    for path in (paths.app_home(), paths.selections_dir(), paths.logs_dir()):
        assert path.is_dir()


def test_ensure_dirs_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    paths.ensure_dirs()
    paths.ensure_dirs()
    assert os.path.isdir(paths.app_home())


def test_override_wins_over_packaged(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "ov"))
    monkeypatch.setattr(paths, "package_family_name", lambda: "FAM")
    assert paths.app_home() == tmp_path / "ov"


def test_packaged_uses_real_localcache_path(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.ENV_HOME, raising=False)
    monkeypatch.setattr(paths, "package_family_name", lambda: "FAM")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    (tmp_path / "Packages" / "FAM").mkdir(parents=True)

    assert paths.app_home() == tmp_path / "Packages" / "FAM" / "LocalCache" / "Roaming" / "screen_watch"


def test_packaged_ignored_when_package_dir_missing(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.ENV_HOME, raising=False)
    monkeypatch.setattr(paths, "package_family_name", lambda: "FAM")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # "Packages/FAM" nao existe -> cai no caminho padrao do SO
    assert "Packages" not in str(paths.app_home())
