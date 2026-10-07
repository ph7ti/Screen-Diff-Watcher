# Screen Diff Watcher — Documento de Arquitetura e Especificação
[English](00-Architecture_and_Specification.md) · **Português (Brasil)**

> **Propósito deste documento**: servir como **fonte única de verdade do design** para que outra IA
> (ou desenvolvedor) continue o projeto sem precisar reconstruir decisões, e registrar **o que está
> implementado** (referência: v0.11.0). Toda decisão aqui registrada foi tomada deliberadamente; onde
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
4. **Emite alertas** quando a mudança é confirmada: som local, popup local, log JSONL e/ou canais
   remotos (Telegram, push ntfy, e-mail/SMTP, MQTT, webhook/HTTP POST genérico, syslog), com
   snooze/mute e escalação opcional até o acknowledge (§11).
5. Opcionalmente, **executa ações pseudo-humanas** (clique/teclas/texto) quando **armadas** — por
   padrão em ensaio (dry-run), com auditoria em `logs/actions.jsonl` (§11.4).
6. Oferece **GUI com tray** (PyQt6 + pystray) e **CLI completa**, com perfis, agendador e i18n
   (pt-BR/en-US na GUI; CLI e log em inglês fixo).

**Plataformas alvo do build**: Windows (x64), Linux Debian/Ubuntu (amd64, X11) e, a partir da
v0.11.0, macOS (arm64) como **bundle `.app` sem assinatura** (exige contornar o Gatekeeper;
validação manual pendente — §15).

### 1.2 O que o projeto NÃO é

- Não é um gravador de tela.
- Não é um OCR de documentos (o OCR serve apenas para detectar mudança de texto).
- Não captura de janelas ocluídas (limitação fundamental da API de captura — ver §7.5).
- Não contorna DRM, anti-cheat ou janelas protegidas.
- Não depende de nenhum serviço em nuvem proprietário: todo canal remoto (Telegram, ntfy, SMTP,
  MQTT, webhook) é opcional e configurado pelo usuário, com credenciais em variáveis de ambiente.
- Não suporta **Wayland** (§3.2) nem **ARM64** fora do build macOS arm64; não assina digitalmente
  nem notariza os instaladores (no macOS aparece o aviso usual de app sem assinatura).
- Não é um RPA genérico: as ações são um subsistema opt-in e deliberado (§11.4).

### 1.3 Caso de uso canônico

Monitorar um painel/indicador dentro de um aplicativo desktop (ex.: painel de estoque de um ERP) e
alertar o usuário quando aquele painel sofrer alteração visual, sem exigir que o usuário fique
olhando para a tela. Extensão natural: reagir à mudança com uma ação simples (ex.: clicar em
"Atualizar") quando isso for explicitamente armado.

### 1.4 Estado da implementação (v0.11.0)

Implementado e coberto por testes: fronteira de plataforma, captura/ancoragem (Modelo B), os três
modos de comparação, pipeline com curto-circuito (`advanced` com gate de phash e bypass pelo
`text_watch`), alertas (som/popup/Telegram/log mais
`webhook`/`http_post`/`syslog`, com modelo de payload, `id` estável e cooldown) com re-arm,
**som selecionável (Qt Multimedia na GUI, `miniaudio` no CLI, fallback legado)** e o filtro
**`text_watch`** (aparece/desaparece, somente `advanced`, override por seleção), teste de envio por
canal (`test-alert --list/--only` e o botão da GUI), evidências, ações
pseudo-humanas (arming, ensaio, limites, auditoria, editor na GUI, gravador), agendador (suspende
apenas ações), perfis + migração v1→v2, seleção JSON v2 com overrides e o **nome da seleção**
(`name`/renomeação para `selections/<slug>.json`), CLI (`init-config` …
`validate-i18n`), GUI + tray com i18n e ajuda no hover — incluindo **"Ver local"** (realce
transitório da ROI que nunca pinta dentro dela), **duplo clique para reeditar a região / Enter para
iniciar-parar**, a **repaginação da janela em grid 2×2** (Seleções e Ações da sessão à esquerda;
Monitoramento e Detecção e alertas à direita; Status+Log no rodapé com os botões à direita), o **som
default empacotado `alert.mp3`** (resolver em `app_home()/sounds` → `assets/sounds` → CWD) e o
**popup ao escolher o som** que orienta a colar o caminho no YAML — empacotamento (PyInstaller;
Inno Setup no Windows; `.deb` no Linux) e pipeline de release por tag.

**Adições da v0.8.0**: **editor visual de máscaras** (desenhar/remover no overlay, JSON de seleção
atômico, precedência de `overrides.masks`, bloqueado com sessão rodando), **seletor de som gravando
`file:` no YAML do perfil ativo** (atômico + `.bak`, config v1 recusada), **preview do frame**
(baseline + último, miniaturas reduzidas), **histórico de alertas** sobre `logs/alerts.jsonl`
(filtros de data/severidade/modo, print de evidência best-effort) e **calibração ao vivo**
(score × limite, export CSV); CI agora em Python 3.11/3.12/3.13 com artefato de cobertura e a wiki
com runbook manual de publicação.

**Adições da v0.9.0**: três canais de alerta (**ntfy**, **SMTP** via stdlib, **MQTT** via o extra
opcional `mqtt`) seguindo o schema `options:` e códigos de erro estáveis; **snooze/mute** via o
`AlertGate` compartilhado e thread-safe, persistido no `state.json` (GUI/tray, desfecho
`SUPPRESSED_MANUAL`) e **escalação** (repetir até o acknowledge, `acknowledge()` + cadência pelo
cooldown de cada alerta, evidência de mudança atrelada às tentativas de entrega); o **ciclo de vida
da seleção no CLI** (`remove-selection`, `rename-selection`, `edit-selection`,
`list-selections --json`) completando o fluxo headless (o item "Radar" do README); e **múltiplas
ROIs simultâneas** na GUI (`SessionManager` rodando N `MonitorLoop`s com preview/calibração por
sessão, conjunto de checkboxes, `ui.max_sessions`, status/tray agregados, iniciar/parar por seleção
no tray).

**Correção da v0.9.1**: `SessionManager.escalating` é um **método**; o código de status/acknowledge
do gate na GUI o chama (`main_window._update_gate_status`/`_acknowledge`). O acesso residual como
propriedade levantava `TypeError` dentro do slot do `QTimer` e o PyQt6 aborta o processo em exceção
não tratada em slot — a GUI morria no primeiro tick do drain (`0xC0000409`) sem traceback visível.
Testes de regressão em `tests/test_gui_main_window.py` exercitam os métodos reais com stubs sem Qt
(e import preguiçoso do `main_window`, para que os testes que simulam a ausência do Qt continuem
funcionando).

**Adições da v0.10.0**: **gatilhos de tempo** por ação (`when.trigger: change|at|every|after`,
§11.4): o avaliador puro `actions/triggers.py` (relógios de parede/monotonic injetáveis; tolerância
de 60 s registrada como `skipped -> missed`; sem catch-up nem replay), as fases de
`ArmingController.armed_since`, o `ActionDispatcher.on_tick` avaliado em todo frame pós-baseline
mais o `next_deadline_delay()` limitando a espera do `MonitorLoop` (§3.5), validação estrita (campos
de `change`, `rebaseline` recusado, `cooldown_s >= every_s`), `trigger` nos payloads de
auditoria/log, seletor de gatilho no editor da GUI, resumo no `list-actions`, aviso
`trigger ... ignored (explicit run)` nos fluxos avulsos e dica comentada no gravador; i18n nos dois
catálogos e testes com relógios falsos.

**Correção da v0.10.1**: o localizador de mouse da GUI e o realce da ROI agora convertem entre o
espaço lógico do Qt e o físico, ancorados na origem do monitor (§9.5); antes, ações criadas pelo
localizador clicavam em coordenadas **lógicas** em monitores com escala (`ref: roi`/`window`/`screen`;
ex.: ~192×120 px de erro no centro de uma tela 1920×1200 a 125%). Captura, gravador e coordenadas
digitadas à mão já eram físicas e não mudaram.

**Adições da v0.11.0**: **checagem passiva de nova versão** (`updates.py`: no máximo um `GET`
anônimo/dia à API do GitHub, cache no `state.json` com TTL de 24 h e `notified_version`, opt-out
`ui.update_check`; linha no log da GUI + item no tray que abre o release — nunca popup, nunca
download, nunca no caminho de captura) (§3.8/§12.1/§12.4/§15); alvo **macOS arm64** (célula de CI
com `QT_QPA_PLATFORM=offscreen`, `build_release.py --macos` gerando o zip via `ditto` de um
`BUNDLE` do PyInstaller, asset do release) — sem assinatura e com validação em hardware pendente
(§1.1/§3.1/§5.3/§15); a decisão do **spike de Wayland** (portal
`org.freedesktop.portal.ScreenCast` + PipeWire avaliados e mantidos fora de escopo na linha 1.x —
§3.2/§5.1); o instalador Windows agora torna o Tesseract **opcional com consentimento** (Sim/Não no
interativo; silencioso só com `/TESSERACT=yes`; falha nunca aborta — §3.8/§15); housekeeping: o
extra `logging` sem uso foi removido e o **mypy** (dev-only, escopo do núcleo, gate de CI no
Linux/3.13) é o gate de tipagem (§3.1/§15).

Pendências de **validação manual** (não automatizável no CI):

- GUI/tray/overlay em escalas 100/125/150% (§5.1, §9).
- Bundle em máquina limpa: ícone da janela/tray, `StartupWMClass` do `.desktop`, tamanho do pacote,
  aviso do SmartScreen (assinatura fora de escopo) e o **fluxo de consentimento do Tesseract**
  (aceitar/recusar/offline/silencioso `/TESSERACT=yes`). Checklist em
  [`doc/01`](01-Build_e_Release.md) §9.
- macOS em hardware físico: permissões TCC (Gravação de Tela/Acessibilidade), tray, áudio e a
  primeira execução do `.app` sem assinatura (Gatekeeper); ARM64 fora do macOS segue fora de escopo.

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
- **Alvos (v0.11.0)**: Windows x64, Linux Debian/Ubuntu amd64 (X11) e macOS arm64 (sem assinatura,
  `BUNDLE` do PyInstaller; validação manual pendente em hardware físico — o checklist cobre as
  permissões TCC de Gravação de Tela/Acessibilidade).
- **Tipagem (v0.11.0)**: **`mypy`**, dev-only (extra `dev`), com configuração **não estrita** no
  `pyproject.toml` (`ignore_missing_imports` para stubs de terceiros, sem `strict` global). Escopo
  inicial é o núcleo sem Qt: `capture/`, `compare/`, `config/`, `persistence/`, `platform/`,
  `errors.py`, `naming.py`. Gate de CI: `python -m mypy` na célula Linux/3.13; os módulos de
  GUI/Qt ficam fora do escopo por ora.
- **Logging (v0.11.0)**: o `logging` da stdlib basta (logs em inglês fixo); o extra opcional
  `structlog` (sem uso) foi **removido** e adotar log estruturado está **rejeitado** por ora.
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
- **Limitação conhecida e aceita — Wayland (spike, v0.11.0)**: `mss` **não funciona em Wayland**. O
  projeto detecta (`XDG_SESSION_TYPE=wayland`) e encerra `run`/GUI com aviso claro (`is_wayland()` em
  `platform/dpi.py`). O spike da v0.11.0 avaliou a única rota suportada —
  `org.freedesktop.portal.ScreenCast` (D-Bus) + **PipeWire** (`CreateSession` → `SelectSources` →
  `Start` → `OpenPipeWireRemote`, consentimento por sessão e restore tokens) — e **decidiu manter
  Wayland fora de escopo na linha 1.x**, mantendo a detecção/aviso atual, porque:
  - a entrega de frames exige a pilha PipeWire do sistema mais GStreamer/`gi` (`pipewiresrc`) ou um
    binding de baixo nível da libpipewire; ainda não existe cliente maduro, instalável por wheel e
    empacotável (o promissor `pipewire-capture` é novo e ainda exige libpipewire + portal);
  - o portal expõe **streams de monitor ou janela**, não o modelo de ancoragem
    `(janela, roi_relative)` do projeto: streams de janela entregam o conteúdo sem posição na tela,
    então o Modelo B (§3.3) e a semântica de evidências exigiriam redesenho;
  - consentimento por sessão/restore token e as implementações por compositor (portais
    GNOME/KDE/wlroots) aumentam a superfície de suporte sem equivalente no CLI/headless.
  Um backend futuro (pós-1.0, sem data) deve ficar atrás de `capture/backend.py` como
  `ScreenCastBackend` separado, ser opt-in e manter o `mss` no X11. **Não adicionar dependências de
  portal/PipeWire antes disso** (§15).

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
- **Detalhes da implementação**: `light`/`default` mapeiam para **um estágio**; `advanced` mapeia
  para **dois** (`default` → `advanced`), de modo que o phash funciona como **gate de pixel** antes do
  OCR: se os pixels não mudaram, o pipeline curto-circuita e o OCR não roda/pontua. Isso evita ruído
  de OCR em quadros quase idênticos gerar "mudança" a cada tick (atualizado §10.5).
- **Alternativas rejeitadas**:
  - Apenas phash — não distingue mudança semântica de ruído estrutural em alguns casos.
  - Apenas OCR — caro demais por tick, inviável em 1 Hz.
  - SSIM — mais caro que phash sem ganho claro para o caso de uso.

### 3.5 Agendamento

- **Decisão**: `threading.Thread` + `threading.Event.wait(timeout)` como loop principal.
- **Motivo**: cancelamento imediato, sem dependência extra, simples de raciocinar. O `wait` subtrai
  o tempo de trabalho do intervalo, garantindo cadência estável.
- **Múltiplas sessões (v0.9.0)**: a GUI roda **N `MonitorLoop`s** — uma thread, um backend `mss`
  e um `MonitorSession` por alvo — coordenados pelo `gui/session_manager.SessionManager`. O
  isolamento por thread do `mss` (§3.2, §14.16) é o que garante a segurança; cada sessão mantém seus
  próprios buffers de preview/calibração e o `AlertGate` de snooze/mute é compartilhado.
  `ui.max_sessions` (default 4, faixa 1..16) limita o conjunto da GUI; o OCR no `advanced` multiplica
  a CPU por sessão (documentado). O `run` do CLI permanece intencionalmente single-selection
  (multi-ROI headless está fora de escopo por ora).
- **Deadlines dos gatilhos de ação (v0.10.0)**: o mesmo `Event.wait` é limitado pelo próximo
  vencimento armado (`ActionDispatcher.next_deadline_delay()`, repassado pelo `build_loop`), para o
  `at` pontual e o `every_s` menor que o poll dispararem na hora; o piso é 0,05 s e, sem deadline, a
  cadência continua o intervalo do poll (§11.4).
- **Alternativas rejeitadas**:
  - `asyncio` — overhead desnecessário; `mss`/`pywinctl` são síncronos e bloqueantes.
  - `APScheduler` — sobre-engenharia para um único loop.
  - Um processo por sessão — config/state/alert gate duplicados e empacotamento mais pesado, sem
    benefício para o escopo.

### 3.6 Alertas

- **Decisão**: cadeia de notificadores (**Chain of Responsibility**), cada um com `enabled`,
  `severity_min` e `cooldown_s`. Implementados no protótipo:
  - **Som local** — atrás da fronteira `platform/audio.py`: Qt Multimedia na GUI (`QMediaPlayer`,
    WAV/MP3/M4A/AAC/…), `miniaudio` no CLI/`run` (dependência core; WAV/MP3/OGG/FLAC numa thread
    daemon) e o fallback legado (`winsound` no Windows; `paplay`/`aplay`/`ffplay` no Linux; `afplay`
    no macOS). O extra `simpleaudio` continua opcional.
  - **Popup local** (`plyer.notification`).
  - **Webhook Telegram Bot** (`httpx`, `sendPhoto`/`sendMessage`, timeout de 5 s; token via
    variável de ambiente).
  - **ntfy** (`httpx`; POST de texto puro em `server/topic`, PUT opcional de PNG com `attach_roi`,
    headers `Title`/`Priority`/`Tags`; token via variável de ambiente, anônimo quando ausente).
  - **E-mail (SMTP)** (stdlib `smtplib`; STARTTLS/SSL/none, credenciais via variáveis de ambiente,
    anexo PNG opcional).
  - **MQTT** (extra opcional `paho-mqtt`; publicação de payload JSON com QoS/retain/TLS, credenciais
    via variáveis de ambiente, sem imagem).
  - **Log JSONL** (`app-data/logs/alerts.jsonl`).
- **Motivo**: Telegram é gratuito, confiável, permite anexar imagem do ROI no alerta (essencial
  para validar falsos positivos), e não exige setup de servidor. O ntfy cobre push no celular sem
  bot; o SMTP cobre e-mail corporativo; o MQTT cobre barramentos de automação do próprio usuário.
  Os três mantêm as credenciais em variáveis de ambiente e seguem o mesmo contrato de cadeia/
  cooldown. O log JSONL dá auditoria local; o popup/som cobrem o uso offline.
- **Alternativas rejeitadas**:
  - Pushover — pago.
  - FCM — complexidade de setup desproporcional.
  - `simpleaudio` como única via de som — sem wheel confiável para Python 3.13; virou extra
    opcional (`pip install -e ".[sound]"`), com fallback por player externo.
  - Qt Multimedia como **única** via de som — exige um `QCoreApplication`, então o CLI/`run` não
    pode usá-lo (daí o `miniaudio` no core).

### 3.7 GUI e overlay de seleção

- **Decisão**: **PyQt6** para GUI e overlay.
- **Motivo**: multi-monitor nativo (`QGuiApplication.screens()`), transparência real, alta DPI
  resolvida corretamente, `CompositionMode_Clear` disponível para o "buraco" da seleção.
- **Detalhes da implementação**:
  - **Layout**: a janela segue o mockup `UI.txt` (painel superior num **grid 2×2**: à esquerda os
    grupos **Seleções** — fileira de botões Novo Target/Remover/Recarregar/**Ver local da seleção**
    / **Editar máscaras…**,
    legenda, lista e a linha **Nome da seleção** (`name` + Renomear) — e **Ações da sessão** — checklist,
    contador e a fileira Nova ação…/Editar…/Remover Ação/Executar ação; à direita **Monitoramento** —
    grid de duas colunas Iniciar/Idioma, Parar/Re-armar baseline, Modo/Perfil, Armar Ações/Desarmar
    Ações, Armar por…/Minimizar para o tray, mais **Gravar prints (evidências)** e o status de arming —
    e **Detecção e alertas** — texto primeiro (`text_watch`) e depois o som, com **Escolher…/Reproduzir/
    Copiar caminho**; no rodapé, num `QSplitter`, o grupo **Status** com Status/Último/**Log** e a
    coluna direita com **Prints/Testar alerta…/Abrir YAML**). Edição de passos com
    Subir/Descer/drag&drop/Editar/Duplicar.
  - **Seletor de som (v0.8.0)**: ao escolher um som, a GUI **pede confirmação e grava** o `file:` no
    alerta `sound` do perfil ativo no `config.yaml` (atômico + `.bak`, §11.2/§12.1); o diálogo mantém
    **Copiar caminho e abrir YAML**/**Só abrir o YAML**/**Fechar** como ações secundárias, avisa
    quando a seleção tem `alerts` em `overrides` e mostra mensagem de migração para config v1 em vez
    de gravar.
  - **Interações da seleção**: **duplo clique reedita a região** (overlay de novo, mesma janela,
    preservando `name`/`mode`/`overrides` e limpando `masks`); **Enter inicia/para** a sessão
    (`QShortcut` com `WidgetShortcut`; `itemActivated` não é usado porque também dispara no duplo
    clique). Renomear grava o nome de exibição e move o arquivo (slug; nunca sobrescreve).
  - **Realce ("Ver local")**: uma janela por monitor, sem borda, *top-most*, transparente a
    cliques/foco (`WindowTransparentForInput` + `WA_TransparentForMouseEvents`, sem grabs e sem
    modal), escurecendo **apenas fora** da ROI (`overlay_geometry.dim_rects`) com borda de 2 px
    desenhada logo fora do buraco; fecha sozinha em 2 s. Como os pixels da ROI nunca são pintados,
    pode rodar com a sessão monitorando (`gui/highlight.py`).
  - **Editor de máscaras ("Editar máscaras…", v0.8.0)**: overlay modal por monitor (mesmo padrão
    visual do overlay de seleção) que mostra a borda da ROI e as máscaras efetivas; arrastar com o
    botão esquerdo adiciona, clique direito remove a máscara sob o cursor, Enter salva e Esc cancela.
    Fica bloqueado com a sessão rodando e grava o JSON da seleção de forma atômica (§8.3, §12.3).
  - **Preview, histórico e calibração (v0.8.0)**: a área Monitoramento mostra um **Preview** com o
    último frame capturado e o baseline; só miniaturas reduzidas cruzam a fronteira de thread — o
    controller guarda dois arrays limitados sob lock e a GUI monta/copia o `QImage` na própria thread
    (a thread do loop nunca entrega seu array `numpy` a um widget). Uma tabela de **histórico de
    alertas** lê `logs/alerts.jsonl` (tolerante a linhas inválidas) com filtros de
    data/severidade/modo e "abrir print" best-effort (o `*_change.png` mais próximo em ±2 s, senão a
    pasta de capturas). Um widget de **calibração** plota `score` × `threshold` de um ring buffer
    por sessão limitado, alimentado por **todas** as comparações (não só as mudanças), com export
    CSV; sem dependência nova (`QPainter` custom).
  - **Tray**: `pystray` (`gui/tray.py`) com mostrar/ocultar, iniciar/parar, armar/desarmar, perfil,
    **Soneca/Silenciar/Reativar/Reconhecer escalação** (v0.9.0) e sair. A GUI recebe eventos por
    **fila** consumida por `QTimer` (`gui/session_manager.py`); callbacks de tray/hotkey nunca chamam Qt
    de dentro da thread do listener.
  - **Controles de snooze/mute/escalação (v0.9.0)**: o grupo Detecção e alertas tem **Soneca…**
    (durações de `ui.snooze_minutes`), **Silenciar alertas/Reativar alertas** e **Ciente**
    (habilitado enquanto uma sessão escala), além de um rótulo com o tempo restante de snooze/mute;
    as mesmas ações estão no tray. Snooze/mute persistem no `state.json` e valem para todas as
    sessões que compartilham o gate (§11.3).
  - **Múltiplas ROIs (v0.9.0)**: a lista de seleções tem **checkboxes**; Iniciar inicia todas as
    seleções marcadas (nenhuma marcada = a destacada) via `SessionManager`, até `ui.max_sessions`.
    Linhas de sessões rodando recebem o prefixo `▶`, a linha de status agrega a contagem
    (`status.monitoring_multi`), as linhas de log/resultado recebem o prefixo `[selection]` quando
    2+ rodam, e preview/calibração/ações seguem a linha rodando **destacada** (senão a primeira em
    execução). Parar encerra todas as sessões; Remover encerra antes as afetadas; o menu do tray tem
    iniciar/parar agregados e um submenu de iniciar/parar por seleção. (O `MonitorController` foi
    substituído pelo `gui/session_manager.SessionManager`; §3.5.)
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
  **Inno Setup** (Windows), **`.deb`** (Linux) e **zip do `.app` sem assinatura** (macOS, v0.11.0).
- **Motivo**: mais maduro, ampla documentação, funciona nos SOs alvo; instaladores nativos dão
  atalhos, desinstalação e dependências declaradas.
- **Detalhes da implementação**: bundle **onedir** com dois executáveis (`screen-watch` console e
  `screen-watch-gui` windowless) que compartilham `PYZ`/`COLLECT`; o script
  `scripts/build_release.py` roda **no SO alvo** (sem cross-build), lê a versão de
  `screen_watch.__version__` e grava `dist/installers/`. Guia completo: [`doc/01`](01-Build_e_Release.md).
- **Checagem passiva de nova versão (v0.11.0)**: `updates.py` faz no máximo **um `GET` anônimo por
  dia** para `https://api.github.com/repos/ph7ti/Screen-Diff-Watcher/releases/latest`
  (`Accept: application/vnd.github+json`, timeout de 5 s, **sem token**), guarda o resultado em
  `state.json` (`update_check`, TTL de 24 h — a tentativa que falhou também é cacheada, então
  aberturas offline não repetem a requisição) e o expõe apenas como linha no log da GUI + item no
  tray que abre o release (**só URLs `https` em `github.com`** são abertas) — **sem popup, sem
  download** e nunca no caminho de captura/loop. A checagem roda uma vez por start da GUI numa
  thread daemon e é desligada com `ui.update_check: false`; o `notified_version` do cache evita
  repetir o aviso. O CLI permanece offline.
- **Tesseract opcional no Windows (v0.11.0)**: o instalador roda o helper fixado e verificado por
  SHA256 **somente com consentimento** — o fluxo interativo pergunta Sim/Não e explica que
  `light`/`default` funcionam sem ele (só o `advanced` precisa); instalação silenciosa (`/SILENT` ou
  `/VERYSILENT`) pula salvo `/TESSERACT=yes`. Qualquer falha do helper avisa e o setup continua; a
  desinstalação preserva o Tesseract.
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
│   ├── 00-Architecture_and_Specification.md            # SSoT (EN)
│   ├── 00-Documento_de_Arquitetura_e_Especificação.md  # este documento (espelho PT)
│   ├── 01-Build_and_Release.md                         # build/release (EN)
│   ├── 01-Build_e_Release.md                           # espelho PT
│   └── releases/                                       # notas por versão (EN + .pt-BR.md)
├── wiki/                          # páginas do GitHub Wiki (uso e recursos)
├── src/
│   └── screen_watch/
│       ├── __init__.py            # __version__ (fonte única)
│       ├── __main__.py            # entry point: python -m screen_watch (só main())
│       ├── cli/                   # CLI: 22 subcomandos (commands.py) + parser (parser.py)
│       ├── app.py                 # orquestração: pipeline + cadeia + sessão + evidências
│       ├── errors.py              # AppError/ConfigError + ERROR_CODES + render_error
│       ├── naming.py              # slugify do nome de arquivo das seleções (puro)
│       ├── updates.py             # checagem passiva de release (parse puro + fetch injetável)
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
│       │   ├── roi.py             # resolução janela+ROI compartilhada (captura e Ver local)
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
│       │   ├── ntfy.py            # NtfyNotifier (httpx; push no celular)
│       │   ├── smtp.py            # SmtpNotifier (smtplib; e-mail)
│       │   ├── mqtt.py            # MqttNotifier (extra opcional paho-mqtt; sem imagem)
│       │   ├── log.py             # JsonlNotifier (logs/alerts.jsonl)
│       │   ├── template.py        # modelo ${campo}/${env:VAR} (string.Template)
│       │   ├── http.py            # WebhookNotifier + HttpPostNotifier (httpx; modelo de payload)
│       │   ├── syslog.py          # SyslogNotifier (SysLogHandler; udp/tcp; severity_map)
│       │   ├── test_send.py       # list_alert_targets + send_test (teste de envio CLI/GUI)
│       │   ├── gate.py            # AlertGate (supressão manual: snooze/mute; state.json)
│       │   └── chain.py           # AlertChain + DispatchOutcome (chave de cooldown = uid; gate)
│       │
│       ├── actions/               # ações pseudo-humanas (opt-in)
│       │   ├── protocol.py        # ActionSpec/ActionStep (puros)
│       │   ├── plan.py            # parse/validação (click exige activate; text_* exige advanced)
│       │   ├── dispatch.py        # ActionDispatcher (on_tick/deadline; ensaio/armado/agendador/limites)
│       │   ├── triggers.py        # avaliador puro dos gatilhos de tempo (at/every/after; clocks injetáveis)
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
│       │   └── selection.py       # JSON de seleção v1/v2 + build_target (overrides) +
│       │                          #   helpers de edição do CLI + name/rename
│       │
│       ├── i18n/
│       │   ├── __init__.py        # catálogo JSON, resolução de idioma, tr()
│       │   ├── pt-BR.json         # fallback
│       │   └── en-US.json
│       │
│       ├── gui/
│       │   ├── main_window.py     # janela (layout; checkboxes; status agregado)
│       │   ├── session_manager.py # SessionManager: N sessões + eventos + preview/calibração
│       │   ├── tray.py            # pystray (iniciar/parar, soneca/silenciar/ciente, por seleção)
│       │   ├── overlay.py         # SelectionOverlay (uma janela por monitor)
│       │   ├── overlay_geometry.py# conversões lógico<->físico (puro, sem Qt)
│       │   ├── mask_overlay.py    # overlay do editor de máscaras
│       │   ├── mask_editor_geometry.py  # geometria do editor de máscaras (puro)
│       │   ├── preview_widget.py  # painel de preview (baseline/último)
│       │   ├── preview_geometry.py# downsample/thumbnail (puro)
│       │   ├── history_dialog.py  # histórico de alertas (logs/alerts.jsonl)
│       │   ├── calibration_widget.py    # gráfico da calibração ao vivo
│       │   ├── calibration.py     # helpers de calibração (puro)
│       │   ├── countdown.py       # contagem de 3 s (overlay sem foco)
│       │   ├── locator.py         # localizador de posição do mouse
│       │   ├── action_editor.py   # editor de ações da seleção
│       │   ├── alert_dialog.py    # diálogo "Testar alerta…" + worker de envio
│       │   ├── hotkeys.py         # hotkeys globais (pynput, lazy)
│       │   ├── help.py            # textos de ajuda (puro)
│       │   ├── hover_help.py      # tooltip de 2 s
│       │   ├── labels.py          # rótulos do catálogo
│       │   ├── highlight.py       # realce transitório da ROI ("Ver local"; nunca pinta a ROI)
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
lógico do Qt — usado apenas nas fronteiras do Qt: o overlay de seleção, o localizador de mouse e o
realce da ROI (§9.5).

Ao iniciar `run`, o app verifica cada monitor, marca os adequados (`OK`, 100%) e avisa se a janela
do target estiver num monitor com escala. `probe-dpi` e `scripts/probe_dpi.py` imprimem a matriz.

**Wayland**: se `is_wayland()` retornar `True`, o `run` exibe mensagem clara e encerra (código 2).
Não tentar capturar; a decisão do spike (portal + PipeWire fora de escopo na 1.x) está no §3.2.

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

**macOS (v0.11.0)**: os ramos de caminhos/áudio/shell existem desde as primeiras portas; o incremento
adiciona a **célula de CI (macos-latest, py3.13, `QT_QPA_PLATFORM=offscreen`)** e o **bundle `.app`
sem assinatura** (`BUNDLE` + `plyer.platforms.macosx.notification`); a captura usa `mss` e portanto
exige a permissão TCC de **Gravação de Tela**; popup/ações exigem Acessibilidade. A validação em
hardware Apple físico (permissões, tray, áudio) é item do checklist da v1.0.0; até lá o build é
publicado como está (o Gatekeeper exige "Abrir" pelo menu de contexto ou
`xattr -d com.apple.quarantine`).

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
  "name": "verificando download",
  "origin_at_selection": [100, 200],
  "roi_relative": [120, 340, 400, 80],
  "mode": "advanced",
  "masks": [],
  "overrides": { "poll_interval_s": 1.5, "rearm": false }
}
```

Campos obrigatórios: `version`, `window_handle`, `origin_at_selection`, `roi_relative`.
`app_name`, `name`, `mode`, `masks` e `overrides` são opcionais com defaults. Seleções `version: 1`
continuam carregando sem `overrides`/`app_name`/`name` (§12.3). `window_title_hint` é apenas hint
humano; o lookup usa `window_handle`. `roi_relative` é a fonte de verdade para reconstruir a ROI a
cada tick. `name` é o nome de exibição (prefixo no rótulo da GUI e no `run`); o **nome do arquivo**
é o slug do nome (`naming.slugify`), que é o valor usado por `--selection`.

**Ciclo de vida headless (v0.9.0)**: todo o ciclo de vida da seleção é via CLI, sem overlay:
`list-windows` → `select-manual --handle H --roi X Y W H [--name N]` → `edit-selection N ...`
(mode/ROI/máscaras/overrides) → `validate-config --selections` → `run --selection N`. O
`list-selections` lista os arquivos e `--json` emite a forma scriptável; `rename-selection OLD NAME`
reusa `plan_rename`/`rename_selection`; `remove-selection NAME...` apaga e limpa o `state.json`
quando `last_selection` apontava para um arquivo removido. O `edit-selection` grava atomicamente
(`dump_selection`) e segue as mesmas regras da GUI: `--mode` atualiza `overrides.mode` quando ele
existe, senão `mode`; `--roi` reancora `origin_at_selection` e limpa **os dois** campos de máscara
(relativos à ROI antiga); `--mask` usa a regra de local efetivo (`set_masks`); `--clear-masks`
esvazia os dois campos; `--poll-interval-s`/`--rearm` gravam em `overrides`; `--clear-override KEY`
remove uma das cinco chaves de override. Os erros são em inglês, exit code 1 (2 para opção de edição
ausente), e o arquivo fica intacto em falha.

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

Cursor, spinner de loading, relógio, indicador de rede, qualquer coisa que pisque.

**Editor visual de máscaras (v0.8.0)**: a GUI tem o botão **Editar máscaras…** (grupo Seleções) que
abre um overlay transparente por monitor sobre a janela alvo. Arrastar com o botão esquerdo
**adiciona** uma máscara; clique direito sobre uma máscara existente **remove**; **Enter confirma**
(grava o JSON da seleção) e **Esc cancela** (sem gravar). As máscaras continuam em pixels físicos
relativos à ROI, então acompanham a janela. O editor é **bloqueado com a sessão rodando** (mesma regra
do rename) porque a ROI está sendo medida; diferente do Highlight (pitfall 23), este overlay é modal e
pode pintar sobre a ROI justamente porque o monitoramento está parado. Ele grava onde as máscaras
efetivas vivem (§12.3) e a escrita é atômica (§12.4). A geometria (ROI em lógico local da tela,
drag → máscara, clamp, hit-test) vive no módulo puro `gui/mask_editor_geometry.py`; o overlay Qt é
`gui/mask_overlay.py::run_mask_editor`.

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

A mesma ancoragem vale para **pontos** e para a **direção inversa** (helpers puros em
`gui/overlay_geometry.py`, testáveis sem display): `point_to_physical` (localizador de mouse — o
`QCursor.pos()` é lógico, o runner/`pynput` é físico; ancora no monitor sob o cursor via `screenAt`),
`point_to_logical` e `rect_to_logical` (realce "Ver local" — o retângulo vem do caminho físico e o Qt
pinta lógico). **Regra**: toda fronteira Qt ↔ físico converte **exatamente uma vez**, ancorada na
origem do monitor; o overlay de seleção, o localizador de mouse e o realce são as únicas fronteiras
do Qt (v0.10.1).

### 9.6 Validação pós-drag

Antes de persistir:

1. **Área mínima**: rejeitar retângulos com menos de 10×10 pixels lógicos (`MIN_ROI_SIDE = 10`).
2. **Dentro da janela-alvo**: converter para relativo e checar com `fits_in_window`. Se extrapolar
   (x/y < 0 ou x+w/y+h além da janela), **rejeitar** com `runtime.roi_outside_window` e não
   persistir — uma ROI fora da janela faria o tick capturar uma região alheia ao alvo (ex.: outro
   monitor), gerando prints/alertas que não correspondem à janela. *(Mudou de "permitir mas logar
   warning" — o comportamento antigo gerava prints errados em silêncio.)*
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

**Verificação de texto (`compare/text_watch.py::TextWatchStrategy`, opcional)**:

```python
class TextWatchStrategy:              # envolve o OCRTextDiffStrategy no modo advanced
    name = "advanced"
    def initialize(self, baseline):   # OCR do baseline; guarda present_before
    def compare(self, current):       # changed = transição de presença esperada (severity=3)
                                      # detail = {baseline_text, current_text, ocr_score,
                                      #           ocr_threshold, text_watch: {...}}
```

- **Semântica de filtro**: com um `text_watch` configurado (`compare_options.advanced.text_watch` no
  perfil ou `overrides.text_watch` na seleção, que tem precedência), o alerta dispara **somente na
  transição** escolhida (`expect: appears|disappears`); as demais mudanças de texto não disparam. O
  `changed` do OCR **não** é propagado — só o veredito do filtro é autoritativo — e `score`/
  `threshold` do OCR ficam no `detail` (visíveis no `compare-modes`).
- **Casamento**: substring, com `case_sensitive: false` e `ignore_accents: true` por padrão
  (NFKD + remoção de diacríticos nos dois lados). `text` é obrigatório (não vazio).
- **Severidade = 3** na transição (evento definitivo): uma severidade derivada do score do OCR
  poderia ficar abaixo do `severity_min` e o alerta falharia em silêncio.
- **A presença acompanha o stream** (filtro de borda): a transição dispara uma vez; re-arm/re-baseline
  recalculam a presença do baseline, então o estado nunca dessincroniza.
- **Somente `advanced`** (`config.text_watch_needs_advanced` fora dele); a GUI limpa o override ao
  trocar o modo.
- Como ele decide o `changed`, **as ações também só rodam na transição**.

### 10.5 Pipeline com curto-circuito

```python
MODE_STAGES: dict[str, tuple[str, ...]] = {
    "light": ("light",),
    "default": ("default",),
    "advanced": ("default", "advanced"),  # gate de phash: OCR só roda quando os pixels mudaram
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

**Decisão registrada (atualizada)**: o `advanced` roda `("default", "advanced")` — o phash roda
**antes** do OCR como *gate de pixel*: o OCR só roda/pontua quando os pixels mudaram, o que cortou
falsos positivos repetidos em quadros quase idênticos (ruído de OCR em tela estática). **Com um
`text_watch` configurado o gate é bypassado** (`build_pipeline` monta `("advanced",)`): o OCR roda a
cada tick e o veredito do filtro (presença/ausência, não similaridade) é autoritativo, de modo que a
transição nunca é escondida pelo gate; o custo aceito é OCR por tick (100–500 ms, intervalo default
2 s). O mecanismo de curto-circuito permanece implementado e testado para outras composições
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
  independentemente de novas mudanças (inclusive em falha — backoff, ver §11.3). A chave é o **`id`**
  do alerta (`uid`), não o nome da classe (§11.2).
- `frame` é passado completo para permitir anexar a imagem do ROI (Telegram) ou logar contexto.

### 11.2 Notificadores do protótipo

**Som (`sound.py`)**:
- Toda a reprodução passa pela fronteira `platform/audio.py`; `alerts/` **não** conhece
  `sys.platform`, Qt nem miniaudio.
- **Camadas** (ordem de despacho): **Qt** (`QMediaPlayer`/QtMultimedia, criado no thread da GUI por
  `install_qt_player()`; reprodução enfileirada com `QueuedConnection`, então a thread do loop nunca
  toca em Qt) → **miniaudio** (dependência core; CLI/`run`; roda numa **thread daemon**, WAV/MP3/OGG/
  FLAC, sem AAC/M4A) → **legado** (`winsound`, só WAV; `paplay`/`aplay -q`/`ffplay`/`afplay`).
- Matriz de formatos por contexto: a GUI no Windows/macOS (Media Foundation/AVFoundation) toca
  M4A/AAC; no Linux a GUI depende dos plugins do GStreamer; o CLI depende do miniaudio (M4A/AAC só
  com player externo, senão `beep`).
- `file` relativo é resolvido por `platform/audio.py::resolve_sound_path` nesta ordem:
  **`app_home()/sounds`** (usuário) → **`resources.bundled_sounds_dir()`** (`screen_watch/assets/sounds`,
  onde mora o `alert.mp3` default) → **CWD**. Um `file` absoluto é usado como está; um arquivo do
  usuário sempre vence o empacotado. Arquivo ausente ou formato sem decoder → `beep()` + aviso no log
  (nunca silêncio/exceção).
- **Default `"alert.mp3"`** (empacotado): `AlertOptions.file`, o `parse` de `loader.py` e o
  `SoundNotifier` usam `"alert.mp3"`. Configs antigas com `alert.wav` (ou outro caminho) não mudam;
  o default novo só vale para configs novas ou quando o usuário trocar a linha.
- Extra opcional `simpleaudio` (`pip install -e ".[sound]"`); **não** entra nos instaladores (sem
  wheel confiável para Python 3.13) e só é tentado para WAV.
- **Não usar** `playsound` (abandonado).
- **Seletor de som grava no YAML (v0.8.0)**: após escolher um arquivo, a GUI pede confirmação e grava
  `file:` no primeiro alerta `type: sound` do **perfil ativo** via
  `config/loader.py::set_profile_sound_file`, criando o alerta com o shape default quando ele não
  existe. O `save_config` é atômico e mantém `config.yaml.bak`, então falha de escrita deixa o
  original intacto. Config v1 é recusada (`config.v1_not_editable`) com mensagem apontando o
  `migrate-config`. Quando a seleção atual tem `overrides.alerts`, esse override substitui os alertas
  do perfil, então a GUI avisa (`dialog.sound_override_warning`) que o som não valerá para ela.

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

**ntfy (`ntfy.py`, v0.9.0)**:
- `POST` de texto puro em `{server}/{topic}` com headers `Title`, `Priority` (mapeamento
  severidade→1..5, default `1→3`, `2→4`, `3→5`) e `Tags` opcional; `attach_roi: true` troca para
  `PUT` de imagem (`Filename: roi.png`, o header `Message` carrega o texto renderizado).
- `token_env` é **opcional** e vazio por default (tópico anônimo); quando definido para uma variável
  ausente, o notificador loga e pula (mesma regra do Telegram). Erros
  (`alert.ntfy_unavailable`, `alert.ntfy_status`) carregam apenas o servidor redigido
  (`scheme://host/…`).

**E-mail / SMTP (`smtp.py`, v0.9.0)**:
- Stdlib `smtplib` + `email.message.EmailMessage`; `security` é `starttls` (default), `ssl` ou
  `none`. `subject`/`message` são templates (mesmas regras de `${...}`, §11.2 webhook); `attach_roi`
  anexa o PNG da ROI como `image/png`.
- `host`, `from_addr` e uma lista `to` não vazia são obrigatórios no load da config. `username_env`/
  `password_env` (defaults `SMTP_USERNAME`/`SMTP_PASSWORD`) fazem login apenas quando a variável do
  usuário está definida; segredos nunca aparecem em erros/logs.
- Erros: `alert.smtp_unavailable` (conexão/TLS), `alert.smtp_auth_failed` (login),
  `alert.smtp_send_failed` (mensagem rejeitada); o texto do servidor é sanitizado de credenciais.

**MQTT (`mqtt.py`, v0.9.0)**:
- Extra opcional `mqtt` (`paho-mqtt`); o import é lazy. Um canal configurado sem o extra levanta
  `alert.mqtt_missing_extra` (visível como `FAILED`, nunca um skip silencioso).
- `host`/`topic` obrigatórios; `port` default 1883 (8883 quando `tls`), `qos` 0/1/2, `retain`,
  `client_id`, `username_env`/`password_env` (mesmos defaults do SMTP). O payload é um mapeamento de
  template (default `text`/`target`/`severity`/`strategy`/`score`/`threshold`/`timestamp`) ou
  `payload_raw`. **Sem imagem**.
- Erros: `alert.mqtt_unavailable` (conexão), `alert.mqtt_publish_failed` (publicação rejeitada).

**Log (`log.py`)**:
- `JsonlNotifier`: uma linha JSON por disparo em `app-data/logs/alerts.jsonl` (ou caminho
  configurado em `path`). Campos: `ts`, `strategy`, `changed`, `score`, `threshold`, `severity`,
  `window_handle`, `absolute_rect`, `sequence`, `detail`. O registro **não tem** canal/alvo/caminho
  de evidência, então o histórico da v0.8.0 filtra data/severidade/modo e localiza o print
  best-effort (o `*_change.png` mais próximo em ±2 s — `alerts/history.py`).

**Webhook / HTTP POST (`http.py`)**:
- `post_json` faz `POST`/`PUT`/`PATCH` JSON via `httpx`, redirects **não** seguidos, sucesso = 2xx
  (não-2xx → `alert.http_status`; falha de rede → `alert.http_unreachable`).
- `WebhookNotifier` usa `url` ou `url_env`; `HttpPostNotifier` também aceita `scheme`/`host`/`port`/
  `path`. Payload default `{"text": "${message}"}`; `payload_raw` envia um corpo que não é objeto.
- **Modelo de payload** (`alerts/template.py`): `string.Template` com `idpattern` estendido para
  `${env:VAR}` (lido de `os.environ` **no envio**); placeholders `message`, `strategy`, `score`,
  `threshold`, `severity`, `target`, `timestamp`, `window_handle`, `changed`, `roi`. Placeholder
  desconhecido é erro de config (`config.alert_unknown_placeholder`).
- **Segredos**: a URL resolvida é redigida (`scheme://host/…`) em erros/logs; `verify_tls: false`
  avisa **a cada envio**.
- **Sem imagem/ROI** (o print anexado continua exclusivo do Telegram).

**Syslog (`syslog.py`)**:
- `logging.handlers.SysLogHandler` para `(host, port)`; `socktype=SOCK_DGRAM` (udp, default) ou
  `SOCK_STREAM` (tcp); `facility` default `local0`; `app_name` vira o `ident`/tag; `append_nul=False`.
- `timeout=` no `SysLogHandler` só existe no Python 3.14, então o `createSocket` é sobrescrito para
  chamar `settimeout`; no Windows, use **UDP**.
- **Informational por default** (a severidade real vai no texto via `${severity}`), com `severity_map`
  opcional (chaves 0..3). UDP é *fire-and-forget* (não confirma entrega) → prefira TCP quando a entrega
  precisa ser confirmada.

**`id` e chave de cooldown**:
- Cada alerta tem `id` opcional (default `type`; `type#n` quando repetido no mesmo perfil, validado).
  O `build_notifier` atribui `notifier.uid = id or type`; o `AlertChain` usa
  `getattr(n, "uid", n.name)` como chave, então dois webhooks não compartilham o cooldown.
- O seletor de som da GUI edita o alerta `sound` do perfil ativo **em disco** via
  `set_profile_sound_file` + `save_config` (atômico, `.bak`, comentários não preservados — §12.4);
  config v1 é recusada com `config.v1_not_editable`.

**Regra**: tipo desconhecido é **erro de config** (`config.alert_unknown_type`) — o `build_notifier`
mantém um `log.warning` + `None` defensivo.

### 11.3 Encadeamento, desfechos e re-arm

```python
class AlertChain:
    def __init__(self, notifiers, gate: AlertGate | None = None): ...
    def dispatch(self, result: ComparisonResult, frame: Frame) -> DispatchOutcome:
        # gate ativo (snooze/mute) -> SUPPRESSED_MANUAL (nenhum notificador é tentado)
        # sem notificadores habilitados -> NONE_ENABLED
        # nenhum com severity >= severity_min -> BELOW_MIN
        # para cada elegível fora do cooldown: notifica; falha não impede os demais
        #   -> FIRED (algum disparou) / FAILED (todos falharam) /
        #      SUPPRESSED_COOLDOWN (todos em cooldown)
```

**Desfechos** (`DispatchOutcome`): `FIRED`, `SUPPRESSED_COOLDOWN`, `SUPPRESSED_MANUAL`, `BELOW_MIN`,
`NONE_ENABLED`, `FAILED`. O `MonitorSession` usa o desfecho para o **re-arm edge-triggered**:

- Com `rearm: true` (default), o baseline avança após `FIRED`, `BELOW_MIN` ou `NONE_ENABLED` — uma
  mudança sustentada alarma uma vez, e uma nova mudança realarma.
- Em `SUPPRESSED_COOLDOWN`, `SUPPRESSED_MANUAL` e `FAILED` o baseline é **mantido**: a mudança
  pendente alarma quando o cooldown/snooze expirar ou o mute for levantado, e falhas são re-tentadas
  respeitando o cooldown (backoff) — sem martelar a cada tick.
- Falha em um notificador registra a tentativa (`_last_attempt`) e não impede os demais; cada um tem
  seu próprio `try`.
- Re-arm manual: tray/botão "Re-armar baseline"/hotkey `rearm`, via `MonitorSession.request_rebaseline()`
  (thread-safe) ou `rebaseline_now(frame)`.

**Supressão manual (`AlertGate`, v0.9.0)**: um gate thread-safe compartilhado pelas sessões guarda
`snooze_until` (epoch) e `muted`, inicializados do `state.json` (`alerts_snooze_until`,
`alerts_muted`) e persistidos a cada mudança na GUI/tray. Enquanto ativo, o `dispatch` retorna
`SUPPRESSED_MANUAL` antes de olhar os notificadores e o baseline é mantido, então a mudança pendente
é reportada quando o snooze expirar ou o mute for levantado. Um `test-alert` explícito ignora o
gate. Um snooze pode sobreviver a uma mudança transitória: se a tela voltar ao baseline antes de ele
expirar, a mudança pendente é descartada (risco documentado de usar snooze).

**Escalação (repetir até o acknowledge, v0.9.0)**: `defaults.escalation` (ou
`overrides.escalation`) tem `enabled` (default false) e `severity_min` (default 2). Com ela
habilitada e um desfecho `FIRED` com `severity >= severity_min`, o baseline **não** avança;
`MonitorSession.awaiting_ack` fica true e cada tick seguinte despacha de novo — a cadência de
repetição é o `cooldown_s` de cada alerta (não existe intervalo de escalação separado). O
`acknowledge()` (botão da GUI, item do tray, `ui.hotkeys.acknowledge` opcional) limpa o estado e
re-arma o baseline no frame seguinte, parando as repetições; o `rearm` manual faz o mesmo. Se a
mudança desaparecer sozinha, a escalação ainda espera um acknowledge explícito. Evidência:
`record_change` é gravado **somente quando a cadeia realmente tentou uma entrega** (`FIRED`/
`FAILED`) — uma mudança suprimida por cooldown/snooze/mute ou abaixo do mínimo não grava mais print
a cada tick (§11.5).

### 11.4 Ações pseudo-humanas (opt-in, `actions/`)

Reação **separada** dos alertas: o gatilho `change` é avaliado depois do `AlertChain.dispatch` quando
`result.changed`, e os gatilhos de tempo são avaliados em **todo frame pós-baseline** (mesmo sem
mudança) — em ambos os casos **sem alterar** o `DispatchOutcome` nem o re-arm dos alertas. Só executa
quando **armada**; por padrão fica em **ensaio** (dry-run), que registra o que faria e grava
evidências, sem clicar. Os gatilhos de tempo **não têm ensaio**: armado é o único estado em que são
avaliados.

- **Gatilho (v0.10.0)**: exatamente um por ação, `when.trigger` = `change` (padrão) | `at` | `every` |
  `after`.
  - `change` mantém a semântica anterior: `changed` (só `true` é aceito; `changed: false` é erro de
    validação), `severity_min` efetivo (`when.severity_min` > `severity_min`) e filtros de OCR
    (`text_any`/`text_all`/`text_regex`, case-insensitive por padrão). Filtros de texto exigem
    `mode: advanced` (validação recusa nos demais modos).
  - `at`: `at: ["HH:MM", ...]` (24 h) + `days` opcional (nomes de 3 letras `mon`..`sun`, o mesmo
    conjunto do `schedule.days`; ausente = todos os dias). Dispara quando o horário é **cruzado com
    as ações armadas**; a referência de cruzamento reinicia no armar, então horários já passados no
    dia não disparam.
  - `every`: `every_s >= 1`; a fase começa ao armar e **reinicia a cada disparo** (próximo vencimento
    = disparo + `every_s`); rearmar reinicia a fase; sem rajada e sem catch-up após sleep/suspensão
    (um vencimento mais velho que a tolerância é registrado como `missed`).
  - `after`: `after_s >= 1`, atraso único relativo ao armar; desarmar cancela, rearmar reinicia;
    dispara uma única vez (`done` até o próximo armar).
  - Gatilhos de tempo não aceitam os campos de `change` (`changed`, `severity_min`, `text_*`,
    `case_sensitive`) e são rejeitados com `rebaseline: true`; `cooldown_s >= every_s` é erro no
    `every`. Ocorrências atrasadas mais de **60 s** (tolerância/grace) viram
    `skipped -> missed` no `logs/actions.jsonl` e nunca executam; o relógio local ingênuo do `at`
    permite que o DST dobre ou perca um disparo (limitação documentada). O avaliador é o módulo puro
    `actions/triggers.py` (relógios injetáveis; `at` usa tempo de parede, `every`/`after` o relógio
    monotonic do arming, de `ArmingController.armed_since`).
- **Passos**: `activate`/`click`/`move`/`type`/`key`/`wait`; `ref` é `roi` (relativo a
  `frame.absolute_rect`), `window` (`frame.window_rect`) ou `screen`. Clique exige `activate` antes
  (foco explícito + verificação `isActive`). Como o `SetForegroundWindow` do Windows é
  assíncrono/bloqueado (foreground lock), o foco é confirmado com pequenas pausas (até ~0,5 s antes
  de abortar); o motivo distingue `activate recusado` de `foco não confirmou`
  (`focus_changed: ...`).
- **Humanização** (`defaults.humanize`, §12.2): movimento do mouse interpolado em `mouse_steps`
  pontos com `jitter_px`; pausas com jitter de `wait_jitter_ms`; digitação com intervalo default de
  `key_interval_ms`; `seed` para testes determinísticos.
- **Cooldown**: um gatilho ignorado por `cooldown_s` (change ou tempo) **não** vai para o JSONL
  (para não poluir), mas é publicado no log ao vivo como `skipped -> cooldown`.
- **Limites**: `max_per_min` (janela móvel de 60 s) e `max_per_session`, checados antes da execução
  (`reason: rate_limited` no resultado/auditoria).
- **Execução síncrona na thread do loop**: captura/comparação pausam durante a sequência
  (sem re-entrância); `settle_s` ao final. Entre passos, o runner re-checa arming/aborto. O
  `on_tick` roda na mesma thread; o loop limita a espera pelo próximo deadline armado
  (`ActionDispatcher.next_deadline_delay()`, §3.5) para o `at` disparar na hora.
- **Re-arm**: `rebaseline: false` por padrão (o baseline permanece após a ação); `rebaseline: true`
  opt-in repete o gatilho (relatório/página). Re-arm manual em runtime (tray/botão/hotkey `rearm`,
  via `MonitorSession.request_rebaseline()`).
- **Ensaio x armado**: `ArmingController` com estados `disarmed`/`armed`/`timed`; estado só em
  memória, começa desarmado a cada sessão. `Esc` aborta na hora (`aborted`). Gatilhos de tempo não
  são avaliados enquanto desarmado (estado resetado no próximo armar; `armed_since` reinicia a
  fase/referência de cruzamento).
- **Agendador (portão de suspensão)**: fora da janela de horário a ação é suspensa
  (`suspended_schedule`); nos gatilhos de tempo a ocorrência vencida é **consumida** pela suspensão
  (sem replay quando a janela reabre). Monitoramento e alertas seguem. O `schedule` nunca dispara
  nada: o disparo é decidido apenas pelo `when.trigger`.
- **Auditoria**: `logs/actions.jsonl` (ensaio, execução, suspensão, `missed`, motivo, duração e
  caminhos das evidências). Todo registro carrega `trigger` (`change`/`at`/`every`/`after`).
- **Criação pela GUI**: `gui/action_editor.py` (`Nova ação...`/`Editar...`/`Remover ação`) grava em
  `overrides.actions` do JSON de seleção, incluindo o seletor de gatilho da v0.10.0 (`change` mantém
  os campos de when/severidade; `at`/`every`/`after` mostram só os próprios campos). Como
  `resolve_actions` lê os overrides antes do perfil, isso funciona também com config v1 (`targets:`),
  sem migração. A validação reusa `parse_actions` (clique exige `activate`, `text_*` exige
  `mode: advanced`, regras dos gatilhos de tempo inclusas), então as regras do YAML valem na janela;
  ações do perfil/YAML são somente leitura na GUI.
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
  comandos de tray/hotkey); a fonte de verdade continua sendo o JSONL. Os payloads carregam
  `trigger`.
- **Contagem de 3s**: fluxos avulsos (`test-action --armed`, `record-actions` e o botão "Executar
  ação (3s)" da GUI) usam `gui/countdown.py::run_countdown` — overlay Qt sem borda, always-on-top e
  `WindowDoesNotAcceptFocus`, **sem** `activateWindow` (a janela-alvo pode ser focada durante a
  contagem); clique cancela. Instanciado por `gui/qt_app.py::ensure_app` com `QEventLoop` (chamável
  de dentro da GUI). O disparo automático do loop **não** tem contagem. Fallback textual no console
  sem Qt/display. Fluxos avulsos ignoram o gatilho da ação (execução explícita) e imprimem
  `trigger <t> ignored (explicit run)`; o `record-actions` segue gerando o `when` comentado (change)
  mais uma dica comentada dos campos de gatilho de tempo.
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
- **Prints de mudança atrelados às tentativas de entrega (v0.9.0)**: o `record_change` roda somente
  quando o desfecho da cadeia é `FIRED`/`FAILED`; uma mudança mantida pendente por
  cooldown/snooze/mute/abaixo do mínimo não grava um print por tick (os prints de baseline não
  mudam). Durante a escalação os prints acompanham cada disparo.
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
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.mp3" }
      - { type: "popup",    enabled: true, severity_min: 1, cooldown_s: 30 }
      - { type: "telegram", enabled: true, severity_min: 2, cooldown_s: 60,
          bot_token_env: "TELEGRAM_BOT_TOKEN", chat_id: "123456789", attach_roi: true }
      - { type: "log",      enabled: true, severity_min: 1, cooldown_s: 0 }   # opcional
      - type: webhook                    # Teams Workflows / Slack / Discord / Mattermost…
        id: teams
        severity_min: 2
        cooldown_s: 60
        options: { url_env: TEAMS_WEBHOOK, payload: { text: "Mudança em ${target} sev=${severity}" } }
      - type: http_post
        id: erp-api
        options: { scheme: http, host: "10.0.0.20", port: 8080, path: "/alerta" }
      - type: syslog
        id: siem
        options: { host: "10.0.0.9", port: 514, protocol: udp, facility: local0 }
      - type: ntfy                     # push no celular (v0.9.0)
        id: celular
        options: { server: "https://ntfy.sh", topic: "meu-topico-secreto",
                   token_env: NTFY_TOKEN, priority_map: { 1: 3, 2: 4, 3: 5 },
                   attach_roi: true }
      - type: smtp                     # e-mail (v0.9.0)
        id: email
        options: { host: "smtp.example.com", port: 587, security: starttls,
                   from_addr: "watch@example.com", to: ["oncall@example.com"],
                   username_env: SMTP_USERNAME, password_env: SMTP_PASSWORD }
      - type: mqtt                     # extra opcional `mqtt` (v0.9.0)
        id: barramento
        options: { host: "10.0.0.30", topic: "screen-watch/default",
                   qos: 1, retain: false, username_env: MQTT_USERNAME,
                   password_env: MQTT_PASSWORD, tls: false }
    actions: []                  # ver §11.4
  trabalho:
    defaults: { mode: "default", poll_interval_s: 1.0 }
ui:
  hotkeys: { arm: "<ctrl>+<alt>+a", disarm: "<ctrl>+<alt>+d", toggle: "<ctrl>+<alt>+<space>",
             rearm: "<ctrl>+<alt>+r", abort: "<esc>" }
  arm_durations_min: [1, 5, 15, 30]
  language: auto                 # auto | pt-BR | en-US | tag descoberta em i18n/*.json
  update_check: true             # checagem passiva de release no GitHub (1 GET/dia; opt-out)
schedule: { enabled: false, days: [mon, tue, wed, thu, fri], windows: ["08:00-12:00"] }
evidence: { enabled: false, dir: null, keep_per_target: 50, max_total_mb: 200,
            on_baseline: true, on_change: true, per_step: false }
```

**Regras**:
- Tokens e segredos **nunca** no YAML. Usar variáveis de ambiente (`bot_token_env`, `url_env`,
  `${env:VAR}` em `headers`/`payload`); erros/logs nunca expõem a URL resolvida nem os valores das
  variáveis.
- `type` de alerta: `sound`/`popup`/`telegram`/`log` mantêm **campos planos**;
  `webhook`/`http_post`/`syslog`/`ntfy`/`smtp`/`mqtt` usam um bloco aninhado **`options:`**. `type`
  desconhecido é `ConfigError` (`config.alert_unknown_type`).
- Cada alerta tem **`id`** opcional (default `type`; `type#n` quando repetido), usado como **chave de
  cooldown** e no teste de envio. `payload` XOR `payload_raw`; `${...}` desconhecido → `ConfigError`.
- `version` aceita 1 ou 2 (outro valor é `ConfigError`); v2 **exige** `profiles`; `profile`
  inexistente é `ConfigError` (`config.profile_unknown`).
- `version` ausente com `targets:` é o v1 legado: carrega por uma versão, com aviso, e é convertido
  por `migrate-config` (backup `config.yaml.bak`, uma seleção JSON por target).
- `ui.language` desconhecido gera aviso e volta para `auto` (não é erro).
- `ui.update_check` (default `true`) liga a checagem passiva de release (§3.8): best-effort, com
  cache, nunca bloqueante e sem baixar nada.
- `TargetConfig` continua sendo o contrato interno do runtime; o perfil + a seleção são resolvidos
  para ele por `persistence.selection.build_target`.

### 12.2 Perfis e defaults

Perfis nomeados (`profiles.<nome>.defaults` + `.alerts` + `.actions`) permitem alternar conjuntos de
parâmetros com `--profile` (CLI) ou o seletor da GUI/tray. A troca **aplica no próximo start** (não
ao vivo). O perfil ativo também é gravado em `state.json.profile`.

`defaults` cobre: `mode`, `poll_interval_s` (>= 1.0), `rearm`, `compare_options`, `humanize`
(§11.4) e `escalation` (`enabled`/`severity_min`, §11.3; também aceita override por seleção). O
`humanize` não tem UI própria: edite o YAML (a GUI cria ações, não humanização).
Os perfis também carregam `actions:`; o `when:` de cada ação aceita
`trigger: change|at|every|after` (§11.4) — `at`/`days`/`every_s`/`after_s` são os campos dos
gatilhos de tempo da v0.10.0 e `days` reusa os nomes do `schedule` (`mon`..`sun`).
`ui.snooze_minutes` lista as durações oferecidas pelo menu Snooze (GUI + tray); `ui.max_sessions`
(default 4, faixa 1..16) limita as sessões simultâneas da GUI (§3.5); `ui.update_check` (default
`true`) liga/desliga a checagem passiva de release (§3.8).

### 12.3 Seleção JSON e overrides

Cada seleção é um JSON v2; `overrides` é opcional e **substitui** (não soma) os valores do perfil
para aquele alvo: `mode`, `poll_interval_s`, `rearm`, `masks`, `alerts`, `actions` e `text_watch`
(o override do filtro é aplicado em `compare_options.advanced`). Seleções
`version: 1` continuam carregando sem overrides.

```json
{
  "version": 2,
  "window_handle": 123456,
  "window_title_hint": "ERP - Estoque",
  "app_name": "ERP",
  "name": "verificando download",
  "origin_at_selection": [100, 200],
  "roi_relative": [120, 340, 400, 80],
  "mode": "advanced",
  "masks": [],
  "overrides": { "poll_interval_s": 1.5, "rearm": false,
                 "text_watch": { "text": "CONCLUÍDO", "expect": "appears" } }
}
```

**Precedência do modo**: `mode` explícito do `build_target` (seletor da GUI) > `overrides.mode` >
`selection.mode`. Overrides de `actions` são parseados com o modo resolvido (filtros `text_*`
exigem `advanced`; §11.4) e o `text_watch` também (`config.text_watch_needs_advanced` fora dele).
`window_title_hint` é apenas hint humano; o lookup usa `window_handle`.

**Nome e renomeação** (`name`, opcional): o `build_target` copia para `TargetConfig.label`, que a
GUI/CLI prefere ao stem do arquivo no status/`run`; o stem continua sendo a chave do arquivo
(`state.json:last_selection`, seleção de ações). O campo da GUI confirma pelo botão Renomear ou
Enter: `plan_rename` calcula o slug (`naming.slugify`, sem acentos, máx. 60) e `rename_selection`
grava o destino + remove o antigo, **nunca sobrescrevendo** (conflito →
`selection.name_conflict`) e com rollback em falha (`selection.rename_failed`); slug igual ao stem
atual é no-op que só grava `name`. O `last_selection` é atualizado quando apontava para o nome
antigo. Renomear é bloqueado com sessão rodando.

**Reedição da região (GUI)**: o duplo clique reabre o overlay para a janela da seleção e regrava
`roi_relative`/`origin_at_selection`, preservando `name`, `mode`, `overrides`, `app_name` e
`window_title_hint`; as `masks` (tanto `selection.masks` quanto `overrides.masks`) são **limpas**
por serem relativas à ROI antiga.

**Editor de máscaras (GUI, v0.8.0)**: o editor carrega as máscaras **efetivas** (`overrides.masks`
quando a chave existe — tem precedência — senão `selection.masks`) e grava no **mesmo lugar**:
`overrides.masks` existente é atualizado, senão `selection.masks` não vazio, senão cria
`overrides.masks` (específico do alvo, precedência maior). Nunca migra nem limpa o outro campo em
silêncio, e salvar a mesma lista vazia quando nenhum campo tinha conteúdo é no-op. A gravação usa o
`dump_selection` atômico (§12.4).

**Ciclo de vida da seleção no CLI (v0.9.0)**: `edit-selection`, `rename-selection` e
`remove-selection` aplicam as mesmas regras de precedência na linha de comando (detalhes em §7.3);
`list-selections --json` expõe o arquivo resolvido/modo/contagem de máscaras efetivas/chaves de
override para script.

### 12.4 Estado, app-data e gravação

`platform/paths.py` centraliza `app_home()`, `config_path()`, `selections_dir()`, `logs_dir()`,
`sounds_dir()` (sons do usuário: `file` relativo procura lá primeiro) e `state_path()`.
Os sons empacotados ficam em `resources.bundled_sounds_dir()` (`screen_watch/assets/sounds`, o
`alert.mp3` default); a ordem de resolução é usuário → pacote → CWD (§11.2).
Base: `%APPDATA%\screen_watch` no Windows, `~/.config/screen_watch` no Linux,
`~/Library/Application Support/screen_watch` no macOS, ou o override `SCREEN_WATCH_HOME`.

`state.json` guarda `{"last_selection": "...", "profile": "...", "language": "...",
"action_selection": {"<seleção>": ["nome-da-acao", ...]}, "evidence_enabled": true|false,
"alerts_muted": false, "alerts_snooze_until": 0.0, "update_check": {"checked_at": 0.0,
"latest": "vX.Y.Z", "url": "https://...", "notified_version": "vX.Y.Z"}}` e é atualizado ao iniciar
`run`/GUI com sucesso (as chaves `action_selection`, `evidence_enabled`, `alerts_muted`,
`alerts_snooze_until` e `update_check` são opcionais e retrocompatíveis). As duas chaves do gate de
alertas alimentam o `AlertGate` no próximo start da GUI/`run` (§11.3); um `alerts_snooze_until`
expirado é simplesmente ignorado. O cache `update_check` alimenta a checagem passiva de release
(§3.8) e deve ser gravado via `update_state` (load-modify-write), nunca `save_state`.

O YAML é regravado de forma atômica (temp + `os.replace`) com backup `config.yaml.bak` **sem
preservar comentários**; `state.json` é atômico, sem backup; o JSON de seleção (`dump_selection`)
também é atômico (temp + `os.replace`), sem backup. O `migrate-config` recarrega do disco
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
- **Agendador × gatilhos** (`scheduler/schedule.py::is_open`, função pura com relógio injetável;
  `gate()` devolve o callable): o `schedule` é só o **portão de suspensão** — nunca dispara nada. O
  disparo é decidido pelo `when.trigger` de cada ação (§11.4): `change` reage às mudanças detectadas;
  `at`/`every`/`after` são por tempo e exigem armar. Fora da janela de horário apenas as **ações**
  são suspensas (`suspended_schedule`, consumindo um vencimento de gatilho de tempo); captura,
  comparação e alertas seguem. Janelas que cruzam a meia-noite são aceitas; agendador ligado sem
  `days`/`windows` não restringe.
- **Gravador** (`actions/recorder.py` + `record-actions`): com o extra `input`, captura
  cliques/teclas (`F10` encerra), converte coordenadas absolutas para `ref: roi`/`window`/`screen` e
  gera um snippet de `actions:` com `when` comentado. Padrão: contagem de 3s e gravação automática
  (a contagem roda na thread principal, antes dos listeners do `pynput`); `--no-countdown` mantém o
  `F9` explícito. Cliques fora da janela caem para `ref: screen`. O snippet mantém o `when`
  comentado (gatilho change) e acrescenta uma linha comentada com os campos de gatilho de tempo
  (`trigger`/`at`/`days`/`every_s`/`after_s`); o gravador nunca grava um gatilho.
- **Seleção de ações na UI**: checklist "Ações da sessão" (`describe_action`/`describe_actions` em
  `actions/summary.py`) + contador "N de M"; persiste por nome de seleção
  (`actions/selection.py::load_action_selection`/`save_action_selection`) e vale no próximo start.
  No CLI, `--actions a,b|all|none` (one-shot, não persiste, precede o salvo) e `list-actions` para
  conferir; `run` imprime o resumo e as linhas ao vivo
  `[action] rehearsal|armed <nome> -> ok|failed|rehearsal`.
- **Testes/validação**: `is_open` e o avaliador de gatilhos com relógios falsos, conversão do
  gravador sem listener real e troca de perfil (próximo start).

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
- `ConfigError` herda de `AppError` (não de `ValueError`); o loader converte erros de ação
  (`ActionError`) em `ConfigError` preservando código/params.
- A GUI chama `render_error(exc)`, que traduz `error.<code>` pelo catálogo ativo e cai para
  `str(exc)` quando não há código/tradução.
- Códigos são **estáveis** (contrato com os catálogos): renomear um código quebra a tradução.
- Canais de alerta acrescentam códigos `config.alert_*` (tipo desconhecido, options/URL/porta/protocolo/
  facility/method, conflito de payload, placeholder desconhecido, severity map, id duplicado) e os de
  runtime `alert.http_status`/`alert.http_unreachable`/`alert.syslog_unavailable`;

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
são os originais; os itens 16–29 foram registrados durante a implementação.

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
23. **Pintar sobre a ROI no realce**: nunca. A camada escura é calculada **fora** da ROI
    (`dim_rects`) e a borda é desenhada 2 px por fora do buraco; um único pixel pintado dentro da
    ROI pode virar falso positivo se um tick capturar durante os 2 s do realce (§3.7).
24. **Usar `itemActivated` para o Enter na lista de seleções**: nunca. Ele também dispara no duplo
    clique, o que iniciaria/pararia e reeditaria a região no mesmo gesto; usar `QShortcut` com
    `WidgetShortcut` (§3.7).
25. **Renomear com um move/`os.replace` simples**: nunca. `plan_rename`/`rename_selection` validam o
    slug (vazio/longo/conflito), nunca sobrescrevem, fazem rollback em falha e atualizam o
    `last_selection`; a reedição da região ainda limpa `masks`/`overrides.masks` (relativas à ROI
    antiga).
26. **Replay de gatilho de tempo perdido**: nunca. Uma ocorrência além da tolerância de 60 s é
    registrada como `skipped -> missed` e descartada (sem rajada após sleep/suspensão e sem
    catch-up entre reinícios); o `at` usa o relógio local ingênuo, então o DST pode dobrar ou perder
    um disparo (§11.4).
27. **Ensaiar um gatilho de tempo**: nunca. `at`/`every`/`after` só são avaliados com as ações
    armadas e não têm dry-run; o caminho de ensaio do §11.4 pertence apenas ao `trigger: change`.
28. **Disparar o caminho errado**: nunca. O `on_result` avalia só ações com `trigger: change`; os
    gatilhos de tempo rodam uma vez por frame pós-baseline no `ActionDispatcher.on_tick`, mesmo sem
    mudança (§11.4).
29. **Girar em espera ocupada por um gatilho**: nunca. O `MonitorLoop` limita o `Event.wait` pelo
    `next_deadline_delay()` (piso de 0,05 s, §3.5); sem polling/spin.

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
| Alertas | `httpx` | Telegram, ntfy, webhook/`http_post` e a checagem passiva de release |
| Alertas | `miniaudio` | som no CLI/`run` (WAV/MP3/OGG/FLAC; a GUI usa o Qt Multimedia já empacotado) |
| Config | `PyYAML` | config |

**Extras opcionais** (`pyproject.toml::[project.optional-dependencies]`):

| Extra | Pacotes | Observação |
|---|---|---|
| `sound` | `simpleaudio>=1.0.4` | sem wheel confiável no 3.13; **não** entra no bundle |
| `input` | `pynput>=1.7` | ações pseudo-humanas e hotkeys globais |
| `ocr-preproc` | `opencv-python>=4.8` | experimentos de pré-processamento de OCR (não exigido) |
| `macosx` | `pyobjus>=1.2` | ponte Objective-C para o popup do plyer no macOS (v0.11.0; empacotado no `.app`) |
| `mqtt` | `paho-mqtt>=2.1` | canal de alerta MQTT (v0.9.0); não empacotado nos instaladores |
| `dev` | `pytest>=8.0`, `pytest-cov>=5.0`, `ruff==0.16.9`, `mypy==2.4.0` | desenvolvimento, gates de lint/tipagem e CI |
| `build` | `pyinstaller>=6.11.1` | empacotamento (suporta 3.13 a partir dessa versão) |

O extra opcional `logging` (`structlog`) foi **removido na v0.11.0** (sem uso em `src/`; adotar log
estruturado está rejeitado — o `logging` da stdlib permanece, §3.1).

**Requisitos externos**:
- **Tesseract** instalado no sistema (não vem com `pytesseract`), com os traineddata `por` e `eng`.
  No Windows o instalador **oferece** o release fixado (verificação SHA256) com prompt de
  consentimento — instalação silenciosa só com `/TESSERACT=yes` — e o transforma em `Depends:` no
  `.deb` do Linux. Caminho procurável via `compare_options.advanced.tesseract_cmd`.
- **Som no Linux**: o CLI/`run` usa o `miniaudio` empacotado; nos formatos do caminho legado a GUI
  depende dos plugins do GStreamer e um player externo (`paplay`/`aplay`/`ffplay`) segue como
  fallback; no `.deb`, `pulseaudio-utils` e `alsa-utils` vêm como `Recommends`.
- **Linux**: sessão X11 (Wayland fora de escopo).
- **macOS (v0.11.0)**: somente arm64, zip do `.app` sem assinatura (sem notarização); Tesseract via
  Homebrew ou `tesseract_cmd`; a primeira execução exige permissões de **Gravação de Tela**
  (captura) e **Acessibilidade** (popup/ações); validação em hardware físico pendente (v1.0.0).
- **Rede (opcional)**: só a checagem passiva de release a usa (uma requisição anônima/dia à API do
  GitHub, com cache; `ui.update_check: false` desliga). Captura, comparação e alertas nunca exigem
  rede, a menos que um canal de rede (`telegram`/`ntfy`/`smtp`/`mqtt`/…) esteja configurado.

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

alerts/chain.AlertChain(notifiers, gate=...) → chain
alerts/chain.AlertChain.dispatch(result, frame) → DispatchOutcome
alerts/gate.AlertGate.snooze(minutes)/mute()/unmute()/status()/active() → supressão manual
actions/dispatch.ActionDispatcher.on_result(result, frame) → rebaseline: bool   (trigger: change)
actions/dispatch.ActionDispatcher.on_tick(frame) → None                         (gatilhos de tempo)
actions/dispatch.ActionDispatcher.next_deadline_delay() → float | None          (limite da espera)
actions/triggers.evaluate(action, state, now_wall=..., now_mono=..., armed_since=...) → decisão

config/loader.load_config(path) → AppConfig
gui/session_manager.SessionManager(events, gate=..., max_sessions=...) → manager
SessionManager.start(target, recorder=...) → name; .stop(name|None)/.names()/.running/.actions(name)
persistence/selection.build_target(selection, profile, name=..., mode=..., schedule=...,
                                   action_filter=...) → TargetConfig
app.MonitorSession(target, recorder=..., on_action=..., on_frame=..., on_compare=..., gate=...) → sink(frame)
app.MonitorSession.acknowledge()/.awaiting_ack → controle de escalação (flags thread-safe)
app.build_loop(target, session, on_event=..., on_error=...) → MonitorLoop (liga o deadline provider)
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
      → ActionDispatcher.on_result     (trigger: change; ensaio/armado; agendador; limites; auditoria)
      → ActionDispatcher.on_tick       (gatilhos de tempo em todo frame pós-baseline; deadlines; auditoria)
      → re-arm do baseline (outcome/rebaseline) + evidência de mudança
```

Callbacks opcionais do `MonitorSession` (v0.8.0): `on_frame(frame, is_baseline)` roda a cada tick
(antes da comparação) e `on_compare(result)` roda a cada comparação, inclusive `changed == False`;
ambos têm default `None`. O controller da GUI usa os dois para os thumbnails do preview e o ring
buffer de calibração (`gui/session_manager.py`), sem nunca tocar em Qt a partir da thread do loop.

O `SessionManager` (v0.9.0) monta um par desses por seleção rodando na GUI e canaliza os callbacks
para a mesma fila de eventos com uma chave `session`; `preview(name)`/`calibration(name)` leem os
buffers por sessão e `actions(name)`/`acknowledge(name)`/`rebaseline(name)` roteiam para a sessão
escolhida (`name=None` = todas/agregado).

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
  `SUPPRESSED_MANUAL`, `BELOW_MIN`, `NONE_ENABLED`, `FAILED`) usado pelo re-arm edge-triggered.
- **Snooze / mute** — supressão manual no `AlertGate`: o snooze expira após N minutos, o mute dura
  até ser desmutado; ambos persistem no `state.json` e mantêm a mudança pendente.
- **Escalação / acknowledge** — com `escalation.enabled`, um alerta `FIRED` se repete (no cooldown
  de cada alerta) até o `acknowledge()` re-armar o baseline; o estado vive apenas em memória.
- **Sessão** — uma seleção monitorada com seu próprio `MonitorLoop`/thread/backend, gerenciada pelo
  `SessionManager`; a GUI pode rodar até `ui.max_sessions` simultâneas (somente GUI na v0.9.0).
- **Gatilho (`trigger`)** — condição de disparo por ação (`when.trigger`): `change` (mudança visual
  detectada, comportamento anterior) ou os gatilhos de tempo `at`/`every`/`after` (v0.10.0); os de
  tempo só existem com as ações armadas.
- **Tolerância (grace)** — janela de 60 s para um gatilho de tempo disparar após o vencimento; além
  dela a ocorrência é registrada como `missed` e nunca executa.
- **Missed** — ocorrência atrasada auditada (`skipped -> missed` no `logs/actions.jsonl`) de um
  gatilho de tempo; é descartada, nunca repetida.

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
