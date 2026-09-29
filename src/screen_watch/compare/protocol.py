"""Protocolo de comparacao e resultado canonico (doc, secao 10.1).

`compare` e funcao pura sobre o `Frame`: sem I/O, sem sono, sem captura.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from screen_watch.capture.frame import Frame


@dataclass(frozen=True)
class ComparisonResult:
    changed: bool
    score: float
    threshold: float
    strategy: str
    # `severity` (0..3) nao aparece no dataclass da secao 10.1, mas a `AlertChain`
    # (secao 11.3) le `result.severity`. Adicionado para reconciliar as duas secoes.
    severity: int = 0
    detail: dict[str, Any] | None = None


def compute_severity(score: float, threshold: float) -> int:
    """Mapeia o quao acima do limiar o score ficou para uma severidade 0..3."""
    if threshold <= 0:
        return 1 if score > 0 else 0
    ratio = score / threshold
    if ratio >= 3.0:
        return 3
    if ratio >= 2.0:
        return 2
    if ratio >= 1.0:
        return 1
    return 0


@runtime_checkable
class CompareStrategy(Protocol):
    name: str

    def initialize(self, baseline: Frame) -> None: ...

    def compare(self, current: Frame) -> ComparisonResult: ...
