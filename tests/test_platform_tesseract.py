from __future__ import annotations

from screen_watch.platform import tesseract


def test_explicit_path_wins(monkeypatch):
    monkeypatch.setattr(tesseract.shutil, "which", lambda name: "/from/path/tesseract")
    assert tesseract.resolve_tesseract_cmd(r"C:\x\tesseract.exe") == r"C:\x\tesseract.exe"


def test_path_lookup_is_preferred(monkeypatch):
    monkeypatch.setattr(tesseract.shutil, "which", lambda name: "/usr/bin/tesseract")
    assert tesseract.resolve_tesseract_cmd(None) == "/usr/bin/tesseract"


def test_common_directories_when_not_on_path(monkeypatch, tmp_path):
    monkeypatch.setattr(tesseract.shutil, "which", lambda name: None)
    executable = "tesseract.exe" if tesseract.sys.platform == "win32" else "tesseract"
    candidate = tmp_path / executable
    candidate.write_text("")
    monkeypatch.setattr(tesseract, "_common_dirs", lambda: [tmp_path])
    assert tesseract.resolve_tesseract_cmd(None) == str(candidate)


def test_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(tesseract.shutil, "which", lambda name: None)
    monkeypatch.setattr(tesseract, "_common_dirs", lambda: [tmp_path])
    assert tesseract.resolve_tesseract_cmd(None) is None
