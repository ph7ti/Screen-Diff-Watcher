# Ações pseudo-humanas (opt-in)
[English](Pseudo-Human-Actions.md) · **Português (Brasil)**

As ações são uma **reação separada dos alertas**: **não alteram** o resultado dos alertas nem o
re-arm, e são **opt-in e desarmadas por padrão** — em modo ensaio o app apenas registra o que faria
(e grava evidência), sem clicar. A execução real exige **armar** (tray, hotkeys ou "Armar por N min").
Desde a **v0.10.0** cada ação tem exatamente um **gatilho**: `change` (padrão; avaliado após uma
mudança detectada) ou um gatilho de tempo (`at`/`every`/`after`; avaliado a cada ciclo de
monitoramento, **só com as ações armadas**, sem ensaio).

- Backend de entrada: **`pynput`**, extra opcional (`pip install -e ".[input]"`). Sem ele, as ações
  permanecem em ensaio e as hotkeys globais ficam indisponíveis (a GUI avisa e fica tray-only).
- A execução é **síncrona na thread do loop**: captura/comparação pausam durante a sequência.
- Cada gatilho vira uma linha em `logs/actions.jsonl` (ensaio, execução, suspensão, motivo, duração
  e caminhos das evidências).

## Configurar no YAML

```yaml
profiles:
  default:
    actions:
      - name: reprocessar
        enabled: true
        severity_min: 1
        cooldown_s: 30
        when:
          changed: true
          text_any: ["erro", "falha"]   # exige mode: advanced (OCR)
        settle_s: 1.5
        rebaseline: false               # default: baseline permanece após a ação
        max_per_min: 6
        max_per_session: 100
        steps:
          - activate: true              # obrigatório quando houver cliques
          - click: { x: 380, y: 40, ref: roi, button: left, clicks: 1 }
          - wait:  { ms: 400 }
          - key:   { keys: "ctrl+s" }
          - type:  { text: "abc", interval_ms: 60 }
```

### Campos da ação

| Campo | Default | Papel |
|---|---|---|
| `name` | — (obrigatório) | nome único no conjunto |
| `enabled` | `true` | desabilitar sem remover |
| `when.trigger` | `change` | `change` \| `at` \| `every` \| `after` (v0.10.0; ver abaixo) |
| `severity_min` | `1` | severidade mínima da mudança para disparar (gatilho `change`) |
| `when.severity_min` | — | tem precedência sobre `severity_min` quando presente (`change`) |
| `when.changed` | `true` | único valor suportado (`false` é erro; `change`) |
| `when.text_any` / `text_all` / `text_regex` | vazio | filtros sobre o texto do OCR; exigem `mode: advanced` (`change`) |
| `case_sensitive` | `false` | sensibilidade dos filtros de texto (`change`) |
| `when.at` | — | `["HH:MM", ...]` (24 h) para `trigger: at` |
| `when.days` | todos | filtro de dias para `at` (`mon`..`sun`, igual ao `schedule.days`) |
| `when.every_s` | — | intervalo em segundos para `trigger: every` (>= 1) |
| `when.after_s` | — | atraso único em segundos para `trigger: after` (>= 1) |
| `cooldown_s` | `30` | intervalo mínimo entre disparos desta ação |
| `settle_s` | `1.5` | pausa ao final da sequência |
| `rebaseline` | `false` | `true` re-arma o baseline após executar (só no gatilho `change`) |
| `max_per_min` | `6` | teto em janela móvel de 60 s |
| `max_per_session` | `100` | teto por sessão |

## Gatilhos de tempo (v0.10.0)

`when.trigger` escolhe o que dispara a ação (um gatilho por ação). Gatilhos de tempo exigem as ações
**armadas** (sem ensaio) e também respeitam o `schedule`: uma ocorrência vencida com a janela fechada
é registrada como `suspended_schedule` e **não** é repetida quando a janela reabre.

```yaml
actions:
  - name: conferir_painel           # a cada 60 s enquanto armado
    when: { trigger: every, every_s: 60 }
    cooldown_s: 30                  # precisa ser menor que every_s
    steps: [ ... ]
  - name: fechamento                # às 18:00, só em dias úteis
    when: { trigger: at, at: ["18:00"], days: [mon, tue, wed, thu, fri] }
    steps: [ ... ]
  - name: lembrete                  # uma vez, 5 min após armar
    when: { trigger: after, after_s: 300 }
    steps: [ ... ]
```

- `at`: `at: ["HH:MM", ...]` (24 h) e `days` opcional (`mon`..`sun`; ausente = todos os dias).
  Dispara quando o horário é **cruzado com as ações armadas** — horários já passados no dia não
  disparam, e rearmar reinicia a referência de cruzamento.
- `every`: a fase começa ao armar e **reinicia a cada disparo** (próximo vencimento = disparo +
  `every_s`); rearmar reinicia a fase; sem rajada.
- `after`: contado uma única vez a partir do armar; desarmar cancela, rearmar reinicia.
- **Tolerância (60 s)**: um vencimento atrasado mais de 60 s (sleep/suspend) vira
  `skipped -> missed` no `logs/actions.jsonl` e **nunca executa**; não há catch-up nem repetição
  após reiniciar o app.
- Gatilhos de tempo não aceitam `changed`/`severity_min`/`text_*`/`case_sensitive` nem
  `rebaseline: true`; a validação rejeita com mensagens traduzidas, e `cooldown_s >= every_s` é erro.
- O loop acorda mais cedo quando há gatilho a vencer (`min(poll_interval_s, próximo deadline)`), o
  que mantém o `at` pontual e permite `every_s` menor que o poll.
- Janela minimizada/fechada = sem frame = os gatilhos de tempo pausam como o resto (retomam no
  próximo frame capturado).
- `test-action` e o botão **Executar ação (3s)** **ignoram** o gatilho (execução explícita; imprimem
  `trigger ... ignored (explicit run)`) — é assim que se testa uma ação de tempo.

### Passos

| Passo | Campos | Observações |
|---|---|---|
| `activate` | — | foca a janela-alvo e confirma `isActive`; **obrigatório antes de `click`** |
| `click` | `x`, `y`, `ref`, `button` (`left`/`right`/`middle`), `clicks` | move o mouse até o ponto e clica |
| `move` | `x`, `y`, `ref` | só move o cursor |
| `key` | `keys` (ex.: `"ctrl+s"`) | pressiona a combinação e solta na ordem inversa |
| `type` | `text`, `interval_ms` | digita caractere a caractere; sem `interval_ms`, usa `humanize.key_interval_ms` |
| `wait` | `ms` | pausa (com jitter de `humanize.wait_jitter_ms`) |

- `ref` é relativo à **ROI** (`roi`, base `frame.absolute_rect`), à **janela** (`window`, base
  `frame.window_rect`) ou absoluto na tela (`screen`).
- **Foco**: no Windows o `SetForegroundWindow` pode ser assíncrono/bloqueado (foreground lock); o
  app tenta reativar e reconfere o foco por ~0,5 s antes de abortar. O motivo no log diferencia
  `activate recusado` de `foco não confirmou` (`focus_changed: ...`).
- Entre passos, o runner re-checa o arming e um `Esc` pendente (`aborted`/`disarmed_during_run`).

### Limites e comportamento

- Um gatilho barrado por `cooldown_s` aparece no log ao vivo como `skipped -> cooldown` e **não**
  vai para o JSONL (para não poluir a auditoria).
- `max_per_min`/`max_per_session` são checados antes de executar (`rate_limited`).
- Fora da janela do **agendador**, a ação é suspensa (`suspended_schedule`); monitoramento e alertas
  seguem normais.
- Todo registro do JSONL carrega `trigger` (`change`/`at`/`every`/`after`); vencimentos atrasados são
  auditados uma vez como `skipped -> missed` e nunca executam.

## Armar/desarmar

- Estados: `disarmed` (ensaio, default), `armed` e `timed` (`Armar por N min`). O estado vive
  **apenas em memória** e começa desarmado a cada sessão.
- **Tray**: "Armar ações"/"Desarmar ações"/"Armar por N min".
- **Janela**: botões **Armar ações**/**Desarmar**/**Armar por…** (ativos só com sessão em execução).
- **Hotkeys globais** (extra `input`), defaults: `arm` `<ctrl>+<alt>+a`, `disarm`
  `<ctrl>+<alt>+d`, `toggle` `<ctrl>+<alt>+<space>`, `rearm` `<ctrl>+<alt>+r`, `abort` `Esc`.
  Combos inválidos são ignorados individualmente (não derrubam os demais).
- `Esc` aborta na hora e volta ao ensaio.

## Testar sem esperar um evento real

```powershell
python -m screen_watch test-action --selection painel            # ensaio (default)
python -m screen_watch test-action --selection painel --armed    # executa de verdade (contagem de 3s)
python -m screen_watch test-action --selection painel --armed --no-countdown   # sem contagem
python -m screen_watch list-actions --selection painel           # confere sem iniciar
```

Em `--armed`, uma contagem de 3 s aparece no topo da tela (overlay Qt **sem roubar foco**) para você
focar a janela-alvo; um clique no overlay cancela. O disparo automático do `run` **não** tem
contagem. A janela tem o botão equivalente **Executar ação (3s)**, que usa o subconjunto marcado no
checklist. Execuções avulsas **ignoram o gatilho** (executam os passos escolhidos e imprimem
`trigger ... ignored (explicit run)`), o que também é a forma de testar uma ação de tempo sem
esperar.

## Criar ações pela janela

A coluna de botões ao lado do checklist tem **Nova ação…**, **Editar…** e **Remover Ação**:

- **Nova ação…** abre um formulário com nome, `enabled`, **gatilho** (`change`/`at`/`every`/`after`;
  os campos de tempo aparecem conforme a escolha), `severity_min` (gatilho), `cooldown_s`,
  `settle_s`, `rebaseline` e a lista de passos. Ao confirmar, o app valida com o **mesmo parser do
  YAML** (`parse_actions`): cliques exigem um passo `activate` antes, filtros de texto exigem
  `mode: advanced` e as regras dos gatilhos de tempo valem; erros aparecem num diálogo traduzido.
- **Ordem dos passos**: use **Subir**/**Descer**, arraste e solte, **Editar passo** (carrega o passo
  no formulário; o botão vira **Salvar alteração** com **Cancelar**) ou **Duplicar passo**.
- **Localizar posição do mouse…** (nos passos `click`/`move`): aparece uma caixa seguindo o cursor
  com os valores já no `ref` escolhido (mais o absoluto); mova o mouse até o ponto e pressione
  **Enter** para preencher `x`/`y` (**Esc** ou clique direito cancela). A conversão usa a mesma base
  do disparo (ver `ref` acima); se a janela/ROI não estiver disponível, cai para `screen` e avisa.
- As ações criadas pela janela são gravadas em `overrides.actions` do **JSON da seleção**
  (`selections/<nome>.json`) — funcionam **mesmo com `config.yaml` v1**. Cada seleção tem o seu
  conjunto; sem override, a seleção herda as ações do perfil. Ações do perfil/YAML são somente
  leitura na GUI (edite o YAML).

## Selecionar ações por sessão

Abaixo da lista de seleções, o checklist **"Ações da sessão (aplicam no próximo start)"** mostra
todas as ações resolvidas com o contador "N de M selecionadas":

- **sem escolha salva** → todas as ações habilitadas rodam;
- **lista vazia (tudo desmarcado)** → nenhuma roda: a sessão **só monitora** (alertas continuam).

A escolha é **por nome de seleção** e persiste em `state.json["action_selection"][seleção]`; a troca
vale **no próximo start**. No CLI, `--actions a,b|all|none` sobrepõe o subconjunto salvo **sem
persistir** (one-shot):

```powershell
python -m screen_watch run --selection painel --actions reprocessar,confirmar
python -m screen_watch run --selection painel --actions none
```

## Gravador de ações (`record-actions`)

Com o extra `input`, `record-actions` escuta cliques e teclas e gera um snippet pronto para colar em
`actions:`:

```powershell
python -m screen_watch record-actions --selection painel --out snippet.yaml
```

Fluxo padrão: contagem de 3 s (mesmo overlay sem foco) → a gravação começa automaticamente → `F10`
encerra. Use `--no-countdown` para voltar ao `F9` manual (tempo para se preparar sem o overlay). Um
clique no overlay cancela a contagem. Os cliques são convertidos de coordenadas absolutas para
`ref: roi`/`window` (ou `screen` se caírem fora da janela) e o snippet já inclui um passo `activate`
e o bloco `when` comentado, para você revisar antes de armar. O snippet também traz uma dica
comentada dos campos de gatilho de tempo (`trigger`/`at`/`days`/`every_s`/`after_s`); o gravador
nunca grava um gatilho.

A contagem roda na **thread principal**, antes de criar os listeners do `pynput`. Sem Qt/display
(headless/Wayland), a contagem cai para o console (`3... 2... 1...`) e segue. Ressalva: em Wayland a
captura/entrada continuam limitadas; a elevação (UAC) não é contornada.

## Auditoria e log ao vivo

- **Auditoria** (`logs/actions.jsonl`, fonte de verdade): cada linha tem `ts`, `mode`
  (`rehearsal`/`armed`/`skipped`), `action`, `trigger`, `steps`, `executed`, `duration_s`, `reason`
  e `evidence` (caminhos dos prints).
- **Log ao vivo**: no CLI, uma linha por gatilho
  (`[action] rehearsal|armed <nome> -> ok|failed (motivo)`); na GUI, o mesmo evento aparece no log
  (`kind: action_event`). É efêmero e respeita o `cooldown_s`; a auditoria continua sendo a fonte
  de verdade.

## Relacionados

- [Configuração](Configuracao.md) — `humanize`, perfis, overrides
- [GUI e tray](GUI-e-Tray.md) — os botões de arming e o editor
- [Alertas](Alertas.md) — a reação que roda antes das ações
- [doc/00 §11.4](../doc/00-Documento_de_Arquitetura_e_Especificação.md) — decisões de design
