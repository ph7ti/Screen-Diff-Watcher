# Changelog

Todas as mudanças relevantes deste projeto. Formato inspirado em "Keep a Changelog";
versionamento semântico. Versão: `screen_watch.__version__` (fonte única).

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
