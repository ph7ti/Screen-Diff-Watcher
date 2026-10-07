# Instalação
[English](Installation.md) · **Português (Brasil)**

O Screen Diff Watcher roda em **Windows (x64)** e **Linux Debian/Ubuntu (amd64, X11)** e, a partir
da v0.11.0, no **macOS (arm64)** como `.app` sem assinatura. Há duas formas de instalar: pelos
**binários** (instaladores) ou pelo **código-fonte**.

| Plataforma | Formato | Observações |
|---|---|---|
| Windows x64 | `screen-diff-watcher_<versão>_windows_x64_setup.exe` (Inno Setup) | requer admin (per-machine); oferece o download opcional do Tesseract (pergunta antes; silencioso só com `/TESSERACT=yes`) |
| Linux Debian/Ubuntu amd64 | `screen-watch_<versão>_amd64.deb` | requer X11; Wayland não captura |
| macOS arm64 | `screen-diff-watcher_<versão>_macos_arm64.zip` | `.app` sem assinatura (sem notarização); **ainda não validado em hardware**; exige permissões de Gravação de Tela + Acessibilidade |

## Opção 1 — binários

Os instaladores são publicados no
[GitHub Releases](https://github.com/ph7ti/Screen-Diff-Watcher/releases).

### Windows

1. Baixe e execute `screen-diff-watcher_<versão>_windows_x64_setup.exe`.
2. O instalador é **per-machine** (instala em `Program Files`) e **requer admin** — por causa do
   Tesseract instalado por máquina. Cria atalho no Menu Iniciar e, opcionalmente (desmarcados),
   atalho na Área de Trabalho e **início automático com o Windows**.
3. **SmartScreen**: como o `.exe` não é assinado, o Windows vai avisar — use "Mais informações" →
   "Executar assim mesmo". O antivírus pode fazer o mesmo. Assinatura de código está fora do escopo.
4. **Tesseract opcional**: o instalador pergunta antes de baixar (Sim/Não). Se o Tesseract não
   estiver instalado e você aceitar, ele baixa o release fixado do UB-Mannheim, **verifica o
   SHA256**, instala em silêncio e garante o `por.traineddata` (o pacote já traz `eng`). Precisa de
   rede e admin; se você recusar, o download/verificação falhar ou estiver offline, ele **avisa e
   continua** — os modos `light`/`default` funcionam e o `advanced` acusa a falta com mensagem clara.
   Instalação silenciosa (`/SILENT` ou `/VERYSILENT`) pula salvo `/TESSERACT=yes`.
   - **Offline**: instale o Tesseract manualmente
     (https://github.com/UB-Mannheim/tesseract/wiki) com os traineddata `por` e `eng`; o instalador
     detecta o binário e não baixa nada.
5. Desinstalar remove só o app e **preserva** o Tesseract e os dados do usuário.

### Linux (Debian/Ubuntu amd64)

```bash
sudo apt install ./screen-watch_<versão>_amd64.deb
```

- Requer **X11** (Wayland não é suportado na captura).
- O `.deb` declara `tesseract-ocr` + `tesseract-ocr-por` e as libs Qt6/X11 como dependências;
  `pulseaudio-utils`/`alsa-utils` vêm como `Recommends` (players do caminho legado).
- Comandos instalados: `screen-watch` (CLI) e `screen-diff-watcher-gui` (GUI, também no atalho de
  menu).
- **Autostart**: o `.deb` não configura. Para iniciar com a sessão, crie
  `~/.config/autostart/screen-diff-watcher.desktop`:

  ```ini
  [Desktop Entry]
  Type=Application
  Exec=screen-diff-watcher-gui
  X-GNOME-Autostart-enabled=true
  ```

- Desinstalar preserva o Tesseract e o app-data.

## Opção 2 — código-fonte

Requer **Python 3.11+**.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"     # núcleo + ferramentas de teste (ruff/pytest)
```

Extras opcionais:

| Extra | Para quê |
|---|---|
| `pip install -e ".[input]"` | ações pseudo-humanas e hotkeys globais (`pynput`) |
| `pip install -e ".[sound]"` | som via `simpleaudio` (sem wheel confiável no Python 3.13; opcional) |
| `pip install -e ".[ocr-preproc]"` | experimentos de pré-processamento de OCR (`opencv-python`) |
| `pip install -e ".[mqtt]"` | canal de alerta MQTT (`paho-mqtt`; não entra nos instaladores) |
| `pip install -e ".[macosx]"` | popups no **macOS** (`pyobjus`; exigido pelo backend do plyer) |
| `pip install -e ".[build]"` | gerar instaladores (`pyinstaller`) |

Os canais **ntfy** e **SMTP** não precisam de extra (usam o `httpx` do núcleo e o `smtplib` da
stdlib); só o **MQTT** exige o extra `mqtt`. As credenciais de todos os canais (Telegram, ntfy,
SMTP, MQTT) vêm de **variáveis de ambiente**, nunca do YAML.

Depois:

```powershell
python -m screen_watch --help
python -m screen_watch init-config    # cria o config.yaml v2 em app-data
```

## Onde ficam config, seleções e logs (app-data)

Tudo fica em `%APPDATA%\screen_watch` no Windows (`config.yaml`, `selections/`, `state.json`,
`logs/`). Para apontar para outro diretório, defina `SCREEN_WATCH_HOME`. Veja os caminhos efetivos:

```powershell
python -m screen_watch show-paths
```

**Python da Microsoft Store (MSIX)**: o Windows redireciona `%APPDATA%` para dentro do pacote, e o
arquivo fica invisível para o Explorer/editor. Nesse caso o app passa a usar o caminho real
(`...\AppData\Local\Packages\<pacote>\LocalCache\Roaming\screen_watch`).

## Diagnóstico: `features`

```powershell
screen-watch features           # versão/origem, app-data, nº de seleções, Tesseract, entrada, som, tray, monitores
screen-watch features --json    # saída JSON (usada no smoke do CI)
```

Degrada sem display (não quebra) e informa se o binário é `bundle` ou `source`. É o primeiro comando
para diagnosticar um ambiente (ex.: Tesseract ausente, `pynput` indisponível).

## Limitações dos instaladores

- **Wayland**: a captura via `mss` não funciona; rode em X11. O app avisa e encerra o `run`.
- **Tray no GNOME**: pode não aparecer sem extensão de tray; a janela continua funcional.
- **Som no Linux**: o CLI/`run` usa o `miniaudio` empacotado (WAV/MP3/OGG/FLAC); a GUI depende dos
  plugins do GStreamer, e **M4A/AAC** no CLI precisa de um player externo (`ffplay`); senão cai no
  `beep`.
- **Arquitetura**: apenas `amd64`/`x86_64`. ARM fora de escopo.
