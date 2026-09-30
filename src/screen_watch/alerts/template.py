"""Modelo de texto dos alertas: placeholders `${campo}` e `${env:VAR}`.

Modulo puro (sem Qt, sem rede): usado tanto na validacao (loader) quanto no envio
(notificadores `webhook`/`http_post`/`syslog`). Usa `string.Template` em vez de
`str.format` justamente porque o corpo costuma ser JSON (`{`/`}` ficam literais);
`$$` escapa o cifrao.

Placeholders de configuracao: `message`, `strategy`, `score`, `threshold`,
`severity`, `target`, `timestamp`, `window_handle`, `changed`, `roi`. O prefixo
`env:` le `os.environ` **no momento do envio** (variavel pode ser definida depois
do parse). Placeholder desconhecido e erro de config (`config.alert_unknown_placeholder`).
"""

from __future__ import annotations

import os
import string
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from screen_watch.capture.frame import Frame
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.errors import ConfigError

PLACEHOLDERS: tuple[str, ...] = (
    "message",
    "strategy",
    "score",
    "threshold",
    "severity",
    "target",
    "timestamp",
    "window_handle",
    "changed",
    "roi",
)

ENV_PREFIX = "env:"


class _AlertTemplate(string.Template):
    """`string.Template` que aceita `${env:VAR}` como nome de placeholder."""

    idpattern = r"(?a:env:)?[_a-z][_a-z0-9]*"


class _PlaceholderMapping(Mapping[str, str]):
    """Resolve `${campo}`/`${env:VAR}`; `env:` e lido agora, o resto vem de `values`."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> str:
        if key.startswith(ENV_PREFIX):
            return os.environ.get(key[len(ENV_PREFIX) :], "")
        return self._values.get(key, "")

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


def _format_roi(rect: Any) -> str:
    if rect is None:
        return ""
    try:
        x, y, w, h = rect
    except (TypeError, ValueError):
        return ""
    return f"{x},{y},{w},{h}"


def context(
    result: ComparisonResult,
    frame: Frame,
    target_name: str = "",
    roi: Any = None,
) -> dict[str, str]:
    """Valores de substituicao a partir do resultado/frame (mesmo estilo do Telegram)."""
    rect = roi if roi is not None else getattr(frame, "absolute_rect", None)
    timestamp = getattr(frame, "timestamp", None) or datetime.now(tz=UTC).timestamp()
    stamp = datetime.fromtimestamp(float(timestamp), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "message": f"{result.strategy}: score={result.score:.2f} (severity {result.severity})",
        "strategy": str(result.strategy),
        "score": f"{result.score:.3f}",
        "threshold": f"{result.threshold:.3f}",
        "severity": str(int(result.severity)),
        "target": str(target_name or ""),
        "timestamp": stamp,
        "window_handle": str(getattr(frame, "window_handle", "")),
        "changed": "true" if result.changed else "false",
        "roi": _format_roi(rect),
    }


def render_string(text: str, values: Mapping[str, str]) -> str:
    """Substitui os placeholders de uma string (levanta `KeyError`/`ValueError` se invalida)."""
    return _AlertTemplate(text).substitute(_PlaceholderMapping(values))


def render_mapping(value: Any, values: Mapping[str, str]) -> Any:
    """Aplica `render_string` recursivamente em strings de mappings/listas."""
    if isinstance(value, str):
        return render_string(value, values)
    if isinstance(value, Mapping):
        return {key: render_mapping(item, values) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [render_mapping(item, values) for item in value]
    return value


def _validate_string(text: str, field: str) -> None:
    for match in _AlertTemplate.pattern.finditer(text):
        if match.group("escaped") is not None:
            continue
        name = match.group("named") or match.group("braced")
        if name is None:
            raise ConfigError(
                code="config.alert_unknown_placeholder",
                params={"field": field, "value": text, "valid": PLACEHOLDERS},
            )
        if name not in PLACEHOLDERS and not name.startswith(ENV_PREFIX):
            raise ConfigError(
                code="config.alert_unknown_placeholder",
                params={"field": field, "value": name, "valid": PLACEHOLDERS},
            )


def validate_placeholders(value: Any, field: str) -> None:
    """Valida placeholders de uma string, mapping ou lista (erro de config se invalido)."""
    if isinstance(value, str):
        _validate_string(value, field)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            validate_placeholders(item, f"{field}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            validate_placeholders(item, f"{field}[{index}]")


def env_secrets(value: Any) -> list[str]:
    """Valores de `os.environ` referenciados por `${env:VAR}` (para redacao em erros)."""
    found: list[str] = []

    def _walk(text: str) -> None:
        for match in _AlertTemplate.pattern.finditer(text):
            name = match.group("named") or match.group("braced")
            if name and name.startswith(ENV_PREFIX):
                resolved = os.environ.get(name[len(ENV_PREFIX) :])
                if resolved:
                    found.append(resolved)

    def _visit(item: Any) -> None:
        if isinstance(item, str):
            _walk(item)
        elif isinstance(item, Mapping):
            for sub in item.values():
                _visit(sub)
        elif isinstance(item, (list, tuple)):
            for sub in item:
                _visit(sub)

    _visit(value)
    return found
