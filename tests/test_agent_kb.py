from __future__ import annotations

import re
from pathlib import Path

from screen_watch import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]
KB_DIR = REPO_ROOT / ".kilo" / "knowledge"
KB_FILES = ("architecture.md", "development.md", "roadmap.md")
AGENTS = REPO_ROOT / "AGENTS.md"
LINK_RE = re.compile(r"\]\(([^)#]+)(?:#[^)]*)?\)")


def _relative_links(path: Path) -> list[str]:
    targets = LINK_RE.findall(path.read_text(encoding="utf-8"))
    return [t for t in targets if not t.startswith(("http://", "https://", "mailto:"))]


def test_knowledge_base_files_exist():
    for name in KB_FILES:
        assert (KB_DIR / name).is_file(), name


def test_agents_file_links_every_knowledge_base_file():
    text = AGENTS.read_text(encoding="utf-8")
    for name in KB_FILES:
        assert f"](.kilo/knowledge/{name})" in text, name


def test_knowledge_base_status_matches_version():
    pattern = re.compile(rf"^Status: v{re.escape(__version__)}\b", re.MULTILINE)
    for name in KB_FILES:
        assert pattern.search((KB_DIR / name).read_text(encoding="utf-8")), name


def test_roadmap_lists_planned_versions():
    text = (KB_DIR / "roadmap.md").read_text(encoding="utf-8")
    for version in ("v0.8.0", "v0.9.0", "v1.0.0"):
        assert f"## {version}" in text, version


def test_agents_relative_links_resolve():
    for target in _relative_links(AGENTS):
        assert (REPO_ROOT / target).exists(), target


def test_knowledge_base_relative_links_resolve():
    for name in KB_FILES:
        path = KB_DIR / name
        for target in _relative_links(path):
            assert (path.parent / target).exists(), f"{name}: {target}"
