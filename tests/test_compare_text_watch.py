from __future__ import annotations

import numpy as np
import pytest

from screen_watch.compare.protocol import ComparisonResult
from screen_watch.compare.text_watch import (
    EXPECT_APPEARS,
    EXPECT_DISAPPEARS,
    TextWatchStrategy,
    normalize_text,
)


class FakeOCR:
    """OCR falso: devolve os textos na ordem em que `compare` for chamado."""

    name = "advanced"

    def __init__(self, baseline_text: str = "", *texts: str) -> None:
        self._baseline_text = baseline_text
        self._texts = iter(texts)
        self.initialized = False

    @property
    def baseline_text(self) -> str:
        return self._baseline_text

    def initialize(self, baseline) -> None:
        self.initialized = True

    def compare(self, current) -> ComparisonResult:
        text = next(self._texts)
        return ComparisonResult(
            changed=True,
            score=0.9,
            threshold=0.08,
            strategy="advanced",
            detail={"baseline_text": self._baseline_text, "current_text": text},
        )


def _watch(inner: FakeOCR, **kwargs) -> TextWatchStrategy:
    options = {"text": "concluido"}
    options.update(kwargs)
    return TextWatchStrategy(inner, **options)


def _frame(make_frame, sequence: int):
    return make_frame(np.zeros((4, 4, 3), dtype=np.uint8), sequence=sequence)


def test_normalize_text_strips_accents_and_case():
    assert normalize_text("  CONCLUÍDO\t ") == "concluido"
    assert normalize_text("Concluído", case_sensitive=True) == "Concluido"
    assert normalize_text("Concluído", case_sensitive=True, ignore_accents=False) == "Concluído"
    assert normalize_text("Concluído", ignore_accents=False) == "concluído"


def test_appears_fires_only_on_transition(make_frame):
    inner = FakeOCR("", "CONCLUIDO", "CONCLUIDO")
    watch = _watch(inner, expect=EXPECT_APPEARS)
    watch.initialize(_frame(make_frame, 0))

    first = watch.compare(_frame(make_frame, 1))
    assert first.changed is True
    assert first.severity == 3  # transicao: evento definitivo
    assert first.strategy == "advanced"
    assert first.detail["ocr_score"] == 0.9
    assert first.detail["ocr_threshold"] == 0.08
    state = first.detail["text_watch"]
    assert state == {
        "text": "concluido",
        "expect": "appears",
        "present_before": False,
        "present_now": True,
    }
    assert first.detail["current_text"] == "CONCLUIDO"

    second = watch.compare(_frame(make_frame, 2))
    assert second.changed is False
    assert second.severity == 0
    assert second.detail["text_watch"]["present_before"] is True


def test_disappears_fires_only_on_transition(make_frame):
    inner = FakeOCR("CONCLUIDO", "", "")
    watch = _watch(inner, expect=EXPECT_DISAPPEARS)
    watch.initialize(_frame(make_frame, 0))

    first = watch.compare(_frame(make_frame, 1))
    assert first.changed is True
    assert first.severity == 3
    assert first.detail["text_watch"]["present_before"] is True
    assert first.detail["text_watch"]["present_now"] is False

    assert watch.compare(_frame(make_frame, 2)).changed is False


def test_other_text_changes_do_not_fire(make_frame):
    inner = FakeOCR("", "outro texto qualquer", "terceiro texto")
    watch = _watch(inner, expect=EXPECT_APPEARS)
    watch.initialize(_frame(make_frame, 0))

    assert watch.compare(_frame(make_frame, 1)).changed is False
    assert watch.compare(_frame(make_frame, 2)).changed is False


def test_baseline_already_present_does_not_fire_until_reappears(make_frame):
    inner = FakeOCR("CONCLUIDO", "CONCLUIDO", "", "CONCLUIDO")
    watch = _watch(inner, expect=EXPECT_APPEARS)
    watch.initialize(_frame(make_frame, 0))

    assert watch.compare(_frame(make_frame, 1)).changed is False  # continua presente
    assert watch.compare(_frame(make_frame, 2)).changed is False  # desapareceu (sem expect)
    assert watch.compare(_frame(make_frame, 3)).changed is True  # apareceu de novo


@pytest.mark.parametrize(
    ("case_sensitive", "ignore_accents", "needle", "haystack", "expected"),
    [
        # defaults: sem caixa e sem acentos nos dois lados
        (False, True, "concluido", "CONCLUÍDO", True),
        (False, True, "CONCLUÍDO", "concluido", True),
        # case-sensitive
        (True, True, "CONCLUIDO", "CONCLUIDO", True),
        (True, True, "concluido", "CONCLUIDO", False),
        # acentos significativos
        (False, False, "concluído", "concluído", True),
        (False, False, "concluido", "concluído", False),
        (False, False, "concluído", "concluido", False),
    ],
)
def test_matching_options(
    make_frame, case_sensitive, ignore_accents, needle, haystack, expected
):
    inner = FakeOCR("", haystack)
    watch = _watch(
        inner,
        text=needle,
        case_sensitive=case_sensitive,
        ignore_accents=ignore_accents,
    )
    watch.initialize(_frame(make_frame, 0))
    assert watch.compare(_frame(make_frame, 1)).changed is expected


def test_empty_text_never_fires(make_frame):
    inner = FakeOCR("", "qualquer coisa")
    watch = _watch(inner, text="")
    watch.initialize(_frame(make_frame, 0))
    assert watch.compare(_frame(make_frame, 1)).changed is False


def test_invalid_expect_raises():
    with pytest.raises(ValueError):
        _watch(FakeOCR(), expect="blink")


def test_initialize_recomputes_presence_after_rebaseline(make_frame):
    inner = FakeOCR("", "CONCLUIDO", "CONCLUIDO")
    watch = _watch(inner, expect=EXPECT_APPEARS)
    watch.initialize(_frame(make_frame, 0))
    assert watch.compare(_frame(make_frame, 1)).changed is True

    # Re-baseline com o texto presente: a presenca e recalculada e nada dispara.
    inner._baseline_text = "CONCLUIDO"
    watch.initialize(_frame(make_frame, 2))
    assert watch.compare(_frame(make_frame, 3)).changed is False
