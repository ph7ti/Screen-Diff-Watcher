"""Leitura e filtros do historico de alertas (puro, sem Qt) — doc secao 3.7.

O `JsonlNotifier` grava uma linha JSON por disparo em `logs/alerts.jsonl`; o
registro nao tem canal/alvo/caminho de evidencia, entao os filtros cobrem data,
severidade e strategy, e o print e localizado por proximidade de horario
(heuristica documentada no doc/00).
"""

from __future__ import annotations

import json
from pathlib import Path

EVIDENCE_TOLERANCE_S = 2.0


def read_records(path: str | Path) -> tuple[list[dict], int]:
    """Le o JSONL tolerando linhas invalidas; devolve `(registros, invalidas)`."""
    source = Path(path)
    if not source.is_file():
        return [], 0
    records: list[dict] = []
    invalid = 0
    text = source.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except ValueError:
            invalid += 1
            continue
        if isinstance(data, dict):
            records.append(data)
        else:
            invalid += 1
    return records, invalid


def filter_records(
    records: list[dict],
    *,
    since: float | None = None,
    until: float | None = None,
    severity_min: int | None = None,
    strategy: str | None = None,
) -> list[dict]:
    """Filtra registros por janela de tempo, severidade minima e strategy.

    Registros sem o campo exigido pelo filtro ativo sao descartados.
    """
    selected: list[dict] = []
    for record in records:
        timestamp = record.get("ts")
        if since is not None and (
            not isinstance(timestamp, (int, float)) or timestamp < since
        ):
            continue
        if until is not None and (
            not isinstance(timestamp, (int, float)) or timestamp > until
        ):
            continue
        severity = record.get("severity")
        if severity_min is not None and (
            not isinstance(severity, (int, float)) or severity < severity_min
        ):
            continue
        if strategy and record.get("strategy") != strategy:
            continue
        selected.append(record)
    return selected


def find_evidence(
    ts: float, captures_dir: str | Path, *, tolerance_s: float = EVIDENCE_TOLERANCE_S
) -> Path | None:
    """Print `*_change.png` mais proximo de `ts` (heuristica; `None` fora da tolerancia)."""
    directory = Path(captures_dir)
    if not directory.is_dir():
        return None
    best: Path | None = None
    best_delta = tolerance_s
    for candidate in directory.rglob("*_change.png"):
        try:
            delta = abs(candidate.stat().st_mtime - float(ts))
        except OSError:
            continue
        if delta <= best_delta:
            best_delta = delta
            best = candidate
    return best
