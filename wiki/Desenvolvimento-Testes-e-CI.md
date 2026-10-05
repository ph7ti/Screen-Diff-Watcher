# Desenvolvimento, testes e CI
[English](Development-Tests-and-CI.md) · **Português (Brasil)**

## Preparar o ambiente

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"     # núcleo + ruff/pytest
```

Extras que afetam o desenvolvimento: `input` (pynput — ações/hotkeys), `build` (pyinstaller),
`sound`/`ocr-preproc`/`logging` (opcionais), `dev` (testes).

## Qualidade e testes

```powershell
ruff check .
python -m pytest                  # unitários (padrão)
python -m pytest -q -m "not integration"
```

Testes que dependem de `imagehash`/`pytesseract` são pulados automaticamente se a dependência não
estiver instalada. O CI não instala `simpleaudio`, não usa Tesseract (OCR é mockado) e não importa Qt
na coleta.

### Integração (opt-in, fora do CI)

```powershell
$env:TEST_REAL_CAPTURE="1"; python -m pytest -m integration
$env:TEST_REAL_TELEGRAM="1"; $env:TELEGRAM_BOT_TOKEN="..."; `
  $env:TELEGRAM_TEST_CHAT_ID="..."; python -m pytest -m integration
$env:TEST_REAL_WEBHOOK_URL="https://..."; python -m pytest -m integration
$env:TEST_REAL_HTTP_URL="https://..."; python -m pytest -m integration
$env:TEST_REAL_AUDIO="1"; $env:TEST_REAL_AUDIO_FILE="C:\sons\alerta.mp3"; python -m pytest -m integration
```

`TEST_REAL_CAPTURE` captura de verdade do monitor primário; `TEST_REAL_TELEGRAM` envia uma foto
sintética e falha se o HTTP não for 2xx; `TEST_REAL_WEBHOOK_URL`/`TEST_REAL_HTTP_URL` enviam um payload
JSON sintético para a URL informada; `TEST_REAL_AUDIO` reproduz o `TEST_REAL_AUDIO_FILE`
(WAV/MP3/OGG/FLAC) pelo caminho de som do CLI e falha se a reprodução não funcionar.

## Escada de validação (diagnóstico de captura/DPI)

Em regressões de captura/DPI, use os scripts na ordem — **não comece pela GUI**:

1. `python scripts/step1_absolute_roi.py` — ROI absoluta hardcoded; valida captura e mede Hz real.
2. `python scripts/step2_anchored_roi.py` — ancoragem via `pywinctl` (Modelo B); mova a janela e
   confirme que a ROI segue.
3. `python scripts/step3_selection_overlay.py` — overlay PyQt6; seleção por mouse e dump do JSON.
4. `python scripts/probe_dpi.py` — matriz de DPI (mss × Qt × escala).

## CI (GitHub Actions)

`.github/workflows/ci.yml` roda, em **`ubuntu-latest` e `windows-latest`** × **Python 3.11, 3.12 e 3.13**:

- `ruff check .`
- `python -m screen_watch validate-i18n`
- `pytest -q -m "not integration" --cov=screen_watch --cov-report=term-missing`

A cobertura é **informativa** por enquanto (sem nota mínima). O artefato `coverage-xml` é enviado
pela célula Linux/3.13.

Em pull requests, o job `package` também monta os instaladores **sem publicar** (pega quebra de
empacotamento).

`.github/workflows/release.yml` builda os instaladores a partir de uma tag `v*.*.*` (Windows
`windows-latest` + Inno Setup; Linux em `ubuntu-latest` dentro de um container `ubuntu:22.04`,
mantendo a glibc mais antiga) e publica o GitHub Release com `SHA256SUMS.txt`. Ele **falha** se a tag
(sem `v`) for diferente de `screen_watch.__version__`. Com `workflow_dispatch` e o input `version`,
gera apenas os artefatos do workflow (sem release).

## Publicação da wiki (runbook manual)

A GitHub Wiki é um **repositório git separado**; a pasta `wiki/` do repo é apenas um espelho e o CI
não a publica. Para publicar alterações de páginas:

```powershell
git clone https://github.com/ph7ti/Screen-Diff-Watcher.wiki.git
# copie o conteúdo das páginas para o clone preservando o estilo de links remoto:
# links internos da wiki sem o sufixo .md; links para doc/README apontam para
# https://github.com/ph7ti/Screen-Diff-Watcher/blob/main/...
git -C Screen-Diff-Watcher.wiki add -A
git -C Screen-Diff-Watcher.wiki commit -m "Sync wiki with vX.Y.Z"
git -C Screen-Diff-Watcher.wiki push origin master
```

A publicação automática (workflow com o segredo `WIKI_PUSH_TOKEN`) fica adiada até o segredo existir.

## Build local dos instaladores

Rode no SO alvo (o script recusa cross-build):

```powershell
python -m pip install -e ".[dev,build,input]"
python scripts/build_release.py --windows   # no Windows (requer Inno Setup 6 / ISCC.exe)
python scripts/build_release.py --linux     # no Linux (requer dpkg-deb)
```

Artefatos em `dist/installers/` (+ `build-info.json`). Guia completo (versão, pin do Tesseract,
ícone, validação, troubleshooting): [`doc/01-Build_e_Release.md`](../doc/01-Build_e_Release.md).

## Regras do repositório

- **Versão**: fonte única em `src/screen_watch/__init__.py::__version__`; nunca edite `version` no
  `pyproject.toml` (é dinâmico). A tag é `vX.Y.Z` (sem `v`, igual ao `__version__`).
- **Nunca commite** `dist/`, `build/` ou segredos.
- `ruff` e `pytest` verdes antes de qualquer PR; `validate-i18n` incluído no CI.
- Ações/tokens só por variáveis de ambiente (`TELEGRAM_BOT_TOKEN` etc.).

## Relacionados

- [Instalação](Instalacao.md) — preparar o ambiente de uso
- [Uso (CLI)](Uso-CLI.md) — `features`, `probe-dpi`, `validate-config`, `validate-i18n`
- [doc/00](../doc/00-Documento_de_Arquitetura_e_Especificação.md) — decisões de design
