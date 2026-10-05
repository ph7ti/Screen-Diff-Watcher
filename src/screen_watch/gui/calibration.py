"""Amostras e CSV da calibracao ao vivo (puro, sem Qt) — doc secao 3.7."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

# (ts, strategy, score, threshold, severity)
Sample = tuple[float, str, float, float, int]

HEADER = ("timestamp", "strategy", "score", "threshold", "severity")


def to_csv(samples: Iterable[Sample]) -> str:
    """Exporta as amostras em CSV (cabeçalho fixo, `\\n` como terminador)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    for timestamp, strategy, score, threshold, severity in samples:
        writer.writerow(
            [
                f"{float(timestamp):.3f}",
                str(strategy),
                f"{float(score):.6f}",
                f"{float(threshold):.6f}",
                str(int(severity)),
            ]
        )
    return buffer.getvalue()


def severity_counts(samples: Iterable[Sample]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for _timestamp, _strategy, _score, _threshold, severity in samples:
        level = int(severity)
        counts[level] = counts.get(level, 0) + 1
    return counts
