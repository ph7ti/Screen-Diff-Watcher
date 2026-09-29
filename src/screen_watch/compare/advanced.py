"""Estrategia Avancada — diff de texto via OCR (doc, secao 10.4).

No modo `advanced` o OCR e o detector: roda a cada tick. Custo 100-500 ms por
chamada (medir na Etapa D). `tesseract_cmd` cobre o caso em que o binario nao esta
no PATH; a busca por caminhos do SO fica em `platform/tesseract.py`, nunca aqui.
Sem o binario, falha com mensagem clara em vez de stacktrace crua.
"""

from __future__ import annotations

import difflib

import numpy as np
import pytesseract
from PIL import Image

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.platform.tesseract import resolve_tesseract_cmd

_MISSING_TESSERACT_MSG = (
    "Tesseract nao encontrado. Instale o Tesseract (Windows: "
    "https://github.com/UB-Mannheim/tesseract/wiki) com os traineddata 'por' e 'eng' "
    "e informe 'compare_options.advanced.tesseract_cmd' no YAML, ou adicione o executavel ao PATH."
)


class OCRTextDiffStrategy:
    name = "advanced"

    def __init__(
        self,
        similarity_threshold: float = 0.92,
        psm: int = 6,
        lang: str = "por+eng",
        upscale: int = 2,
        tesseract_cmd: str | None = None,
    ) -> None:
        self.similarity_threshold = float(similarity_threshold)
        self.psm = int(psm)
        self.lang = lang
        self.upscale = int(upscale)
        self._tesseract_cmd = resolve_tesseract_cmd(tesseract_cmd)
        self._baseline_text = ""

    def _extract(self, rgb: np.ndarray) -> str:
        if self._tesseract_cmd is None:
            raise RuntimeError(_MISSING_TESSERACT_MSG)
        if self.upscale > 1:
            rgb = np.repeat(np.repeat(rgb, self.upscale, axis=0), self.upscale, axis=1)
        img = Image.fromarray(rgb)

        # `pytesseract` so aceita o caminho via atributo global: define e restaura
        # para nao vazar estado entre instancias/targets.
        previous = pytesseract.pytesseract.tesseract_cmd
        pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd
        try:
            text = pytesseract.image_to_string(img, lang=self.lang, config=f"--psm {self.psm}")
        except pytesseract.TesseractNotFoundError as exc:
            raise RuntimeError(_MISSING_TESSERACT_MSG) from exc
        finally:
            pytesseract.pytesseract.tesseract_cmd = previous
        return " ".join(text.split())

    def initialize(self, baseline: Frame) -> None:
        self._baseline_text = self._extract(baseline.rgb)

    def compare(self, current: Frame) -> ComparisonResult:
        current_text = self._extract(current.rgb)
        ratio = difflib.SequenceMatcher(None, self._baseline_text, current_text).ratio()
        score = 1.0 - ratio  # normalizado: alto = mudou
        threshold = 1.0 - self.similarity_threshold
        return ComparisonResult(
            changed=score > threshold,
            score=score,
            threshold=threshold,
            strategy=self.name,
            detail={"baseline_text": self._baseline_text, "current_text": current_text},
        )
