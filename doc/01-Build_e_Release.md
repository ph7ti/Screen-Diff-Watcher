# Screen Diff Watcher — Build e Release (instaladores Windows/Linux)

[English](01-Build_and_Release.md) · **Português (Brasil)**

Guia operacional para **humano ou IA**: como atualizar as informações de build e gerar os
instaladores depois de novos incrementos de código.

Decisões de arquitetura: [`00-Documento_de_Arquitetura_e_Especificação.md`](00-Documento_de_Arquitetura_e_Especificação.md) §3.8 (PyInstaller, build por plataforma).
Resumo de uso no [`README.pt-BR.md`](../README.pt-BR.md) (seção "Build dos instaladores").

Todos os comandos assumem o **repositório como diretório atual** (`cd ScreenDiffWatcher`).

---

## 1. Visão geral do pipeline

```
código-fonte ──PyInstaller(spec)──► dist/screen-watch/  (onedir: screen-watch, screen-watch-gui)
                                         │
                       scripts/build_release.py  ──►  dist/installers/
                                         │               ├─ build-info.json
   Windows: ISCC (Inno Setup)  ─────────┘               ├─ screen-diff-watcher_<v>_windows_x64_setup.exe
   Linux:   dpkg-deb           ─────────────────────────└─ screen-watch_<v>_amd64.deb
```

- `scripts/build_release.py` roda **no SO alvo** e recusa cross-build.
- `packaging/screen-watch.spec`: 1 `Analysis` + 2 `EXE` (console e windowless) que compartilham
  `PYZ`/`COLLECT`; empacota `screen_watch/assets/icons/`.
- `dist/installers/build-info.json` é **gerado a cada build** (versão, SO, Python, capacidades
  `pynput`/`cv2`). Não editar à mão.
- Os caminhos `build/` e `dist/` são ignorados pelo Git.

---

## 2. Pré-requisitos

| SO | Requisitos |
|---|---|
| Windows | Python 3.13, `pip install -e ".[dev,build,input]"` e **Inno Setup 6** (`choco install innosetup -y`, ou instalar o app; o script também procura em `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`) |
| Linux (Debian/Ubuntu) | Python 3.13, `pip install -e ".[dev,build,input]"` e `dpkg-deb` (`sudo apt-get install -y dpkg-dev`) |

Notas:
- `build = ["pyinstaller>=6.11.1"]` — **obrigatório**: o PyInstaller só suporta Python 3.13 a partir
  do 6.11.1.
- `simpleaudio` **não** entra no bundle de propósito (sem wheel confiável no 3.13).
- O `.deb` é para `amd64` e exige X11; build em `ubuntu-22.04` para pegar glibc mais antiga.

---

## 3. Rotina após novos incrementos de código

1. **Qualidade**: `ruff check .` e `python -m pytest -q -m "not integration"`.
2. **Subir a versão** (ver §4) — obrigatório antes de publicar.
3. **Atualizar o pin do Tesseract** apenas quando quiser adotar um release novo (ver §5).
4. **Regenerar o ícone** apenas se os PNGs de `src/screen_watch/assets/icons/` mudarem (ver §6).
5. **Buildar** (ver §7) e rodar o **smoke** (ver §9).
6. **Commit/tag** e deixar o CI publicar (ver §8). Nunca commitar segredos nem `dist/`/`build/`.

---

## 4. Atualizar a versão (fonte única)

A versão vive **apenas** em `src/screen_watch/__init__.py`; o `pyproject.toml` é dinâmico
(`[tool.setuptools.dynamic] version = {attr = "screen_watch.__version__"}`). Não crie/edite
`version` no `pyproject`.

```python
# src/screen_watch/__init__.py
__version__ = "0.3.0"   # <- unica fonte de verdade
```

Confirme que metadados e atributo batem:

```powershell
python -c "import importlib.metadata as m, screen_watch; print(m.version('screen-watch'), screen_watch.__version__)"
```

O `scripts/build_release.py` revalida isso e aborta se `project.dynamic` não apontar para
`screen_watch.__version__`. O CI (`.github/workflows/release.yml`) **falha** se a tag (sem `v`) for
diferente de `__version__`.

---

## 5. Atualizar o pin do Tesseract (Windows)

Arquivo: `packaging/windows/tesseract.json` — versão, URL e **SHA256** do instalador UB-Mannheim e
do `por.traineddata`. A instalação no cliente usa exatamente esse pin (**nunca "latest" em tempo de
instalação**).

1. Descubra o release e o asset:

```powershell
$rel = Invoke-RestMethod -Headers @{ "User-Agent"="kilo" } `
  "https://api.github.com/repos/UB-Mannheim/tesseract/releases/latest"
$rel.tag_name
($rel.assets | Where-Object { $_.name -like '*w64-setup*.exe' }).browser_download_url
```

2. Baixe e calcule o SHA256 do instalador:

```powershell
Invoke-WebRequest "<URL_DO_INSTALADOR>" -OutFile "$env:TEMP\tesseract-setup.exe"
(Get-FileHash "$env:TEMP\tesseract-setup.exe" -Algorithm SHA256).Hash
```

3. Faça o mesmo para o `por.traineddata`, fixando um **commit** do `tessdata_fast`:

```powershell
$commit = (Invoke-RestMethod -Headers @{ "User-Agent"="kilo" } `
  "https://api.github.com/repos/tesseract-ocr/tessdata_fast/commits/main").sha
$commit
Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$commit/por.traineddata" `
  -OutFile "$env:TEMP\por.traineddata"
(Get-FileHash "$env:TEMP\por.traineddata" -Algorithm SHA256).Hash
```

4. Edite `packaging/windows/tesseract.json`:

```json
{
  "version": "5.4.0.20240606",
  "installer": {
    "url": "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe",
    "sha256": "<sha256 minusculo do .exe>"
  },
  "traineddata": {
    "lang": "por",
    "url": "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/<commit>/por.traineddata",
    "sha256": "<sha256 minusculo do por.traineddata>",
    "dest": "tessdata/por.traineddata"
  }
}
```

O `packaging/windows/install-tesseract.ps1` (chamado pelo instalador, elevado) verifica o SHA256,
instala com `/VERYSILENT` e valida `tesseract --list-langs` (precisa conter `eng` e `por`). Não defina
`TESSDATA_PREFIX`: o `compare/advanced.py` não passa `--tessdata-dir` e usa o `tessdata` do binário.
No Linux o Tesseract vem do `Depends:` do `.deb` — nada a pinar.

---

## 6. Regenerar o ícone (só se os PNGs mudarem)

```powershell
python packaging/make_ico.py        # gera packaging/icons/ScreenDiffWatcher.ico
```

O `.ico` é usado pelo PyInstaller (ícone dos EXEs) e pelo `SetupIconFile` do Inno Setup. Ele é
versionado; rode só quando os PNGs de origem mudarem.

---

## 7. Gerar o instalador

**Windows** (PowerShell, gera os EXEs + `setup.exe`):

```powershell
python scripts/build_release.py --windows
```

**Linux** (gera os binários + `.deb`):

```bash
python scripts/build_release.py --linux
```

Cada execução:
1. valida a versão (§4) e os pré-requisitos (`ISCC.exe` / `dpkg-deb`);
2. roda o PyInstaller com `packaging/screen-watch.spec` (`--clean --noconfirm`) → `dist/screen-watch/`;
3. escreve `dist/installers/build-info.json`;
4. monta o instalador em `dist/installers/`.

Rodar em SO errado (ex.: `--linux` no Windows) aborta com mensagem clara (sem cross-build).

---

## 8. Publicar (CI)

Repositório: `https://github.com/ph7ti/Screen-Diff-Watcher`.

- **PR / `workflow_dispatch` do CI**: o job `package` do `ci.yml` monta os instaladores **sem
  publicar** (artefatos `installer-Windows` / `installer-Linux`) — pega quebra de empacotamento.
- **Release de teste**: `workflow_dispatch` em `release.yml` com `version` = valor de `__version__`
  (ex.: `0.3.0-rc1`) gera **só artefatos de workflow**, sem release.
- **Release final**: crie a tag e faça push:

```powershell
git tag v0.3.0          # tag sem 'v' deve ser IGUAL a __version__
git push origin v0.3.0
```

O `release.yml` builda Windows (`windows-latest` + `choco install innosetup -y`) e Linux
(`ubuntu-22.04`), gera `SHA256SUMS.txt` e cria o GitHub Release com `gh release create`.

---

## 9. Validação (definição de pronto)

Smoke rápido do bundle (sem instalar):

```powershell
dist\screen-watch\screen-watch.exe --help
dist\screen-watch\screen-watch.exe features --json
```

```bash
dist/screen-watch/screen-watch --help
xvfb-run -a dist/screen-watch/screen-watch features --json
```

O `features --json` deve mostrar `frozen: true`, `input.available`, `tray.pystray`, backend de som,
monitores e o Tesseract (caminho + idiomas). Compare com o ambiente de dev (`python -m screen_watch
features`) — a diferença esperada é `frozen`.

Validação manual (não automatizada):

- **Windows, máquina limpa sem Tesseract**: instalar → Tesseract baixado/instalado; `features` mostra
  `eng`+`por`; GUI abre; atalhos criados; opção "iniciar com o Windows" funciona; desinstalar remove
  o app e **preserva** Tesseract e app-data.
- **Linux, container limpo**: `apt install ./screen-watch_0.3.0_amd64.deb` resolve as dependências
  (Tesseract junto); `screen-watch features --json` ok; `xvfb-run -a screen-diff-watcher-gui` abre.
- Ícone da janela/tray no bundle, `StartupWMClass` do `.desktop`, tamanho do pacote e aviso do
  SmartScreen (`.exe` sem assinatura — fora de escopo assinar).

---

## 10. Ajustar as dependências do `.deb` (`Depends`)

A lista atual está em `packaging/linux/control.template`. Para conferir/aparar, rode no container
alvo e veja as libs do binário:

```bash
ldd dist/screen-watch/screen-watch-gui | grep -E 'not found' || true
ldd dist/screen-watch/screen-watch-gui | awk '{print $1}' | sort -u
```

Mantenha no `Depends` só o que o Ubuntu 22.04/24.04 não traz por padrão (Qt6/X11/Tesseract/
`xdg-utils`). O som usa player externo: `Recommends: pulseaudio-utils, alsa-utils`.

---

## 11. Troubleshooting

| Sintoma | Causa / correção |
|---|---|
| `ISCC.exe (Inno Setup) nao encontrado` | Instale `choco install innosetup -y` ou adicione o Inno ao `PATH` (o script também busca em `Program Files (x86)\Inno Setup 6`). |
| `dpkg-deb nao encontrado` | `sudo apt-get install -y dpkg-dev`. |
| PyInstaller falha no Python 3.13 | Atualize o extra `build` (`pyinstaller>=6.11.1`). |
| "funciona no build, falha no pacote" (Linux) | O `/usr/bin` usa **wrapper `exec`**, não symlink: o PyInstaller resolve `_internal` pelo caminho real. Não trocar por symlink. |
| CI: guarda de versão falha | A tag (sem `v`) precisa ser idêntica a `screen_watch.__version__`. |
| OCR falha no cliente | Tesseract ausente/idioma faltando; `features --json` mostra caminho e `--list-langs`. Nunca usar `TESSDATA_PREFIX`. |
| Acentuação no console do Windows | O CLI reconfigura `stdout`/`stderr` para UTF-8 em `_configure_std_streams()`. |

---

## 12. Checklist rápido (novo incremento)

- [ ] `ruff check .` e `python -m pytest -q -m "not integration"` verdes.
- [ ] `__version__` atualizado (e nenhum `version` manual no `pyproject`).
- [ ] (Se mudou) pin do Tesseract atualizado em `packaging/windows/tesseract.json`.
- [ ] (Se mudou) `python packaging/make_ico.py`.
- [ ] `python scripts/build_release.py --windows|--linux` e smoke do `features --json`.
- [ ] PR verde (job `package`) antes do merge.
- [ ] Tag `vX.Y.Z` = `__version__` para publicar o release.
