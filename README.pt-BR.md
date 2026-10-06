# Screen Diff Watcher

[English](README.md) · **Português (Brasil)**

<p align="center">
  <img src="src/screen_watch/assets/icons/ScreenDiffWatcher.png" width="60%">
</p>

Vigia uma **região retangular (ROI) de uma janela** e avisa quando ela muda — som, popup,
Telegram, webhook/HTTP POST, syslog ou log — para você não precisar ficar olhando para a tela.

Roda no **Windows e no Linux**, capturando apenas pixels (não toca no aplicativo vigiado).

[Wiki — guia de uso](wiki/Home-pt-BR.md) ·
[Arquitetura e especificação](doc/00-Documento_de_Arquitetura_e_Especificação.md) ·
[Build e release](doc/01-Build_e_Release.md) ·
[Changelog](CHANGELOG.md)

## O que ele faz

- **Monitora uma ROI de uma janela**: você desenha o retângulo e o app captura só aquela área a
  cada N segundos. A ROI é ancorada à janela — se ela se mover, a ROI acompanha (Modelo B, doc §3.3).
- **Detecta mudanças visuais** em três modos: `light` (cor média), `default` (hash perceptivo) e
  `advanced` (OCR + diff de texto; exige Tesseract), incluindo a **verificação de texto** que dispara
  só quando um texto **aparece/desaparece** na ROI (`text_watch`, somente no `advanced`).
- **Alerta** por som, popup, Telegram, log JSONL, **webhook**, **HTTP POST** e **syslog**, com severidade
  mínima e cooldown por canal. O som toca **WAV/MP3/M4A/AAC/OGG/FLAC/WMA** conforme o contexto (GUI
  via Qt Multimedia; CLI via `miniaudio`), e o seletor da GUI pré-visualiza o arquivo e **grava** no
  alerta `sound` do perfil ativo no `config.yaml` (atômico + `.bak`; config v1 precisa ser migrada
  antes). O som default é um **`alert.mp3` empacotado** que vai junto com o app; um `file` relativo é
  resolvido como `app-data/sounds/` → `assets/sounds/` empacotado → CWD.
- **Máscaras** para ignorar áreas que mudam sozinhas (relógio, spinner, cursor). A GUI desenha e
  remove em um overlay sobre a janela alvo (**Editar máscaras…**, bloqueado com o monitoramento) e
  grava no JSON da seleção (`overrides.masks` vence `masks`).
- **Observabilidade na GUI**: **preview** do baseline + último frame, **histórico de alertas** sobre
  `logs/alerts.jsonl` (filtros de data/severidade/modo, print de evidência best-effort) e
  **calibração ao vivo** (score × limite, export CSV).
- **Evidências**: prints do baseline e de cada mudança — opt-in.
- **Ações pseudo-humanas** (clique, teclas, texto) quando armadas — ensaio por padrão e auditoria
  em `logs/actions.jsonl`.
- **GUI com tray + CLI completa**, com **perfis**, agendador (suspende ações fora do horário) e
  atalhos globais.
- **Nome e conferência da seleção**: dê um **nome** à seleção (o arquivo é renomeado para o slug do
  nome, sem sobrescrever outro), use **Ver local** para destacar a ROI na tela por ~2 s **sem alterar
  os pixels dela** (funciona com o monitoramento rodando) e **duplo clique** na lista para reeditar a
  região — **Enter** inicia/para.
- **Multi-idioma**: GUI em pt-BR/en-US; o CLI e o log técnico são em inglês fixo.

## O que ele não faz

- **Não grava tela nem vídeo** — só observa uma região e compara.
- **Não é OCR de documentos**: o OCR serve apenas para perceber mudança de texto.
- **Não captura janelas ocluídas**: a captura lê **pixels da tela**; se outra janela cobrir a ROI,
  o conteúdo sobreposto entra na comparação. É limitação das APIs de captura, não um bug (doc §7.5).
- **Não funciona em Wayland**: no Linux, rode em X11 — o app detecta e avisa.
- **Não tem instalador para macOS nem para ARM** (o build é Windows x64 e Linux amd64).
- **Não assina digitalmente os instaladores** — o SmartScreen vai avisar (assinatura fora de escopo).
- **Não contorna DRM/anti-cheat** nem elevação (UAC).
- **Não clica sozinho por padrão**: as ações exigem o extra `input` e precisam ser armadas.

## Como funciona (resumo)

1. Você escolhe a **janela-alvo** e **desenha a ROI** (`select` no overlay, ou coordenadas no
   `select-manual`).
2. A cada `poll_interval_s`, o app captura a ROI. O **primeiro frame é o baseline** — não é mudança.
3. Cada tick: captura → **máscaras** → **comparação** com o baseline no modo escolhido.
4. Mudança confirmada → a **cadeia de alertas** dispara (severidade + cooldown) e, se as ações
   estiverem armadas, a sequência configurada roda.
5. Config e estado ficam em **app-data**: `config.yaml`, `selections/`, `state.json` e `logs/`.

```text
janela-alvo ──► ROI ──► captura ──► máscara ──► comparação (light/default/advanced)
                                                      │ mudou?
                                                      ▼
                                    alertas (som/popup/Telegram/ntfy/SMTP/MQTT/log + webhook/HTTP POST/syslog)
                                    + ações (se armadas)
```

## Recursos de alerta

Quando uma mudança é confirmada, a cadeia de alertas dispara os canais habilitados no perfil, cada
um com seu `severity_min` e `cooldown_s`:

| Canal (`type`) | O que faz | Detalhes |
|---|---|---|
| `sound` | toca um som local (WAV/MP3/M4A/AAC/OGG/FLAC…) | [wiki/Alertas.md](wiki/Alertas.md) |
| `popup` | notificação local | [wiki/Alertas.md](wiki/Alertas.md) |
| `telegram` | mensagem + imagem da ROI via bot | **[Configuração do Telegram — passo a passo](wiki/Configuracao-Telegram.md)** |
| `log` | uma linha JSON por alerta (`logs/alerts.jsonl`) | [wiki/Alertas.md](wiki/Alertas.md) |
| `webhook` | POST/PUT/PATCH JSON para URL de webhook (Teams **Workflows**, Slack, Discord, Mattermost) | [wiki/Alertas.md](wiki/Alertas.md) |
| `http_post` | POST JSON para host/IP + porta (ou URL completa) | [wiki/Alertas.md](wiki/Alertas.md) |
| `syslog` | mensagem syslog informacional (`udp`/`tcp`) — sem imagem | [wiki/Alertas.md](wiki/Alertas.md) |
| `ntfy` | push para um tópico no ntfy.sh (ou servidor próprio); imagem da ROI opcional | [wiki/Alertas.md](wiki/Alertas.md) |
| `smtp` | e-mail via STARTTLS/SSL; anexo da ROI opcional | [wiki/Alertas.md](wiki/Alertas.md) |
| `mqtt` | publica JSON em um tópico MQTT (exige o extra `mqtt`) — sem imagem | [wiki/Alertas.md](wiki/Alertas.md) |

Os alertas são configurados por perfil no `config.yaml` (lista `alerts:`), cada um com um `id` estável
opcional. Segredos nunca vão no YAML: o token do Telegram, o token do ntfy, o login SMTP e as
credenciais MQTT vêm todos de variáveis de ambiente. O canal MQTT exige o extra opcional `mqtt`
(`pip install -e ".[mqtt]"`); ntfy e SMTP usam o núcleo (`httpx`/stdlib). Teste um canal com
`test-alert --list`/`--only ID` ou o botão **Testar alerta…** da janela. O mapa de canais é
extensível por `type`.

## Que problemas ele resolve

- Acompanhar um **painel/indicador** (ERP, dashboard, tela de status) sem ficar de olho nele.
- Saber que **algo mudou** (fila, pedido, senha de atendimento, saldo, estado de job) mesmo quando
  o sistema não oferece notificação.
- Ser avisado quando um **texto** muda — modo `advanced`.
- Vigiar um **processo longo** (build, importação, robô) e reagir quando ele termina ou falha.
- Responder a uma mudança com uma **ação simples** (clique/atalho/texto) — opt-in, tipo um mini-RPA.

## Plataformas atendidas

| Plataforma | Como rodar | Status |
|---|---|---|
| **Windows (x64)** | instalador `.exe` (Inno Setup) ou código-fonte | suportado; o instalador baixa o Tesseract automaticamente (opcional) |
| **Linux Debian/Ubuntu (amd64, X11)** | pacote `.deb` ou código-fonte | suportado; Wayland não é suportado na captura |
| **macOS** | somente código-fonte | **não validado** e sem instalador (fora do escopo do build) |

Detalhes por plataforma: [wiki/Instalacao.md](wiki/Instalacao.md).

## Como utilizar (passo a passo)

Se você instalou pelos binários, o comando é `screen-watch`; com o código-fonte, use
`python -m screen_watch`.

```powershell
python -m screen_watch list-windows                           # 1. escolha a janela (veja o handle)
python -m screen_watch select --handle 12345 --name painel    # 2. desenhe a ROI no overlay
python -m screen_watch test-alert --selection painel          # 3. confira o alerta
python -m screen_watch run --selection painel                 # 4. monitore
python -m screen_watch gui                                    # ...ou use a GUI com tray
```

O caminho mais curto é a GUI: **Novo Target (overlay)** → desenhe a ROI → **Iniciar**. A seleção
fica salva em app-data (`selections/painel.json`) e pode ser reusada por `run`.

**Referência rápida dos comandos** (detalhes em [wiki/Uso-CLI.md](wiki/Uso-CLI.md)):

```powershell
python -m screen_watch init-config            # cria o config.yaml v2 em app-data
python -m screen_watch validate-config --selections
python -m screen_watch list-windows           # handle/título/rect
python -m screen_watch probe-dpi              # matriz de DPI (mss físico × Qt lógico)
python -m screen_watch select --handle 12345 --name painel    # overlay: arrastar na tela
python -m screen_watch select-manual --handle 12345 --roi 120 340 400 80 --name painel
python -m screen_watch list-selections
python -m screen_watch list-selections --json                 # inventário para scripts
python -m screen_watch edit-selection painel --mode light --poll-interval-s 1.5
python -m screen_watch rename-selection painel "Painel ERP"
python -m screen_watch remove-selection painel                # limpa o last_selection se preciso
python -m screen_watch migrate-config --dry-run               # conv. YAML v1 -> v2
python -m screen_watch test-alert --selection painel          # alerta sintético
python -m screen_watch test-alert --selection painel --list   # id/tipo/estado/destino
python -m screen_watch test-alert --selection painel --only ID # um canal (modo texto)
python -m screen_watch test-evidence --selection painel       # prints de exemplo
python -m screen_watch test-action --selection painel         # ensaio das ações (--armed executa)
python -m screen_watch list-actions --selection painel
python -m screen_watch record-actions --selection painel --out snippet.yaml
python -m screen_watch compare-modes --selection painel --delay 5   # calibração
python -m screen_watch show-paths
python -m screen_watch run --selection painel                 # monitorar
python -m screen_watch gui                                    # GUI + tray
python -m screen_watch features                               # diagnóstico do ambiente
python -m screen_watch validate-i18n                          # valida os catálogos de idioma
```

As flags globais `--language TAG` (idioma da GUI) e `--verbose` vêm **antes** do subcomando, por
exemplo: `python -m screen_watch --language en-US gui`.

- Guia completo do CLI: [wiki/Uso-CLI.md](wiki/Uso-CLI.md)
- Janela e tray: [wiki/GUI-e-Tray.md](wiki/GUI-e-Tray.md)
- Configuração (perfis, overrides, migração): [wiki/Configuracao.md](wiki/Configuracao.md)

## Pré-requisitos

**Para usar os instaladores (Windows/Linux):**

- Nenhum para os modos `light`/`default`.
- **Tesseract** no sistema (traineddata `por` + `eng`) para o modo `advanced` — no Windows o
  instalador baixa sob demanda; no `.deb` ele já vem como dependência.
- **Telegram** (opcional): token via variável de ambiente `TELEGRAM_BOT_TOKEN` (nunca no YAML) —
  passo a passo em [wiki/Configuracao-Telegram.md](wiki/Configuracao-Telegram.md).
- **Ações e hotkeys globais** (opcional): extra `input` (`pynput`).
- **Alertas MQTT** (opcional, em instalações do código-fonte): extra `mqtt` (`paho-mqtt`) — não entra
  nos instaladores. ntfy e SMTP não precisam de extra (`httpx`/stdlib).
- **Som** (opcional, mas incluído nos instaladores): o CLI/`run` usa **`miniaudio`**
  (WAV/MP3/OGG/FLAC); a GUI usa **Qt Multimedia** (ganha M4A/AAC/WMA no Windows/macOS). No Linux a
  GUI depende dos plugins do GStreamer, e o caminho legado usa `winsound` (WAV) ou um player externo
  (`paplay`/`aplay`/`ffplay`).
- **Linux**: sessão **X11** — Wayland não é suportado.

**Para rodar do código-fonte:** Python **3.11+** e os extras conforme o uso:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"     # núcleo + testes (ruff/pytest)
python -m pip install -e ".[input]"   # opcional: ações/hotkeys (pynput)
python -m pip install -e ".[mqtt]"    # opcional: canal de alerta MQTT (paho-mqtt)
python -m pip install -e ".[sound]"   # opcional: som via simpleaudio
```

## Instalação

### Opção 1 — binários (recomendado)

Baixe em [GitHub Releases](https://github.com/ph7ti/Screen-Diff-Watcher/releases):

- **Windows**: `screen-diff-watcher_<versão>_windows_x64_setup.exe` (Inno Setup, per-machine,
  requer admin). Cria atalhos no menu Iniciar e, opcionalmente, na Área de Trabalho e o início
  automático com o Windows. O SmartScreen vai avisar (`.exe` sem assinatura): use
  "Mais informações" → "Executar assim mesmo"; o antivírus pode fazer o mesmo.
- **Linux (Debian/Ubuntu amd64)**: `screen-watch_<versão>_amd64.deb`
  (`sudo apt install ./screen-watch_<versão>_amd64.deb`). O pacote declara `tesseract-ocr` +
  `tesseract-ocr-por` e as libs Qt6/X11.

### Opção 2 — código-fonte

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m screen_watch --help
```

Instalação detalhada (Tesseract automático, autostart no Linux, desinstalação, app-data,
diagnóstico `features`): [wiki/Instalacao.md](wiki/Instalacao.md).

## Build dos instaladores

Os instaladores são gerados **no SO alvo** (sem cross-build) por `scripts/build_release.py`.
Guia completo: [`doc/01-Build_e_Release.md`](doc/01-Build_e_Release.md).

```powershell
python -m pip install -e ".[dev,build,input]"
python scripts/build_release.py --windows   # no Windows (requer Inno Setup 6 / ISCC.exe)
python scripts/build_release.py --linux     # no Linux (requer dpkg-deb)
```

O script lê a versão de `screen_watch.__version__` (fonte única; o `pyproject.toml` é dinâmico),
roda o PyInstaller e grava os artefatos + `build-info.json` em `dist/installers/`. Para publicar,
crie a tag `vX.Y.Z` (igual à `__version__`) e faça push: o workflow
`.github/workflows/release.yml` builda os dois instaladores, gera `SHA256SUMS.txt` e cria o
GitHub Release. `workflow_dispatch` gera só os artefatos (sem release).

## Estado atual

**Implementado:** captura e ancoragem (Modelo B), modos de comparação (`light`/`default`/`advanced`)
com pipeline e curto-circuito (`advanced` com gate de phash, bypassado pelo `text_watch`), alertas
(som/popup/Telegram/**ntfy/SMTP/MQTT**/log + webhook/HTTP POST/syslog) com cooldown/rearm,
**soneca/silenciar e escalação até o ciente**, e teste de envio, **som
selecionável (MP3/M4A/OGG/FLAC…)** com **default empacotado `alert.mp3`** e o filtro **`text_watch`**
(aparece/desaparece), **nome da seleção** (renomeia o arquivo pelo slug), o **ciclo de vida completo
das seleções no CLI** (incluindo o fluxo headless abaixo), **Ver local** (realce da ROI
sem tocar nos pixels), **reedição da região por duplo clique** (Enter inicia/para), a **janela em
grid 2×2** e **múltiplas ROIs simultâneas** (conjunto por checkbox, `ui.max_sessions`, status/tray
agregados), evidências, ações pseudo-humanas (com editor na GUI e gravador), agendador, perfis, CLI
completa, GUI + tray com i18n (pt-BR/en-US), empacotamento (Inno Setup e `.deb`) e CI/release por tag.

**Validação manual pendente:** GUI/tray/overlay em 100/125/150% (doc §5.1, §9.5) e detalhes do
bundle em máquina limpa (ícone, `StartupWMClass`, tamanho do pacote, aviso do SmartScreen) —
checklist em [`doc/01`](doc/01-Build_e_Release.md) §9.

**Fluxo headless:** a seleção inteira funciona sem overlay — `list-windows` → `select-manual` →
`edit-selection` (modo/ROI/máscaras/overrides) → `validate-config --selections` → `run --selection` —
e o ciclo de vida tem `list-selections [--json]`, `rename-selection` e `remove-selection` (detalhes na
[wiki de CLI](wiki/Uso-CLI.md)).

## Limitações conhecidas (resumo)

- **Wayland** não captura; **janela ocluída** compara o que estiver na frente; **ARM** e **macOS**
  não fazem parte do build.
- **Tray no GNOME** pode não aparecer sem extensão de tray (a janela continua funcional).
- **Som no Linux** depende dos plugins do GStreamer (GUI) ou de um player externo (legado); no CLI, o
  `miniaudio` cobre WAV/MP3/OGG/FLAC — **M4A/AAC** precisa de um player como `ffplay`, senão o alerta
  cai no `beep`. Nunca quebra.
- Janela minimizada ou ausente emite `target_unavailable` e o loop segue tentando (nunca quebra).

Lista completa, escala de tela (DPI) e notas de robustez:
[wiki/DPI-e-Limitacoes.md](wiki/DPI-e-Limitacoes.md).

## Desenvolvimento

```powershell
ruff check .
python -m pytest -q -m "not integration"
```

Testes de integração são opt-in (`TEST_REAL_CAPTURE`, `TEST_REAL_TELEGRAM`,
`TEST_REAL_WEBHOOK_URL`, `TEST_REAL_HTTP_URL`) — detalhes,
escada de scripts e CI em [wiki/Desenvolvimento-Testes-e-CI.md](wiki/Desenvolvimento-Testes-e-CI.md).

## Documentação

| Onde | O que tem |
|---|---|
| [**Wiki**](wiki/Home-pt-BR.md) | detalhes de uso e recursos: CLI, GUI, config, ações, alertas, evidências, idiomas, DPI, build |
| [`doc/00-Documento_de_Arquitetura_e_Especificação.md`](doc/00-Documento_de_Arquitetura_e_Especificação.md) | arquitetura e especificação — **fonte única de verdade do design** |
| [`doc/01-Build_e_Release.md`](doc/01-Build_e_Release.md) | pipeline de build e release dos instaladores |
| [`doc/releases/`](doc/releases/v0.9.1.pt-BR.md) | notas de release por versão (arquivo de detalhe) |
| [`CHANGELOG.md`](CHANGELOG.md) | mudanças por versão (semântico) |
| [`README.md`](README.md) | este guia em inglês |

> **Nota de design**: o `doc/00` decide o design; a Wiki descreve uso e recursos. Não registre uma
> decisão de design aqui sem que ela esteja (ou deva estar) no `doc/00`.
