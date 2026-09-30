# Changelog

Todas as mudanças relevantes deste projeto. Formato inspirado em "Keep a Changelog";
versionamento semântico. Versão: `screen_watch.__version__` (fonte única).

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
