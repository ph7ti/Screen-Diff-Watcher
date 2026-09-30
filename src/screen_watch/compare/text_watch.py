"""Filtro de presenca de texto na ROI (doc, secao 10.4).

Usado apenas no modo `advanced` e **sozinho** (sem o gate de phash): com um
`text_watch` configurado o OCR roda a cada tick e o veredito do filtro e
autoritativo — o `changed` do OCR nao e propagado e `score`/`threshold` do OCR
ficam apenas no `detail` (calibracao via `compare-modes`).

Semantica (filtro): o alerta dispara **somente** na transicao escolhida
(`expect: appears|disappears`); as demais mudancas de texto nao disparam. O
casamento e por substring, com `case_sensitive` (default false) e
`ignore_accents` (default true; NFKD + remocao de diacriticos nos dois lados).
O estado de presenca acompanha o stream, de modo que uma transicao dispara uma
unica vez mesmo sem re-arm (o re-arm/re-baseline recalcula a presenca).
"""

from __future__ import annotations

import unicodedata
from typing import Any

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult

EXPECT_APPEARS = "appears"
EXPECT_DISAPPEARS = "disappears"
VALID_EXPECTS = (EXPECT_APPEARS, EXPECT_DISAPPEARS)

# Severidade fixa da transicao: e um evento definitivo. Derivar do score do OCR
# poderia deixa-la abaixo do `severity_min` e o alerta nao dispararia em silencio.
TRANSITION_SEVERITY = 3


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_text(
    text: str, *, case_sensitive: bool = False, ignore_accents: bool = True
) -> str:
    """Normaliza whitespace e, opcionalmente, acentos e caixa (nos dois lados)."""
    value = " ".join(str(text).split())
    if ignore_accents:
        value = _strip_accents(value)
    if not case_sensitive:
        value = value.casefold()
    return value


class TextWatchStrategy:
    """Envolve o OCR no modo `advanced` e decide pela presenca do texto.

    O `inner` deve ser o `OCRTextDiffStrategy` (expoe `baseline_text` e o
    `current_text` no `detail`); o veredito do filtro substitui o dele.
    """

    name = "advanced"

    def __init__(
        self,
        inner,
        *,
        text: str,
        expect: str = EXPECT_APPEARS,
        case_sensitive: bool = False,
        ignore_accents: bool = True,
    ) -> None:
        if expect not in VALID_EXPECTS:
            raise ValueError(f"expect invalido: {expect!r}; use um de {VALID_EXPECTS}")
        self._inner = inner
        self.text = str(text)
        self.expect = expect
        self.case_sensitive = bool(case_sensitive)
        self.ignore_accents = bool(ignore_accents)
        self._needle = normalize_text(
            self.text, case_sensitive=self.case_sensitive, ignore_accents=self.ignore_accents
        )
        self._baseline_text = ""
        self._present_before = False

    def initialize(self, baseline: Frame) -> None:
        self._inner.initialize(baseline)
        self._baseline_text = str(getattr(self._inner, "baseline_text", ""))
        self._present_before = self._present(self._baseline_text)

    def compare(self, current: Frame) -> ComparisonResult:
        inner = self._inner.compare(current)
        detail: dict[str, Any] = dict(inner.detail or {})
        current_text = str(detail.get("current_text", ""))
        present_now = self._present(current_text)
        before = self._present_before
        if self.expect == EXPECT_APPEARS:
            changed = present_now and not before
        else:
            changed = before and not present_now
        self._present_before = present_now
        detail.update(
            {
                "ocr_score": inner.score,
                "ocr_threshold": inner.threshold,
                "text_watch": {
                    "text": self.text,
                    "expect": self.expect,
                    "present_before": before,
                    "present_now": present_now,
                },
            }
        )
        return ComparisonResult(
            changed=changed,
            score=inner.score,
            threshold=inner.threshold,
            strategy=self.name,
            severity=TRANSITION_SEVERITY if changed else 0,
            detail=detail,
        )

    def _present(self, text: str) -> bool:
        if not self._needle:
            return False
        haystack = normalize_text(
            text, case_sensitive=self.case_sensitive, ignore_accents=self.ignore_accents
        )
        return self._needle in haystack
