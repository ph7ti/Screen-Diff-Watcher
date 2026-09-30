# Screen Diff Watcher — Documento de Arquitetura e Especificação
[English](00-Architecture_and_Specification.md) · **Português (Brasil)**

> **Propósito deste documento**: servir como **fonte única de verdade do design** para que outra IA
> (ou desenvolvedor) continue o projeto sem precisar reconstruir decisões, e registrar **o que está
> implementado** (referência: v0.3.0). Toda decisão aqui registrada foi tomada deliberadamente; onde
> houver alternativas, elas estão listadas como "rejeitadas" com o motivo.
>
> **Regra de manutenção**: não substitua uma decisão registrada por uma alternativa "mais moderna"
> sem justificativa explícita. Se o código divergir do documento, **atualize o documento registrando
> o motivo da mudança e o histórico** — nunca altere o documento silenciosamente para esconder a
> divergência.

Guias relacionados:

- Uso e recursos (wiki): [`../wiki/Home-pt-BR.md`](../wiki/Home-pt-BR.md)
- Build e release: [`01-Build_e_Release.md`](01-Build_e_Release.md)
- Visão geral no README: [`../README.pt-BR.md`](../README.pt-BR.md)

---

## 1. Visão geral

### 1.1 O que o projeto é

Um aplicativo desktop **multiplataforma em Python** que:

1. Permite ao usuário **selecionar uma janela** e, dentro dela, uma **região retangular (ROI)**.
2. **Monitora essa ROI periodicamente** (intervalo configurável, mínimo 1 s).
3. Detecta **mudanças visuais** conforme um modo de comparação (Leve / Default / Avançado).
4. **Emite alertas** quando a mudança é confirmada: som local, popup local, log JSONL e/ou webhook
   remoto (Telegram inicialmente).
5. Opcionalmente, **executa ações pseudo-humanas** (clique/teclas/texto) quando **armadas** — por
   padrão em ensaio (dry-run), com auditoria em `logs/actions.jsonl` (§11.4).
6. Oferece **GUI com tray** (PyQt6 + pystray) e **CLI completa**, com perfis, agendador e i18n
   (pt-BR/en-US na GUI; CLI e log em inglês fixo).

**Plataformas alvo do build**: Windows (x64) e Linux Debian/Ubuntu (amd64, X11). macOS tem caminhos
de código (áudio/caminhos), mas **não é alvo de build nem de validação** (§15).

### 1.2 O que o projeto NÃO é

- Não é um gravador de tela.
- Não é um OCR de documentos (o OCR serve apenas para detectar mudança de texto).
- Não captura de janelas ocluídas (limitação fundamental da API de captura — ver §7.5).
- Não contorna DRM, anti-cheat ou janelas protegidas.
- Não depende de nenhum serviço em nuvem proprietário (o único canal remoto opcional é o Telegram).
- Não suporta **Wayland** (§3.2) nem **ARM**; não assina digitalmente os instaladores.
- Não é um RPA genérico: as ações são um subsistema opt-in e deliberado (§11.4).

### 1.3 Caso de uso canônico

Monitorar um painel/indicador dentro de um aplicativo desktop (ex.: painel de estoque de um ERP) e
alertar o usuário quando aquele painel sofrer alteração visual, sem exigir que o usuário fique
olhando para a tela. Extensão natural: reagir à mudança com uma ação simples (ex.: clicar em
"Atualizar") quando isso for explicitamente armado.

### 1.4 Estado da implementação (v0.3.0)

Implementado e coberto por testes: fronteira de plataforma, captura/ancoragem (Modelo B), os três
modos de comparação, pipeline com curto-circuito, alertas (som/popup/Telegram/log) com cooldown e
re-arm, evidências, ações pseudo-humanas (arming, ensaio, limites, auditoria, editor na GUI,
gravador), agendador (suspende apenas ações), perfis + migração v1→v2, seleção JSON v2 com
overrides, CLI (`init-config` … `validate-i18n`), GUI + tray com i18n e ajuda no hover, empacotamento
(PyInstaller; Inno Setup no Windows; `.deb` no Linux) e pipeline de release por tag.

Pendências de **validação manual** (não automatizável no CI):

- GUI/tray/overlay em escalas 100/125/150% (§5.1, §9).
- Bundle em máquina limpa: ícone da janela/tray, `StartupWMClass` do `.desktop`, tamanho do pacote,
  aviso do SmartScreen (assinatura fora de escopo). Checklist em [`doc/01`](01-Build_e_Release.md) §9.

---

## 2. Princípios arquiteturais não negociáveis

Estes princípios guiam todas as decisões abaixo. Se um detalhe de implementação entrar em conflito
com algum deles, o princípio vence.

1. **Captura e comparação são desacopladas por um contrato de dados (`Frame`).** A comparação nunca
   acessa a tela, nunca conhece janela, nunca dorme.
2. **Toda dependência de SO fica atrás de uma fronteira explícita.** Nada de `if sys.platform == ...`
   espalhado pelo código de negócio.
3. **DPI awareness é fixado no início do processo, antes de qualquer backend.** Ver §5.1.
4. **O loop de captura é cancelável imediatamente** e sua cadência é estável sob carga.
5. **Primeiro frame é baseline, não mudança.** O estado inicial da comparação é explícito, nunca
   implícito.
6. **Falhas de captura não quebram o loop.** Elas emitem evento e o próximo tick tenta de novo.
7. **Configuração é declarativa e persistida.** Nada de estado de sessão hardcoded.
8. **Ações são opt-in, desarmadas por padrão e auditadas.** O estado de arming vive apenas em
   memória (§11.4); nunca no YAML.
9. **Erros têm código estável (`AppError.code`)** e mensagem inglesa; a GUI traduz por código
   (`render_error`), o CLI/log mostram inglês (§12.7).
10. **A GUI é traduzível (catálogos JSON no pacote); CLI e logging são em inglês fixo** (§12.6).

---

## 3. Decisões de arquitetura (ADR resumido)

Cada item abaixo é uma decisão fechada. Formato: **Decisão → Motivo → Alternativas rejeitadas**.

### 3.1 Linguagem e runtime

- **Decisão**: Python 3.11+.
- **Motivo**: `Protocol`, `dataclass(frozen=True)`, `tomllib`/`typing` modernos, `asyncio` maduro;
  ampla disponibilidade de bindings para captura, GUI e OCR. O PyInstaller só passou a suportar
  Python 3.13 a partir do 6.11.1 (pin no extra `build`).
- **Rejeitado**: Python 3.9/3.10 (faltam recursos de tipagem usados no design); Rust/Go (custo de
  integração com `mss`, `pywinctl`, Tesseract não compensa para o escopo).

### 3.2 Captura de tela

- **Decisão**: **`mss`** como único backend no protótipo. `pyautogui` não é usado.
- **Motivo**: `mss` é mais rápido, retorna `numpy`-compatível direto, tem API estável entre
  plataformas, e mantém uma instância reutilizável.
- **Detalhes da implementação**:
  - O backend vive atrás do contrato de `capture/backend.py`; `MssCaptureBackend` cria a instância
    **uma vez** e a reutiliza (nunca por tick). `mss` **não é thread-safe**: o `MonitorLoop` cria o
    backend **dentro da própria thread** e o fecha no `finally` do worker.
  - `MssCaptureBackend.bounds()` devolve o retângulo do desktop virtual (inclui coordenadas
    negativas), usado pelo recorte da ROI (§7.6).
  - A conversão BGRA→RGB é feita no backend (`np.asarray(...)[:, :, [2, 1, 0]]`).
- **Alternativas rejeitadas**:
  - `pyautogui` — mais lento, API de screenshot limitada; só valeria como fallback que não temos
    necessidade de usar.
  - `dxcam` / `d3dshot` — específicos de Windows com GPU; quebram a promessa multiplataforma.
  - `Pillow.ImageGrab` — cobre menos casos que `mss` e não traz vantagem.
- **Limitação conhecida e aceita**: `mss` **não funciona em Wayland**. O projeto detecta
  (`XDG_SESSION_TYPE=wayland`) e encerra o comando `run` com aviso claro (`is_wayland()` em
  `platform/dpi.py`). **Não implementar backend Wayland no protótipo** — está fora de escopo.

### 3.3 Localização e ancoragem da janela

- **Decisão**: **`pywinctl`**, ancoragem por **Modelo B (relativo à origem da janela)**.
- **Motivo**: `pywinctl` é mantido e cross-platform. O Modelo B segue a janela quando ela se move,
  sem exigir acesso à client area (que é plumbing por SO).
- **Detalhes da implementação**: o wrapper `platform/window.py` expõe `WindowInfo`
  (`handle`, `title`, `rect`, `is_minimized`, `exists`), `find_window_by_handle`, `list_windows`,
  `activate_window` e `is_window_active`. O `resolver` usa o conversor identidade por padrão
  (`identity_converter`) — ver §5.1.
- **Alternativas rejeitadas**:
  - `pygetwindow` — abandonado, só Windows/macOS com lacunas.
  - Modelo A (coordenadas absolutas congeladas) — quebra quando a janela se move.
  - Modelo C (relativo à client area, excluindo chrome) — mais robusto semanticamente, mas exige
    plumbing por SO desnecessário para o escopo.

### 3.4 Comparação

- **Decisão**: três estratégias plugáveis:
  1. **Leve** — `MeanColorStrategy` (cor média RGB + distância euclidiana).
  2. **Default** — `PerceptualHashStrategy` (`imagehash.phash`, `hash_size=8`).
  3. **Avançado** — `OCRTextDiffStrategy` (`pytesseract` + `difflib.SequenceMatcher`).
- **Motivo**: cada modo cobre um trade-off custo/sensibilidade; a estratégia barata veta as caras
  quando compostas no pipeline (§10.5).
- **Detalhes da implementação**: cada modo mapeia para **um estágio** (`MODE_STAGES`), com o
  pipeline mantendo o curto-circuito para composições futuras. `advanced` roda o OCR **como
  detector**, sem gate de phash/mean (decisão registrada em §10.5).
- **Alternativas rejeitadas**:
  - Apenas phash — não distingue mudança semântica de ruído estrutural em alguns casos.
  - Apenas OCR — caro demais por tick, inviável em 1 Hz.
  - SSIM — mais caro que phash sem ganho claro para o caso de uso.

### 3.5 Agendamento

- **Decisão**: `threading.Thread` + `threading.Event.wait(timeout)` como loop principal.
- **Motivo**: cancelamento imediato, sem dependência extra, simples de raciocinar. O `wait` subtrai
  o tempo de trabalho do intervalo, garantindo cadência estável.
- **Alternativas rejeitadas**:
  - `asyncio` — overhead desnecessário; `mss`/`pywinctl` são síncronos e bloqueantes.
  - `APScheduler` — sobre-engenharia para um único loop.

### 3.6 Alertas

- **Decisão**: cadeia de notificadores (**Chain of Responsibility**), cada um com `enabled`,
  `severity_min` e `cooldown_s`. Implementados no protótipo:
  - **Som local** — atrás da fronteira `platform/audio.py` (`winsound` no Windows;
    `paplay`/`aplay`/`ffplay` no Linux; `afplay` no macOS). O extra `simpleaudio` continua opcional.
  - **Popup local** (`plyer.notification`).
  - **Webhook Telegram Bot** (`httpx`, `sendPhoto`/`sendMessage`, timeout de 5 s; token via
    variável de ambiente).
  - **Log JSONL** (`app-data/logs/alerts.jsonl`).
- **Motivo**: Telegram é gratuito, confiável, permite anexar imagem do ROI no alerta (essencial
  para validar falsos positivos), e não exige setup de servidor. O log JSONL dá auditoria local; o
  popup/som cobrem o uso offline.
- **Alternativas rejeitadas**:
  - `ntfy.sh` — igualmente válido, mas Telegram permite imagem + texto em uma única mensagem com
    menos atrito.
  - Pushover — pago.
  - FCM — complexidade de setup desproporcional.
  - `simpleaudio` como única via de som — sem wheel confiável para Python 3.13; virou extra
    opcional (`pip install -e ".[sound]"`), com fallback por player externo.

### 3.7 GUI e overlay de seleção

- **Decisão**: **PyQt6** para GUI e overlay.
- **Motivo**: multi-monitor nativo (`QGuiApplication.screens()`), transparência real, alta DPI
  resolvida corretamente, `CompositionMode_Clear` disponível para o "buraco" da seleção.
- **Detalhes da implementação**:
  - **Layout**: a janela segue o mockup `UI.txt` (coluna **Monitoramento** com
    Iniciar/Parar/Re-armar/Minimizar, Modo/Perfil/Idioma e arming; grupo **Seleções**; linha de
    Novo Target/Remover/Recarregar/Abrir YAML/Prints + evidências; grupo **Ações da sessão** com
    checklist e botões; Status/Último e **Log** no rodapé num `QSplitter`). Edição de passos com
    Subir/Descer/drag&drop/Editar/Duplicar.
  - **Tray**: `pystray` (`gui/tray.py`) com mostrar/ocultar, iniciar/parar, armar/desarmar, perfil
    e sair. A GUI recebe eventos por **fila** consumida por `QTimer` (`gui/controller.py`); callbacks
    de tray/hotkey nunca chamam Qt de dentro da thread do listener.
  - **Idiomas**: a GUI passa pelo i18n (catálogo JSON no pacote); CLI/log ficam em inglês (§12.6).
  - **Ajuda**: hover de 2 s mostra propósito + exemplo de cada controle (`gui/help.py` +
    `gui/hover_help.py`).
  - **Arming pela janela**: botões `Armar ações`/`Desarmar`/`Armar por…` ligados ao mesmo caminho do
    tray/hotkey (§11.4).
- **Alternativas rejeitadas**:
  - `tkinter` — transparência e multi-monitor exigem gambiarras; `overrideredirect` quebra em
    alguns WMs Linux.
  - Nenhuma GUI (só config manual) — o caso de uso exige seleção visual.

### 3.8 Empacotamento

- **Decisão**: **PyInstaller**, build por plataforma, com instaladores nativos:
  **Inno Setup** (Windows) e **`.deb`** (Linux).
- **Motivo**: mais maduro, ampla documentação, funciona nos SOs alvo; instaladores nativos dão
  atalhos, desinstalação e dependências declaradas.
- **Detalhes da implementação**: bundle **onedir** com dois executáveis (`screen-watch` console e
  `screen-watch-gui` windowless) que compartilham `PYZ`/`COLLECT`; o script
  `scripts/build_release.py` roda **no SO alvo** (sem cross-build), lê a versão de
  `screen_watch.__version__` e grava `dist/installers/`. Guia completo: [`doc/01`](01-Build_e_Release.md).
- **Alternativas rejeitadas**:
  - Nuitka — mais rápido, mas build mais frágil e tempo de compilação maior.
  - Briefcase — promissor, mas ecossistema menor para o stack escolhido.

### 3.9 Configuração

- **Decisão**: **YAML** (`PyYAML`) para config do usuário; **JSON** para o dump de seleção de ROI.
- **Motivo**: YAML é legível para edição manual; JSON é gerado pela GUI e não precisa de comentários.
- **Detalhes da implementação**: o YAML é **global e versionado** (`version` 1 ou 2). O v2 traz
  `profiles` (defaults/alertas/ações), `ui`, `schedule` e `evidence`; os alvos viram arquivos de
  seleção JSON em app-data (§12). Segredos nunca no YAML (§12.1).
- **Alternativas rejeitadas**: TOML (bom, mas `tomllib` é read-only em versões antigas); INI
  (limitado para estruturas aninhadas).

---

## 4. Estrutura de diretórios (implementada)

```
ScreenDiffWatcher/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE
├── doc/
│   ├── 00-Documento_de_Arquitetura_e_Especificação.md   # este documento
│   └── 01-Build_e_Release.md
├── wiki/                          # páginas do GitHub Wiki (uso e recursos)
├── src/
│   └── screen_watch/
│       ├── __init__.py            # __version__ (fonte única)
│       ├── __main__.py            # entry point: python -m screen_watch (CLI + parsers)
│       ├── app.py                 # orquestração: pipeline + cadeia + sessão + evidências
│       ├── errors.py              # AppError/ConfigError + ERROR_CODES + render_error
│       ├── gui_main.py            # entry point do executável windowless (GUI)
│       ├── resources.py           # recursos do pacote (ícones etc.)
│       │
│       ├── platform/              # fronteira de SO (nada de sys.platform fora daqui)
│       │   ├── dpi.py             # set_dpi_awareness, is_wayland
│       │   ├── window.py          # wrapper pywinctl; activate_window/is_window_active
│       │   ├── paths.py           # app-data, state.json (atômico), MSIX
│       │   ├── display.py         # escala por monitor (matriz mss × Qt)
│       │   ├── tesseract.py       # localização do binário (PATH + diretórios comuns)
│       │   ├── audio.py           # winsound / paplay / aplay / ffplay / afplay
│       │   ├── input.py           # pynput (lazy), interpolação/jitter (humanização)
│       │   └── shell.py           # open_path (os.startfile / open / xdg-open)
│       │
│       ├── capture/
│       │   ├── frame.py           # dataclass Frame
│       │   ├── backend.py         # Protocol ScreenCaptureBackend (bounds/capture/close)
│       │   ├── mss_backend.py     # implementação mss (BGRA->RGB, instância por thread)
│       │   ├── resolver.py        # janela + roi_relative -> ROI absoluta (Modelo B)
│       │   ├── geometry.py        # intersect_rect (recorte contra o desktop virtual)
│       │   └── mask.py            # apply_mask
│       │
│       ├── compare/
│       │   ├── protocol.py        # CompareStrategy, ComparisonResult, compute_severity
│       │   ├── light.py           # MeanColorStrategy
│       │   ├── default.py         # PerceptualHashStrategy
│       │   ├── advanced.py        # OCRTextDiffStrategy
│       │   └── pipeline.py        # MODE_STAGES + ComparePipeline (curto-circuito)
│       │
│       ├── alerts/
│       │   ├── protocol.py        # Notifier
│       │   ├── sound.py           # SoundNotifier (fronteira platform/audio.py)
│       │   ├── popup.py           # PopupNotifier (plyer)
│       │   ├── telegram.py        # TelegramNotifier (httpx; token por env)
│       │   ├── log.py             # JsonlNotifier (logs/alerts.jsonl)
│       │   └── chain.py           # AlertChain + DispatchOutcome
│       │
│       ├── actions/               # ações pseudo-humanas (opt-in)
│       │   ├── protocol.py        # ActionSpec/ActionStep (puros)
│       │   ├── plan.py            # parse/validação (click exige activate; text_* exige advanced)
│       │   ├── dispatch.py        # ActionDispatcher (ensaio/armado/agendador/limites)
│       │   ├── runner.py          # execução síncrona + foco + humanização + limites
│       │   ├── arming.py          # ArmingController (disarmed/armed/timed; só memória)
│       │   ├── audit.py           # ActionAudit (logs/actions.jsonl)
│       │   ├── selection.py       # subconjunto por sessão (state.json)
│       │   ├── summary.py         # descrição legível das ações
│       │   ├── once.py            # execução avulsa (test-action / botão da GUI)
│       │   └── recorder.py        # gravador de cliques/teclas -> snippet YAML
│       │
│       ├── evidence/
│       │   └── recorder.py        # EvidenceRecorder (prints; retenção; pasta efetiva)
│       │
│       ├── scheduler/
│       │   ├── loop.py            # MonitorLoop (threading + Event; eventos deduplicados)
│       │   └── schedule.py        # is_open/gate (função pura com relógio injetável)
│       │
│       ├── config/
│       │   ├── schema.py          # dataclasses (AppConfig/ProfileOptions/TargetConfig/…)
│       │   └── loader.py          # YAML <-> dataclasses; defaults; migração v1->v2
│       │
│       ├── persistence/
│       │   └── selection.py       # JSON de seleção v1/v2 + build_target (overrides)
│       │
│       ├── i18n/
│       │   ├── __init__.py        # catálogo JSON, resolução de idioma, tr()
│       │   ├── pt-BR.json         # fallback
│       │   └── en-US.json
│       │
│       ├── gui/
│       │   ├── main_window.py     # janela (layout do UI.txt)
│       │   ├── controller.py      # fila de eventos + QTimer
│       │   ├── tray.py            # pystray
│       │   ├── overlay.py         # SelectionOverlay (uma janela por monitor)
│       │   ├── overlay_geometry.py# conversões lógico<->físico (puro, sem Qt)
│       │   ├── countdown.py       # contagem de 3 s (overlay sem foco)
│       │   ├── locator.py         # localizador de posição do mouse
│       │   ├── action_editor.py   # editor de ações da seleção
│       │   ├── hotkeys.py         # hotkeys globais (pynput, lazy)
│       │   ├── help.py            # textos de ajuda (puro)
│       │   ├── hover_help.py      # tooltip de 2 s
│       │   ├── labels.py          # rótulos do catálogo
│       │   └── qt_app.py          # ensure_app (QApplication única)
│       │
│       └── assets/icons/          # ícones (usados no bundle)
│
├── tests/                         # unitários (padrão) + marcador integration (opt-in)
├── scripts/
│   ├── step1_absolute_roi.py      # escada de validação (captura)
│   ├── step2_anchored_roi.py      # escada de validação (ancoragem)
│   ├── step3_selection_overlay.py # escada de validação (overlay)
│   ├── probe_dpi.py               # matriz de DPI
│   └── build_release.py           # build dos instaladores (SO alvo)
├── packaging/
│   ├── screen-watch.spec          # PyInstaller (2 EXEs, onedir)
│   ├── make_ico.py                # gera o .ico a partir dos PNGs
│   ├── windows/                   # .iss (Inno Setup), install-tesseract.ps1, tesseract.json
│   └── linux/                     # control.template, launcher.template, .desktop, postinst
└── .github/workflows/             # ci.yml (matriz) e release.yml (tag -> Release)
```

---

## 5. Fronteira de plataforma (`platform/`)

### 5.1 DPI awareness — obrigatório e primeiro

**Regra**: `set_dpi_awareness()` deve ser chamado **antes** de instanciar qualquer backend de
captura, qualquer janela Qt, qualquer chamada a `pywinctl`. Na implementação, é a primeira linha
executável do `main()` em `__main__.py` (e do entry point da GUI).

```python
# platform/dpi.py
import ctypes, sys, os

def set_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()

def is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
```

**Motivo**: sem isso, `pywinctl` (lógico) e `mss` (físico) discordam em escalas != 100%, e a ROI
"escorrega" de forma silenciosa. É o bug mais caro de depurar se descoberto tarde.

**Resultado medido na implementação**: com `set_dpi_awareness()` no início, `pywinctl` e `mss`
ficam no **mesmo espaço físico** (`pywinctl == GetWindowRect` em 15/15 janelas medidas). Por isso o
`resolver` usa o conversor identidade e **não há drift** no caminho de monitoramento, mesmo em
monitor com escala (ex.: 125%). O `device_pixel_ratio` do Qt (`1.25` no primário) é do espaço
lógico do Qt — usado apenas pelo overlay (§9.5).

Ao iniciar `run`, o app verifica cada monitor, marca os adequados (`OK`, 100%) e avisa se a janela
do target estiver num monitor com escala. `probe-dpi` e `scripts/probe_dpi.py` imprimem a matriz.

**Wayland**: se `is_wayland()` retornar `True`, o `run` exibe mensagem clara e encerra (código 2).
Não tentar capturar.

### 5.2 Wrapper de janela (`platform/window.py`)

Encapsular `pywinctl` para que o resto do código nunca importe `pywinctl` diretamente.

Interface implementada:

```python
@dataclass(frozen=True)
class WindowInfo:
    handle: int
    title: str
    rect: tuple[int, int, int, int]   # (x, y, w, h) em espaço lógico
    is_minimized: bool
    exists: bool

def find_window_by_handle(handle: int) -> WindowInfo | None: ...
def list_windows() -> list[WindowInfo]: ...
def activate_window(handle: int) -> bool: ...   # usado pelas ações (activate)
def is_window_active(handle: int) -> bool: ...  # confirmação de foco das ações
```

**Regras**:
- Sempre identificar por `handle`. Título é apenas `title_hint` para exibição, nunca chave de lookup
  (muda em browsers, IDEs).
- Se `is_minimized` for `True`, o `rect` é lixo — o resolver retorna `None` e o loop emite
  `target_unavailable` (§7.2).
- Na GUI, `list_windows()` filtra janelas que não são de aplicativos ativos (invisíveis, ocultas
  pelo DWM, tool windows, filhas/auxiliares, sem título) e exibe o **nome do aplicativo** no estilo
  Gerenciador de Tarefas (`FileDescription`/`ProductName`, com fallback para o nome do `.exe`).

### 5.3 Demais portas de SO (implementadas)

| Módulo | Responsabilidade |
|---|---|
| `platform/paths.py` | `app_home()`, `config_path()`, `selections_dir()`, `logs_dir()`, `state_path()`; override `SCREEN_WATCH_HOME`; detecção de Python MSIX/Store (usa o caminho real do pacote, visível fora dele); `load_state`/`update_state` (atômico, sem backup). |
| `platform/display.py` | escala por monitor: matriz `mss` (físico) × Qt (lógico) × DPR, usada pelo aviso de monitores e pelo `probe-dpi`. |
| `platform/tesseract.py` | `resolve_tesseract_cmd(configured)`: caminho explícito > `PATH` > diretórios comuns do SO (nunca caminho fixo de máquina). |
| `platform/audio.py` | única porta para tocar som: `winsound` no Windows (com `MessageBeep()` quando não há WAV), players externos no Linux/macOS (`paplay`/`aplay`/`ffplay`/`afplay`); `probe` para o `features`. |
| `platform/input.py` | `pynput` **importado sob demanda** (extra `input`); helpers puros `interpolate_points`/`make_rng` (testáveis sem display) para a humanização das ações. |
| `platform/shell.py` | `open_path()`: `os.startfile` no Windows, `open`/`xdg-open` nos demais; devolve `False` com `log.warning` quando não há associação (a GUI mostra "abra manualmente: <caminho>"). |

**Regra**: nenhum outro pacote pode importar `pynput`, `winsound`, `mss` ou `pywinctl` diretamente.

---

## 6. Contrato `Frame`

Definição canônica. Qualquer estratégia de comparação consome apenas isto.

```python
# capture/frame.py
from dataclasses import dataclass
import numpy as np

Rect = tuple[int, int, int, int]          # (x, y, w, h) em espaço físico

@dataclass(frozen=True)
class Frame:
    rgb: np.ndarray                     # (H, W, 3) uint8, ordem RGB
    timestamp: float                    # time.time()
    absolute_rect: Rect                 # espaço físico (para mss/debug)
    window_rect: Rect                   # espaço lógico (para debug e ref=window)
    window_handle: int
    sequence: int                       # incrementa a cada tick bem-sucedido
```

**Invariantes**:
- `rgb.shape[2] == 3` e `dtype == np.uint8` (o backend já entrega RGB; o loop normaliza e garante
  contiguidade).
- `rgb` já está mascarado (ver §8).
- `sequence` é monotônico por sessão de monitoramento; usado para descartar frames obsoletos se o
  consumidor atrasar.

---

## 7. Cadeia de captura — funcionamento detalhado

### 7.1 Fase de seleção (uma vez, por ROI)

Ordem exata dos passos:

1. Usuário escolhe a **janela-alvo** (`list_windows()` no CLI, ou a lista da GUI/"Novo Target").
2. Overlay é exibido (ver §9); alternativa sem overlay: `select-manual` com `--roi X Y W H`.
3. Usuário arrasta o retângulo (ou passa as coordenadas).
4. Ao soltar, o overlay emite um `QRect` em **coordenadas lógicas globais**.
5. **Imediatamente** consultar `window.getRect()` → `origin_at_selection`.
6. Converter rect lógico global → rect relativo à janela: `roi_relative = global_rect − origin_at_selection`.
7. Persistir JSON v2 (§7.3), com `app_name` (nome amigável do executável) e, quando houver,
   `overrides`.

**Regra crítica**: passo 5 deve acontecer antes de qualquer I/O, log, ou processamento. A janela
pode se mover entre o `mouseRelease` e a persistência.

### 7.2 Fase de tick (loop)

```
┌─────────────────────────────────────────────────────────┐
│ 1. Resolver janela (handle → WindowInfo)                │
│    - se não existe: emitir target_unavailable           │
│      (reason: not_found), aguardar                      │
│    - se minimizada: emitir target_unavailable           │
│      (reason: minimized), aguardar                      │
│    - se ROI fora dos limites: target_unavailable        │
│      (reason: roi_out_of_bounds), aguardar              │
├─────────────────────────────────────────────────────────┤
│ 2. Resolver ROI absoluta                                │
│    abs = roi_relative + window_rect.topLeft()           │
│    - conversão lógico→físico (identity por padrão)      │
├─────────────────────────────────────────────────────────┤
│ 3. Recortar contra o desktop virtual do backend         │
│    - sem recorte: capture_clipped (evento)              │
│    - 100% fora: roi_off_screen (evento) e pula o tick   │
├─────────────────────────────────────────────────────────┤
│ 4. Capturar (mss, instância criada na thread do loop)   │
├─────────────────────────────────────────────────────────┤
│ 5. Normalizar (shape (H, W, 3), uint8, contíguo)        │
├─────────────────────────────────────────────────────────┤
│ 6. Aplicar máscara                                      │
├─────────────────────────────────────────────────────────┤
│ 7. Emitir Frame para o sink (sequence++)                │
└─────────────────────────────────────────────────────────┘
```

**Contrato de `_tick`**: retorna `Frame | None`. `None` significa "nada a processar neste tick", e o
`sink` **não é chamado**.

**Eventos do loop** (emitidos por `on_event`, deduplicados por nome consecutivo):
`target_unavailable` (com `reason`), `capture_clipped` e `roi_off_screen` (§7.6).

### 7.3 Esquema do JSON de seleção

Versão atual (**v2**):

```json
{
  "version": 2,
  "window_handle": 123456,
  "window_title_hint": "ERP - Estoque",
  "app_name": "ERP",
  "origin_at_selection": [100, 200],
  "roi_relative": [120, 340, 400, 80],
  "mode": "advanced",
  "masks": [],
  "overrides": { "poll_interval_s": 1.5, "rearm": false }
}
```

Campos obrigatórios: `version`, `window_handle`, `origin_at_selection`, `roi_relative`.
`app_name`, `mode`, `masks` e `overrides` são opcionais com defaults. Seleções `version: 1`
continuam carregando sem `overrides`/`app_name` (§12.3). `window_title_hint` é apenas hint humano;
o lookup usa `window_handle`. `roi_relative` é a fonte de verdade para reconstruir a ROI a cada
tick.

### 7.4 Loop de captura — esqueleto implementado

```python
def _run(self) -> None:
    backend = self.backend or self.backend_factory()   # mss NÃO é thread-safe: criar na thread
    try:
        while not self._stop.is_set():
            t0 = time.perf_counter()
            frame = None
            try:
                frame = self._tick(backend)
            except Exception as exc:
                self._error(exc)                        # deduplica erros consecutivos idênticos
            if frame is not None:
                try:
                    self.sink(frame)                    # sink FORA do try de captura
                except Exception as exc:
                    self._error(exc)
            elapsed = time.perf_counter() - t0
            self._stop.wait(max(0.0, self.interval_s - elapsed))
    finally:
        backend.close()
```

**Decisões embutidas** (não alterar sem justificativa):
- `_stop.wait` é o único sleep. Nunca `time.sleep` dentro do loop.
- O tempo de trabalho é subtraído do intervalo.
- Exceções no `_tick` **e no sink** não quebram o loop (há `try` separado para cada um).
- O `sink` (comparação) está fora do `try` de captura — captura e comparação são responsabilidades
  separadas.
- O backend é criado e fechado **na thread do loop** (o `mss` não é thread-safe).
- Falhas consecutivas idênticas (mesma mensagem) são reportadas **uma vez**; reaparecem se mudarem.

### 7.5 Limitação de janela ocluída

`mss` captura **pixels da tela**, não a superfície da janela. Se outra janela cobrir a ROI, o frame
capturado conterá o conteúdo da janela sobreposta. **Isto não é um bug a ser corrigido** — é uma
limitação fundamental das APIs disponíveis. Documentado no README e na Wiki.

### 7.6 Robustez do loop (Etapa H)

- **Coordenadas negativas/fora da tela**: a ROI é recortada contra o desktop virtual
  (`mss.monitors[0]`, via `bounds()` + `intersect_rect`). Quando há recorte, o loop emite
  `capture_clipped`; quando a ROI cai 100% fora, emite `roi_off_screen` e **pula o tick** — sem
  quebrar o loop.
- **Falhas repetidas**: deduplicadas por mensagem (ex.: Tesseract ausente, token ausente).
- **Parada**: `stop()` sinaliza o evento e faz `join`; o `backend.close()` roda no `finally` do
  worker.
- **DPI**: `probe-dpi`/`scripts/probe_dpi.py` imprimem a matriz (mss físico × Qt lógico × escala).

---

## 8. Máscara

### 8.1 Formato

Lista de retângulos `[x, y, w, h]` **relativos à ROI** (não absolutos, não relativos à janela).
Sobrevivem a mover a janela. Vêm de `selection.masks` ou de `overrides.masks` (§12.3).

### 8.2 Aplicação

```python
def apply_mask(rgb: np.ndarray, masks: list[tuple[int, int, int, int]]) -> np.ndarray:
    out = rgb.copy()
    for (x, y, w, h) in masks:
        out[y:y+h, x:x+w] = 0
    return out
```

- Pinta de **preto (0,0,0)**.
- **Motivo**: phash e mean color tratam preto de forma neutra. Para OCR, preto é aceitável no
  protótipo (não gera texto fantasma).
- **Ponto de aplicação**: estágio 6 da cadeia de captura, **antes** do `Frame` ser emitido. As
  estratégias nunca veem a máscara.

### 8.3 Regiões tipicamente mascaradas

Cursor, spinner de loading, relógio, indicador de rede, qualquer coisa que pisque. O overlay ainda
não desenha máscaras (fora do MVP); edite `masks` no YAML/JSON de seleção.

---

## 9. Overlay de seleção (PyQt6)

### 9.1 Estratégia multi-monitor

**Decisão**: **uma janela por monitor**, não uma única janela cobrindo `virtualGeometry`.

**Motivo**: com DPI misto entre monitores, uma janela única força o Qt a mapear um único framebuffer
para escalas distintas — comportamento varia por plataforma. Janela por tela simplifica o cálculo
(cada uma opera no espaço do seu próprio `screen`).

```python
overlays = []
for screen in QGuiApplication.screens():
    ov = SelectionOverlay(screen)
    ov.setGeometry(screen.geometry())
    ov.show()
    overlays.append(ov)
```

Ao final do drag em um overlay, o rect é convertido para global somando `screen.geometry().topLeft()`.
As conversões puras vivem em `gui/overlay_geometry.py` (sem Qt, testável).

### 9.2 Flags e atributos

```python
self.setWindowFlags(
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
)
self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
self.setCursor(Qt.CursorShape.CrossCursor)
```

### 9.3 Desenho do "buraco" da seleção

Usar `QPainter.CompositionMode.CompositionMode_Clear` para remover a máscara escura na área
selecionada. **Não usar `setMask`** — é lento e problemático com DPI.

```python
painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
if self._origin and self._current:
    r = QRect(self._origin, self._current).normalized()
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.fillRect(r, Qt.GlobalColor.transparent)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.setPen(QPen(QColor("#0052d6"), 2))
    painter.drawRect(r)
```

### 9.4 High DPI no Qt

Antes de criar `QApplication`:

```python
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)
```

**Motivo**: evita que fatores como 1.25 sejam arredondados para 1.0, o que desalinha o overlay do
`mss`.

### 9.5 Conversão lógico → físico

O `QRect` do Qt está em espaço **lógico**. O `mss` consome espaço **físico**.

```python
def to_physical(rect: QRect, screen) -> tuple[int, int, int, int]:
    dpr = screen.devicePixelRatio()
    offset = screen.geometry().topLeft()
    x = int((rect.x() - offset.x()) * dpr + offset.x() * dpr)
    y = int((rect.y() - offset.y()) * dpr + offset.y() * dpr)
    return (x, y, int(rect.width() * dpr), int(rect.height() * dpr))
```

**Nota**: com `SetProcessDpiAwareness(2)` + `PassThrough`, em muitos casos `dpr == 1.0` e a conversão
é identidade. **Não assumir isso** — testar em 125%, 150%, 200%.

### 9.6 Validação pós-drag

Antes de persistir:

1. **Área mínima**: rejeitar retângulos com menos de 10×10 pixels lógicos (`MIN_ROI_SIDE = 10`).
2. **Dentro da janela-alvo**: converter para relativo e checar. Se extrapolar, **permitir mas logar
   warning** (alguns apps têm popups fora do rect principal).
3. **Origem capturada antes do I/O**: ver §7.1.

---

## 10. Comparação — interface e estratégias

### 10.1 Protocolo

```python
from typing import Protocol, Any
from dataclasses import dataclass

@dataclass(frozen=True)
class ComparisonResult:
    changed: bool
    score: float
    threshold: float
    strategy: str
    severity: int = 0                 # 0..3; calculado ao final do pipeline quando 0
    detail: dict[str, Any] | None = None

def compute_severity(score: float, threshold: float) -> int:
    """score/threshold >= 3.0 -> 3; >= 2.0 -> 2; >= 1.0 -> 1; senão 0."""

class CompareStrategy(Protocol):
    name: str
    def initialize(self, baseline: Frame) -> None: ...
    def compare(self, current: Frame) -> ComparisonResult: ...
```

**Regras**:
- `compare` é **função pura** sobre o `Frame` (pode ler estado interno, mas não I/O, não sono, não
  captura).
- `initialize` é chamado uma vez por sessão com o primeiro frame (baseline); também é re-chamado no
  re-arm (§11.3) e no re-baseline manual.
- `changed` sempre no mesmo sentido (True = mudança detectada). Para OCR, que naturalmente produz
  similaridade, normalizar antes de expor.
- `severity` (0..3) alimenta `severity_min` de alertas e ações; quando um estágio não a define, o
  pipeline calcula `compute_severity(score, threshold)` no veredito final.

### 10.2 Estratégia Leve — `MeanColorStrategy`

```python
class MeanColorStrategy:
    name = "light"
    def __init__(self, threshold: float = 12.0):
        self.threshold = threshold
        self._baseline_mean = None

    def initialize(self, baseline: Frame) -> None:
        self._baseline_mean = baseline.rgb.mean(axis=(0, 1))

    def compare(self, current: Frame) -> ComparisonResult:
        current_mean = current.rgb.mean(axis=(0, 1))
        delta = float(np.linalg.norm(current_mean - self._baseline_mean))
        return ComparisonResult(
            changed=delta > self.threshold,
            score=delta, threshold=self.threshold, strategy=self.name,
        )
```

- `threshold=12.0` é ponto de partida empírico (escala 0–255).
- Se houver compressão JPEG no pipeline, subir para 20–25.
- **Não usar** para conteúdo textual ou estrutural fino.

### 10.3 Estratégia Default — `PerceptualHashStrategy`

```python
class PerceptualHashStrategy:
    name = "default"
    def __init__(self, hash_size: int = 8, threshold: int = 6):
        self.hash_size = hash_size
        self.threshold = threshold
        self._baseline_hash = None

    def initialize(self, baseline: Frame) -> None:
        img = Image.fromarray(baseline.rgb)
        self._baseline_hash = imagehash.phash(img, hash_size=self.hash_size)

    def compare(self, current: Frame) -> ComparisonResult:
        img = Image.fromarray(current.rgb)
        h = imagehash.phash(img, hash_size=self.hash_size)
        dist = int(self._baseline_hash - h)
        return ComparisonResult(
            changed=dist > self.threshold,
            score=float(dist), threshold=float(self.threshold),
            strategy=self.name,
        )
```

- `hash_size=8` (64 bits) é o default.
- `threshold` típico: 4–10. Começar com 6.
- **ROIs pequenas (< 100×100)**: phash fica instável. Considerar `hash_size=6` ou mudar para Leve.
- **`hash_size=16`**: mais sensível, mais caro, mais nervoso com anti-aliasing. Não usar como
  default.

### 10.4 Estratégia Avançada — `OCRTextDiffStrategy`

```python
class OCRTextDiffStrategy:
    name = "advanced"
    def __init__(self, similarity_threshold: float = 0.92,
                 psm: int = 6, lang: str = "por+eng", upscale: int = 2,
                 tesseract_cmd: str | None = None):
        ...
        self._tesseract_cmd = resolve_tesseract_cmd(tesseract_cmd)  # platform/tesseract.py
        self._baseline_text = ""

    def _extract(self, rgb: np.ndarray) -> str:
        # sem binário: AppError(code="runtime.tesseract_missing") com mensagem clara
        # upscale > 1: vizinho-mais-próximo (np.repeat), sem depender de cv2
        # define/restaura pytesseract.pytesseract.tesseract_cmd (não vaza entre instâncias)
        ...

    def compare(self, current: Frame) -> ComparisonResult:
        ratio = difflib.SequenceMatcher(None, self._baseline_text, current_text).ratio()
        score = 1.0 - ratio          # normalizado: alto = mudou
        threshold = 1.0 - self.similarity_threshold
        return ComparisonResult(changed=score > threshold, score=score,
                                threshold=threshold, strategy=self.name,
                                detail={"baseline_text": ..., "current_text": ...})
```

- Defaults da implementação: `similarity_threshold=0.92`, `psm=6`, `lang="por+eng"`,
  `upscale=2`. O texto é normalizado (`" ".join(txt.split())`).
- O `upscale` usa **repetição de pixels** (`np.repeat`) — suficiente para ROI pequena e sem a
  dependência opcional de `cv2` (o extra `ocr-preproc` traz `opencv-python` para experimentos, mas
  não é exigido pelo caminho padrão).
- **Caminho do Tesseract**: resolvido atrás de `platform/tesseract.py` (explícito > `PATH` >
  diretórios comuns). Nunca usar `TESSDATA_PREFIX` — o `tessdata` vem do binário.
- **Pré-processamento recomendado para ROIs difíceis** (extensões futuras): escala de cinza +
  Otsu, `image_to_data` para texto disperso; medir com `compare-modes` antes de mudar defaults.
- **Performance**: OCR leva 100–500 ms por chamada. No modo `advanced` ele **é** o detector (roda a
  cada tick); por isso não se combina com OCR em 1 Hz — o intervalo default é 2 s.

### 10.5 Pipeline com curto-circuito

```python
MODE_STAGES: dict[str, tuple[str, ...]] = {
    "light": ("light",),
    "default": ("default",),
    "advanced": ("advanced",),   # OCR é o detector: roda sozinho, sem gate de phash/mean
}

class ComparePipeline:
    def compare(self, current: Frame) -> ComparisonResult:
        last = self.stages[0].compare(current)
        for stage in self.stages[1:]:
            if not last.changed:
                return last        # primeiro estágio que retorna False encerra o pipeline
            last = stage.compare(current)
        if last.changed and last.severity == 0:
            last = replace(last, severity=compute_severity(last.score, last.threshold))
        return last
```

**Decisão registrada (mudança em relação à recomendação original)**: o modo `advanced` roda **OCR
puro**, e não `[MeanColor, PerceptualHash, OCRTextDiff]`. Motivo: as camadas baratas funcionariam
como *gate* e poderiam retornar `changed=False` antes do OCR, mascarando mudanças de texto (o que o
modo avançado existe para pegar); o custo do OCR por tick é aceito com `poll_interval_s` default de
2 s. O mecanismo de curto-circuito permanece implementado e testado para composições futuras
(ex.: `[MeanColor, PerceptualHash]` como modo "estrito").

**Regra**: primeiro estágio que retornar `changed=False` encerra o pipeline. O veredito final é do
último estágio que rodou, com `severity` calculada quando ausente.

### 10.6 Estado inicial

**Regra não negociável**: o primeiro frame é **baseline**, não mudança. O pipeline é inicializado
com ele via `initialize`, e `compare` só é chamado a partir do **segundo** frame. O mesmo vale após
re-arm/re-baseline: o frame que re-inicializa não gera alerta.

---

## 11. Alertas

### 11.1 Protocolo

```python
class Notifier(Protocol):
    name: str
    enabled: bool
    severity_min: int
    cooldown_s: float

    def notify(self, result: ComparisonResult, frame: Frame) -> None: ...
```

**Regras**:
- `severity_min`: o notificador só dispara se a severidade da mudança for >= este valor.
- `cooldown_s`: após **tentar** disparar, o notificador é silenciado por N segundos,
  independentemente de novas mudanças (inclusive em falha — backoff, ver §11.3).
- `frame` é passado completo para permitir anexar a imagem do ROI (Telegram) ou logar contexto.

### 11.2 Notificadores do protótipo

**Som (`sound.py`)**:
- Toda a reprodução passa pela fronteira `platform/audio.py`; `alerts/` **não** conhece
  `sys.platform`.
- Windows: `winsound` (stdlib); sem `alert.wav`, usa `MessageBeep()`.
- Linux/macOS: player externo em ordem de preferência — `paplay`, `aplay -q`,
  `ffplay -nodisp -autoexit -loglevel quiet`; no macOS, `afplay`.
- Extra opcional `simpleaudio` (`pip install -e ".[sound]"`); **não** entra nos instaladores (sem
  wheel confiável para Python 3.13). Sem player algum, o som fica silencioso — o alerta nunca
  quebra.
- **Não usar** `playsound` (abandonado).

**Popup (`popup.py`)**:
- Biblioteca: `plyer.notification`.

**Telegram (`telegram.py`)**:
- Envio via `httpx` para `https://api.telegram.org/bot<token>/sendPhoto` (com `attach_roi: true`,
  default) ou `sendMessage`.
- **Anexa o screenshot do ROI** no momento do alerta — essencial para validar falsos positivos.
- Serializa `rgb` → PNG em memória (`PIL.Image.fromarray(...).save(buf, format="PNG")`).
- Timeout curto (**5 s**) para não travar o loop; token lido de `bot_token_env`
  (`TELEGRAM_BOT_TOKEN` por default) — **nunca** no YAML.
- **Erros sanitizados**: falhas HTTP são convertidas em `TelegramAPIError` com a descrição do
  Telegram (ex.: `chat not found`), sem URL/token — o `httpx` incluiria o token (que vai na URL)
  na mensagem de erro, deixando-o vazar no log da cadeia.

**Log (`log.py`)**:
- `JsonlNotifier`: uma linha JSON por disparo em `app-data/logs/alerts.jsonl` (ou caminho
  configurado em `path`).

**Regra**: tipo desconhecido é ignorado com `log.warning` (`build_notifier` devolve `None`).

### 11.3 Encadeamento, desfechos e re-arm

```python
class AlertChain:
    def dispatch(self, result: ComparisonResult, frame: Frame) -> DispatchOutcome:
        # sem notificadores habilitados -> NONE_ENABLED
        # nenhum com severity >= severity_min -> BELOW_MIN
        # para cada elegível fora do cooldown: notifica; falha não impede os demais
        #   -> FIRED (algum disparou) / FAILED (todos falharam) /
        #      SUPPRESSED_COOLDOWN (todos em cooldown)
```

**Desfechos** (`DispatchOutcome`): `FIRED`, `SUPPRESSED_COOLDOWN`, `BELOW_MIN`, `NONE_ENABLED`,
`FAILED`. O `MonitorSession` usa o desfecho para o **re-arm edge-triggered**:

- Com `rearm: true` (default), o baseline avança após `FIRED`, `BELOW_MIN` ou `NONE_ENABLED` — uma
  mudança sustentada alarma uma vez, e uma nova mudança realarma.
- Em `SUPPRESSED_COOLDOWN` e `FAILED` o baseline é **mantido**: a mudança pendente alarma quando o
  cooldown expirar, e falhas são re-tentadas respeitando o cooldown (backoff) — sem martelar a cada
  tick.
- Falha em um notificador registra a tentativa (`_last_attempt`) e não impede os demais; cada um tem
  seu próprio `try`.
- Re-arm manual: tray/botão "Re-armar"/hotkey `rearm`, via `MonitorSession.request_rebaseline()`
  (thread-safe) ou `rebaseline_now(frame)`.

### 11.4 Ações pseudo-humanas (opt-in, `actions/`)

Reação **separada** dos alertas: avaliada depois do `AlertChain.dispatch` quando `result.changed`,
**sem alterar** o `DispatchOutcome` nem o re-arm dos alertas. Só executa quando **armada**; por
padrão fica em **ensaio** (dry-run), que registra o que faria e grava evidências, sem clicar.

- **Gatilho**: `changed` (único suportado; `changed: false` é erro de validação), `severity_min`
  efetivo (`when.severity_min` > `severity_min`) e filtros de OCR
  (`text_any`/`text_all`/`text_regex`, case-insensitive por padrão). Filtros de texto exigem
  `mode: advanced` (validação recusa nos demais modos).
- **Passos**: `activate`/`click`/`move`/`type`/`key`/`wait`; `ref` é `roi` (relativo a
  `frame.absolute_rect`), `window` (`frame.window_rect`) ou `screen`. Clique exige `activate` antes
  (foco explícito + verificação `isActive`). Como o `SetForegroundWindow` do Windows é
  assíncrono/bloqueado (foreground lock), o foco é confirmado com pequenas pausas (até ~0,5 s antes
  de abortar); o motivo distingue `activate recusado` de `foco não confirmou`
  (`focus_changed: ...`).
- **Humanização** (`defaults.humanize`, §12.2): movimento do mouse interpolado em `mouse_steps`
  pontos com `jitter_px`; pausas com jitter de `wait_jitter_ms`; digitação com intervalo default de
  `key_interval_ms`; `seed` para testes determinísticos.
- **Cooldown**: um gatilho ignorado por `cooldown_s` **não** vai para o JSONL (para não poluir), mas
  é publicado no log ao vivo como `skipped -> cooldown`.
- **Limites**: `max_per_min` (janela móvel de 60 s) e `max_per_session`, checados antes da execução
  (`reason: rate_limited` no resultado/auditoria).
- **Execução síncrona na thread do loop**: captura/comparação pausam durante a sequência
  (sem re-entrância); `settle_s` ao final. Entre passos, o runner re-checa arming/aborto.
- **Re-arm**: `rebaseline: false` por padrão (o baseline permanece após a ação); `rebaseline: true`
  opt-in repete o gatilho (relatório/página). Re-arm manual em runtime (tray/botão/hotkey `rearm`,
  via `MonitorSession.request_rebaseline()`).
- **Ensaio x armado**: `ArmingController` com estados `disarmed`/`armed`/`timed`; estado só em
  memória, começa desarmado a cada sessão. `Esc` aborta na hora (`aborted`).
- **Agendador**: fora da janela de horário a ação é suspensa (`suspended_schedule`); monitoramento e
  alertas seguem.
- **Auditoria**: `logs/actions.jsonl` (ensaio, execução, suspensão, motivo, duração e caminhos das
  evidências).
- **Criação pela GUI**: `gui/action_editor.py` (`Nova ação...`/`Editar...`/`Remover ação`) grava em
  `overrides.actions` do JSON de seleção. Como `resolve_actions` lê os overrides antes do perfil,
  isso funciona também com config v1 (`targets:`), sem migração. A validação reusa `parse_actions`
  (clique exige `activate`, `text_*` exige `mode: advanced`), então as regras do YAML valem na
  janela; ações do perfil/YAML são somente leitura na GUI.
- **Localizador de posição**: `gui/locator.py::run_locator` (botão "Localizar posição do
  mouse..." nos passos `click`/`move`) mostra uma caixa seguindo o cursor; Enter/clique esquerdo
  confirma, Esc/clique direito cancela. Devolve o ponto global **lógico** (mesma base do `Frame`) e
  converte pelo `ref` via `overlay_geometry.resolve_ref_point` (`roi`→`absolute_rect`,
  `window`→`window_rect`, `screen`→origem); sem base, cai para `screen`. Difere do countdown: aqui o
  foco é necessário para capturar o Enter.
- **Seleção por sessão**: checklist na GUI (e `--actions` no CLI, one-shot) reduz o subconjunto por
  **nome de ação**; aplica só no próximo `build_target`. O estado fica em
  `state.json["action_selection"][seleção]` (chave ausente = todas, lista vazia = nenhuma).
  `resolve_actions` mantém a validação OCR/mode; o filtro apenas subtrai nomes (nunca reabilita
  `enabled: false`).
- **Log ao vivo**: cada gatilho emite um payload efêmero (`ActionDispatcher.on_event` →
  `MonitorSession.on_action` → `kind: "action_event"` na fila da GUI, distinto de `action` =
  comandos de tray/hotkey); a fonte de verdade continua sendo o JSONL.
- **Contagem de 3s**: fluxos avulsos (`test-action --armed`, `record-actions` e o botão "Executar
  ação (3s)" da GUI) usam `gui/countdown.py::run_countdown` — overlay Qt sem borda, always-on-top e
  `WindowDoesNotAcceptFocus`, **sem** `activateWindow` (a janela-alvo pode ser focada durante a
  contagem); clique cancela. Instanciado por `gui/qt_app.py::ensure_app` com `QEventLoop` (chamável
  de dentro da GUI). O disparo automático do loop **não** tem contagem. Fallback textual no console
  sem Qt/display.
- **Backend**: `pynput` como extra opcional (`pip install -e ".[input]"`), import preguiçoso em
  `platform/input.py`; sem ele, hotkeys caem para tray-only e a execução real falha com mensagem
  clara (`InputUnavailable`). Wayland/elevação seguem fora de escopo.

### 11.5 Evidências (prints)

Subsistema de saída, como os alertas: grava **prints da janela inteira** (sem máscara) do baseline
e de cada mudança detectada, para auditoria visual.

- **Formato/pasta**: `<pasta>/<alvo>/<AAAAMMDD-HHMMSS-mmm>_<baseline|change>.png` (ações usam
  `_action`/`_action-<passo>`). A gravação é **síncrona** (chamada pelo loop/sessão); falhas apenas
  `log.warning` e nunca quebram o loop. A pasta efetiva é
  `evidence.dir` quando configurado; senão `%TEMP%/screen_watch/captures`
  (`platform.paths`/`evidence.recorder.captures_dir`, exibida em `show-paths` como `captures:`).
- **Retenção**: `keep_per_target` (contagem por alvo) e `max_total_mb` (teto total), podadas após
  cada gravação.
- **Ligar/desligar**: `evidence.enabled` no YAML v2 **ou** o toggle de runtime
  `state.json["evidence_enabled"]` (checkbox "Gravar prints" na GUI), que tem **precedência** e
  funciona também com config v1. `app.effective_evidence_options()` faz a composição.
- **Fluxos avulsos**: `test-evidence` e o caminho de `run_actions` (`test-action --armed` e botão
  "Executar ação (3s)") gravam com `force_enabled=True`, respeitando `per_step` (print por passo)
  e registrando os caminhos na auditoria de ações.
- **Abrir pasta/arquivo**: passa sempre por `platform/shell.py::open_path`; a GUI avisa quando os
  prints do loop estão desligados.

---

## 12. Configuração

### 12.1 Schema YAML v2 (config global por perfil)

O YAML deixou de ser uma lista de targets e passou a ser **configuração global**. Os alvos vivem em
arquivos de seleção JSON (`app-data/selections/*.json`); o YAML define perfis, alertas, atalhos,
agendador, humanização e evidências.

```yaml
version: 2
profile: default                 # perfil ativo; trocável com --profile / seletor da GUI
profiles:
  default:
    defaults:
      mode: "advanced"           # "light" | "default" | "advanced"
      poll_interval_s: 2.0       # mínimo 1.0
      rearm: true
      humanize:                  # ruído pseudo-humano das ações (§11.4)
        mouse_steps: 24
        key_interval_ms: 60
        jitter_px: 3
        wait_jitter_ms: 150
        seed: null               # só para testes determinísticos
      compare_options:
        light:    { threshold: 12.0 }
        default:  { hash_size: 8, threshold: 6 }
        advanced: { similarity_threshold: 0.92, psm: 6, lang: "por+eng", upscale: 2,
                    tesseract_cmd: null }
    alerts:
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.wav" }
      - { type: "popup",    enabled: true, severity_min: 1, cooldown_s: 30 }
      - { type: "telegram", enabled: true, severity_min: 2, cooldown_s: 60,
          bot_token_env: "TELEGRAM_BOT_TOKEN", chat_id: "123456789", attach_roi: true }
      - { type: "log",      enabled: true, severity_min: 1, cooldown_s: 0 }   # opcional
    actions: []                  # ver §11.4
  trabalho:
    defaults: { mode: "default", poll_interval_s: 1.0 }
ui:
  hotkeys: { arm: "<ctrl>+<alt>+a", disarm: "<ctrl>+<alt>+d", toggle: "<ctrl>+<alt>+<space>",
             rearm: "<ctrl>+<alt>+r", abort: "<esc>" }
  arm_durations_min: [1, 5, 15, 30]
  language: auto                 # auto | pt-BR | en-US | tag descoberta em i18n/*.json
schedule: { enabled: false, days: [mon, tue, wed, thu, fri], windows: ["08:00-12:00"] }
evidence: { enabled: false, dir: null, keep_per_target: 50, max_total_mb: 200,
            on_baseline: true, on_change: true, per_step: false }
```

**Regras**:
- Tokens e segredos **nunca** no YAML. Usar variáveis de ambiente (`bot_token_env`).
- `version` aceita 1 ou 2 (outro valor é `ConfigError`); v2 **exige** `profiles`; `profile`
  inexistente é `ConfigError` (`config.profile_unknown`).
- `version` ausente com `targets:` é o v1 legado: carrega por uma versão, com aviso, e é convertido
  por `migrate-config` (backup `config.yaml.bak`, uma seleção JSON por target).
- `ui.language` desconhecido gera aviso e volta para `auto` (não é erro).
- `TargetConfig` continua sendo o contrato interno do runtime; o perfil + a seleção são resolvidos
  para ele por `persistence.selection.build_target`.

### 12.2 Perfis e defaults

Perfis nomeados (`profiles.<nome>.defaults` + `.alerts` + `.actions`) permitem alternar conjuntos de
parâmetros com `--profile` (CLI) ou o seletor da GUI/tray. A troca **aplica no próximo start** (não
ao vivo). O perfil ativo também é gravado em `state.json.profile`.

`defaults` cobre: `mode`, `poll_interval_s` (>= 1.0), `rearm`, `compare_options` e `humanize`
(§11.4). O `humanize` não tem UI própria: edite o YAML (a GUI cria ações, não humanização).

### 12.3 Seleção JSON e overrides

Cada seleção é um JSON v2; `overrides` é opcional e **substitui** (não soma) os valores do perfil
para aquele alvo: `mode`, `poll_interval_s`, `rearm`, `masks`, `alerts` e `actions`. Seleções
`version: 1` continuam carregando sem overrides.

```json
{
  "version": 2,
  "window_handle": 123456,
  "window_title_hint": "ERP - Estoque",
  "app_name": "ERP",
  "origin_at_selection": [100, 200],
  "roi_relative": [120, 340, 400, 80],
  "mode": "advanced",
  "masks": [],
  "overrides": { "poll_interval_s": 1.5, "rearm": false }
}
```

**Precedência do modo**: `mode` explícito do `build_target` (seletor da GUI) > `overrides.mode` >
`selection.mode`. Overrides de `actions` são parseados com o modo resolvido (filtros `text_*`
exigem `advanced`; §11.4). `window_title_hint` é apenas hint humano; o lookup usa `window_handle`.

### 12.4 Estado, app-data e gravação

`platform/paths.py` centraliza `app_home()`, `config_path()`, `selections_dir()`, `logs_dir()` e
`state_path()`. Base: `%APPDATA%\screen_watch` no Windows, `~/.config/screen_watch` no Linux,
`~/Library/Application Support/screen_watch` no macOS, ou o override `SCREEN_WATCH_HOME`.

`state.json` guarda `{"last_selection": "...", "profile": "...", "language": "...",
"action_selection": {"<seleção>": ["nome-da-acao", ...]}, "evidence_enabled": true|false}` e é
atualizado ao iniciar `run`/GUI com sucesso (as chaves `action_selection` e `evidence_enabled` são
opcionais e retrocompatíveis).

O YAML é regravado de forma atômica (temp + `os.replace`) com backup `config.yaml.bak` **sem
preservar comentários**; `state.json` é atômico, sem backup. O `migrate-config` recarrega do disco
antes de regravar.

A pasta de prints efetiva vem de `evidence/recorder.py::captures_dir(options)` (`evidence.dir` quando
configurado, senão `%TEMP%/screen_watch/captures`) e `ensure_captures_dir` a cria se faltar;
`show-paths` imprime-a como `captures:` (com nota de override). Abrir pasta/arquivo é feito
exclusivamente por `platform/shell.py::open_path` (best-effort) — o botão "Abrir pasta de prints" da
GUI e "Abrir YAML" usam esse helper.

Ligar/desligar os prints do loop não depende do YAML: `app.effective_evidence_options(config)` parte
do `evidence` do YAML (v2) e aplica o toggle de runtime `state.json["evidence_enabled"]` (checkbox
"Gravar prints" na GUI), que tem precedência — funciona também com config v1 (§11.5).

### 12.5 Agendador, perfis na UI e gravador

- **Perfis na UI**: seletor na janela + submenu no tray; a troca vale no próximo start e persiste em
  `state.json.profile` (`--profile` no CLI).
- **Agendador** (`scheduler/schedule.py::is_open`, função pura com relógio injetável; `gate()`
  devolve o callable): fora da janela de horário apenas as **ações** são suspensas
  (`suspended_schedule`); captura, comparação e alertas seguem. Janelas que cruzam a meia-noite são
  aceitas; agendador ligado sem `days`/`windows` não restringe.
- **Gravador** (`actions/recorder.py` + `record-actions`): com o extra `input`, captura
  cliques/teclas (`F10` encerra), converte coordenadas absolutas para `ref: roi`/`window`/`screen` e
  gera um snippet de `actions:` com `when` comentado. Padrão: contagem de 3s e gravação automática
  (a contagem roda na thread principal, antes dos listeners do `pynput`); `--no-countdown` mantém o
  `F9` explícito. Cliques fora da janela caem para `ref: screen`.
- **Seleção de ações na UI**: checklist "Ações da sessão" (`describe_action`/`describe_actions` em
  `actions/summary.py`) + contador "N de M"; persiste por nome de seleção
  (`actions/selection.py::load_action_selection`/`save_action_selection`) e vale no próximo start.
  No CLI, `--actions a,b|all|none` (one-shot, não persiste, precede o salvo) e `list-actions` para
  conferir; `run` imprime o resumo e as linhas ao vivo
  `[action] rehearsal|armed <nome> -> ok|failed|rehearsal`.
- **Testes/validação**: `is_open` com relógio falso, conversão do gravador sem listener real e troca
  de perfil (próximo start).

### 12.6 Idiomas (i18n)

- **Catálogo**: JSON dentro do pacote (`screen_watch/i18n/<tag>.json`), descoberto em runtime por
  `i18n.available_locales()` (usa `_meta.code`). Iniciais: `pt-BR` (fallback) e `en-US`. Nenhum
  idioma vem de app-data.
- **Escopo**: GUI + ajuda (`help.*`) + resumo/labels exibidos + erros traduzidos por código
  (`errors.py::ERROR_CODES` → `error.<code>`). **CLI e `logging` permanecem em inglês fixo**; o
  painel de log da GUI também é inglês (é log). `str(exc)` de `AppError`/`ConfigError` é inglês e
  `render_error(exc)` traduz pelo código (sem código, cai para `str(exc)`).
- **Escolha**: `--language` > `state.json["language"]` > `ui.language` > `auto` (locale do SO via
  `QLocale.system()` com fallback para `locale`/`LANG`); casamento exato (`pt-BR`) → mesmo idioma
  (`pt` → `pt-BR`) → `pt-BR`. A troca vale **no próximo start**; o seletor da janela grava
  `state.json["language"]`. `ui.language` desconhecido avisa e volta para `auto`.
- **Validação**: `python -m screen_watch validate-i18n` (também no CI) confere chaves
  faltando/sobrando vs. fallback, `error.*`/`help.*` sem tradução e `_meta` inválido.
- **Ajuda no hover**: `QTimer` de 2 s + tooltip HTML (`título`, `propósito`, `exemplo`) em
  `gui/help.py` (puro) + `gui/hover_help.py` (Qt).

### 12.7 Erros com código estável

- `AppError` carrega `code` + `params`; `str(exc)` renderiza **em inglês** (CLI/log).
- `ConfigError` herda de `AppError` e `ValueError` (preserva `except ValueError` existentes) — o
  loader converte erros de ação (`ActionError`) em `ConfigError` preservando código/params.
- A GUI chama `render_error(exc)`, que traduz `error.<code>` pelo catálogo ativo e cai para
  `str(exc)` quando não há código/tradução.
- Códigos são **estáveis** (contrato com os catálogos): renomear um código quebra a tradução.

---

## 13. Escada de teste (histórico de implementação e validação atual)

A implementação seguiu a escada abaixo, na ordem; **os scripts continuam no repositório** como
ferramentas de diagnóstico. Em regressões de captura/DPI, refaça a escada — não comece pela GUI.

1. **`scripts/step1_absolute_roi.py`** — ROI absoluta hardcoded, imprime hash a cada 1 s. Valida
   captura e mede Hz real.
2. **`scripts/step2_anchored_roi.py`** — ancoragem via `pywinctl` (Modelo B). Move a janela e
   confirma que a ROI segue. Valida DPI e multi-monitor.
3. **`scripts/step3_selection_overlay.py`** — overlay PyQt6, seleção por mouse, dump do JSON.
   Valida conversão lógico↔físico.
4. **Carregamento de JSON** — carregar a seleção do passo 3 e rodar captura ancorada (hoje:
   `run`/`select-manual`).
5. **Máscara** — confirmar que mexer na área mascarada não altera o hash.
6. **Comparação** — testar as três estratégias separadamente antes de compor (`compare-modes`).
7. **Alertas locais** — som + popup (`test-alert`).
8. **Telegram** — webhook com imagem anexada (teste de integração opt-in).
9. **GUI completa** — janela principal, tray, edição de ações.

**Não pule etapas.** O custo de depurar DPI/multi-monitor através da GUI é ordens de magnitude maior
do que via script.

---

## 14. Armadilhas conhecidas (para a IA implementadora)

Cada item abaixo é uma armadilha **real** já discutida e resolvida. Não reintroduzir. Os itens 1–15
são os originais; os itens 16–22 foram registrados durante a implementação.

1. **Wayland**: `mss` não captura. Detectar e avisar. Não tentar contornar no protótipo.
2. **DPI awareness fora de ordem**: se `SetProcessDpiAwareness` for chamado depois de `mss` ou Qt,
   não tem efeito. Chamar primeiro.
3. **`window_title_hint` como chave**: nunca. Usar `window_handle`.
4. **`time.sleep` no loop**: nunca. Usar `Event.wait`, subtraindo tempo de trabalho.
5. **Comparação dentro do `try` de captura**: nunca. Separação de responsabilidades.
6. **Primeiro frame como mudança**: nunca. É baseline.
7. **`setMask` no overlay**: nunca. Usar `CompositionMode_Clear`.
8. **Reconsultar `window.getRect()` depois do I/O**: nunca. Capturar imediatamente após o drag.
9. **`hash_size=16` como default**: nunca. 8.
10. **OCR a cada tick**: nunca. Só no pipeline avançado, com curto-circuito.
11. **`playsound`**: abandonado. Usar a fronteira `platform/audio.py`.
12. **`pygetwindow`**: abandonado. Usar `pywinctl`.
13. **Token no YAML**: nunca. Variável de ambiente.
14. **Criar `mss.mss()` a cada tick**: nunca. Instância reutilizada.
15. **Confiar em `devicePixelRatio()` como 1.0**: nunca. Testar em 125/150/200%.
16. **`mss` fora da thread do loop**: nunca. Ele não é thread-safe; o backend é criado/fechado
    dentro do worker (inclusive a instância reutilizada).
17. **Importar `pynput`/`winsound`/`mss`/`pywinctl` fora de `platform/`**: nunca. Toda dependência de
    SO fica atrás da fronteira (o CI roda sem `pynput`).
18. **Presumir `simpleaudio`**: nunca. Não tem wheel confiável para 3.13; som é extra opcional com
    fallback para player externo; os instaladores **não** o incluem.
19. **Usar `%APPDATA%` cru no Windows com Python da Store/MSIX**: o caminho é redirecionado para
    dentro do pacote. `platform/paths.py` detecta e usa o caminho real.
20. **Trocar o wrapper do `.deb` por symlink**: nunca. O PyInstaller resolve `_internal` pelo
    caminho real; o wrapper usa `exec`.
21. **Definir `TESSDATA_PREFIX`**: nunca. O `tessdata` vem do binário; `advanced.py` não passa
    `--tessdata-dir`.
22. **Publicar tag != `__version__`**: o `release.yml` falha de propósito. A tag `vX.Y.Z` deve ser
    idêntica (sem `v`) a `screen_watch.__version__`.

---

## 15. Dependências (implementadas)

Fixadas em `pyproject.toml`. Organizadas por camada (núcleo obrigatório):

| Camada | Pacote | Uso |
|---|---|---|
| Captura | `mss` | captura de tela |
| Captura | `numpy` | buffer canônico |
| Janela | `pywinctl` | localização e geometria de janela |
| Comparação | `Pillow` | ponte `numpy` ↔ `imagehash`/Tesseract |
| Comparação | `imagehash` | phash |
| Comparação | `pytesseract` | OCR (requer binário Tesseract instalado) |
| GUI | `PyQt6` | overlay e janela principal |
| Tray | `pystray` | ícone de bandeja |
| Alertas | `plyer` | popup |
| Alertas | `httpx` | Telegram |
| Config | `PyYAML` | config |

**Extras opcionais** (`pyproject.toml::[project.optional-dependencies]`):

| Extra | Pacotes | Observação |
|---|---|---|
| `sound` | `simpleaudio>=1.0.4` | sem wheel confiável no 3.13; **não** entra no bundle |
| `input` | `pynput>=1.7` | ações pseudo-humanas e hotkeys globais |
| `ocr-preproc` | `opencv-python>=4.8` | experimentos de pré-processamento de OCR (não exigido) |
| `logging` | `structlog>=24.1` | log estruturado opcional |
| `dev` | `pytest>=8.0`, `pytest-cov>=5.0`, `ruff==0.16.9` | desenvolvimento e CI |
| `build` | `pyinstaller>=6.11.1` | empacotamento (suporta 3.13 a partir dessa versão) |

**Requisitos externos**:
- **Tesseract** instalado no sistema (não vem com `pytesseract`), com os traineddata `por` e `eng`.
  No Windows o instalador baixa um release fixado (com verificação SHA256) e o transforma em
  `Depends:` no `.deb` do Linux. Caminho procurável via `compare_options.advanced.tesseract_cmd`.
- **Som no Linux**: um player externo (`paplay`/`aplay`/`ffplay`); no `.deb`, `pulseaudio-utils` e
  `alsa-utils` vêm como `Recommends`.
- **Linux**: sessão X11 (Wayland fora de escopo).

---

## 16. Contratos entre módulos (resumo executivo)

Para referência rápida da IA implementadora:

```
platform/dpi.set_dpi_awareness()   → chamar PRIMEIRO (primeira linha do main)
platform/window.find_window_by_handle(handle) → WindowInfo | None

capture/resolver.resolve(window_info, roi_relative, logical_to_physical=...) → Rect | None
capture/backend.MssCaptureBackend.bounds() → Rect          (desktop virtual, pode ser negativo)
capture/backend.MssCaptureBackend.capture(abs_rect) → np.ndarray   (RGB)
capture/mask.apply_mask(rgb, masks) → np.ndarray
capture/frame.Frame(rgb, timestamp, absolute_rect, window_rect, window_handle, sequence)

compare/protocol.CompareStrategy.initialize(baseline: Frame)
compare/protocol.CompareStrategy.compare(current: Frame) → ComparisonResult
compare/pipeline.MODE_STAGES / ComparePipeline.compare(current) → ComparisonResult

alerts/chain.AlertChain.dispatch(result, frame) → DispatchOutcome
actions/dispatch.ActionDispatcher.on_result(result, frame) → rebaseline: bool

config/loader.load_config(path) → AppConfig
persistence/selection.build_target(selection, profile, name=..., mode=..., schedule=...,
                                   action_filter=...) → TargetConfig
app.MonitorSession(target, recorder=..., on_action=...) → sink(frame)
app.build_loop(target, session, on_event=..., on_error=...) → MonitorLoop
scheduler/loop.MonitorLoop.start()/.stop()/.join()
scheduler/schedule.is_open(options, now=...) → bool; gate(options) → Callable | None

evidence/recorder.EvidenceRecorder.from_options(options, force_enabled=...) → recorder
app.effective_evidence_options(config) → EvidenceOptions
```

**Fluxo de dados**:

```
MonitorLoop._tick
  → window_lookup → resolve → clip → backend.capture → normalize → apply_mask
  → Frame
  → MonitorSession.__call__(frame)
      → (1º frame / re-arm) pipeline.initialize  (baseline; grava evidência)
      → pipeline.compare
      → AlertChain.dispatch            (som/popup/Telegram/log; cooldown; DispatchOutcome)
      → ActionDispatcher.on_result     (ensaio/armado; agendador; limites; auditoria)
      → re-arm do baseline (outcome/rebaseline) + evidência de mudança
```

---

## 17. Glossário

- **ROI** — Region of Interest; o retângulo monitorado dentro da janela.
- **Baseline** — primeiro frame capturado em uma sessão (ou após re-arm); referência para
  comparação. Nunca é mudança.
- **Modelo B** — ancoragem por origem da janela: `abs = roi_relative + window_rect.topLeft()`.
- **Pipeline** — composição de estratégias de comparação com curto-circuito.
- **Frame** — dataclass imutável com `rgb` (numpy) e metadados de captura.
- **Tick** — uma iteração do loop de captura.
- **DPR** — device pixel ratio; fator entre espaço lógico e físico.
- **Chrome** — elementos não-cliente de uma janela (barra de título, bordas).
- **Perfil** — conjunto nomeado de defaults/alertas/ações no YAML v2 (`profiles.<nome>`), trocável
  no próximo start.
- **Overrides** — campos do JSON de seleção que **substituem** (não somam) os valores do perfil
  para aquele alvo.
- **Arming / ensaio** — estado em memória que decide se as ações executam (`armed`/`timed`) ou
  apenas registram (`disarmed` = ensaio). Sempre começa desarmado.
- **Evidência** — print (baseline/change/por passo) gravado pelo `EvidenceRecorder` para auditoria
  visual.
- **Desfecho (`DispatchOutcome`)** — resultado de um `dispatch` (`FIRED`, `SUPPRESSED_COOLDOWN`,
  `BELOW_MIN`, `NONE_ENABLED`, `FAILED`) usado pelo re-arm edge-triggered.

---

## 18. Notas finais para a IA implementadora

1. **Leia este documento inteiro antes de mexer no código.** Muitas decisões aqui parecem
   arbitrárias isoladamente, mas têm motivação registrada.
2. **Use a escada de teste (§13) ao investigar regressões de captura/DPI.** Ela existe para reduzir
   o espaço de busca de bugs.
3. **Se algo aqui parecer errado ou insuficiente, registre como comentário/issue — não mude
   silenciosamente.** Se o código mudou de propósito, atualize o documento com o novo motivo e o
   histórico da decisão.
4. **Toda dependência de SO fica em `platform/`.** Nunca importe `pywinctl`/`pynput`/`mss`/
   `winsound` fora dessa pasta.
5. **A comparação nunca toca em tela, janela, ou sono.** Se sua implementação precisar de qualquer
   um desses, o design foi violado.
6. **Primeiro frame é baseline.** Se seu código dispara alerta no primeiro tick, há bug.
7. **Se um teste falhar em 125% ou 150% de escala no Windows, isso é o bug mais importante do
   projeto.** Priorize antes de qualquer feature.
8. **Documente cada experimento empírico** (thresholds, hash_size, psm, upscale) com o contexto em
   que foi ajustado. Os defaults são pontos de partida, não verdades.
