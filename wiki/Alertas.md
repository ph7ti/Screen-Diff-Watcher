# Alertas
[English](Alerts.md) · **Português (Brasil)**

Um alerta é disparado quando a comparação confirma uma **mudança** (`changed: true`) e a
**severidade** da mudança atinge o `severity_min` do canal, respeitando o `cooldown_s` de cada um.

## Canais

| Tipo (`type`) | O que faz | Campos específicos |
|---|---|---|
| `sound` | toca um som local | `file` (WAV/MP3/M4A/AAC/OGG/FLAC…; default `alert.mp3`, empacotado) |
| `popup` | notificação local (`plyer`) | — |
| `telegram` | envia mensagem (e a imagem do ROI) via bot | `bot_token_env`, `chat_id`, `attach_roi` |
| `log` | grava uma linha JSON em `logs/alerts.jsonl` | `path` (opcional; vazio = default) |
| `webhook` | POST/PUT/PATCH JSON para uma URL de webhook (Teams **Workflows**, Slack, Discord, Mattermost) | `options:` (`url`/`url_env`, `method`, `headers`, `payload`/`payload_raw`, `timeout_s`, `verify_tls`) |
| `http_post` | POST JSON para host/IP + porta (ou URL completa) | `options:` (`url`/`url_env`, `scheme`, `host`, `port`, `path`, `method`, `headers`, `payload`/`payload_raw`, `verify_tls`) |
| `syslog` | mensagem syslog informacional (host/porta, `udp`/`tcp`) — sem imagem | `options:` (`host`, `port`, `protocol`, `facility`, `app_name`, `payload_raw`, `severity_map`, `timeout_s`) |
| `ntfy` | publica texto ou o PNG da ROI no tópico ntfy | `options:` (`server`, `topic`, `token_env`, `title`/`message`, `priority_map`, `tags`, `attach_roi`, `timeout_s`) |
| `smtp` | envia e-mail (assunto/corpo, com o PNG da ROI anexado) | `options:` (`host`, `port`, `security`, `from_addr`, `to`, `subject`/`message`, `username_env`, `password_env`, `attach_roi`, `timeout_s`) |
| `mqtt` | publica JSON num broker MQTT (extra `mqtt`) — sem imagem | `options:` (`host`, `topic`, `port`, `qos`, `retain`, `client_id`, `username_env`, `password_env`, `tls`, `payload`/`payload_raw`, `timeout_s`) |

Os quatro primeiros mantêm **campos planos**; os demais (`webhook`, `http_post`, `syslog`, `ntfy`,
`smtp` e `mqtt`) usam um bloco aninhado **`options:`**. Todos
aceitam `enabled`, `severity_min`, `cooldown_s` e o **`id`** opcional (default `type`; `type#n` quando
repetido no mesmo perfil). O `id` é a **chave de cooldown**, então dois webhooks não compartilham mais o
cooldown. Exemplo de perfil:

```yaml
profiles:
  default:
    alerts:
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.mp3" }
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

- Toda a reprodução passa pela fronteira `platform/audio.py`; `alerts/` não conhece `sys.platform`,
  Qt nem miniaudio.
- **GUI**: `QMediaPlayer` (QtMultimedia) criado no thread da GUI — WAV/MP3/M4A/AAC/FLAC/WMA via
  Media Foundation (Windows), GStreamer (Linux, depende dos plugins instalados) ou AVFoundation
  (macOS). Tocar de novo interrompe o som anterior.
- **CLI/`run`** (sem aplicação Qt): **miniaudio** (dependência core) toca WAV/MP3/OGG/FLAC numa
  **thread daemon** (nunca bloqueia o loop). **Sem AAC/M4A** — cai para um player externo se
  existir, senão `beep`.
- **Fallback legado**: `winsound` (stdlib; só WAV) no Windows; no Linux/macOS, player externo em
  ordem de preferência — `paplay`, `aplay -q`, `ffplay -nodisp -autoexit -loglevel quiet`; no macOS,
  `afplay`.
- `file` pode ser **absoluto** ou **relativo**: relativo procura em **`app-data/sounds/`** primeiro,
  depois nos **sons empacotados** (`screen_watch/assets/sounds`, onde mora o `alert.mp3` default) e por
  fim no CWD. Arquivo ausente — ou formato sem decoder — cai no `beep()` com aviso no log
  (nunca silêncio nem exceção).
- O extra `simpleaudio` (`pip install -e ".[sound]"`) segue opcional e **não** entra nos instaladores
  (sem wheel confiável para Python 3.13); ele só é tentado para `.wav`.
- **Seletor da GUI (v0.8.0)**: a linha **Som do alerta** pré-visualiza qualquer arquivo com
  **Reproduzir** e, depois de **Escolher…**, pede confirmação e **grava** o `file:` no alerta
  `type: "sound"` do perfil ativo no `config.yaml` (escrita atômica, backup `config.yaml.bak`;
  comentários não são preservados). O diálogo mantém **Copiar caminho e abrir YAML** /
  **Só abrir o YAML** / **Fechar** como ações secundárias. Config v1 é recusada com mensagem para
  rodar `migrate-config`; quando a seleção atual tem `overrides.alerts` (que substituem os alertas do
  perfil), o diálogo avisa que o som não valerá para ela.
- Matriz completa de formatos por contexto: [notas da v0.6.0](../doc/releases/v0.6.0.pt-BR.md).

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
- O registro não tem canal/alvo/caminho de evidência (`ts`, `strategy`, `changed`, `score`,
  `threshold`, `severity`, `window_handle`, `absolute_rect`, `sequence`, `detail`).
- **Histórico de alertas (v0.8.0)**: o botão **Histórico…** da GUI abre uma tabela sobre esse arquivo
  com filtros (data de/até, severidade mínima, modo), tolerante a linhas inválidas. **Abrir print**
  procura o `*_change.png` mais próximo em ±2 s do alerta (best effort; senão informa que não achou) e
  **Abrir pasta de prints** abre a pasta efetiva de capturas.

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

### ntfy

- Publica em `server/topic`: `server` default `https://ntfy.sh`; `topic` é obrigatório.
- `token_env` é **opcional**: vazio = tópico anônimo; com a variável configurada mas ausente no
  ambiente, o canal registra aviso e pula (como o Telegram).
- Headers `Title` e `Priority` (mapa severidade→prioridade 1..5, default 1→3, 2→4, 3→5; severidade
  0 também usa 3) e `Tags` opcionais; `title`/`message` são templates (default `${message}`).
- `attach_roi: true` (default `false`) envia o PNG da ROI por **`PUT`** (`Filename: roi.png`, texto
  no header `Message`); sem anexo o corpo é o texto renderizado.
- `timeout_s` default 5; falhas viram `alert.ntfy_status`/`alert.ntfy_unavailable` com a URL
  redigida.

```yaml
alerts:
  - type: ntfy
    id: celular
    severity_min: 2
    cooldown_s: 60
    options: { server: "https://ntfy.sh", topic: "meu-topico", token_env: NTFY_TOKEN,
               priority_map: { 1: 3, 2: 4, 3: 5 }, tags: ["monitor"],
               attach_roi: true, timeout_s: 5 }
```

### SMTP

- `host` e `from_addr` são obrigatórios; `to` exige uma lista **não vazia**.
- `port` default 587; `security` é `starttls` (default), `ssl` ou `none`.
- `subject`/`message` são templates (subject default `[screen-diff-watcher] ${target} sev=${severity}`).
- Credenciais só por env: `username_env`/`password_env` (defaults `SMTP_USERNAME`/`SMTP_PASSWORD`);
  o login só acontece quando a variável de usuário existe, e a senha nunca aparece em erros/logs.
- `attach_roi: true` (default) anexa o PNG da ROI (`roi.png`); `timeout_s` default 10.
- Erros saneados: `alert.smtp_unavailable`, `alert.smtp_auth_failed` e `alert.smtp_send_failed`.

```yaml
alerts:
  - type: smtp
    id: email
    severity_min: 3
    cooldown_s: 120
    options: { host: "smtp.example.com", port: 587, security: starttls,
               from_addr: "watch@example.com", to: ["oncall@example.com"],
               subject: "[monitor] ${target} sev=${severity}", attach_roi: true }
```

### MQTT

- Extra opcional: `python -m pip install -e ".[mqtt]"` (`paho-mqtt`); não entra nos instaladores.
  Um canal `mqtt` configurado sem o extra falha visível com `alert.mqtt_missing_extra` — nunca em
  silêncio. O `features --json` informa se o extra está instalado.
- `host` e `topic` são obrigatórios; `port` default 1883 (8883 quando `tls: true`).
- `qos` 0/1/2 (default 0), `retain` (default false) e `client_id` (default `screen-diff-watcher`).
- Credenciais por env (`username_env`/`password_env`, defaults `MQTT_USERNAME`/`MQTT_PASSWORD`);
  `tls: true` usa o TLS default do paho.
- Payload: mapping `payload` (default `text`/`target`/`severity`/`strategy`/`score`/`threshold`/
  `timestamp`, serializado em JSON) **ou** string `payload_raw`, mutuamente exclusivos.
- `timeout_s` default 5; **sem imagem**. Erros: `alert.mqtt_unavailable`/`alert.mqtt_publish_failed`.

```yaml
alerts:
  - type: mqtt
    id: barramento
    options: { host: "10.0.0.30", topic: "screen-watch/default", qos: 1, retain: false,
               client_id: screen-diff-watcher, username_env: MQTT_USERNAME,
               password_env: MQTT_PASSWORD }
```

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
- Re-arm manual: tray, botão **Re-armar baseline** da janela ou hotkey `rearm` (`<ctrl>+<alt>+r`).

## Soneca, silenciar e escalação

- **Soneca…** (grupo Detecção e alertas, tray e hotkey) usa as durações de `ui.snooze_minutes`
  (default 5/15/30/60 min); **Silenciar/Reativar** corta os alertas até reativar, e o **Ciente**
  reconhece uma escalação (GUI/tray; hotkey opcional `ui.hotkeys.acknowledge`).
- O estado vive no `state.json` (`alerts_snooze_until`, `alerts_muted`) e é herdado por um `run`
  headless posterior; soneca expirada é ignorada no start.
- Enquanto o gate está ativo, o `dispatch` devolve `suppressed_manual` **antes** de qualquer canal e
  o baseline é mantido: a mudança pendente alerta quando a soneca expirar ou o silêncio for
  desfeito.
- **Escalação** (`defaults.escalation`/`overrides.escalation`; `enabled` default false,
  `severity_min` default 2): com um `fired` em `severity >= severity_min`, o baseline **não** avança
  e o alerta repete na cadência do `cooldown_s` de cada canal até o **Ciente**, que re-arma o
  baseline.
- A evidência de mudança só é gravada em `fired`/`failed` (e a cada disparo da escalação), em vez
  de um print por tick enquanto suprimido.

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
