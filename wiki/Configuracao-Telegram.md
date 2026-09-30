# Configuração do Telegram (passo a passo)

[English](Telegram-Setup.md) · **Português (Brasil)**

Este tutorial configura o canal de alerta `telegram`: criar o bot, descobrir o `chat_id`, definir o
token por variável de ambiente (nunca no YAML) e testar a entrega.

> O canal Telegram é opcional e independente dos demais: se ele falhar, som, popup e log continuam
> funcionando, e o loop de monitoramento nunca quebra.

## O que você precisa

- Uma conta no Telegram (aplicativo móvel ou desktop).
- O `screen-watch` instalado (ou `python -m screen_watch` do código-fonte).
- Uma seleção e um `config.yaml` configurados (veja [Configuração](Configuracao.md)); o
  `init-config` cria um padrão.

## 1. Criar o bot e obter o token

1. No Telegram, procure **@BotFather** e abra a conversa.
2. Envie `/newbot`.
3. Escolha um **nome de exibição** (qualquer) e um **username** terminado em `bot`
   (ex.: `meu_watcher_de_painel_bot`).
4. O BotFather responde com o **token da API**, no formato `123456789:AAE...`. **Esse token é um
   segredo** — nunca versione nem coloque no YAML.
   - Se o token vazar, envie `/revoke` ao BotFather para gerar outro.

## 2. Iniciar a conversa com o bot

Bots não podem iniciar conversa com você:

1. Abra a conversa do seu bot (link `https://t.me/<username_do_bot>`).
2. Aperte **Iniciar** (ou envie `/start`).

Para um **grupo**: adicione o bot ao grupo e envie uma mensagem (se o `getUpdates` não mostrar,
envie `/start@<username_do_bot>` ou mencione o bot).

## 3. Descobrir o `chat_id`

**Opção A — via `getUpdates` (funciona para conversa privada e grupos):**

1. Envie uma mensagem ao bot (privado) ou no grupo.
2. No navegador, abra:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. No JSON, encontre a mensagem enviada e leia `"chat": {"id": ...}`:
   - conversa privada: número positivo (ex.: `123456789`);
   - grupo: número negativo (ex.: `-1001234567890`).

**Opção B — bots auxiliares:** fale com **@userinfobot** (ou adicione-o ao grupo) e copie o id
mostrado.

> O `chat_id` no YAML é o id **da conversa em que o bot pode postar** (seu chat com o bot, ou um
> grupo do qual o bot participa).

## 4. Definir o token por variável de ambiente

Nunca coloque o token no `config.yaml`. O nome padrão da variável é `TELEGRAM_BOT_TOKEN`
(configurável com `bot_token_env`).

**Windows (permanente, nível de usuário):**

```powershell
setx TELEGRAM_BOT_TOKEN "123456789:AAE..."
# novos terminais e aplicativos passam a enxergar; reinicie o app/GUI
```

**Windows (só no terminal atual, para teste rápido):**

```powershell
$env:TELEGRAM_BOT_TOKEN = "123456789:AAE..."
```

**Linux/macOS (permanente):**

```bash
echo 'export TELEGRAM_BOT_TOKEN="123456789:AAE..."' >> ~/.profile
# relogue (ou `source ~/.profile` para o shell atual)
```

> Se o app aberto pelo menu não enxergar a variável, crie
> `~/.config/environment.d/telegram.conf` com `TELEGRAM_BOT_TOKEN=123456789:AAE...` e relogue.

Confira que a variável está visível:

```powershell
echo $env:TELEGRAM_BOT_TOKEN     # Windows PowerShell
```

```bash
printenv TELEGRAM_BOT_TOKEN      # Linux/macOS
```

> O valor é lido na hora do disparo; se você mudar a variável, reinicie o app (processos herdam o
> ambiente na inicialização).

## 5. Configurar o alerta no `config.yaml`

Abra o config (`python -m screen_watch show-paths` mostra onde ele está) e adicione a entrada
`telegram` na lista `alerts:` do perfil:

```yaml
version: 2
profile: default
profiles:
  default:
    alerts:
      - { type: "sound",    enabled: true, severity_min: 1, cooldown_s: 30 }
      - { type: "telegram", enabled: true, severity_min: 2, cooldown_s: 60,
          bot_token_env: "TELEGRAM_BOT_TOKEN", chat_id: "123456789", attach_roi: true }
```

O `config.yaml` criado pelo `init-config` já traz um exemplo de Telegram com
`chat_id: "123456789"` — troque pelo seu id (ou deixe `enabled: false` até configurar).

| Campo | Default | Significado |
|---|---|---|
| `enabled` | `true` | liga/desliga o canal |
| `severity_min` | `1` | severidade mínima (0–3) para enviar; `2` evita avisos barulhentos |
| `cooldown_s` | `30` | intervalo mínimo entre envios deste canal |
| `bot_token_env` | `TELEGRAM_BOT_TOKEN` | nome da variável de ambiente com o token |
| `chat_id` | — (obrigatório) | id do chat/grupo de destino |
| `attach_roi` | `true` | anexa o screenshot da ROI na mensagem (melhor para validar falso positivo) |

## 6. Testar

```powershell
screen-watch test-alert --selection painel     # do fonte: python -m screen_watch test-alert --selection painel
```

Isso dispara um **alerta sintético com severidade 3** com a ROI atual, sem passar pela comparação.
Saída esperada:

```text
target='painel' handle=12345 roi=(120, 340, 400, 80)
outcome: fired
jsonl: C:\Users\...\AppData\Roaming\screen_watch\logs\alerts.jsonl
```

Você deve receber uma mensagem com a imagem da ROI (com `attach_roi: true`); a legenda mostra a
estratégia, o score e a severidade que dispararam o alerta. Código de saída `0` significa que a
cadeia disparou; `1` significa que nada disparou (veja abaixo).

### Validação automatizada (opt-in)

```powershell
$env:TEST_REAL_TELEGRAM="1"; python -m pytest -m integration -k from_app_config
```

Lê o **config ativo** (app-data), valida o token com `getMe` e envia uma foto sintética ao chat
configurado. Em falha, reporta a descrição do próprio Telegram (ex.:
`HTTP 400: Bad Request: chat not found`) e também detecta o erro clássico de usar o ID do próprio
bot como `chat_id`.

## Solução de problemas

- **`variable TELEGRAM_BOT_TOKEN missing, Telegram disabled` (aviso)** — o processo não viu a
  variável de ambiente. Defina-a e abra um terminal novo / reinicie o app.
- **`notifier telegram failed: HTTP 400/403: ...` (erro)** — a chamada HTTP falhou. A mensagem
  mostra a descrição do próprio Telegram (ex.: `chat not found`, `the bot can't send messages to
  the bot`) e nunca inclui o token. Causas mais comuns:
  - `401 Unauthorized`: token errado (ou revogado).
  - `400 Bad Request` / `chat not found`: `chat_id` errado; em grupos use o id negativo.
  - `403 Forbidden`: bot bloqueado, ou você nunca enviou `/start` a ele.
- **`outcome: fired` mas nenhuma mensagem** — outro canal (som/popup) pode ter disparado enquanto o
  Telegram falhou; `fired` não significa que *todos* os canais tiveram sucesso. Procure as linhas
  acima no console.
- **A mensagem parou depois da primeira** — o `cooldown_s` suprime repetições; a mudança pendente
  alerta de novo quando o cooldown expirar.
- **Sem aviso e sem mensagem** — confirme `enabled: true`, `severity_min` <= 3 (o alerta sintético é
  severidade 3) e que o bot pode postar naquela conversa.

## Relacionados

- [Alertas](Alertas.md) — canais, severidade, cooldown e re-arm
- [Configuração](Configuracao.md) — onde `alerts:` fica no YAML
- [doc/00 §11.2](../doc/00-Documento_de_Arquitetura_e_Especificação.md) — design do notificador Telegram
