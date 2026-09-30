"""Pipeline com curto-circuito (doc, secao 10.5).

O primeiro estagio que retornar `changed=False` encerra o pipeline. O veredito final
e do ultimo estagio que rodou, enriquecido com a severidade calculada.
"""

from __future__ import annotations

from dataclasses import replace

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import CompareStrategy, ComparisonResult, compute_severity

MODE_STAGES: dict[str, tuple[str, ...]] = {
    "light": ("light",),
    "default": ("default",),
    # `advanced` roda o phash (`default`) como gate **antes** do OCR: so roda/pontua o
    # OCR quando os pixels mudaram. Sem o gate, ruido de OCR sobre quadros quase
    # identicos virava "mudanca" a cada tick (falso positivo; doc, secao 10.5).
    "advanced": ("default", "advanced"),
}


class ComparePipeline:
    def __init__(self, stages: list[CompareStrategy]) -> None:
        if not stages:
            raise ValueError("ComparePipeline precisa de pelo menos um estagio")
        self.stages = stages

    def initialize(self, baseline: Frame) -> None:
        for stage in self.stages:
            stage.initialize(baseline)

    def compare(self, current: Frame) -> ComparisonResult:
        last = self.stages[0].compare(current)
        for stage in self.stages[1:]:
            if not last.changed:
                return last
            last = stage.compare(current)
        if last.changed and last.severity == 0:
            last = replace(last, severity=compute_severity(last.score, last.threshold))
        return last
