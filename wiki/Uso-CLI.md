# Uso (CLI)
[English](CLI-Usage.md) · **Português (Brasil)**

Se você instalou pelos binários, o comando é **`screen-watch`**; do código-fonte, use
**`python -m screen_watch`**. Os dois têm a mesma superfície de comandos.

```powershell
python -m screen_watch --help
python -m screen_watch <comando> --help
```

**Flags globais**:

| Flag | Efeito |
|---|---|
| `--language TAG` | idioma da GUI (`auto`, `pt-BR`, `en-US` ou tag descoberta); não afeta o CLI, que é inglês fixo |
| `--verbose` | log de diagnóstico em nível DEBUG |

## Referência dos comandos

### Configuração

| Comando | O que faz |
|---|---|
| `init-config [--path CAMINHO] [--force]` | cria o `config.yaml` v2 padrão em app-data (ou no caminho dado); sem `--force`, não sobrescreve |
| `validate-config [--config CAMINHO] [--selections]` | valida o YAML (e, com `--selections`, os overrides de cada seleção) |
| `show-paths` | mostra app-data, config, seleções, estado, logs e a pasta efetiva de prints (`captures:`) |

```powershell
python -m screen_watch init-config
python -m screen_watch validate-config --selections
python -m screen_watch show-paths
```

### Seleção de ROI

| Comando | O que faz |
|---|---|
| `list-windows` | lista as janelas: `handle`, estado (`ok`/`minimized`), posição/tamanho e título |
| `select --handle H [--name NOME] [--mode light|default|advanced]` | abre o **overlay**: arraste com o botão esquerdo; botão direito cancela. Grava o JSON em app-data |
| `select-manual --handle H --roi X Y W H [--name NOME] [--title T] [--mode ...]` | grava a seleção por coordenadas, sem overlay |
| `list-selections [--json]` | lista as seleções (marca a última usada); `--json` imprime `file`/`name`/`label`/`window_handle`/`roi_relative`/`mode`/máscaras efetivas/chaves de override/`last` |
| `edit-selection NAME [opções]` | edita a seleção sem overlay: `--mode`, `--roi X Y W H`, `--mask X Y W H` (repetível), `--clear-masks`, `--poll-interval-s`, `--rearm`/`--no-rearm`, `--text-watch TEXT` + `--text-expect appears`/`disappears`, `--clear-text-watch`, `--clear-override KEY` |
| `rename-selection OLD NAME` | renomeia (o arquivo passa a ser o slug do novo nome; conflito e rollback como na GUI) |
| `remove-selection NAME...` | apaga um ou mais JSONs e limpa o `last_selection` quando apontava para um removido |
| `migrate-config [--path CAMINHO] [--dry-run]` | converte um YAML v1 (`targets:`) em `selections/*.json` + YAML v2 |

```powershell
python -m screen_watch list-windows
python -m screen_watch select --handle 12345 --name painel
python -m screen_watch select-manual --handle 12345 --roi 120 340 400 80 --name painel
python -m screen_watch list-selections
python -m screen_watch edit-selection painel --mode advanced --mask 10 10 40 20
python -m screen_watch edit-selection painel --roi 120 340 400 80 --poll-interval-s 1.5
python -m screen_watch edit-selection painel --text-watch "CONCLUÍDO" --text-expect appears
python -m screen_watch edit-selection painel --clear-override poll_interval_s
python -m screen_watch list-selections --json
python -m screen_watch rename-selection painel painel-erp
python -m screen_watch remove-selection painel-antigo
```

- O modo default das seleções é `advanced`; dá para trocar depois no seletor da GUI ou pelos
  `overrides` do JSON.
- A área mínima aceita é de 10×10 pixels lógicos.
- No overlay (`select` e o Novo Target/reedição da GUI), a ROI precisa caber **inteiramente na
  janela**; uma região que extrapola é rejeitada (`runtime.roi_outside_window`).
- `edit-selection` grava de forma **atômica**: em erro (ex.: ROI menor que 10×10) o arquivo fica
  **intacto**; sem nenhuma opção de edição o comando sai com **código 2**. `--roi` reancora
  `origin_at_selection` e **limpa os dois campos de máscara** (eram relativas à ROI antiga);
  `--mask` é repetível e **substitui** as máscaras efetivas; `--clear-override KEY` aceita `mode`,
  `poll_interval_s`, `rearm`, `masks` e `text_watch`.
- `rename-selection` reusa a lógica da GUI (slug, conflito e rollback); `remove-selection` limpa o
  `state.json:last_selection` quando ele apontava para um removido.

### Fluxo headless

Sem overlay, o ciclo completo de uma seleção fica:

```powershell
python -m screen_watch list-windows
python -m screen_watch select-manual --handle 123456 --roi 120 340 400 80 --name "painel erp"
python -m screen_watch edit-selection painel-erp --mode advanced --mask 10 10 40 20 `
  --poll-interval-s 1.5 --text-watch "CONCLUÍDO" --text-expect appears
python -m screen_watch validate-config --selections
python -m screen_watch run --selection painel-erp
```

Isso resolve o item "Radar" do README: `list-windows` → `select-manual` → `edit-selection` →
`validate-config --selections` → `run --selection` cobre todo o ciclo da seleção.

### Execução

| Comando | O que faz |
|---|---|
| `run [--config C] [--profile P] [--selection S] [--actions a,b\|all\|none]` | inicia o monitoramento da seleção |
| `gui [--config C] [--profile P]` | abre a GUI com tray (ver [GUI e tray](GUI-e-Tray.md)) |

**Como o `run` resolve a seleção**: `--selection NOME` procura `selections/NOME.json` em app-data;
também aceita um **caminho** para um `.json`. Sem `--selection`, usa `state.json.last_selection`; se
não houver, lista as disponíveis e sai com erro.

**Como o `run` monta o alvo**: seleção JSON + perfil do YAML; os `overrides` da seleção
**substituem** os valores do perfil (não somam). Sem YAML (ou com YAML v1 sem target
correspondente), usa os alertas padrão: **som + popup + log** (Telegram exige `chat_id`, então não
entra no default).

```powershell
python -m screen_watch run --selection painel
python -m screen_watch run --selection "%APPDATA%\screen_watch\selections\painel.json"
python -m screen_watch run --profile trabalho --selection painel
python -m screen_watch run --selection painel --actions reprocessar,confirmar   # subconjunto só desta sessão
python -m screen_watch run --selection painel --actions none                    # só monitora
```

Durante a execução, cada gatilho imprime uma linha `[action] rehearsal|armed <nome> -> ok|failed
(motivo)`. Ctrl+C encerra com `shutting down...`. Em Wayland, o `run` avisa e sai (código 2).

### Testes e diagnóstico

| Comando | O que faz |
|---|---|
| `test-alert --selection S [--list] [--only ID]` | dispara um alerta **sintético** (severidade 3); `--list` imprime id/tipo/estado/destino; `--only ID` envia a um destino (modo texto, ignora `enabled`) |
| `test-evidence --selection S` | grava um par baseline+change de exemplo e imprime os caminhos |
| `test-action --selection S [--armed] [--actions ...] [--no-countdown]` | ensaia (default) ou executa as ações; `--armed` mostra a contagem de 3 s; execuções avulsas ignoram o gatilho da ação (linha de aviso) |
| `list-actions --selection S` | lista as ações resolvidas e o subconjunto salvo, incluindo o gatilho de cada ação (`change`/`at`/`every`/`after`), sem iniciar sessão |
| `record-actions --selection S [--name NOME] [--out ARQUIVO] [--no-countdown]` | grava cliques/teclas e gera um snippet de `actions:` (extra `input`; `F10` encerra) |
| `compare-modes --selection S [--delay 5] [--repeat 1] [--modes light,default,advanced]` | mede `changed`/`score`/`threshold`/`severity`/tempo de cada modo (calibração) |
| `probe-dpi` | imprime a matriz de monitores (mss físico × Qt lógico × escala) e o rect de uma janela |
| `features [--json]` | diagnóstico do ambiente (versão/origem, Tesseract, entrada, som, tray, monitores) |
| `validate-i18n` | valida os catálogos de idioma (chaves, `error.*`, `help.*`, `_meta`) |

```powershell
python -m screen_watch test-alert --selection painel
python -m screen_watch test-alert --selection painel --list
python -m screen_watch test-alert --selection painel --only siem
python -m screen_watch test-action --selection painel            # ensaio
python -m screen_watch test-action --selection painel --armed    # executa de verdade
python -m screen_watch compare-modes --selection painel --delay 5
python -m screen_watch features --json
```

## Máscaras de regiões voláteis

Máscaras são retângulos `[x, y, w, h]` **relativos à ROI**, pintados de preto antes da comparação —
úteis para spinners/relógios que mudam sozinhos. A GUI desenha/remove com o botão **Editar máscaras…**
(veja [Janela e tray](GUI-e-Tray.md)); sem a GUI, edite `masks` (ou `overrides.masks`, que tem
precedência) no JSON da seleção — o perfil não tem máscaras.

## Calibração (Etapa D)

`compare-modes` captura o ROI, espera `--delay` segundos (altere o painel nesse intervalo) e mede
`changed`/`score`/`threshold`/`severity` e o tempo de `compare` de cada modo; para o `advanced`,
imprime também os textos reconhecidos pelo OCR. Use isso para ajustar `similarity_threshold`,
`upscale`, `psm` e o `severity_min` dos alertas/ações. Registre cada ajuste com o contexto em que foi
feito (doc/00 §18, item 8).

## Re-arm (edge-triggered)

Com `rearm: true` (default), uma mudança sustentada alarma **uma vez**; uma nova mudança realarma. Se
um alerta falhar (ex.: Telegram fora do ar), ele é re-tentado respeitando o `cooldown_s` (backoff),
sem martelar a cada tick. O re-arm manual está no tray, no botão **Re-armar baseline** da janela e na
hotkey `rearm`.

## Robustez (eventos do loop)

- `target_unavailable` — janela fechada, minimizada ou ROI fora dos limites; o loop segue tentando.
- `capture_clipped` — a ROI foi recortada contra o desktop virtual (monitor desligado/fora da tela).
- `roi_off_screen` — a ROI caiu 100% fora: o tick é pulado, sem quebrar o loop.
- Falhas consecutivas idênticas são reportadas uma vez (não a cada tick).

## Relacionados

- [Configuração](Configuracao.md) — `config.yaml`, overrides, migração
- [Ações pseudo-humanas](Acoes-Pseudo-Humanas.md) — formato de `actions:` e fluxo de arming
- [Alertas](Alertas.md) — canais, severidade e cooldown
