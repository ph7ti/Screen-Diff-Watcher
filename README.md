# Screen Diff Watcher

Aplicativo desktop multiplataforma (Python) que monitora uma região retangular (ROI) de
uma janela e alerta quando essa região sofre mudança visual.

Fonte única de verdade para o design: [`doc/00-Documento_de_Arquitetura_e_Especificação.md`](doc/00-Documento_de_Arquitetura_e_Especificação.md).
Leia-o inteiro antes de alterar qualquer decisão registrada.

## Estado atual

Implementado:

- Fronteira de plataforma (`platform/`): DPI awareness, detecção de Wayland, wrapper `pywinctl`,
  caminhos em app-data (`paths.py`), escala por monitor (`display.py`) e localização do Tesseract
  (`tesseract.py`).
- Camada de captura (`capture/`): `Frame`, protocolo de backend, backend `mss`, resolver
  janela→ROI (Modelo B), máscaras.
- Camada de comparação (`compare/`): `MeanColorStrategy`, `PerceptualHashStrategy`,
  `OCRTextDiffStrategy`, `ComparePipeline` com curto-circuito. Modo padrão: **`advanced`**
  (OCR puro); `default` = phash; `light` = cor média.
- Camada de alertas (`alerts/`): som, popup, Telegram, log JSONL e `AlertChain` com cooldown;
  `dispatch` devolve `DispatchOutcome`
  (`FIRED`/`SUPPRESSED_COOLDOWN`/`BELOW_MIN`/`NONE_ENABLED`/`FAILED`) para o re-arm. O som passa
  pela fronteira `platform/audio.py` (`winsound` no Windows; `paplay`/`aplay`/`ffplay` no Linux,
  `afplay` no macOS) — `alerts/` nao conhece `sys.platform`.
- Agendamento (`scheduler/loop.py`): `threading.Thread` + `Event.wait`. A janela de horário
  (`scheduler/schedule.py::is_open`, função pura) suspende **apenas as ações** fora do horário.
- Config (`config/`): schema v2 global (perfis `profiles`, `ui`, `schedule`, `evidence`) +
  loader YAML com defaults `advanced`, `rearm: true`, `lang="por+eng"`, `upscale=2`, validação de
  tipos com mensagem clara e gravação atômica com backup. O YAML v1 (`targets:`) ainda carrega por
  uma versão, com aviso, e é convertido por `migrate-config`. Persistência (`persistence/`): JSON de
  seleção v2 (com `overrides`) e `state.json` (`platform/paths.py`) para a última seleção/perfil.
- Evidências (`evidence/`): `EvidenceRecorder` grava prints da janela inteira (baseline/change) em
  `%TEMP%`, com retenção por contagem e por MB; desabilitado por padrão.
- Ações pseudo-humanas (`actions/`): passos `activate`/`click`/`move`/`type`/`key`/`wait`,
  ensaio (dry-run) por padrão, armado/temporizado (`ArmingController`), limites por minuto/sessão,
  guarda de foco e auditoria em `logs/actions.jsonl`. Backend `pynput` no extra opcional `input`.
- CLI (`__main__.py`): `init-config`, `validate-config` (`--selections`), `list-selections`,
  `migrate-config` (`--dry-run`), `list-windows`, `show-paths`, `probe-dpi`, `select-manual`
  (coordenadas), `select` (overlay), `test-alert`, `test-evidence`, `test-action`, `record-actions`,
  `compare-modes` (calibração), `run`, `gui`, `features` (diagnóstico do ambiente).
- Overlay de seleção (`gui/`): `overlay_geometry.py` (conversões lógico↔físico, sem Qt) e
  `overlay.py` (PyQt6, uma janela por monitor).
- GUI mínima + tray (`gui/`): `main_window.py` (lista de seleções, iniciar/parar, status/último
  resultado, novo target via overlay, abrir YAML) e `tray.py` (mostrar/ocultar, iniciar/parar,
  sair); eventos via fila + `QTimer` (`gui/controller.py`).
- Escada: `scripts/step1_absolute_roi.py`, `scripts/step2_anchored_roi.py`,
  `scripts/step3_selection_overlay.py`, `scripts/probe_dpi.py`.
- Empacotamento (PyInstaller onedir) com dois executáveis (`screen-watch` console e
  `screen-watch-gui` sem console) e instaladores nativos: **Inno Setup** (Windows) e **`.deb`**
  (Linux). Build por `scripts/build_release.py`; release por tag em
  `.github/workflows/release.yml`. Diagnóstico de ambiente pelo comando `features`.

Ainda não implementado / validação manual pendente:

- Validação manual da GUI/tray e do overlay em 100/125/150% (§6.3).
- Ícone da janela/tray no bundle, `StartupWMClass` do `.desktop`, tamanho do pacote e o aviso do
  SmartScreen (assinatura de código fora de escopo) — checar numa máquina/container limpos.

## Config, seleção e logs (app-data)

Tudo fica em `%APPDATA%\screen_watch` (`config.yaml`, `selections/`, `state.json`, `logs/`). Para
apontar para outro diretório, defina `SCREEN_WATCH_HOME`.

**Python da Microsoft Store (MSIX):** o Windows redireciona `%APPDATA%` para dentro do pacote, e
o arquivo fica invisível para o Explorer/editor. Nesse caso o app passa a usar o caminho real
(`...\AppData\Local\Packages\<pacote>\LocalCache\Roaming\screen_watch`). Rode
`python -m screen_watch show-paths` para ver o caminho efetivo.

O app regrava o YAML sem preservar comentários; a escrita é atômica (temp + `os.replace`)
e deixa um backup `config.yaml.bak`.

## Config global v2 (perfis, overrides e migração)

O `config.yaml` v2 é **global**: define um perfil ativo (`profile`), um ou mais `profiles` nomeados
(cada um com `defaults` + `alerts`), e as seções `ui`, `schedule` e `evidence`.

```yaml
version: 2
profile: default
profiles:
  default:
    defaults:
      mode: advanced
      poll_interval_s: 2.0
      rearm: true
      compare_options: { light: { threshold: 12.0 }, default: { hash_size: 8, threshold: 6 },
                         advanced: { similarity_threshold: 0.92, psm: 6, lang: "por+eng",
                                     upscale: 2, tesseract_cmd: null } }
    alerts:
      - { type: sound, enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.wav" }
  trabalho:
    defaults: { mode: default, poll_interval_s: 1.0 }
ui:
  hotkeys: { arm: "<ctrl>+<alt>+a", disarm: "<ctrl>+<alt>+d", toggle: "<ctrl>+<alt>+space",
             rearm: "<ctrl>+<alt>+r", abort: "<esc>" }
  arm_durations_min: [1, 5, 15, 30]
schedule: { enabled: false, days: [mon, tue, wed, thu, fri], windows: ["08:00-12:00"], timezone: local }
evidence: { enabled: false, dir: null, keep_per_target: 50, max_total_mb: 200 }
```

Regras: segredos nunca no YAML (mantém `bot_token_env`); `profile` inexistente é erro de validação;
`version` ausente com `targets:` é tratado como v1 legado (com aviso); `version` > 2 é erro.

Cada **seleção JSON** pode trazer `overrides` (`mode`, `masks`, `poll_interval_s`, `rearm` e,
adiante, `alerts`/`actions`) que **substituem** os valores do perfil para aquele alvo (não somam).
Seleções `version: 1` continuam carregando sem overrides.

Migração de um YAML v1:

```powershell
python -m screen_watch migrate-config --dry-run   # imprime o plano
python -m screen_watch migrate-config             # grava selections/*.json + config.yaml v2 (.bak)
python -m screen_watch list-selections            # lista as seleções (marca a última usada)
```

`run`/`test-alert`/`compare-modes`/`gui` aceitam `--selection NOME` (resolvido em `selections/`) ou
caminho e `--profile NOME`. Sem `--selection`, usa `state.json.last_selection`; se não houver,
lista as disponíveis e sai com erro. `--target` ainda funciona como alias deprecado de `--selection`.

## Requisitos

- Python 3.11+.
- **Tesseract** instalado no sistema (não vem com `pytesseract`) com os traineddata `por` e
  `eng`. Necessário apenas para o modo `advanced`. O executável é procurado no `PATH` e nos
  diretórios de instalação comuns do sistema; para forçar um caminho, use
  `compare_options.advanced.tesseract_cmd`. Sem o binário, o OCR falha com mensagem clara.
- Som: `simpleaudio` não tem wheel confiável para Python 3.13; instale com
  `pip install -e ".[sound]"` se o seu ambiente suportar (os instaladores **não** o incluem). Sem
  ele, o Windows usa `winsound` (com `MessageBeep()` quando não há `alert.wav`) e o Linux/macOS usa
  um player externo (`paplay`/`aplay`/`ffplay`, ou `afplay`). Sem player, o som fica silencioso
  (o alerta nunca quebra). No `.deb`, `pulseaudio-utils`/`alsa-utils` vêm como `Recommends`.
- Ações pseudo-humanas exigem `pynput` (`pip install -e ".[input]"`). Sem ele, as ações permanecem
  em ensaio e as hotkeys globais ficam indisponíveis (tray-only).
- O token do Telegram vem da variável de ambiente `TELEGRAM_BOT_TOKEN` (nunca do YAML).

## Escala de tela (DPI)

Com `set_dpi_awareness()` no início do processo (feito pelo CLI), `pywinctl` e `mss` ficam no
**mesmo espaço físico** — medido em 15/15 janelas (`pywinctl == GetWindowRect`). Por isso o
`resolver` usa o conversor identidade e **não há drift** no caminho de monitoramento, mesmo no
monitor de 125%. O `device_pixel_ratio` do Qt (`1.25` no primário) é do espaço lógico do Qt.

O overlay, por outro lado, recebe o arrasto em coordenadas lógicas do Qt e converte para físico
com `gui/overlay_geometry.to_physical` antes de gravar a seleção (doc §9.5).

Ao iniciar `run`, o app verifica cada monitor, marca os adequados (`OK`, 100%) e avisa se a janela
do target estiver num monitor com escala. `probe-dpi` e `scripts/probe_dpi.py` mostram a matriz.

## Instalação (código-fonte)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Instalação por binários (Windows e Linux)

Os instaladores são publicados no GitHub Releases (a partir da tag `v0.2.0`):

- **Windows** — `screen-diff-watcher_<versão>_windows_x64_setup.exe` (Inno Setup, per-machine,
  requer admin). Cria atalho no Menu Iniciar e, opcionalmente (desmarcados), na Área de Trabalho e o
  início automático com o Windows.
- **Linux (Debian/Ubuntu amd64)** — `screen-watch_<versão>_amd64.deb`
  (`sudo apt install ./screen-watch_<versão>_amd64.deb`). Requer X11 (Wayland não é suportado). O
  `.deb` declara `tesseract-ocr` + `tesseract-ocr-por` e as libs Qt6/X11 como dependências.

No Windows, o **SmartScreen** vai avisar porque o `.exe` não é assinado (assinatura fora de escopo):
use "Mais informações" → "Executar assim mesmo". O mesmo pode valer para o antivírus.

### Tesseract (OCR) automático

No Windows, se o Tesseract não estiver instalado, o instalador baixa o release fixado do
UB-Mannheim, **verifica o SHA256**, instala em silêncio e garante o `por.traineddata` (o pacote traz
`eng`). Precisa de rede e admin; se o download/verificação falhar, o instalador **avisa e continua** —
o app funciona em `light`/`default` e o `advanced` acusa a falta com a mensagem já existente.
**Offline**: instale o Tesseract manualmente (https://github.com/UB-Mannheim/tesseract/wiki) com os
traineddata `por` e `eng`; o instalador detecta o binário e não baixa nada.

No Linux, `tesseract-ocr` + `tesseract-ocr-por` vêm como dependência do `.deb`. A desinstalação
remove só o app e **preserva** o Tesseract e o app-data do usuário.

### Início automático (Linux)

O `.deb` não configura autostart. Para iniciar com a sessão, crie
`~/.config/autostart/screen-diff-watcher.desktop`:

```ini
[Desktop Entry]
Type=Application
Exec=screen-diff-watcher-gui
X-GNOME-Autostart-enabled=true
```

### Diagnóstico: `features`

```powershell
screen-watch features           # versão/origem, app-data, nº de seleções, Tesseract, entrada, som, tray, monitores
screen-watch features --json    # saída JSON (usada no smoke do CI)
```

Degrada sem display (não quebra) e informa se o binário é `bundle` ou `source`.

### Limitações dos instaladores

- **Wayland**: a captura via `mss` não funciona; rode em X11. O app avisa e encerra.
- **Tray no GNOME**: pode não aparecer sem extensão de tray; a janela continua funcional.
- **Som no Linux**: depende de `paplay`/`aplay`/`ffplay`; sem player, fica silencioso.
- **Arquitetura**: apenas `amd64`/`x86_64`. ARM fora de escopo.

## Build dos instaladores (desenvolvimento)

Guia completo (atualizar versão/pin do Tesseract, buildar, publicar e validar):
[`doc/01-Build_e_Release.md`](doc/01-Build_e_Release.md).

```powershell
python -m pip install -e ".[dev,build,input]"
python scripts/build_release.py --windows   # no Windows (ISCC.exe do Inno Setup no PATH)
python scripts/build_release.py --linux     # no Linux (dpkg-deb)
```

O script roda **no SO alvo** (sem cross-build), lê a versão de `screen_watch.__version__` (fonte
única; o `pyproject` usa versão dinâmica), roda o PyInstaller com `packaging/screen-watch.spec` e
grava os artefatos + `build-info.json` em `dist/installers/`. O ícone `.ico` é versionado; para
regenerá-lo, `python packaging/make_ico.py`.

Para publicar: crie a tag `vX.Y.Z` (igual a `__version__`) e faça push. O workflow
`.github/workflows/release.yml` builda os dois instaladores, gera `SHA256SUMS.txt` e publica o
GitHub Release; `workflow_dispatch` com `version` gera só os artefatos (sem release).

## Uso

```powershell
python -m screen_watch init-config            # cria o YAML v2 em app-data
python -m screen_watch validate-config --selections
python -m screen_watch list-windows          # handle/titulo/rect
python -m screen_watch probe-dpi             # monitores mss/Qt, escala e rect (matriz de DPI)
python -m screen_watch select --handle 12345 --name painel      # overlay: arrastar na tela
python -m screen_watch select-manual --handle 12345 --roi 120 340 400 80 --name painel
python -m screen_watch list-selections
python -m screen_watch migrate-config --dry-run
python -m screen_watch test-alert --selection painel        # alerta sintetico com o ROI atual
python -m screen_watch test-evidence --selection painel     # grava baseline+change de exemplo
python -m screen_watch run --selection painel               # nome em selections/
python -m screen_watch run --selection "%APPDATA%\screen_watch\selections\painel.json"
python -m screen_watch run --profile trabalho --selection painel
python -m screen_watch compare-modes --selection painel --delay 5   # calibracao (Etapa D)
python -m screen_watch show-paths
python -m screen_watch gui --profile default                # GUI minima + tray
python -m screen_watch features                             # diagnostico do ambiente
```

O `select` abre o overlay (uma janela por monitor): arraste com o botão esquerdo; botão direito
cancela. A seleção é gravada como JSON em app-data. Alternativa por coordenadas: `select-manual`.

O `run --selection` monta o target a partir do JSON de seleção + perfil do YAML. Os `overrides` da
seleção substituem os valores do perfil; sem YAML (ou com YAML v1), usa som + popup + log (Telegram
exige `chat_id`, então não entra no default).

## Máscara de regiões voláteis

Máscaras são retângulos `[x, y, w, h]` **relativos à ROI**, pintados de preto antes da comparação
(doc §8) — úteis para spinners/relógios que mudam sozinhos. O `MonitorLoop` aplica a máscara
capturada de `TargetConfig.masks` antes de entregar o `Frame` ao detector. O overlay ainda não
desenha máscaras (fora do MVP); por enquanto edite o campo `masks` no YAML ou no JSON de seleção.

## Evidências (prints)

Desabilitadas por padrão. Quando ligadas, o app grava prints da **janela inteira** (sem máscara) no
baseline e a cada mudança detectada — em
`%TEMP%\screen_watch\captures\<alvo>\<AAAAMMDD-HHMMSS-mmm>_<baseline|change>.png` (o `<alvo>` é o
nome do arquivo de seleção).

A forma mais simples de ligar é o checkbox **Gravar prints (evidências)** na janela: ele persiste em
`state.json` (`evidence_enabled`) e vale **sem editar o YAML** — inclusive com config v1 (`targets:`).
Se preferir pela config (v2), use a seção `evidence:` abaixo; o checkbox tem precedência sobre ela.

```yaml
evidence:
  enabled: true
  dir: null              # null = %TEMP%/screen_watch/captures
  keep_per_target: 50    # mantém os N mais recentes por alvo
  max_total_mb: 200      # teto total (todos os alvos)
  on_baseline: true
  on_change: true
```

Os prints ficam **só na sua máquina** (em `%TEMP%`, fora do repositório) e a retenção os poda após
cada gravação. Duas formas de gerar prints na hora, sem esperar um evento real (ambas **sempre**
gravam, mesmo com as evidências do loop desligadas):

```powershell
python -m screen_watch test-evidence --selection painel   # baseline+change, imprime caminhos
python -m screen_watch test-action --selection painel --armed   # print da execucao da acao
```

O botão **Executar ação (3s)** da janela também grava um print ao executar.

A janela tem o botão **Abrir pasta de prints**, que abre a pasta efetiva (`evidence.dir` quando
configurado, senão `%TEMP%/screen_watch/captures`) no gerenciador de arquivos — criando-a se ainda
não existir; **se os prints do loop estiverem desligados ele avisa no log**. O mesmo caminho aparece
em `python -m screen_watch show-paths` (linha `capturas:`, com nota quando há override). Abrir
pasta/arquivo passa sempre por `platform/shell.py::open_path` (`os.startfile` no Windows,
`open`/`xdg-open` nos demais); se não houver associação/utilitário, a GUI apenas registra
"abra manualmente: <caminho>".

Falhas ao gravar (permissão, disco, janela fora da tela) apenas geram `log.warning`; o
monitoramento continua.

## Ações pseudo-humanas (opt-in)

As ações são **opt-in e desarmadas por padrão**: em modo ensaio o app só registra o que faria (e
grava evidências), sem clicar. A execução real exige armar via tray, hotkey ou "armar por N min".
`Esc` aborta na hora. O backend de entrada (`pynput`) é um extra opcional:

```powershell
python -m pip install -e ".[input]"
```

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
        rebaseline: false               # default: baseline permanece apos a acao
        max_per_min: 6
        max_per_session: 100
        steps:
          - activate: true              # obrigatorio quando houver cliques
          - click: { x: 380, y: 40, ref: roi, button: left, clicks: 1 }
          - wait:  { ms: 400 }
          - key:   { keys: "ctrl+s" }
          - type:  { text: "abc", interval_ms: 60 }
ui:
  hotkeys: { arm: "<ctrl>+<alt>+a", disarm: "<ctrl>+<alt>+d", toggle: "<ctrl>+<alt>+space",
             rearm: "<ctrl>+<alt>+r", abort: "<esc>" }
  arm_durations_min: [1, 5, 15, 30]
```

`ref` é relativo à ROI (`roi`), à janela (`window`) ou absoluto na tela (`screen`). O passo `click`
exige um `activate` antes: o app foca a janela e confere `isActive`. No Windows o `SetForegroundWindow`
é assíncrono/bloqueado (foreground lock), então o foco é reconferido por ~0,5 s antes de abortar; o
motivo no log diferencia `activate recusado` de `foco não confirmou`. Como a execução é síncrona na
thread do loop, captura/comparação pausam durante a sequência. Um gatilho barrado por `cooldown_s`
aparece no log ao vivo como `skipped -> cooldown` (sem gravar no JSONL).

Arme/desarme por: itens do tray ("Armar ações"/"Desarmar ações"/"Armar por N min"), botão
**Re-armar** na janela (re-arma o baseline na hora), botão **Executar ação (3s)** (roda uma vez, com
contagem, fora do loop), ou hotkeys globais (quando o extra `input` está instalado; sem ele a GUI
avisa e fica tray-only).

Para testar sem esperar um evento real:

```powershell
python -m screen_watch test-action --selection painel            # ensaio (default)
python -m screen_watch test-action --selection painel --armed    # executa de verdade (com contagem de 3s)
python -m screen_watch test-action --selection painel --armed --no-countdown   # sem contagem
```

Em `--armed`, uma contagem de 3s aparece no topo da tela (overlay Qt **sem roubar foco**) para você
focar a janela-alvo; um clique no overlay cancela. `--no-countdown` pula a contagem (útil em
automação). O disparo automático por mudança no `run` **não** tem contagem (ele roda no loop). A
janela tem o botão equivalente **Executar ação (3s)**, que usa o subconjunto de ações marcado no
checklist e também respeita a contagem.

Cada gatilho (ensaio, execução, suspensão) vira uma linha em `logs/actions.jsonl` com passos,
resultado, duração, motivo e os caminhos das evidências.

### Criar ações pela janela

A janela tem os botões **Nova ação...**, **Editar...** e **Remover ação**, logo abaixo do checklist.
**Nova ação...** abre um formulário com nome, `enabled`, `severity_min` (gatilho), `cooldown_s`,
`settle_s`, `rebaseline` e uma lista de passos (`activate`, `click`, `move`, `key`, `type`, `wait`);
cada passo é adicionado com os campos do seu tipo (`x`/`y`/`ref`/`botão`/`cliques`, teclas, texto,
`ms`). Ao confirmar, o app valida com o **mesmo parser do YAML** (`parse_actions`): cliques exigem um
passo `activate` antes e filtros de texto exigem `mode: advanced`; erros aparecem num diálogo.

Para não adivinhar o `x`/`y`, há o botão **Localizar posição do mouse...** (nos passos `click`/`move`):
aparece uma caixa seguindo o cursor com os valores já no `ref` escolhido (mais o absoluto); mova o
mouse até o ponto e pressione **Enter** para preencher `x`/`y` (**Esc** ou clique direito cancela).
A conversão usa a mesma base do disparo: `roi` = ROI monitorada, `window` = janela-alvo, `screen` =
tela; se a janela/ROI não estiver disponível no momento, cai para `screen` e avisa.

As ações criadas pela janela são gravadas em `overrides.actions` do **JSON da seleção**
(`app-data/selections/<nome>.json`), então funcionam **mesmo com um `config.yaml` v1** (`targets:`) —
não é preciso migrar. Cada seleção tem o seu conjunto; a seleção atual continua podendo herdar ações do
perfil (v2) quando não há override. Ações que vêm do perfil/YAML aparecem no checklist, mas os botões
de editar/remover avisam que devem ser alteradas no YAML (os botões operam só sobre as ações da
própria seleção).

Depois de criar, use **Executar ação (3s)** para ensaiar a ação marcada, ou
`python -m screen_watch list-actions --selection <nome>` para conferir sem iniciar a sessão.

### Seleção de ações por sessão e log ao vivo

Abaixo da lista de seleções, o checklist **"Ações da sessão (aplicam no próximo start)"** mostra
todas as ações resolvidas da seleção/perfil atuais, com um contador "N de M selecionadas" e um
resumo (`[x]`/`[ ]`) no log. A escolha é **por nome de seleção** e persiste em
`state.json["action_selection"][seleção]`:

- **sem escolha salva** → todas as ações habilitadas rodam;
- **lista vazia** (tudo desmarcado) → nenhuma roda: a sessão **só monitora** (os alertas continuam).

Trocar o subconjunto vale **no próximo start** (mesma regra de perfil/modo); a sessão em execução
não muda. No CLI, `--actions` sobrepõe o subconjunto salvo **sem persistir**:

```powershell
python -m screen_watch run --selection painel --actions reprocessar,confirmar   # lista a,b
python -m screen_watch run --selection painel --actions none                    # so monitora
python -m screen_watch list-actions --selection painel                          # confere sem iniciar
```

`run` imprime o resumo das ações escolhidas e, durante a execução, uma linha por gatilho no
console (`[acao] ensaio|armed <nome> -> ok|falhou (motivo)|ensaio`). Na GUI, o mesmo evento aparece
no log. A auditoria em `logs/actions.jsonl` continua sendo a fonte de verdade; a linha ao vivo é
efêmera e respeita o `cooldown_s`.

## Perfis e agendador

Com mais de um perfil no YAML, a janela mostra um seletor **Perfil** (e o tray, um submenu
equivalente). A troca vale **no próximo start** — o loop ativo não muda; a UI e o `state.json`
registram o perfil escolhido. No CLI, use `--profile NOME` em `run`/`test-alert`/`test-action`/
`compare-modes`/`gui`.

```yaml
schedule:
  enabled: true
  days: [mon, tue, wed, thu, fri]
  windows: ["08:00-12:00", "13:30-18:00"]   # janelas que cruzam a meia-noite sao aceitas
  timezone: local
```

Fora da janela de horário o monitoramento e os alertas seguem normais, mas as **ações** ficam
suspensas (registrado como `suspended_schedule` na auditoria; o tooltip do status mostra "fora do
horário (ações suspensas)").

## Gravador de ações

Com o extra `input`, `record-actions` escuta cliques e teclas e gera um snippet pronto para colar
em `actions:`:

```powershell
python -m screen_watch record-actions --selection painel --out snippet.yaml
```

Fluxo padrão: contagem de 3s (mesmo overlay sem foco) → a gravação começa automaticamente → `F10`
encerra. Use `--no-countdown` para voltar ao `F9` manual (tempo para se preparar sem o overlay). O
clique no overlay cancela a contagem. Os cliques são convertidos de coordenadas absolutas para
`ref: roi`/`window` (ou `screen` se caírem fora da janela) e o snippet já inclui um passo `activate`
e o bloco `when` comentado, para você revisar antes de armar.

A contagem é chamada na **thread principal**, antes de criar os listeners do `pynput` (nunca dentro
do callback). Sem Qt/display (headless/Wayland), a contagem cai para o console (`3... 2... 1...`) e
segue. Ressalva: em Wayland a captura/entrada continuam limitadas (doc §14.1); a elevação (UAC) não
é contornada.

## Calibração (Etapa D)

`compare-modes` captura o ROI, espera `--delay` segundos (altere o painel nesse intervalo) e mede
`changed`/`score`/`threshold`/`severity` e o tempo de `compare` de cada modo (`--modes`,
`--repeat`). Para o `advanced`, imprime também os textos reconhecidos pelo OCR. Use isso para
ajustar `similarity_threshold`, `upscale`, `psm` e o `severity_min` dos alertas; registre cada
ajuste com contexto (doc §18.8).

`rearm: true` (default) torna o alerta edge-triggered: uma mudança sustentada alarma uma vez,
uma nova mudança realarma, e uma mudança durante o cooldown fica pendente e alarma ao expirar.
Se um alerta falhar (ex.: Telegram fora do ar), ele é re-tentado respeitando o `cooldown_s`
(backoff), sem martelar a cada tick.

## Radar (futuras implementações)

- **Seleção via CLI**: o `select-manual` cobre o uso por linha de comando; um fluxo de seleção
  totalmente CLI (sem overlay) ainda não está definido — avaliar viabilidade quando houver
  demanda.

## GUI e tray

`python -m screen_watch gui` abre a janela mínima: lista **apenas as seleções**
(`app-data/selections/*.json`), `Iniciar`/`Parar` (uma seleção por vez), status e último resultado,
`Novo target (overlay)` (escolhe a janela e abre o overlay), `Remover`, `Minimizar para o tray`
(esconde a janela sem encerrar o app) e `Abrir YAML` (config global). Duplo clique na lista
inicia/para. O tray oferece mostrar/ocultar, minimizar, iniciar/parar e sair.

Cada item da lista mostra o **nome do aplicativo**, a **região monitorada** e o **modo** — por
exemplo `Seleção WhatsApp — Região 120,340 400x80 — advanced`. Há um **seletor de modo**
(`light`/`default`/`advanced`) que vale para a próxima execução e é gravado no JSON da seleção, e um
seletor de **Perfil** (aplica no próximo start; o tray tem submenu equivalente).

O botão **Remover** apaga um ou mais JSONs de seleção selecionados (seleção múltipla com
Ctrl/Shift).

No `Novo target (overlay)`, a lista de janelas usa o **nome do aplicativo no estilo Gerenciador de
Tarefas** (`FileDescription`/`ProductName` do executável, com fallback para o nome do `.exe`) e
**oculta janelas que não são de aplicativos ativos** (invisíveis, ocultas pelo DWM, tool windows,
janelas filhas/auxiliares e sem título).

O loop roda em thread separada; a GUI só recebe eventos/resultados por fila (`QTimer`), nunca de
dentro do callback. O `Parar` encerra o loop e fecha o backend antes de sair.

## Limitações conhecidas (aceitas)

- **Wayland**: `mss` não captura. O app avisa e encerra; não há backend Wayland no protótipo.
- **Janela ocluída**: `mss` captura pixels da tela, não a superfície da janela. Se outra janela
  cobrir a ROI, o frame conterá a janela sobreposta. Não é bug a corrigir.

## Robustez (Etapa H)

- **Coordenadas negativas/fora da tela**: a ROI é recortada contra o desktop virtual
  (`mss.monitors[0]`). Quando há recorte, o loop emite `capture_clipped`; quando a ROI cai 100% fora,
  emite `roi_off_screen` e pula o tick — sem quebrar o loop.
- **Falhas repetidas**: erros consecutivos idênticos (ex.: Tesseract ausente, token ausente) são
  reportados uma vez, não a cada tick.
- **Parada**: `parar` sinaliza o evento e faz `join`; o `backend.close()` roda no `finally` do worker.
- **DPI**: `probe-dpi`/`scripts/probe_dpi.py` imprimem a matriz (mss físico × Qt lógico × escala).

## Testes

```powershell
python -m pytest                  # unitarios (padrao)
python -m pytest -m "not integration"
```

Testes que dependem de `imagehash`/`pytesseract` são pulados automaticamente se a dependência
não estiver instalada.

### Integração (opt-in, fora do CI)

```powershell
$env:TEST_REAL_CAPTURE="1"; python -m pytest -m integration
$env:TEST_REAL_TELEGRAM="1"; $env:TELEGRAM_BOT_TOKEN="..."; `
  $env:TELEGRAM_TEST_CHAT_ID="..."; python -m pytest -m integration
```
`TEST_REAL_CAPTURE` captura de verdade do monitor primário; `TEST_REAL_TELEGRAM` envia uma foto
sintética e falha se o HTTP não for 2xx (aceite do §1.3).

## CI (GitHub Actions)

`.github/workflows/ci.yml` roda `ruff check .` e `pytest -m "not integration"` em
**`ubuntu-latest` e `windows-latest`** × **Python 3.11 e 3.13**; em pull requests, o job `package`
(se recomendado) monta os instaladores sem publicar. O CI não instala `simpleaudio`, não usa
Tesseract (OCR é mockado) e não importa Qt na coleta de testes.

`.github/workflows/release.yml` builda os instaladores (Windows/latest, Linux `ubuntu-22.04`) a
partir de uma tag `v*.*.*` e publica o GitHub Release com `SHA256SUMS.txt`; `workflow_dispatch`
gera apenas os artefatos de workflow.

Configurações de ambiente necessárias em produção (nunca no YAML):
- `compare_options.advanced.tesseract_cmd` — caminho do Tesseract quando fora do `PATH`.
- `TELEGRAM_BOT_TOKEN` — token do bot, via `setx`/variável de ambiente.
- `SCREEN_WATCH_HOME` — opcional, redireciona a app-data.
