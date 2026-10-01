# Changelog

Todas as mudanças relevantes deste projeto. Formato inspirado em "Keep a Changelog";
versionamento semântico. Versão: `screen_watch.__version__` (fonte única).

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
