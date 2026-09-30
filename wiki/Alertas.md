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

Todos aceitam `enabled`, `severity_min` e `cooldown_s`. Exemplo de perfil:

```yaml
profiles:
  default:
    alerts:
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.wav" }
      - { type: "popup",    enabled: true, severity_min: 1, cooldown_s: 30 }
      - { type: "telegram", enabled: true, severity_min: 2, cooldown_s: 60,
          bot_token_env: "TELEGRAM_BOT_TOKEN", chat_id: "123456789", attach_roi: true }
      - { type: "log",      enabled: true, severity_min: 1, cooldown_s: 0 }   # opcional
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

### Log

- Uma linha JSON por disparo em `app-data/logs/alerts.jsonl` (ou no `path` configurado).

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
python -m screen_watch test-alert --selection painel
```

Dispara um alerta **sintético** (severidade 3) com o ROI atual, para conferir cada canal sem esperar
uma mudança real. Se a seleção não tiver alertas configurados, o comando falha com mensagem clara.
Para não duplicar registros, a linha extra no `alerts.jsonl` só é gravada quando a configuração não
tem um notificador `log`.

## Relacionados

- [Configuração](Configuracao.md) — onde os alertas ficam no YAML e nos overrides da seleção
- [Evidências](Evidencias.md) — prints gravados junto dos alertas (opcional)
- [doc/00 §11](../doc/00-Documento_de_Arquitetura_e_Especificação.md) — decisões de design
