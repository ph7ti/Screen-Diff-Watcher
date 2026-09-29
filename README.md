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
- Camada de alertas (`alerts/`): som (com fallback `winsound`), popup, Telegram, log JSONL
  e `AlertChain` com cooldown; `dispatch` devolve `DispatchOutcome`
  (`FIRED`/`SUPPRESSED_COOLDOWN`/`BELOW_MIN`/`NONE_ENABLED`/`FAILED`) para o re-arm.
- Agendamento (`scheduler/loop.py`): `threading.Thread` + `Event.wait`.
- Config (`config/`): schema + loader YAML com defaults `advanced`, `rearm: true`,
  `lang="por+eng"`, `upscale=2`, validação de tipos com mensagem clara e gravação atômica
  com backup. Persistência (`persistence/`): JSON de seleção.
- CLI (`__main__.py`): `init-config`, `validate-config`, `list-windows`, `show-paths`,
  `probe-dpi`, `select-manual` (coordenadas), `select` (overlay), `test-alert`, `compare-modes`
  (calibração), `run`, `gui`.
- Overlay de seleção (`gui/`): `overlay_geometry.py` (conversões lógico↔físico, sem Qt) e
  `overlay.py` (PyQt6, uma janela por monitor).
- GUI mínima + tray (`gui/`): `main_window.py` (targets/seleções, iniciar/parar, status/último
  resultado, novo target via overlay, abrir YAML) e `tray.py` (mostrar/ocultar, iniciar/parar,
  sair); eventos via fila + `QTimer` (`gui/controller.py`).
- Escada: `scripts/step1_absolute_roi.py`, `scripts/step2_anchored_roi.py`,
  `scripts/step3_selection_overlay.py`, `scripts/probe_dpi.py`.

Ainda não implementado (na ordem da escada, §13):

- Empacotamento PyInstaller.
- Validação manual da GUI/tray e do overlay em 100/125/150% (§6.3).

## Config, seleção e logs (app-data)

Tudo fica em `%APPDATA%\screen_watch` (`config.yaml`, `selections/`, `logs/`). Para
apontar para outro diretório, defina `SCREEN_WATCH_HOME`.

**Python da Microsoft Store (MSIX):** o Windows redireciona `%APPDATA%` para dentro do pacote, e
o arquivo fica invisível para o Explorer/editor. Nesse caso o app passa a usar o caminho real
(`...\AppData\Local\Packages\<pacote>\LocalCache\Roaming\screen_watch`). Rode
`python -m screen_watch show-paths` para ver o caminho efetivo.

O app regrava o YAML sem preservar comentários; a escrita é atômica (temp + `os.replace`)
e deixa um backup `config.yaml.bak`.

## Requisitos

- Python 3.11+.
- **Tesseract** instalado no sistema (não vem com `pytesseract`) com os traineddata `por` e
  `eng`. Necessário apenas para o modo `advanced`. O executável é procurado no `PATH` e nos
  diretórios de instalação comuns do sistema; para forçar um caminho, use
  `compare_options.advanced.tesseract_cmd`. Sem o binário, o OCR falha com mensagem clara.
- `simpleaudio` não tem wheel confiável para Python 3.13; instale com `pip install -e ".[sound]"`
  se o seu ambiente suportar. Sem ele, o som cai para `winsound` no Windows (e
  `MessageBeep()` quando não há `alert.wav`).
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

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Uso

```powershell
python -m screen_watch init-config            # cria o YAML em app-data
python -m screen_watch validate-config
python -m screen_watch list-windows          # handle/titulo/rect
python -m screen_watch probe-dpi             # monitores mss/Qt, escala e rect (matriz de DPI)
python -m screen_watch select --handle 12345 --name painel      # overlay: arrastar na tela
python -m screen_watch select-manual --handle 12345 --roi 120 340 400 80 --name painel
python -m screen_watch test-alert --target painel_estoque   # alerta sintetico com o ROI atual
python -m screen_watch run --target painel_estoque
python -m screen_watch run --selection "%APPDATA%\screen_watch\selections\painel.json"
python -m screen_watch compare-modes --target painel_estoque --delay 5   # calibracao (Etapa D)
python -m screen_watch show-paths
python -m screen_watch gui                                                # GUI minima + tray
```

O `select` abre o overlay (uma janela por monitor): arraste com o botão esquerdo; botão direito
cancela. A seleção é gravada como JSON em app-data. Alternativa por coordenadas: `select-manual`.

O `run --selection` monta o target a partir do JSON. Se houver um target com o mesmo nome no YAML,
herda alertas/opções dele; senão usa som + popup + log (Telegram exige `chat_id`, então não entra
no default).

## Máscara de regiões voláteis

Máscaras são retângulos `[x, y, w, h]` **relativos à ROI**, pintados de preto antes da comparação
(doc §8) — úteis para spinners/relógios que mudam sozinhos. O `MonitorLoop` aplica a máscara
capturada de `TargetConfig.masks` antes de entregar o `Frame` ao detector. O overlay ainda não
desenha máscaras (fora do MVP); por enquanto edite o campo `masks` no YAML ou no JSON de seleção.

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

`python -m screen_watch gui` abre a janela mínima: lista de targets do YAML e de seleções
(`app-data/selections/*.json`), `Iniciar`/`Parar` (um target por vez), status e último resultado,
`Novo target (overlay)` (escolhe a janela e abre o overlay) e `Abrir YAML`. Duplo clique na lista
inicia/para. O tray oferece mostrar/ocultar, iniciar/parar e sair.

Cada item da lista mostra o **nome do aplicativo**, a **região monitorada** e o **modo** — por
exemplo `Seleção WhatsApp — Região 120,340 400x80 — advanced` ou
`[YAML] painel — ERP — Região 120,340 400x80 — advanced`. Há um **seletor de modo**
(`light`/`default`/`advanced`) que vale para a próxima execução; em seleções, o modo escolhido é
gravado no JSON (targets do YAML não são regravados).

O botão **Remover** apaga um ou mais itens selecionados (seleção múltipla com Ctrl/Shift): targets
do YAML são retirados e o arquivo é regravado (atômico, com backup); seleções têm o JSON apagado.

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
**`ubuntu-latest` e `windows-latest`** × **Python 3.11 e 3.13**. O CI não instala `simpleaudio`,
não usa Tesseract (OCR é mockado) e não importa Qt na coleta de testes.

Configurações de ambiente necessárias em produção (nunca no YAML):
- `compare_options.advanced.tesseract_cmd` — caminho do Tesseract quando fora do `PATH`.
- `TELEGRAM_BOT_TOKEN` — token do bot, via `setx`/variável de ambiente.
- `SCREEN_WATCH_HOME` — opcional, redireciona a app-data.
