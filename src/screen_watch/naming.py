"""Slug de nomes de arquivo (puro, sem Qt e sem I/O).

Compartilhado pelo CLI e pela GUI: o `select`/`select-manual` derivam o nome do
arquivo do titulo/app e o campo "Nome da selecao" da GUI renomeia
`selections/<slug>.json`. Acentos sao normalizados (NFKD sem diacriticos) e
tudo que nao for letra/numero vira `-`.
"""

from __future__ import annotations

import unicodedata

MAX_SLUG_LENGTH = 60


def slugify(text: str, max_len: int | None = MAX_SLUG_LENGTH) -> str:
    """Slug em minusculas a partir de `text`; vazio se nao houver letra/numero.

    `max_len` trunca o resultado no limite (sem `-` sobrando); `None` nao trunca
    (a renomeacao prefere recusar um nome longo a corta-lo silenciosamente).
    """
    decomposed = unicodedata.normalize("NFKD", str(text))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    value = "".join(ch.lower() if ch.isalnum() else "-" for ch in plain)
    slug = "-".join(token for token in value.split("-") if token)
    if max_len is not None and len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug
