# Alertas
[English](Alerts.md) · **Português (Brasil)**

Um alerta é disparado quando a comparação confirma uma **mudança** (`changed: true`) e a
**severidade** da mudança atinge o `severity_min` do canal, respeitando o `cooldown_s` de cada um.

## Canais

| Tipo (`type`) | O que faz | Campos específicos |
|---|---|---|
| `sound` | toca um som local | `file` (WAV; default `alert.wav`) |
| `popup` | notificação local (`plyer`) | — |
| `telegram` | envia mensagem (e a imagem do ROI) via bot | `bot_token_env`, `chat_id`, `attach_roi` |
| `log` | grava uma linha JSON em `logs/alerts.jsonl` | `path` (opcional; vazio = default) |
| `webhook` | POST/PUT/PATCH JSON para uma URL de webhook (Teams **Workflows**, Slack, Discord, Mattermost) | `options:` (`url`/`url_env`, `method`, `headers`, `payload`/`payload_raw`, `timeout_s`, `verify_tls`) |
| `http_post` | POST JSON para host/IP + porta (ou URL completa) | `options:` (`url`/`url_env`, `scheme`, `host`, `port`, `path`, `method`, `headers`, `payload`/`payload_raw`, `verify_tls`) |
| `syslog` | mensagem syslog informacional (host/porta, `udp`/`tcp`) — sem imagem | `options:` (`host`, `port`, `protocol`, `facility`, `app_name`, `payload_raw`, `severity_map`, `timeout_s`) |

Os quatro primeiros mantêm **campos planos**; os novos usam um bloco aninhado **`options:`**. Todos
aceitam `enabled`, `severity_min`, `cooldown_s` e o **`id`** opcional (default `type`; `type#n` quando
repetido no mesmo perfil). O `id` é a **chave de cooldown**, então dois webhooks não compartilham mais o
cooldown. Exemplo de perfil:

```yaml
profiles:
  default:
    alerts:
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.wav" }
      - { type: "popup",    enabled: true, severity_min: 1, cooldown_s: 30 }
      - { type: "telegram", enabled: true, severity_min: 2, cooldown_s: 60,
          bot_token_env: "TELEGRAM_BOT_TOKEN", chat_id: "123456789", attach_roi: true }
      - { type: "log",      enabled: true, severity_min: 1, cooldown_s: 0 }   # opcional
      - type: webhook                   # Teams Workflows / Slack / Discord / Mattermost…
        id: teams
        severity_min: 2
        cooldown_s: 60
        options:
          url_env: TEAMS_WEBHOOK        # segredo fora do YAML
          payload: { text: "Mudança em ${target}: ${strategy} sev=${severity}" }
```

**Sem YAML** (ou YAML v1 sem target correspondente), o app usa os alertas padrão: **som + popup +
log** (Telegram exige `chat_id`, então não entra no default).

## Como cada canal funciona

### Som

- Toda a reprodução passa pela fronteira `platform/audio.py`; `alerts/` não conhece `sys.platform`.
- Windows: `winsound` (stdlib); sem `alert.wav`, usa `MessageBeep()`.
- Linux/macOS: player externo em ordem de preferência — `paplay`, `aplay -q`,
  `ffplay -nodisp -autoexit -loglevel quiet`; no macOS, `afplay`.
- O extra `simpleaudio` (`pip install -e ".[sound]"`) é opcional e **não** entra nos instaladores
  (sem wheel confiável para Python 3.13). Sem player algum, o som fica **silencioso** — o alerta
  nunca quebra.

### Popup

- `plyer.notification` (depende do backend nativo de cada SO).

### Telegram

- Token **nunca** no YAML: lido da variável de ambiente indicada em `bot_token_env`
  (`TELEGRAM_BOT_TOKEN` por default).
- `attach_roi: true` (default) envia o **screenshot do ROI** junto (`sendPhoto`), o que é essencial
  para validar falsos positivos; com `false`, envia só texto (`sendMessage`).
- Timeout curto (**5 s**) para não travar o loop.
- **Passo a passo completo**: [Configuração do Telegram](Configuracao-Telegram.md) — criar o bot,
  obter o chat id, definir o token, editar o YAML e testar.

### Log

- Uma linha JSON por disparo em `app-data/logs/alerts.jsonl` (ou no `path` configurado).

### Webhook / HTTP POST

- **Sem imagem/ROI**: o print anexado continua exclusivo do Telegram.
- URL: literal (`url`) **ou** do ambiente (`url_env: VAR`). Strings de `headers`/`payload` aceitam
  `${env:VAR}`; a URL resolvida e os valores das variáveis **nunca** aparecem em erros/logs.
- `method` é `POST` (default), `PUT` ou `PATCH`; redirects **não** são seguidos; o `Content-Type`
  default é `application/json` (sobrescrevível em `headers`).
- Sucesso = HTTP **2xx**; não-2xx vira `alert.http_status` (URL redigida) e falha de rede vira
  `alert.http_unreachable`.
- **Modelo de payload**: `payload:` (mapping) substitui `${campo}` **só em valores string**;
  `payload_raw:` (string) envia um corpo que não é objeto. Usar ambos é erro de config. Placeholders:
  `message`, `strategy`, `score`, `threshold`, `severity`, `target`, `timestamp`, `window_handle`,
  `changed`, `roi` e `env:VAR`. `$$` escapa `$`; `{`/`}` ficam literais, então o corpo pode ser JSON.
- `http_post` usa `scheme` (default `http`), `host`, `port`, `path` ou uma `url` completa.
- `verify_tls: true` (default); com `false` (endpoints internos/autoassinados) um aviso é registrado
  **a cada envio**.
- **Teams**: os *Incoming Webhooks* legados estão sendo descontinuados (prazo **31/03/2026**,
  desligamento **maio/2026**) — use a URL do **Workflows**.

### Syslog

- **Informational por default**: a severidade real vai no texto via `${severity}`; use `severity_map`
  (`{0: "debug", 3: "error"}`) para definir o nível syslog por severidade (0..3).
- `protocol` é `udp` (default) ou `tcp`; `port` default `514`; `facility` default `local0`; `app_name`
  vira a **tag** do syslog (`ident`).
- **UDP não confirma entrega** (fire-and-forget) — prefira `tcp` quando a entrega precisa ser confirmada.

## Severidade

A severidade (0..3) vem do pipeline de comparação: quando a estratégia não define, o pipeline calcula
`compute_severity(score, threshold)` — razão `score/threshold`: `>= 3.0` → 3; `>= 2.0` → 2;
`>= 1.0` → 1; senão 0. Use os `severity_min` para separar "aviso" de "crítico" (ex.: Telegram só em
severidade 2+).

## Cooldown, falhas e re-arm

- O `cooldown_s` é **por notificador**: mesmo com a ROI mudando a cada tick, cada canal dispara no
  máximo uma vez por janela de cooldown.
- Falha em um notificador **não** impede os demais (cada um tem seu próprio `try`). A tentativa é
  registrada para dar **backoff** — um Telegram fora do ar não é martelado a cada tick.
- Com `rearm: true` (default), o baseline avança após um alerta efetivo (ou inútil) — uma mudança
  sustentada alarma uma vez. Em cooldown ou falha, o baseline é mantido: a mudança pendente alarma
  quando o cooldown expirar.
- Re-arm manual: tray, botão **Re-armar** da janela ou hotkey `rearm` (`<ctrl>+<alt>+r`).

## Testar

```powershell
python -m screen_watch test-alert --selection painel             # todos os canais (respeita enabled)
python -m screen_watch test-alert --selection painel --list      # lista id/tipo/estado/destino
python -m screen_watch test-alert --selection painel --only siem # um destino (modo texto)
```

O `test-alert` dispara um alerta **sintético** (severidade 3) com o ROI atual, para conferir cada canal
sem esperar uma mudança real. Sem flags mantém o comportamento anterior (respeita `enabled`); `--list`
imprime os alertas e `--only ID` envia a um destino único, **ignorando `enabled`** e avisando quando o
alerta está desligado (`--only` envia em modo texto, sem capturar a ROI). Na GUI, o botão **Testar
alerta…** abre a mesma lista e envia em thread de trabalho. Para não duplicar registros, a linha extra no
`alerts.jsonl` só é gravada quando a configuração não tem um notificador `log`.

## Relacionados

- [Configuração](Configuracao.md) — onde os alertas ficam no YAML e nos overrides da seleção
- [Evidências](Evidencias.md) — prints gravados junto dos alertas (opcional)
- [doc/00 §11](../doc/00-Documento_de_Arquitetura_e_Especificação.md) — decisões de design
