"""Tipos de acoes pseudo-humanas (plano, secao 3.2).

Modulo puro (sem I/O e sem dependencias de runtime): o parse fica em
`actions/plan.py`, a execucao em `actions/runner.py`. `steps` e uma sequencia
ordenada de passos discriminados por `kind`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STEP_KINDS = ("activate", "click", "move", "type", "key", "wait")
REF_KINDS = ("roi", "window", "screen")
BUTTONS = ("left", "right", "middle")
TRIGGERS = ("change", "at", "every", "after")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

DEFAULT_COOLDOWN_S = 30.0
DEFAULT_SETTLE_S = 1.5
DEFAULT_MAX_PER_MIN = 6
DEFAULT_MAX_PER_SESSION = 100


@dataclass(frozen=True)
class ActionStep:
    """Um passo. Os campos usados dependem de `kind` (ver `plan.py`)."""

    kind: str
    x: int | None = None
    y: int | None = None
    ref: str = "roi"
    button: str = "left"
    clicks: int = 1
    keys: str = ""
    text: str = ""
    interval_ms: int | None = None
    ms: int = 0


@dataclass(frozen=True)
class ActionSpec:
    """Uma acao do perfil/selecao (doc, secao 12.2)."""

    name: str
    enabled: bool = True
    severity_min: int = 1
    cooldown_s: float = DEFAULT_COOLDOWN_S
    changed: bool = True
    when_severity_min: int | None = None
    text_any: tuple[str, ...] = ()
    text_all: tuple[str, ...] = ()
    text_regex: str | None = None
    case_sensitive: bool = False
    trigger: str = "change"
    at: tuple[str, ...] = ()
    days: tuple[str, ...] = ()
    every_s: float = 0.0
    after_s: float = 0.0
    settle_s: float = DEFAULT_SETTLE_S
    rebaseline: bool = False
    max_per_min: int = DEFAULT_MAX_PER_MIN
    max_per_session: int = DEFAULT_MAX_PER_SESSION
    steps: tuple[ActionStep, ...] = field(default_factory=tuple)

    @property
    def effective_severity_min(self) -> int:
        return self.severity_min if self.when_severity_min is None else self.when_severity_min

    @property
    def needs_ocr(self) -> bool:
        return bool(self.text_any or self.text_all or self.text_regex)
