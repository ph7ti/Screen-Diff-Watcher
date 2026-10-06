# Changelog

Todas as mudanças relevantes deste projeto. Formato inspirado em "Keep a Changelog";
versionamento semântico. Versão: `screen_watch.__version__` (fonte única).

## [0.10.1] — 2026-10-06

### Corrigido

- **Cliques deslocados em monitores com escala ≠ 100%**: o localizador de mouse do editor de ações
  devolvia o ponto em espaço **lógico** do Qt (ex.: 1536×960 num monitor físico de 1920×1200 a 125%),
  mas o clique era executado em espaço **físico** — os cliques caíam deslocados (~192×120 px no
  centro da tela, crescendo até o canto). Agora o localizador converte lógico→físico ancorado no
  monitor sob o cursor (origem + dpr, `doc/00` §9.5), valendo para ações `ref: roi`/`window`/`screen`
  criadas pela GUI.
- **Realce "Ver local" deslocado**: a caixa de realce recebia o retângulo físico e pintava em
  coordenadas lógicas do Qt; agora converte físico→lógico por monitor antes de desenhar.
- **Comentário incorreto em `_locator_bases`**: a base do localizador é física (não lógica); o
  código e o docstring foram alinhados.

### Notas

- Captura/monitoramento, gravador (`record-actions`) e coordenadas digitadas à mão já operavam em
  espaço físico e não mudaram — o bug ficava restrito ao caminho da GUI (localizador + realce).
- 5 testes puros novos em `tests/test_overlay_geometry.py` (conversões de ponto/retângulo em 100%,
  125%, 150% e 200%); `ruff`, `validate-i18n` e a suíte de testes verdes.

## [0.10.0] — 2026-10-06

Notas: [`doc/releases/v0.10.0.md`](doc/releases/v0.10.0.md)
([PT](doc/releases/v0.10.0.pt-BR.md)).

### Adicionado

- **Agendador de ações (gatilhos de tempo)**: cada ação escolhe um gatilho em `when.trigger` —
  `change` (padrão; reage à mudança detectada) ou `at`/`every`/`after`. `at` dispara em horários
  `HH:MM` com `days` opcional (nomes reaproveitados do `schedule`); `every` tem fase que começa ao
  armar e reinicia a cada disparo; `after` é um atraso único contado do armar. Gatilhos de tempo só
  valem com as ações **armadas** (não têm ensaio) e o loop de monitoramento encurta a espera pelo
  próximo vencimento (`min(poll_interval_s, deadline)`), mantendo o `at` pontual mesmo com `every_s`
  menor que o poll.
- **Tolerância e auditoria**: vencimentos atrasados mais de 60 s (sleep/suspensão) viram
  `skipped -> missed` no `logs/actions.jsonl` e nunca executam (sem catch-up e sem repetição ao
  reiniciar); todo registro de ação passa a carregar `trigger`. Fora da janela do `schedule`, a
  ocorrência vencida é consumida com `suspended_schedule` e não é repetida.
- **Editor e CLI**: seletor de gatilho no editor de ações da GUI (campos de tempo conforme a
  escolha), resumo do gatilho no `list-actions`, aviso `trigger ... ignored (explicit run)` nas
  execuções avulsas (`test-action`/botão de 3 s) e dica comentada dos campos de tempo no snippet do
  `record-actions`.

### Notas

- **Mudança de comportamento**: ações com gatilho de tempo não disparam mais por mudança (o caminho
  `change` ficou restrito a `trigger: change`); para gatilhos de tempo, `rebaseline: true` e
  `cooldown_s >= every_s` são erros de validação e os campos de `change` são rejeitados.
- 739 testes unitários (50 novos); `ruff` e `validate-i18n` verdes. `at` usa o relógio local ingênuo
  (DST pode dobrar/perder um disparo) e janela minimizada/fechada pausa os gatilhos de tempo
  (documentado).

## [0.9.1] — 2026-10-06

Notas: [`doc/releases/v0.9.1.md`](doc/releases/v0.9.1.md)
([PT](doc/releases/v0.9.1.pt-BR.md)).

### Corrigido

- **Crash da GUI na inicialização (regressão da 0.9.0)**: o `MonitorController` foi substituído pelo
  `SessionManager`, onde `escalating` é um **método**, mas `_update_gate_status`/`_acknowledge`
  ainda usavam a sintaxe de property. O `TypeError` dentro do slot do `QTimer` faz o PyQt6 abortar o
  processo no primeiro tick do `_drain` (`0xC0000409`), sem traceback visível ao usuário. Os três
  pontos passaram a chamar `escalating()`; testes de regressão novos em
  `tests/test_gui_main_window.py` exercitam os métodos reais com stubs, sem Qt.

### Notas

- 689 testes unitários (4 novos); `ruff` e `validate-i18n` verdes. Nenhuma mudança de
  comportamento fora do fix.

## [0.9.0] — 2026-10-06

Detalhes e exemplos: [`doc/releases/v0.9.0.md`](doc/releases/v0.9.0.md)
([PT](doc/releases/v0.9.0.pt-BR.md)).

### Adicionado

- **Canais de alerta ntfy, e-mail (SMTP) e MQTT**: `ntfy` publica texto ou o PNG da ROI no tópico
  (`Title`/`Priority`/`Tags`, token opcional via env); `smtp` envia e-mail via stdlib
  (`starttls`/`ssl`/`none`, anexo opcional, credenciais só em env); `mqtt` publica JSON em tópico com
  QoS/retain/TLS pelo extra opcional `paho-mqtt` (`pip install -e ".[mqtt]"`; sem o extra o canal
  configurado falha visível com `alert.mqtt_missing_extra`). Segredos apenas em variáveis de
  ambiente; erros saneados.
- **Soneca e silenciar alertas**: novo `AlertGate` compartilhado (thread-safe) com **Soneca…**
  (durações de `ui.snooze_minutes`), **Silenciar/Reativar** na GUI e no tray; o estado persiste em
  `state.json` (`alerts_snooze_until`, `alerts_muted`) e vale também para um `run` headless. Enquanto
  ativo, o outcome é `SUPPRESSED_MANUAL` e a mudança pendente continua valendo quando expirar.
- **Escalação até reconhecer**: `defaults.escalation`/`overrides.escalation`
  (`enabled`, `severity_min`); com o alerta disparado (`FIRED`) acima do mínimo, o baseline não
  avança e o alerta **repete na cadência do `cooldown_s` de cada canal** até **Ciente**
  (`acknowledge()`) — botão na GUI, item no tray e hotkey opcional `acknowledge`, com status
  "aguardando reconhecimento".
- **Ciclo de vida de seleções no CLI (fluxo headless)**: `remove-selection NAME...` (limpa o
  `last_selection` removido), `rename-selection OLD NAME` (reusa slug/rollback da GUI),
  `edit-selection NAME` (`--mode`, `--roi`, `--mask`/`--clear-masks`, `--poll-interval-s`,
  `--rearm/--no-rearm`, `--text-watch`/`--clear-text-watch`, `--clear-override`) e
  `list-selections --json`. O fluxo `list-windows → select-manual → edit-selection →
  validate-config --selections → run` cobre a seleção inteira sem overlay (item "Radar" do README
  resolvido).
- **Múltiplas ROIs na GUI**: novo `SessionManager` roda N sessões simultâneas (uma thread/backend e
  buffers de preview/calibração por sessão); lista com **checkboxes** (Iniciar marca o conjunto;
  sem nenhum marcado, inicia a linha destacada), status agregado, linhas ativas com `▶`, logs/eventos
  prefixados com `[seleção]`, preview/calibração/ações seguindo a linha destacada, start/stop
  individual no tray e limite `ui.max_sessions` (padrão 4, faixa 1..16). O CLI `run` continua
  single-seleção.
- `features --json` passou a reportar se o extra `mqtt` está instalado.

### Mudado

- **Evidências de mudança atreladas à tentativa real**: `record_change` só grava quando o
  `AlertChain` de fato tentou entregar (`FIRED`/`FAILED`); mudanças suprimidas por cooldown,
  soneca/silêncio ou abaixo do mínimo não geram mais um print por tick. A escalação registra um
  print por disparo repetido.
- **`MonitorController` foi substituído por `gui/session_manager.py::SessionManager`** (sem shim de
  depreciação). Eventos da GUI agora carregam `session` e o Start aceita várias seleções; remover
  uma seleção em execução para apenas a sessão afetada.
- `AlertChain.dispatch` consulta o gate antes dos canais e ganhou o outcome `SUPPRESSED_MANUAL`;
  `MonitorSession` ganhou `acknowledge()`/`awaiting_ack` e aceita `gate=` (repassado a
  `build_alert_chain`).
- `edit-selection --roi` reancora `origin_at_selection` na janela atual e limpa **os dois** campos
  de máscara (regra de reedição de região); `--mode` atualiza `overrides.mode` quando existe.

### Notas

- Novos códigos de erro i18n nos dois catálogos (`config.alert_missing_topic`,
  `config.alert_invalid_priority_map`, `config.alert_missing_from`, `config.alert_missing_to`,
  `config.alert_invalid_security`, `config.alert_invalid_qos`, `config.alert_*smtp/ntfy/mqtt`,
  `config.snooze_minutes_*`, `config.escalation_*`, `config.max_sessions_range`,
  `runtime.session_already_running`, `runtime.session_limit`) e chaves de GUI/tray/help
  (`main.btn_snooze`, `status.snoozed/muted/escalating`, `tray.snooze/mute/unmute/acknowledge/selection`,
  `help.window.snooze/mute/ack`); `validate-i18n` verde.
- Extras: `pyproject.toml` ganhou `mqtt = ["paho-mqtt>=2.1"]` (não entra nos instaladores).
- Módulos novos: `alerts/gate.py`, `alerts/ntfy.py`, `alerts/smtp.py`, `alerts/mqtt.py`,
  `gui/session_manager.py`; removido `gui/controller.py`.
- 685 testes unitários (64 novos); `ruff` e `validate-i18n` verdes.

## [0.8.0] — 2026-10-05

Detalhes e exemplos: [`doc/releases/v0.8.0.md`](doc/releases/v0.8.0.md)
([PT](doc/releases/v0.8.0.pt-BR.md)).

### Adicionado

- **Editor visual de máscaras**: o botão **Editar máscaras…** abre um overlay por monitor sobre a
  janela alvo (arrastar adiciona, clique direito remove, Enter salva, Esc cancela). Grava onde as
  máscaras efetivas vivem (`overrides.masks` > `masks`; cria `overrides.masks` quando não há
  nenhuma), fica bloqueado com a sessão rodando e o JSON da seleção agora é gravado atomicamente.
- **Som gravado direto no YAML**: depois de **Escolher…**, a GUI confirma e grava o `file:` no alerta
  `sound` do perfil ativo (criado se faltar), com escrita atômica + `config.yaml.bak`; config v1 é
  recusada com `config.v1_not_editable` e seleções com `overrides.alerts` recebem aviso de precedência.
- **Preview do frame**: o grupo Monitoramento mostra baseline + último frame em miniaturas reduzidas
  (≤240 px), sempre copiadas fora da thread do loop.
- **Histórico de alertas**: o botão **Histórico…** lê `logs/alerts.jsonl` com filtros de data,
  severidade mínima e modo, tolerante a linhas inválidas, com abertura best-effort do print
  (`*_change.png` em ±2 s) e da pasta de prints.
- **Calibração ao vivo**: gráfico score × limite de todas as comparações (ring buffer de 600
  amostras), pontos por severidade e **Exportar CSV…**, sem dependência nova.
- **Qualidade**: CI em Python 3.11/3.12/3.13 com cobertura como artefato `coverage-xml` (sem gate) e
  runbook manual de publicação da wiki.

### Mudado

- O popup de ajuda do som virou **diálogo de confirmação**; copiar o trecho e abrir o YAML seguem
  disponíveis como ações secundárias.
- `MonitorSession` ganhou callbacks opcionais `on_frame`/`on_compare` (default `None`), sem mudar o
  CLI/`run`.
- `dump_selection` é atômico; a reedição de região continua limpando as máscaras.

### Notas

- Chaves i18n novas nos dois catálogos (`main.*`, `overlay_masks.*`, `history.*`, `calibration.empty`,
  `dialog.masks_*`, `dialog.sound_*`, `dialog.calibration_*`, `error.config.v1_not_editable` e ajuda
  `window.edit_masks/preview/alert_history/calibration`); `validate-i18n` verde.
- Módulos puros novos: `gui/mask_editor_geometry.py`, `gui/preview_geometry.py`, `gui/calibration.py`,
  `alerts/history.py`.
- 621 testes unitários (45 novos); `ruff` e `validate-i18n` verdes.

## [0.7.1] — 2026-10-01

Detalhes e exemplos: [`doc/releases/v0.7.1.md`](doc/releases/v0.7.1.md)
([PT](doc/releases/v0.7.1.pt-BR.md)).

### Adicionado

- **Som default empacotado (`alert.mp3`)**: o `file` padrão dos alertas `sound` passa a ser
  `"alert.mp3"`, e o resolver procura também em `screen_watch/assets/sounds/` (empacotado), entre
  `app_home()/sounds` e o CWD. Novas configs já apontam para o som que vem no instalador; configs
  existentes com `alert.wav`/outro caminho não mudam (arquivo ausente continua caindo no `beep`).
- **Popup ao escolher o som**: depois de cada **Escolher…**, a GUI mostra um aviso orientando a colar
  o caminho no `config.yaml` do perfil desejado, com **Copiar caminho e abrir YAML** (padrão),
  **Só abrir o YAML** e **Fechar**.
- **Repaginação da janela principal**: painel superior em **grid 2×2** (Seleções à esquerda,
  Monitoramento à direita; Ações da sessão à esquerda, Detecção e alertas à direita), **Status + Log**
  no rodapé com os botões **Prints / Testar alerta… / Abrir YAML** na coluna direita.

### Mudado

- **Ver local** passou do grupo Monitoramento para a fileira de botões do grupo **Seleções**;
  **Gravar prints (evidências)** passou para o **Monitoramento**.
- Textos da GUI: **Ver local da seleção**, **Armar Ações** e **Desarmar Ações**.
- O campo do som exibe o trecho `file: "..."` (o rótulo de snippet separado foi removido);
  **Copiar caminho** e **Reproduzir** ficam desabilitados sem valor.

### Notas

- Novas chaves i18n `dialog.sound_*` nos dois catálogos; o default empacotado vive em
  `src/screen_watch/assets/sounds/alert.mp3` (declarado em `package-data` e no `datas` do PyInstaller).
- A **0.7.1** é uma escolha consciente de **PATCH** (a regra documentada seria MINOR — só layout/UX e
  o default do som, sem quebra de API nem de dados).

## [0.7.0] — 2026-10-01

Detalhes e exemplos: [`doc/releases/v0.7.0.md`](doc/releases/v0.7.0.md)
([PT](doc/releases/v0.7.0.pt-BR.md)).

### Adicionado

- **Nome da seleção com renomeação do arquivo**: campo **Nome da seleção** abaixo da lista (confirma
  pelo botão **Renomear** ou **Enter**). O nome vira prefixo do rótulo
  (`verificando download - Seleção App — Região …`) e o arquivo passa a ser o **slug** do nome
  (`selections/verificando-download.json`; acentos normalizados, máx. 60). Nunca sobrescreve outra
  seleção (colisão avisa e nada muda), faz rollback em falha e atualiza o
  `state.json:last_selection`. Renomear é bloqueado com sessão rodando. O nome também aparece no
  `run` e no `list-selections`.
- **Ver local**: botão no grupo Monitoramento (que passou a ter **duas colunas**) que destaca a ROI
  na tela por ~2 s. O realce **nunca pinta dentro da ROI** (camada escura só fora + borda logo por
  fora), não captura cliques/foco e fecha sozinho — por isso funciona **com a sessão rodando**.
- **Reeditar a região por duplo clique**: reabre o overlay para a janela da seleção e regrava
  `roi_relative`/`origin_at_selection` preservando nome, modo e overrides; as **máscaras são limpas**
  (eram relativas à ROI antiga), com log explícito.

### Mudado

- **Duplo clique na lista não inicia mais o monitoramento** — agora **reedita a região**. Para
  iniciar/parar, use **Enter** na lista, o botão **Iniciar/Parar**, o tray ou as hotkeys.
- `--selection <nome>` dos scripts passa a exigir o **novo nome de arquivo** após renomear uma
  seleção (o `last_selection` e o `list-selections` acompanham).
- O slug de novas seleções `select`/`select-manual` agora remove acentos e tem limite de 60
  caracteres (`naming.slugify`, compartilhado com a GUI).

### Notas

- 4 códigos de erro novos (`selection.name_invalid`, `selection.name_too_long`,
  `selection.name_conflict`, `selection.rename_failed`), chaves `main.*`/`dialog.*`/`highlight.*`/
  `help.*` nos dois catálogos i18n.
- `Selection` v2 ganhou `name` opcional (seleções antigas continuam carregando); `TargetConfig`
  ganhou `label` (exibição; o `name` continua sendo o arquivo).

## [0.6.0] — 2026-09-30

Detalhes e exemplos: [`doc/releases/v0.6.0.md`](doc/releases/v0.6.0.md)
([PT](doc/releases/v0.6.0.pt-BR.md)).

### Adicionado

- **Som selecionável e em mais formatos** (`.wav`, `.mp3`, `.m4a`, `.aac`, `.ogg`, `.oga`, `.flac`,
  `.wma` conforme a camada): a GUI toca pelo **`QMediaPlayer`** (QtMultimedia, já empacotado), o
  CLI/`run` usa **`miniaudio`** (agora dependência core; thread daemon, sem bloquear o loop) e o
  backend legado (`winsound`/`paplay`/`aplay`/`ffplay`/`afplay`) segue como fallback. `file` relativo
  procura em `app-data/sounds/` **antes** do CWD; arquivo ausente ou formato sem decoder cai no
  `beep()` + aviso (nunca silêncio nem exceção). O `features` mostra camadas, formatos e a pasta.
- **Grupo “Detecção e alertas” na GUI**: linha **Som do alerta** com o caminho efetivo,
  **Escolher…** (só pré-visualiza; nada é gravado), **Reproduzir** e **Copiar caminho** (trecho
  `file: "<caminho>"` para colar no alerta `sound` do YAML);
- **`text_watch` — alertar quando um texto aparece/desaparece na ROI** (somente no modo `advanced`):
  com o filtro configurado (`compare_options.advanced.text_watch` no perfil ou
  `overrides.text_watch` na seleção, que tem precedência), o alerta dispara **somente na transição**
  escolhida (`expect: appears|disappears`) e as demais mudanças de texto não disparam. Casamento por
  substring com `case_sensitive: false` e `ignore_accents: true` (NFKD + remoção de diacríticos nos
  dois lados) por padrão; a transição vale `severity: 3`. Na GUI, a linha **Verificar texto** edita o
  override da seleção atual (habilitada só no `advanced`) e é limpa ao trocar o modo.

### Corrigido

- **Telegram não enviava** quando o `chat_id` do perfil estava com o placeholder do `init-config`
  (`123456789`): o erro do Telegram ("chat not found") era apenas logado. Agora o `test-alert`
  reporta `alert <id> failed: ...` e retorna código != 0 mesmo que outro canal (som/popup) tenha
  funcionado.
- `test-alert --only <id>` e o botão **Testar alerta…** sinalizam **token/URL ausentes** como falha
  (`TELEGRAM_BOT_TOKEN not set` / `no url resolved`) em vez de reportar "sent".
- `httpx`/`httpcore` não logam mais a URL completa em INFO — ela carregava o **token do Telegram** e
  segredos de webhook (vazamento em logs).

### Mudado

- **Modo `advanced`**: agora o `phash` (`default`) roda como **gate de pixel** antes do OCR
  (`MODE_STAGES["advanced"] = ("default", "advanced")`). O OCR só roda/pontua quando os pixels
  mudaram, reduzindo falsos positivos ("mudanças" repetidas sem alteração real). O threshold do gate
  é `compare_options.default.threshold`.
- **Com `text_watch` configurado o gate é bypassado** (`("advanced",)`): o OCR roda a cada tick e o
  veredito do filtro é autoritativo — o `changed` do OCR não é propagado e `score`/`threshold` dele
  ficam apenas no `detail` (calibração pelo `compare-modes`). Sem o bypass o gate esconderia a
  transição.
- **Seleção de ROI**: uma ROI que não cabe inteiramente na janela é **rejeitada**
  (`runtime.roi_outside_window`) em vez de salva com um aviso. Uma ROI fora da janela fazia o tick
  capturar uma região alheia ao alvo, gerando prints e alertas que não correspondiam à janela.

### Notas

- `text_watch` fora do `advanced` é erro de config (`config.text_watch_needs_advanced`); a GUI limpa
  o override ao trocar o modo. Como o filtro decide o `changed`, **as ações também só rodam na
  transição** configurada.
- Custo do bypass: OCR a cada tick (100–500 ms; o intervalo default é 2 s); o veredito por presença
  não sofre o ruído de OCR que motivou o gate.
- Matriz de formatos: a GUI no Windows (Media Foundation) toca M4A/AAC; no CLI isso depende de um
  player externo (`ffplay`) — senão `beep`. No Linux (GUI), depende dos plugins do GStreamer.
- 5 códigos de erro novos (`config.text_watch_*`), chaves `main.*`/`help.*` nos dois catálogos.

## [0.5.0] — 2026-09-30

Detalhes e exemplos: [`doc/releases/v0.5.0.md`](doc/releases/v0.5.0.md)
([PT](doc/releases/v0.5.0.pt-BR.md)).

### Adicionado

- **Canais de alerta `webhook`, `http_post` e `syslog`** (bloco aninhado `options:`; os quatro canais
  atuais mantêm os campos planos, **sem migração**): POST JSON para webhook (Teams **Workflows**,
  Slack, Discord, Mattermost), POST JSON para host/IP + porta e envio syslog informacional
  (`udp`/`tcp`, `facility`, `severity_map`), todos com **modelo de payload** (`payload:` mapping ou
  `payload_raw:`) e placeholders `${campo}`/`${env:VAR}`.
- **`id` estável por alerta** (default `type`; `type#n` quando repetido), usado como **chave de cooldown**
  — corrige dois webhooks compartilhando o mesmo cooldown — e para selecionar o destino no teste.
- **Teste de envio**: `test-alert --list` e `test-alert --only <id>` no CLI e botão **Testar alerta…** na
  GUI (envio em thread de trabalho, com modo texto quando não há ROI).
- `verify_tls` (default `true`) nos canais HTTP, com aviso em log **a cada envio** quando `false`.
- `doc/releases/` (EN/PT): notas detalhadas de release, linkadas no `CHANGELOG`.

### Mudado

- **Tipo de alerta desconhecido passa a ser erro de config** (`config.alert_unknown_type`) em vez de
  aviso silencioso — um canal "mudo" deixa de passar batido (o CLI avisa quando o config existente é
  inválido e cai para os alertas padrão).
- **Cooldown por `id`**: a chave deixou de ser o nome da classe. Um perfil com **dois alertas do mesmo
  tipo** passa a disparar os dois por janela de cooldown (antes compartilhavam a chave).

### Notas

- **Segredos**: `url` literal ou `url_env: VAR`; `${env:VAR}` também em `headers`/`payload`. Erros e logs
  nunca expõem a URL resolvida nem os valores das variáveis.
- **Limitações**: sem imagem/ROI nos canais novos (Telegram continua o único com `attach_roi`); syslog
  por **UDP não confirma entrega** (use `tcp` quando precisar); Incoming Webhooks do **Teams** sendo
  descontinuados (prazo 31/03/2026; desligamento maio/2026 — use **Workflows**).
- 12 códigos de erro novos (`config.alert_*` + `alert.http_*`/`alert.syslog_unavailable`) nos dois
  catálogos i18n.

## [0.4.1] — 2026-09-30

### Removido

- Flag `--dry-run` do `test-action` (redundante: o ensaio já é o comportamento padrão sem `--armed`).

### Mudado

- Refatoração interna sem mudança de comportamento: particionamento do CLI em `cli/` (`commands` +
  `parser`, deixando `__main__.py` só com `main()`), centralização dos caminhos de log/auditoria
  em `platform.paths`, remoção da herança de `ValueError` em `ConfigError`/`ActionError` e limpeza
  dos testes.

## [0.4.0] — 2026-09-30

### Removido

- Flag de CLI `--target` (deprecada) — use `--selection`.
- Campo de configuração `schedule.timezone` (aceitava apenas `local` e não era lido em runtime).
- `seed: null` deixou de ser gravado no `config.yaml` gerado por `init-config` (o campo
  `seed` continua aceito no YAML).

### Corrigido

- **Telegram**: falhas de envio não expõem mais o token no log — o erro agora traz a descrição do
  Telegram (ex.: `HTTP 400: Bad Request: chat not found`) sem a URL; novo teste de integração
  opt-in (`TEST_REAL_TELEGRAM=1`) valida o config real (token via `getMe`, `chat_id` e envio) e
  detecta o caso clássico de `chat_id` igual ao ID do bot.

### Mudado

- Refatoração interna sem mudança de comportamento: remoção de código morto, deduplicação dos
  helpers de coerção de tipos (`config/coerce.py`), centralização da construção de `Frame` nos
  comandos de teste e da execução de ações armadas (`actions/execute.py`).

## [0.3.0] — 2026-09-30

### Adicionado

- **Multi-idioma (i18n) da GUI**: catálogos JSON no pacote (`screen_watch/i18n/*.json`,
  `pt-BR` e `en-US`), descoberta dinâmica, seletor de **Idioma** na janela, `--language` e
  `ui.language` no YAML; precedência `--language` > `state.json` > `ui.language` > `auto`
  (locale do SO). A troca vale no próximo start. CLI e `logging` permanecem **em inglês fixo**.
- **`validate-i18n`**: valida chaves faltando/sobrando, `error.*`/`help.*` e `_meta`; roda no CI.
- **Erros com código estável** (`errors.py::AppError`/`ERROR_CODES`): a GUI mostra a mensagem
  traduzida por código; `str(exc)` continua imprimível em inglês no CLI/log.
- **Novo layout da janela** seguindo o `UI.txt` (Monitoramento/Seleções/Ações da sessão/Log num
  `QSplitter`), com seletor de idioma e indicador de arming.
- **Armar/desarmar pela janela**: `Armar ações`, `Desarmar`, `Armar por…` e rótulo de estado,
  ligados ao mesmo caminho do tray/hotkey (arming por sessão).
- **Editar e reordenar passos no editor**: `Subir`/`Descer`, drag&drop, `Editar passo` (modo
  edição com `Salvar alteração`/`Cancelar`) e `Duplicar passo`; reordenação em função pura
  (`actions/steps.py`).
- **Ajuda no hover (2 s)**: tooltip HTML com propósito + exemplo em cada controle
  (`gui/help.py` + `gui/hover_help.py`; texto em `help.*` no catálogo).

### Mudado

- Textos de CLI e `logging` reescritos em inglês; painel de log da GUI também é inglês.
- `ArmingController.label()` passa a devolver inglês; a GUI traduz por `state`/`remaining_s`.

### Notas

- **Documentação bilíngue (EN/PT)**: `README.md` e a wiki passam a ser publicados em **inglês
  (principal)** com espelho em **português** (`README.pt-BR.md` + páginas PT da wiki, com link de
  idioma no topo); `doc/00` e `doc/01` ganharam versões em inglês, e o `doc/00` em português foi
  reciclado para o estado implementado (v0.3.0).
- **Tutorial do Telegram**: guia passo a passo (EN/PT) na Wiki — criar o bot, obter o `chat_id`,
  definir o token por variável de ambiente, editar o YAML e testar — linkado no README, que ganhou
  a seção "Recursos de alerta" (preparada para novos canais, ex.: webhook).

## [0.2.1] — 2026-09-30

### Adicionado

- **Editor de ações na GUI**: criar, editar e remover ações por seleção (gravadas em
  `overrides.actions` do JSON de seleção) — funciona também com config v1, sem migração;
  a validação reusa o parser do YAML.
- **Localizador de posição do mouse** nos passos `click`/`move` (caixa segue o cursor;
  `Enter`/clique esquerdo confirma, `Esc`/clique direito cancela), convertendo para o
  `ref` escolhido (`roi`/`window`/`screen`).
- **Contagem regressiva de 3s** antes de executar/gravar ações (overlay Qt sem roubar
  foco); `--no-countdown` para pular.
- **Checklist "Ações da sessão"** com seleção por nome, persistida em
  `state.json["action_selection"]` e aplicada no próximo start; no CLI, `--actions
  a,b|all|none` (one-shot) e `list-actions`.
- **Log ao vivo das ações** na GUI/CLI (`kind: action_event`), distinto dos comandos de
  tray/hotkey; gatilho barrado por cooldown reportado como `skipped -> cooldown`.
- **Botão "Abrir pasta de prints"** e linha `capturas:` no `show-paths`.
- **Checkbox "Gravar prints (evidências)"** na GUI, persistido em
  `state.json["evidence_enabled"]`, com precedência sobre o `evidence` do YAML.
- **Comando `features`** (diagnóstico do ambiente) e **empacotamento** (PyInstaller,
  Inno Setup no Windows, `.deb` no Linux) com workflows de CI/Release.

### Corrigido

- **Evidências de execuções manuais** (`test-action --armed` e botão "Executar ação (3s)")
  não gravavam print: agora gravam (respeitando `per_step`) e registram os caminhos na
  auditoria.
- **Hotkey `toggle` default** era inválida no `pynput` (`<ctrl>+<alt>+space`); corrigida
  para `<ctrl>+<alt>+<space>`.
- **`start_hotkeys`**: um combo inválido não derruba mais todas as hotkeys (valida combo a
  combo e ignora só os inválidos).
- **`activate` das ações**: confirmação de foco com retry (~0,5 s) e motivo claro
  (`activate recusado` × `foco não confirmou`), reduzindo `focus_changed` espúrio.
- **Localizador** não recebia teclado/mouse sob o diálogo modal (agora é filho do diálogo e
  captura teclado/mouse).
- **`profile` inválido** reportado com mensagem clara; overrides de ações validados.

### Notas

- Requer Python 3.11+; extras: `input` (`pynput`), `sound`, `ocr-preproc`, `build`.
- Monitores a 100% são recomendados para a ROI; escala ≠ 100% pode deslocar a captura
  (doc §5.1).
