# Idiomas (i18n)
[English](Languages.md) · **Português (Brasil)**

A **GUI é traduzível** por catálogos **JSON dentro do pacote** (`screen_watch/i18n/*.json`); o
**CLI e o `logging` de diagnóstico permanecem em inglês fixo** (o painel de log da GUI também, porque
é log). Idioma inicial: **`pt-BR`** (fallback) e **`en-US`**.

## Descoberta dinâmica

Qualquer arquivo `screen_watch/i18n/xx-YY.json` válido passa a aparecer no seletor da janela e em
`--language`, sem mudar código. O `_meta` precisa trazer:

- `code` — igual ao nome do arquivo (ex.: `pt-BR`);
- `name` — nome nativo exibido no combo (ex.: "Português (Brasil)");
- `fallback` — `"pt-BR"`.

As chaves do novo idioma devem cobrir o mesmo conjunto do `pt-BR` (o `en-US` serve de referência);
`validate-i18n` acusa chaves faltando/sobrando.

## Escolha do idioma (precedência)

```
--language TAG  >  state.json["language"]  >  ui.language do YAML  >  auto (locale do SO)
```

- `auto` usa `QLocale.system()` com fallback para `locale`/`LANG`.
- Casamento: exato (`pt-BR`) → mesmo idioma (`pt` → `pt-BR`) → fallback `pt-BR`.
- A troca vale **no próximo start** (sem retradução ao vivo). O seletor da janela grava
  `state.json["language"]`.
- `ui.language` desconhecido gera aviso e volta para `auto` (não é erro).

No YAML v2:

```yaml
ui:
  language: auto        # auto | pt-BR | en-US | qualquer tag descoberta
```

```powershell
python -m screen_watch --language en-US gui        # abre a GUI em inglês
python -m screen_watch validate-i18n               # valida chaves, error.*, help.* e _meta
```

## Adicionar um idioma

1. Copie `src/screen_watch/i18n/en-US.json` para `src/screen_watch/i18n/<nova-tag>.json`.
2. Ajuste o `_meta` (`code` = nome do arquivo, `name` nativo, `fallback: "pt-BR"`).
3. Traduza os valores (não as chaves). Mantenha `error.*` e `help.*` completos.
4. Rode `python -m screen_watch validate-i18n` até ficar `ok`.
5. O idioma aparece sozinho no seletor e em `--language` (a descoberta é em runtime).

## Erros traduzidos por código

Erros da aplicação têm **códigos estáveis** (`errors.py::ERROR_CODES`, ex.:
`runtime.tesseract_missing`): a GUI exibe a mensagem traduzida (`error.<código>`) pelo catálogo; o
CLI/log mostram o texto em inglês. `str(exc)` é sempre inglês; `render_error(exc)` faz a tradução.

## Ajuda no hover

Cada controle da janela tem um tooltip de **propósito + exemplo** após ~2 s de hover, com o texto
vindo das chaves `help.*` do catálogo.

## CI

O CI roda `validate-i18n` além de `ruff` e `pytest`, então um catálogo incompleto quebra o build.

## Relacionados

- [Configuração](Configuracao.md) — `ui.language` e precedência
- [GUI e tray](GUI-e-Tray.md) — o seletor de idioma
- [doc/00 §12.6](../doc/00-Documento_de_Arquitetura_e_Especificação.md) — decisões de design
