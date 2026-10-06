# DPI e limitações
[English](DPI-and-Limitations.md) · **Português (Brasil)**

## Escala de tela (DPI)

Com `set_dpi_awareness()` no início do processo (feito pelo CLI e pela GUI), `pywinctl` e `mss` ficam
no **mesmo espaço físico** — medido em **15/15 janelas** (`pywinctl == GetWindowRect`). Por isso o
`resolver` usa o conversor identidade e **não há drift** no caminho de monitoramento, mesmo no
monitor de 125%. O `device_pixel_ratio` do Qt (`1.25` no primário) é do espaço **lógico** do Qt.

O overlay, por outro lado, recebe o arrasto em coordenadas lógicas do Qt e converte para físico com
`gui/overlay_geometry.to_physical` antes de gravar a seleção.

Ao iniciar `run`, o app verifica cada monitor, marca os adequados (`OK`, 100%) e avisa se a janela do
target estiver num monitor com escala. `probe-dpi` e `scripts/probe_dpi.py` mostram a matriz
(mss físico × Qt lógico × escala).

> Se um teste falhar em 125% ou 150% de escala no Windows, esse é o bug mais importante do projeto —
> priorize antes de qualquer feature.

## Limitações conhecidas (aceitas)

- **Wayland**: `mss` não captura. O app avisa e encerra o `run`; não há backend Wayland no
  protótipo. Rode em X11.
- **Janela ocluída**: `mss` captura pixels da tela, não a superfície da janela. Se outra janela
  cobrir a ROI, o frame conterá a janela sobreposta. **Não é bug a corrigir** — é limitação
  fundamental das APIs de captura.
- **Múltiplas ROIs (só na GUI)**: cada sessão tem a própria thread, backend de captura e buffers de
  preview/calibração, e o modo `advanced` (OCR) multiplica a CPU por sessão. O `ui.max_sessions`
  (padrão 4, faixa 1..16) limita; o `run` do CLI monitora uma única seleção.
- **macOS e ARM fora do build**: não há instalador nem validação; o build é Windows x64 + Linux
  amd64.
- **Tray no GNOME**: pode não aparecer sem extensão de tray; a janela continua funcional.
- **Som no Linux**: o CLI/`run` toca WAV/MP3/OGG/FLAC pelo `miniaudio` empacotado; a GUI depende dos
  plugins do GStreamer; formatos sem decoder (M4A/AAC no CLI) caem para um player externo
  (`paplay`/`aplay`/`ffplay`) e, sem ele, para o `beep` (o alerta nunca quebra).
- **SmartScreen**: os instaladores não são assinados; o Windows vai avisar (assinatura fora de
  escopo).
- **Elevação (UAC)**: as ações não contornam elevação; para interagir com apps elevados, rode o app
  em contexto equivalente.
- **Janela minimizada ou fechada**: o loop emite `target_unavailable` e segue tentando quando ela
  voltar.

## Robustez (Etapa H)

- **Coordenadas negativas/fora da tela**: a ROI é recortada contra o desktop virtual
  (`mss.monitors[0]`). Quando há recorte, o loop emite `capture_clipped`; quando a ROI cai 100%
  fora, emite `roi_off_screen` e pula o tick — sem quebrar o loop.
- **Falhas repetidas**: erros consecutivos idênticos (ex.: Tesseract ausente, token ausente) são
  reportados uma vez, não a cada tick.
- **Parada**: `stop()` sinaliza o evento e faz `join`; o `backend.close()` roda no `finally` do
  worker.
- **Backend na thread certa**: `mss` não é thread-safe; a instância é criada e fechada dentro da
  thread do loop.

## Relacionados

- [Uso (CLI)](Uso-CLI.md) — `probe-dpi`, eventos do loop
- [doc/00 §5.1 e §7.6](../doc/00-Documento_de_Arquitetura_e_Especificação.md) — decisões de design
