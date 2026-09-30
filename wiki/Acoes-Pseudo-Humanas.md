# Ações pseudo-humanas (opt-in)
[English](Pseudo-Human-Actions.md) · **Português (Brasil)**

As ações são uma **reação separada dos alertas**: só são avaliadas depois de uma mudança detectada,
**não alteram** o resultado dos alertas nem o re-arm, e são **opt-in e desarmadas por padrão** — em
modo ensaio o app apenas registra o que faria (e grava evidência), sem clicar. A execução real exige
**armar** (tray, hotkeys ou "Armar por N min").

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
| `severity_min` | `1` | severidade mínima da mudança para disparar |
| `when.severity_min` | — | tem precedência sobre `severity_min` quando presente |
| `when.changed` | `true` | único valor suportado (`false` é erro) |
| `when.text_any` / `text_all` / `text_regex` | vazio | filtros sobre o texto do OCR; exigem `mode: advanced` |
| `case_sensitive` | `false` | sensibilidade dos filtros de texto |
| `cooldown_s` | `30` | intervalo mínimo entre disparos desta ação |
| `settle_s` | `1.5` | pausa ao final da sequência |
| `rebaseline` | `false` | `true` re-arma o baseline após executar (o gatilho pode repetir) |
| `max_per_min` | `6` | teto em janela móvel de 60 s |
| `max_per_session` | `100` | teto por sessão |

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
checklist.

## Criar ações pela janela

A coluna de botões ao lado do checklist tem **Nova ação…**, **Editar…** e **Remover Ação**:

- **Nova ação…** abre um formulário com nome, `enabled`, `severity_min` (gatilho), `cooldown_s`,
  `settle_s`, `rebaseline` e a lista de passos. Ao confirmar, o app valida com o **mesmo parser do
  YAML** (`parse_actions`): cliques exigem um passo `activate` antes e filtros de texto exigem
  `mode: advanced`; erros aparecem num diálogo traduzido.
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
e o bloco `when` comentado, para você revisar antes de armar.

A contagem roda na **thread principal**, antes de criar os listeners do `pynput`. Sem Qt/display
(headless/Wayland), a contagem cai para o console (`3... 2... 1...`) e segue. Ressalva: em Wayland a
captura/entrada continuam limitadas; a elevação (UAC) não é contornada.

## Auditoria e log ao vivo

- **Auditoria** (`logs/actions.jsonl`, fonte de verdade): cada linha tem `ts`, `mode`
  (`rehearsal`/`armed`/`skipped`), `action`, `steps`, `executed`, `duration_s`, `reason` e
  `evidence` (caminhos dos prints).
- **Log ao vivo**: no CLI, uma linha por gatilho
  (`[action] rehearsal|armed <nome> -> ok|failed (motivo)`); na GUI, o mesmo evento aparece no log
  (`kind: action_event`). É efêmero e respeita o `cooldown_s`; a auditoria continua sendo a fonte
  de verdade.

## Relacionados

- [Configuração](Configuracao.md) — `humanize`, perfis, overrides
- [GUI e tray](GUI-e-Tray.md) — os botões de arming e o editor
- [Alertas](Alertas.md) — a reação que roda antes das ações
- [doc/00 §11.4](../doc/00-Documento_de_Arquitetura_e_Especificação.md) — decisões de design
