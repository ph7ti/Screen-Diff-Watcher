from __future__ import annotations

import difflib
import itertools

import numpy as np
import pytest

pytest.importorskip("pytesseract")

import pytesseract  # noqa: E402

from screen_watch.compare.advanced import OCRTextDiffStrategy  # noqa: E402
from screen_watch.errors import AppError  # noqa: E402


def _patch_texts(monkeypatch, strategy, baseline_text, current_text):
    texts = itertools.chain([baseline_text], itertools.repeat(current_text))
    monkeypatch.setattr(strategy, "_extract", lambda rgb: next(texts))


def test_identical_text_is_not_changed(make_frame, monkeypatch):
    strategy = OCRTextDiffStrategy(similarity_threshold=0.92)
    _patch_texts(monkeypatch, strategy, "ESTOQUE 42", "ESTOQUE 42")
    strategy.initialize(make_frame(np.zeros((10, 10, 3), dtype=np.uint8)))
    result = strategy.compare(make_frame(np.zeros((10, 10, 3), dtype=np.uint8)))
    assert result.changed is False
    assert result.score == 0.0


def test_text_change_is_detected_and_normalized(make_frame, monkeypatch):
    baseline_text = "ESTOQUE 42 UNIDADES"
    current_text = "ESTOQUE 7 UNIDADES"
    strategy = OCRTextDiffStrategy(similarity_threshold=0.92)
    _patch_texts(monkeypatch, strategy, baseline_text, current_text)
    strategy.initialize(make_frame(np.zeros((10, 10, 3), dtype=np.uint8)))
    result = strategy.compare(make_frame(np.zeros((10, 10, 3), dtype=np.uint8)))

    ratio = difflib.SequenceMatcher(None, baseline_text, current_text).ratio()
    assert result.changed is (1.0 - ratio > 0.08)
    assert result.score == pytest.approx(1.0 - ratio)
    assert result.detail == {"baseline_text": baseline_text, "current_text": current_text}


def test_tesseract_cmd_used_during_extract_and_restored(monkeypatch):
    monkeypatch.setattr(pytesseract.pytesseract, "tesseract_cmd", "default")
    strategy = OCRTextDiffStrategy(tesseract_cmd=r"C:\Tesseract\tesseract.exe")
    seen = {}

    def fake_image_to_string(*args, **kwargs):
        seen["cmd"] = pytesseract.pytesseract.tesseract_cmd
        return "texto"

    monkeypatch.setattr(pytesseract, "image_to_string", fake_image_to_string)
    assert strategy._extract(np.zeros((8, 8, 3), dtype=np.uint8)) == "texto"
    assert seen["cmd"] == r"C:\Tesseract\tesseract.exe"
    assert pytesseract.pytesseract.tesseract_cmd == "default"


def test_missing_tesseract_raises_clear_error():
    strategy = OCRTextDiffStrategy()
    strategy._tesseract_cmd = None
    with pytest.raises(AppError, match="Tesseract not found") as excinfo:
        strategy._extract(np.zeros((8, 8, 3), dtype=np.uint8))
    assert excinfo.value.code == "runtime.tesseract_missing"


def test_tesseract_not_found_error_is_wrapped(monkeypatch):
    strategy = OCRTextDiffStrategy()
    strategy._tesseract_cmd = r"C:\missing\tesseract.exe"

    def boom(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_string", boom)
    with pytest.raises(AppError, match="Tesseract not found"):
        strategy._extract(np.zeros((8, 8, 3), dtype=np.uint8))

