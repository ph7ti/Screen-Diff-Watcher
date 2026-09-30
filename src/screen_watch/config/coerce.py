"""Coercao de tipos primitivos do YAML/JSON, parametrizada por classe de erro.

`config/loader.py` usa `ConfigError` (prefixo `config.*`) e `actions/plan.py`
usa `ActionError` (prefixo `action.*`). Ambos herdam de `AppError` e aceitam a
mesma assinatura `(code=..., params=...)`, entao um unico conjunto de helpers
atende aos dois sem duplicar logica.
"""

from __future__ import annotations

from typing import Any

from screen_watch.errors import AppError


def _fail(error: type[AppError], code: str, field: str, value: Any) -> None:
    raise error(code=code, params={"field": field, "value": value})


def as_int(value: Any, field: str, *, error: type[AppError], prefix: str) -> int:
    if isinstance(value, bool):
        _fail(error, f"{prefix}.not_integer", field, value)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise error(
            code=f"{prefix}.not_integer", params={"field": field, "value": value}
        ) from exc


def as_float(value: Any, field: str, *, error: type[AppError], prefix: str) -> float:
    if isinstance(value, bool):
        _fail(error, f"{prefix}.not_number", field, value)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise error(
            code=f"{prefix}.not_number", params={"field": field, "value": value}
        ) from exc


def as_bool(value: Any, field: str, *, error: type[AppError], prefix: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    _fail(error, f"{prefix}.not_bool", field, value)


def as_str(value: Any, field: str, *, error: type[AppError], prefix: str) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    _fail(error, f"{prefix}.not_text", field, value)


def as_str_list(
    value: Any, field: str, *, error: type[AppError], prefix: str
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise error(code=f"{prefix}.not_text_list", params={"field": field})
    return tuple(as_str(item, f"{field}[]", error=error, prefix=prefix) for item in value)
