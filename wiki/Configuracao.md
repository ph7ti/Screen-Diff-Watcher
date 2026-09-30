# Configuração
[English](Configuration.md) · **Português (Brasil)**

## Onde tudo vive (app-data)

| Caminho | O que é |
|---|---|
| `config.yaml` | config global: perfis (defaults/alertas/ações), `ui`, `schedule`, `evidence` |
| `selections/<nome>.json` | seleções de ROI (uma por alvo), com `overrides` opcionais |
| `state.json` | estado leve: `last_selection`, `profile`, `language`, `action_selection`, `evidence_enabled` |
| `logs/` | `alerts.jsonl` (alertas) e `actions.jsonl` (auditoria de ações) |

Base: `%APPDATA%\screen_watch` (Windows), `~/.config/screen_watch` (Linux),
`~/Library/Application Support/screen_watch` (macOS) — ou o override `SCREEN_WATCH_HOME`.
Veja os caminhos efetivos com `python -m screen_watch show-paths`.

## `config.yaml` v2

O YAML é **global**: define um perfil ativo, um ou mais perfis nomeados, e as seções `ui`,
`schedule` e `evidence`. Os alvos vivem em `selections/*.json` (não mais no YAML).

```yaml
version: 2
profile: default                 # perfil ativo; trocável com --profile / seletor da GUI
profiles:
  default:
    defaults:
      mode: "advanced"           # "light" | "default" | "advanced"
      poll_interval_s: 2.0       # mínimo 1.0
      rearm: true
      humanize:                  # ruído pseudo-humano das ações
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
    actions: []                  # ver wiki/Acoes-Pseudo-Humanas.md
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

- **Segredos nunca no YAML** — apenas o nome da variável de ambiente (`bot_token_env`).
- `version` aceita **1 ou 2**; outro valor é erro. O v2 **exige** `profiles`.
- `profile` inexistente é erro de validação.
- `version` ausente com `targets:` é tratado como **v1 legado** (com aviso) e convertido por
  `migrate-config`.
- `ui.language` desconhecido gera aviso e volta para `auto` (não é erro).
- O app regrava o YAML **sem preservar comentários**; a escrita é atômica (temp + `os.replace`) e
  deixa um backup `config.yaml.bak`.

## Canais de alerta

Cada item de `alerts:` aceita `type`, `enabled`, `severity_min`, `cooldown_s` e um **`id`** opcional
(default `type`; `type#n` quando repetido). O `id` é a **chave de cooldown** e o nome usado na seleção do
teste de envio. Os quatro tipos originais (`sound`/`popup`/`telegram`/`log`) usam **campos planos**; os
novos usam um bloco aninhado **`options:`**:

```yaml
alerts:
  - type: webhook
    id: teams
    severity_min: 2
    cooldown_s: 60
    options:
      url_env: TEAMS_WEBHOOK             # ou url: "https://..."
      method: POST                       # POST | PUT | PATCH
      headers: { Content-Type: "application/json" }
      payload: { text: "Mudança em ${target}: ${strategy} sev=${severity}" }   # ou payload_raw: "..."
      timeout_s: 5
      verify_tls: true
  - type: http_post
    id: erp-api
    options: { scheme: http, host: 10.0.0.20, port: 8080, path: /alerta }
  - type: syslog
    id: siem
    options: { host: 10.0.0.9, port: 514, protocol: udp, facility: local0 }
```

Regras (validadas com código estável `config.alert_*`):

- `webhook`/`http_post` exigem `url` ou `url_env`; a URL deve começar com `http://`/`https://`.
- `payload` e `payload_raw` são mutuamente exclusivos; placeholder `${...}` desconhecido é erro.
- `port` deve ser 1..65535; `protocol` é `udp`/`tcp`; `facility` precisa ser uma facility syslog
  conhecida; `method` é `POST`/`PUT`/`PATCH`.
- `type` desconhecido é erro (um canal "mudo" deixa de passar batido).
- Detalhes e a lista completa de placeholders: [Alertas](Alertas.md).

## Perfis

Perfis nomeados (`profiles.<nome>.defaults` + `.alerts` + `.actions`) permitem alternar conjuntos de
parâmetros. A troca (seletor da GUI, submenu do tray ou `--profile`) vale **no próximo start** — o
loop ativo não muda — e é gravada em `state.json.profile`.

`defaults` cobre `mode`, `poll_interval_s`, `rearm`, `compare_options` e `humanize` (abaixo).

### Humanização (`defaults.humanize`)

Usada pelas ações pseudo-humanas:

| Chave | Default | Efeito |
|---|---|---|
| `mouse_steps` | 24 | pontos intermediários no movimento do mouse (>= 1) |
| `key_interval_ms` | 60 | intervalo default da digitação (`type`, quando o passo não define `interval_ms`) |
| `jitter_px` | 3 | ruído em pixels no movimento |
| `wait_jitter_ms` | 150 | ruído nas pausas (`wait`/`settle_s`) |
| `seed` | `null` | semente fixa para testes determinísticos |

Não há UI para humanização: edite o YAML.

### Verificação de texto (`defaults.compare_options.advanced.text_watch`)

Alerta somente quando um texto **aparece** ou **desaparece** na ROI — **somente no modo
`advanced`**. Pode ficar no perfil (paridade para quem usa só CLI) ou no `overrides` da seleção (a
linha **Verificar texto** da GUI grava lá; o **override tem precedência**):

```yaml
compare_options:
  advanced:
    text_watch: { text: "CONCLUÍDO", expect: "appears",
                  case_sensitive: false, ignore_accents: true }
```

```json
"overrides": { "text_watch": { "text": "CONCLUÍDO", "expect": "appears",
                               "case_sensitive": false, "ignore_accents": true } }
```

- `expect`: `appears` (default) ou `disappears`; `text` é obrigatório (não vazio).
- Casamento por substring; `case_sensitive: false` e `ignore_accents: true` por padrão (NFKD +
  remoção de diacríticos nos dois lados — robusto para OCR em pt-BR).
- **Somente no `advanced`**: fora dele é erro de validação (`config.text_watch_needs_advanced`); a
  GUI limpa o override ao trocar o modo.
- Com o filtro configurado o **gate de phash é bypassado** (o OCR roda a cada tick e o veredito do
  filtro é autoritativo) e **as ações também só rodam na transição** — detalhes nas
  [notas da v0.6.0](../doc/releases/v0.6.0.pt-BR.md).

## Seleção JSON v2 e overrides

Cada seleção pode trazer `overrides` que **substituem** (não somam) os valores do perfil para aquele
alvo: `mode`, `poll_interval_s`, `rearm`, `masks`, `alerts`, `actions` e `text_watch`.

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
  "overrides": { "poll_interval_s": 1.5, "rearm": false,
                 "text_watch": { "text": "CONCLUÍDO", "expect": "appears" } }
}
```

- **Precedência do modo**: modo explícito (seletor da GUI) > `overrides.mode` > `selection.mode`.
- Overrides de `actions` são validados com o modo resolvido (filtros `text_*` exigem `advanced`);
  `text_watch` **exige `advanced`** (`config.text_watch_needs_advanced`).
- Seleções `version: 1` continuam carregando (sem overrides/`app_name`).
- `window_handle` é a chave de lookup; `roi_relative` é a fonte de verdade da ROI a cada tick.

## Migração de um YAML v1 (`targets:`)

```powershell
python -m screen_watch migrate-config --dry-run   # imprime o plano
python -m screen_watch migrate-config             # grava selections/*.json + config.yaml v2 (.bak)
python -m screen_watch list-selections            # lista as seleções (marca a última usada)
```

A migração aborta se já existir uma seleção com o mesmo nome de algum target (remova/renomeie
primeiro). Nomes duplicados no v1 também abortam.

## `state.json`

| Chave | Para quê |
|---|---|
| `last_selection` | seleção usada por último (default do `--selection`) |
| `profile` | perfil escolhido (aplica no próximo start) |
| `language` | idioma escolhido no seletor da GUI |
| `action_selection` | subconjunto de ações por seleção (chave ausente = todas; lista vazia = nenhuma) |
| `evidence_enabled` | toggle do checkbox "Gravar prints" (tem precedência sobre o YAML) |

O `state.json` é gravado de forma atômica e sem backup; é estado descartável (apagar não quebra).

## Agendador

```yaml
schedule:
  enabled: true
  days: [mon, tue, wed, thu, fri]
  windows: ["08:00-12:00", "13:30-18:00"]   # janelas que cruzam a meia-noite são aceitas
```

Fora da janela de horário o monitoramento e os alertas seguem normais, mas as **ações** ficam
suspensas (registrado como `suspended_schedule` na auditoria). Agendador ligado sem `days`/`windows`
não restringe nada.

## Evidências

Configuradas na seção `evidence:` do YAML **ou** pelo checkbox da GUI (que tem precedência). Detalhes
em [Evidências](Evidencias.md).

## Relacionados

- [Ações pseudo-humanas](Acoes-Pseudo-Humanas.md) — o formato de `actions:`
- [Alertas](Alertas.md) — o formato de `alerts:`
- [Uso (CLI)](Uso-CLI.md) — `validate-config`, `migrate-config`, `--profile`
- [doc/00 §12](../doc/00-Documento_de_Arquitetura_e_Especificação.md) — schema e decisões de design
