# Screen Diff Watcher — Documento de Arquitetura e Especificação

> **Propósito deste documento**: servir como fonte única de verdade para que outra IA (ou desenvolvedor) implemente o projeto sem precisar reconstruir decisões. Toda decisão aqui registrada foi tomada deliberadamente; onde houver alternativas, elas estão listadas como "rejeitadas" com o motivo. **Não substitua uma decisão registrada por uma alternativa "mais moderna" sem justificativa explícita.**

---

## 1. Visão geral

### 1.1 O que o projeto é

Um aplicativo desktop **multiplataforma em Python** que:

1. Permite ao usuário **selecionar uma janela** e, dentro dela, uma **região retangular (ROI)**.
2. **Monitora essa ROI periodicamente** (intervalo configurável de 1 a X segundos).
3. Detecta **mudanças visuais** conforme um modo de comparação (Leve / Default / Avançado).
4. **Emite alertas** quando a mudança é confirmada: som local, popup local e/ou webhook remoto (Telegram inicialmente).

### 1.2 O que o projeto NÃO é

- Não é um gravador de tela.
- Não é um OCR de documentos.
- Não captura de janelas ocluídas (limitação fundamental da API de captura — ver §5.4).
- Não contorna DRM, anti-cheat ou janelas protegidas.
- Não depende de nenhum serviço em nuvem proprietário.

### 1.3 Caso de uso canônico

Monitorar um painel/indicador dentro de um aplicativo desktop (ex.: painel de estoque de um ERP) e alertar o usuário quando aquele painel sofrer alteração visual, sem exigir que o usuário fique olhando para a tela.

---

## 2. Princípios arquiteturais não negociáveis

Estes princípios guiam todas as decisões abaixo. Se um detalhe de implementação entrar em conflito com algum deles, o princípio vence.

1. **Captura e comparação são desacopladas por um contrato de dados (`Frame`).** A comparação nunca acessa a tela, nunca conhece janela, nunca dorme.
2. **Toda dependência de SO fica atrás de uma fronteira explícita.** Nada de `if sys.platform == ...` espalhado pelo código de negócio.
3. **DPI awareness é fixado no início do processo, antes de qualquer backend.** Ver §5.1.
4. **O loop de captura é cancelável imediatamente** e sua cadência é estável sob carga.
5. **Primeiro frame é baseline, não mudança.** O estado inicial da comparação é explícito, nunca implícito.
6. **Falhas de captura não quebram o loop.** Elas emitem evento e o próximo tick tenta de novo.
7. **Configuração é declarativa e persistida.** Nada de estado de sessão hardcoded.

---

## 3. Decisões de arquitetura (ADR resumido)

Cada item abaixo é uma decisão fechada. Formato: **Decisão → Motivo → Alternativas rejeitadas**.

### 3.1 Linguagem e runtime

- **Decisão**: Python 3.11+.
- **Motivo**: `Protocol`, `dataclass(frozen=True)`, `tomllib`/`typing` modernos, `asyncio` maduro; ampla disponibilidade de bindings para captura, GUI e OCR.
- **Rejeitado**: Python 3.9/3.10 (faltam recursos de tipagem usados no design); Rust/Go (custo de integração com `mss`, `pywinctl`, Tesseract não compensa para o escopo).

### 3.2 Captura de tela

- **Decisão**: **`mss`** como único backend no protótipo. `pyautogui` não é usado.
- **Motivo**: `mss` é mais rápido, retorna `numpy`-compatível direto, tem API estável entre plataformas, e mantém uma instância reutilizável.
- **Alternativas rejeitadas**:
  - `pyautogui` — mais lento, API de screenshot limitada; só valeria como fallback que não temos necessidade de usar.
  - `dxcam` / `d3dshot` — específicos de Windows com GPU; quebram a promessa multiplataforma.
  - `Pillow.ImageGrab` — cobre menos casos que `mss` e não traz vantagem.
- **Limitação conhecida e aceita**: `mss` **não funciona em Wayland**. O projeto deve, ao detectar Wayland (`XDG_SESSION_TYPE=wayland`), exibir aviso claro ao usuário de que a captura não é suportada, e encerrar graciosamente. **Não implementar backend Wayland no protótipo** — está fora de escopo.

### 3.3 Localização e ancoragem da janela

- **Decisão**: **`pywinctl`**, ancoragem por **Modelo B (relativo à origem da janela)**.
- **Motivo**: `pywinctl` é mantido e cross-platform. O Modelo B segue a janela quando ela se move, sem exigir acesso à client area (que é plumbing por SO).
- **Alternativas rejeitadas**:
  - `pygetwindow` — abandonado, só Windows/macOS com lacunas.
  - Modelo A (coordenadas absolutas congeladas) — quebra quando a janela se move.
  - Modelo C (relativo à client area, excluindo chrome) — mais robusto semanticamente, mas exige plumbing por SO desnecessário para o escopo.

### 3.4 Comparação

- **Decisão**: três estratégias plugáveis, compostas em **pipeline com curto-circuito**:
  1. **Leve** — `MeanColorStrategy` (cor média RGB + distância euclidiana).
  2. **Default** — `PerceptualHashStrategy` (`imagehash.phash`, `hash_size=8`).
  3. **Avançado** — `OCRTextDiffStrategy` (`pytesseract` + `difflib.SequenceMatcher`).
- **Motivo**: cada modo cobre um trade-off custo/sensibilidade. O pipeline permite que a estratégia barata "vete" as caras, reduzindo custo médio em regime estável.
- **Alternativas rejeitadas**:
  - Apenas phash — não distingue mudança semântica de ruído estrutural em alguns casos.
  - Apenas OCR — caro demais por tick, inviável em 1 Hz.
  - SSIM — mais caro que phash sem ganho claro para o caso de uso.

### 3.5 Agendamento

- **Decisão**: `threading.Thread` + `threading.Event.wait(timeout)` como loop principal.
- **Motivo**: cancelamento imediato, sem dependência extra, simples de raciocinar. O `wait` subtrai o tempo de trabalho do intervalo, garantindo cadência estável.
- **Alternativas rejeitadas**:
  - `asyncio` — overhead desnecessário; `mss`/`pywinctl` são síncronos e bloqueantes.
  - `APScheduler` — sobre-engenharia para um único loop.

### 3.6 Alertas

- **Decisão**: cadeia de notificadores (**Chain of Responsibility**), cada um com `enabled`, `severity_min`, `cooldown`. No protótipo, implementar:
  - **Som local** (`simpleaudio`).
  - **Popup local** (`plyer.notification`).
  - **Webhook Telegram Bot** (`httpx` ou `requests`).
- **Motivo**: Telegram é gratuito, confiável, permite anexar imagem do ROI no alerta (essencial para validar falsos positivos), e não exige setup de servidor.
- **Alternativas rejeitadas**:
  - `ntfy.sh` — igualmente válido, mas Telegram permite imagem + texto em uma única mensagem com menos atrito.
  - Pushover — pago.
  - FCM — complexidade de setup desproporcional.

### 3.7 GUI e overlay de seleção

- **Decisão**: **PyQt6** para GUI e overlay.
- **Motivo**: multi-monitor nativo (`QGuiApplication.screens()`), transparência real, alta DPI resolvida corretamente, `CompositionMode_Clear` disponível para o "buraco" da seleção.
- **Alternativas rejeitadas**:
  - `tkinter` — transparência e multi-monitor exigem gambiarras; `overrideredirect` quebra em alguns WMs Linux.
  - Nenhuma GUI (só config manual) — o caso de uso exige seleção visual.

### 3.8 Empacotamento

- **Decisão**: **PyInstaller**, build por plataforma.
- **Motivo**: mais maduro, ampla documentação, funciona nos 3 SOs.
- **Alternativas rejeitadas**:
  - Nuitka — mais rápido, mas build mais frágil e tempo de compilação maior.
  - Briefcase — promissor, mas ecossistema menor para o stack escolhido.

### 3.9 Configuração

- **Decisão**: **YAML** (`PyYAML`) para config do usuário; **JSON** para o dump de seleção de ROI.
- **Motivo**: YAML é legível para edição manual; JSON é gerado pela GUI e não precisa de comentários.
- **Alternativas rejeitadas**: TOML (bom, mas `tomllib` é read-only em versões antigas); INI (limitado para estruturas aninhadas).

---

## 4. Estrutura de diretórios proposta

```
screen_watch/
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md              # este documento
├── src/
│   └── screen_watch/
│       ├── __init__.py
│       ├── __main__.py          # entry point: python -m screen_watch
│       ├── app.py               # orquestrador, state machine
│       │
│       ├── platform/            # fronteira de SO
│       │   ├── __init__.py
│       │   ├── dpi.py           # SetProcessDpiAwareness, detecção de Wayland
│       │   └── window.py        # wrapper fino sobre pywinctl
│       │
│       ├── capture/
│       │   ├── __init__.py
│       │   ├── frame.py         # dataclass Frame
│       │   ├── backend.py       # Protocol ScreenCaptureBackend
│       │   ├── mss_backend.py   # implementação mss
│       │   ├── resolver.py      # resolver janela -> ROI absoluta
│       │   └── mask.py          # apply_mask
│       │
│       ├── compare/
│       │   ├── __init__.py
│       │   ├── protocol.py      # CompareStrategy, ComparisonResult
│       │   ├── light.py         # MeanColorStrategy
│       │   ├── default.py       # PerceptualHashStrategy
│       │   ├── advanced.py      # OCRTextDiffStrategy
│       │   └── pipeline.py      # ComparePipeline
│       │
│       ├── alerts/
│       │   ├── __init__.py
│       │   ├── protocol.py      # Notifier
│       │   ├── sound.py
│       │   ├── popup.py
│       │   ├── telegram.py
│       │   └── chain.py         # AlertChain
│       │
│       ├── scheduler/
│       │   ├── __init__.py
│       │   └── loop.py          # MonitorLoop (threading + Event)
│       │
│       ├── gui/
│       │   ├── __init__.py
│       │   ├── main_window.py
│       │   ├── overlay.py       # SelectionOverlay
│       │   └── tray.py          # pystray
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   ├── schema.py        # dataclasses de config
│       │   └── loader.py        # YAML <-> dataclass
│       │
│       └── persistence/
│           ├── __init__.py
│           └── selection.py     # dump/load do JSON de seleção
│
├── tests/
│   ├── fixtures/                # imagens de exemplo para testes de comparação
│   ├── test_compare_light.py
│   ├── test_compare_default.py
│   ├── test_compare_advanced.py
│   ├── test_pipeline.py
│   ├── test_resolver.py
│   └── test_loop.py
│
└── scripts/
    ├── step1_absolute_roi.py    # escada de teste (§10)
    ├── step2_anchored_roi.py
    ├── step3_selection_overlay.py
    └── ...
```

---

## 5. Fronteira de plataforma (`platform/`)

### 5.1 DPI awareness — obrigatório e primeiro

**Regra**: `set_dpi_awareness()` deve ser chamado **antes** de instanciar qualquer backend de captura, qualquer janela Qt, qualquer chamada a `pywinctl`. Idealmente, a primeira linha executável do `__main__.py`.

```python
# platform/dpi.py
import ctypes, sys, os

def set_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()

def is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
```

**Motivo**: sem isso, `pywinctl` (lógico) e `mss` (físico) discordam em escalas != 100%, e a ROI "escorrega" de forma silenciosa. É o bug mais caro de depurar se descoberto tarde.

**Wayland**: se `is_wayland()` retornar `True`, o app deve exibir mensagem clara e encerrar. Não tentar capturar.

### 5.2 Wrapper de janela (`platform/window.py`)

Encapsular `pywinctl` para que o resto do código nunca importe `pywinctl` diretamente.

Interface mínima:

```python
@dataclass(frozen=True)
class WindowInfo:
    handle: int
    title: str
    rect: tuple[int, int, int, int]   # (x, y, w, h) em espaço lógico
    is_minimized: bool
    exists: bool

def find_window_by_handle(handle: int) -> WindowInfo | None: ...
def list_windows() -> list[WindowInfo]: ...
```

**Regras**:
- Sempre identificar por `handle`. Título é apenas `title_hint` para exibição, nunca chave de lookup (muda em browsers, IDEs).
- Se `is_minimized` for `True`, o `rect` é lixo — o resolver deve retornar `None` e o loop emite `target_unavailable`.

---

## 6. Contrato `Frame`

Definição canônica. Qualquer estratégia de comparação consome apenas isto.

```python
# capture/frame.py
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class Frame:
    rgb: np.ndarray                     # (H, W, 3) uint8, ordem RGB
    timestamp: float                    # time.time()
    absolute_rect: tuple[int, int, int, int]   # espaço físico (para mss/debug)
    window_rect: tuple[int, int, int, int]     # espaço lógico (para debug)
    window_handle: int
    sequence: int                       # incrementa a cada tick bem-sucedido
```

**Invariantes**:
- `rgb.shape[2] == 3` e `dtype == np.uint8`.
- `rgb` já está mascarado (ver §8).
- `sequence` é monotônico por sessão de monitoramento; usado para descartar frames obsoletos se o consumidor atrasar.

---

## 7. Cadeia de captura — funcionamento detalhado

### 7.1 Fase de seleção (uma vez, por ROI)

Ordem exata dos passos:

1. Usuário escolhe a **janela-alvo** (lista com `list_windows()`, ou "clique na janela").
2. Overlay é exibido (ver §9).
3. Usuário arrasta o retângulo.
4. Ao soltar, o overlay emite um `QRect` em **coordenadas lógicas globais**.
5. **Imediatamente** consultar `window.getRect()` → `origin_at_selection`.
6. Converter rect lógico global → rect relativo à janela: `roi_relative = global_rect − origin_at_selection`.
7. Persistir JSON (§7.3).

**Regra crítica**: passo 5 deve acontecer antes de qualquer I/O, log, ou processamento. A janela pode se mover entre o `mouseRelease` e a persistência.

### 7.2 Fase de tick (loop)

```
┌─────────────────────────────────────────────────────────┐
│ 1. Resolver janela (handle → WindowInfo)                │
│    - se não existe: emitir target_unavailable, aguardar │
│    - se minimizada: emitir target_unavailable, aguardar │
│    - se rect saiu do virtual screen: log warning        │
├─────────────────────────────────────────────────────────┤
│ 2. Resolver ROI absoluta                                │
│    abs = roi_relative + window_rect.topLeft()           │
│    - converter de espaço lógico para físico (mss)       │
├─────────────────────────────────────────────────────────┤
│ 3. Capturar (mss, instância reutilizada)                │
├─────────────────────────────────────────────────────────┤
│ 4. Normalizar                                            │
│    - validar shape == (H, W, 3)                          │
│    - BGRA → RGB                                          │
├─────────────────────────────────────────────────────────┤
│ 5. Aplicar máscara                                       │
├─────────────────────────────────────────────────────────┤
│ 6. Emitir Frame para o sink                              │
└─────────────────────────────────────────────────────────┘
```

**Contrato de `_tick`**: retorna `Frame | None`. `None` significa "nada a processar neste tick" (janela ausente/minimizada/captura falhou), e o `sink` **não é chamado**.

### 7.3 Esquema do JSON de seleção

```json
{
  "version": 1,
  "window_handle": 123456,
  "window_title_hint": "ERP - Estoque",
  "origin_at_selection": [100, 200],
  "roi_relative": [120, 340, 400, 80],
  "mode": "default",
  "masks": []
}
```

Campos obrigatórios: `version`, `window_handle`, `origin_at_selection`, `roi_relative`. Os demais são opcionais com defaults.

### 7.4 Loop de captura — esqueleto

```python
def _run(self) -> None:
    sct = mss.mss()
    while not self._stop.is_set():
        t0 = time.perf_counter()
        try:
            frame = self._tick(sct)
            if frame is not None:
                self.sink(frame)
        except Exception as e:
            self.on_error(e)
        elapsed = time.perf_counter() - t0
        self._stop.wait(max(0.0, self.interval_s - elapsed))
```

**Decisões embutidas** (não alterar sem justificativa):
- `_stop.wait` é o único sleep. Nunca `time.sleep` dentro do loop.
- O tempo de trabalho é subtraído do intervalo.
- Exceções no `_tick` não quebram o loop.
- O `sink` (comparação) está fora do `try` de captura — captura e comparação são responsabilidades separadas.

### 7.5 Limitação de janela ocluída

`mss` captura **pixels da tela**, não a superfície da janela. Se outra janela cobrir a ROI, o frame capturado conterá o conteúdo da janela sobreposta. **Isto não é um bug a ser corrigido** — é uma limitação fundamental das APIs disponíveis. Documentar no README e na UI.

---

## 8. Máscara

### 8.1 Formato

Lista de retângulos `[x, y, w, h]` **relativos à ROI** (não absolutos, não relativos à janela). Sobrevivem a mover a janela.

### 8.2 Aplicação

```python
def apply_mask(rgb: np.ndarray, masks: list[tuple[int, int, int, int]]) -> np.ndarray:
    out = rgb.copy()
    for (x, y, w, h) in masks:
        out[y:y+h, x:x+w] = 0
    return out
```

- Pinta de **preto (0,0,0)**.
- **Motivo**: phash e mean color tratam preto de forma neutra. Para OCR, preto é aceitável no protótipo (não gera texto fantasma).
- **Ponto de aplicação**: estágio 5 da cadeia de captura, **antes** do `Frame` ser emitido. As estratégias nunca veem a máscara.

### 8.3 Regiões tipicamente mascaradas

Cursor, spinner de loading, relógio, indicador de rede, qualquer coisa que pisque. No protótipo, a lista pode ser vazia; o suporte deve existir desde o início.

---

## 9. Overlay de seleção (PyQt6)

### 9.1 Estratégia multi-monitor

**Decisão**: **uma janela por monitor**, não uma única janela cobrindo `virtualGeometry`.

**Motivo**: com DPI misto entre monitores, uma janela única força o Qt a mapear um único framebuffer para escalas distintas — comportamento varia por plataforma. Janela por tela simplifica o cálculo (cada uma opera no espaço do seu próprio `screen`).

```python
overlays = []
for screen in QGuiApplication.screens():
    ov = SelectionOverlay(screen)
    ov.setGeometry(screen.geometry())
    ov.show()
    overlays.append(ov)
```

Ao final do drag em um overlay, o rect é convertido para global somando `screen.geometry().topLeft()`.

### 9.2 Flags e atributos

```python
self.setWindowFlags(
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
)
self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
self.setCursor(Qt.CursorShape.CrossCursor)
```

### 9.3 Desenho do "buraco" da seleção

Usar `QPainter.CompositionMode.CompositionMode_Clear` para remover a máscara escura na área selecionada. **Não usar `setMask`** — é lento e problemático com DPI.

```python
painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
if self._origin and self._current:
    r = QRect(self._origin, self._current).normalized()
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.fillRect(r, Qt.GlobalColor.transparent)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.setPen(QPen(QColor("#0052d6"), 2))
    painter.drawRect(r)
```

### 9.4 High DPI no Qt

Antes de criar `QApplication`:

```python
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)
```

**Motivo**: evita que fatores como 1.25 sejam arredondados para 1.0, o que desalinha o overlay do `mss`.

### 9.5 Conversão lógico → físico

O `QRect` do Qt está em espaço **lógico**. O `mss` consome espaço **físico**.

```python
def to_physical(rect: QRect, screen) -> tuple[int, int, int, int]:
    dpr = screen.devicePixelRatio()
    offset = screen.geometry().topLeft()
    x = int((rect.x() - offset.x()) * dpr + offset.x() * dpr)
    y = int((rect.y() - offset.y()) * dpr + offset.y() * dpr)
    return (x, y, int(rect.width() * dpr), int(rect.height() * dpr))
```

**Nota**: com `SetProcessDpiAwareness(2)` + `PassThrough`, em muitos casos `dpr == 1.0` e a conversão é identidade. **Não assumir isso** — testar em 125%, 150%, 200%.

### 9.6 Validação pós-drag

Antes de persistir:

1. **Área mínima**: rejeitar retângulos com menos de 10×10 pixels lógicos.
2. **Dentro da janela-alvo**: converter para relativo e checar. Se extrapolar, **permitir mas logar warning** (alguns apps têm popups fora do rect principal).
3. **Origem capturada antes do I/O**: ver §7.1.

---

## 10. Comparação — interface e estratégias

### 10.1 Protocolo

```python
from typing import Protocol, Any
from dataclasses import dataclass

@dataclass(frozen=True)
class ComparisonResult:
    changed: bool
    score: float
    threshold: float
    strategy: str
    detail: dict[str, Any] | None = None

class CompareStrategy(Protocol):
    name: str
    def initialize(self, baseline: Frame) -> None: ...
    def compare(self, current: Frame) -> ComparisonResult: ...
```

**Regras**:
- `compare` é **função pura** sobre o `Frame` (pode ler estado interno, mas não I/O, não sono, não captura).
- `initialize` é chamado uma vez por sessão com o primeiro frame (baseline).
- `changed` sempre no mesmo sentido (True = mudança detectada). Para OCR, que naturalmente produz similaridade, normalizar antes de expor.

### 10.2 Estratégia Leve — `MeanColorStrategy`

```python
class MeanColorStrategy:
    name = "light"
    def __init__(self, threshold: float = 12.0):
        self.threshold = threshold
        self._baseline_mean = None

    def initialize(self, baseline: Frame) -> None:
        self._baseline_mean = baseline.rgb.mean(axis=(0, 1))

    def compare(self, current: Frame) -> ComparisonResult:
        current_mean = current.rgb.mean(axis=(0, 1))
        delta = float(np.linalg.norm(current_mean - self._baseline_mean))
        return ComparisonResult(
            changed=delta > self.threshold,
            score=delta, threshold=self.threshold, strategy=self.name,
        )
```

- `threshold=12.0` é ponto de partida empírico (escala 0–255).
- Se houver compressão JPEG no pipeline, subir para 20–25.
- **Não usar** para conteúdo textual ou estrutural fino.

### 10.3 Estratégia Default — `PerceptualHashStrategy`

```python
class PerceptualHashStrategy:
    name = "default"
    def __init__(self, hash_size: int = 8, threshold: int = 6):
        self.hash_size = hash_size
        self.threshold = threshold
        self._baseline_hash = None

    def initialize(self, baseline: Frame) -> None:
        img = Image.fromarray(baseline.rgb)
        self._baseline_hash = imagehash.phash(img, hash_size=self.hash_size)

    def compare(self, current: Frame) -> ComparisonResult:
        img = Image.fromarray(current.rgb)
        h = imagehash.phash(img, hash_size=self.hash_size)
        dist = int(self._baseline_hash - h)
        return ComparisonResult(
            changed=dist > self.threshold,
            score=float(dist), threshold=float(self.threshold),
            strategy=self.name,
        )
```

- `hash_size=8` (64 bits) é o default.
- `threshold` típico: 4–10. Começar com 6.
- **ROIs pequenas (< 100×100)**: phash fica instável. Considerar `hash_size=6` ou mudar para Leve.
- **`hash_size=16`**: mais sensível, mais caro, mais nervoso com anti-aliasing. Não usar como default.

### 10.4 Estratégia Avançada — `OCRTextDiffStrategy`

```python
class OCRTextDiffStrategy:
    name = "advanced"
    def __init__(self, similarity_threshold: float = 0.92,
                 psm: int = 6, lang: str = "eng"):
        self.similarity_threshold = similarity_threshold
        self.psm = psm
        self.lang = lang
        self._baseline_text = ""

    def _extract(self, rgb: np.ndarray) -> str:
        img = Image.fromarray(rgb)
        txt = pytesseract.image_to_string(
            img, lang=self.lang, config=f"--psm {self.psm}"
        )
        return " ".join(txt.split())

    def initialize(self, baseline: Frame) -> None:
        self._baseline_text = self._extract(baseline.rgb)

    def compare(self, current: Frame) -> ComparisonResult:
        current_text = self._extract(current.rgb)
        ratio = difflib.SequenceMatcher(
            None, self._baseline_text, current_text
        ).ratio()
        return ComparisonResult(
            changed=ratio < self.similarity_threshold,
            score=1.0 - ratio,             # normalizado: alto = mudou
            threshold=1.0 - self.similarity_threshold,
            strategy=self.name,
            detail={"baseline_text": self._baseline_text,
                    "current_text": current_text},
        )
```

**Pré-processamento recomendado para ROIs pequenas**:
- Upscale 2–3× com `cv2.INTER_CUBIC` antes do Tesseract.
- Escala de cinza + `cv2.threshold` com Otsu.
- `--psm 6` costuma ser melhor que o default 3 para ROI pequena de bloco único.
- Se o texto for disperso, usar `image_to_data` em vez de `image_to_string`.

**Performance**: OCR leva 100–500 ms por chamada. **Nunca rodar a cada tick em 1 Hz.** No pipeline (§10.5), ele só dispara após confirmação das camadas anteriores.

### 10.5 Pipeline com curto-circuito

```python
class ComparePipeline:
    def __init__(self, stages: list[CompareStrategy]):
        self.stages = stages

    def initialize(self, baseline: Frame) -> None:
        for s in self.stages:
            s.initialize(baseline)

    def compare(self, current: Frame) -> ComparisonResult:
        last = None
        for s in self.stages:
            last = s.compare(current)
            if not last.changed:
                return last
        return last
```

**Regra**: primeiro estágio que retornar `changed=False` encerra o pipeline. O veredito final é do último estágio que rodou.

**Configuração recomendada**: `[MeanColor, PerceptualHash, OCRTextDiff]` para o modo "Avançado". O modo "Default" pode ser apenas `[PerceptualHash]`. O modo "Leve", apenas `[MeanColor]`.

### 10.6 Estado inicial

**Regra não negociável**: o primeiro frame é **baseline**, não mudança. O pipeline é inicializado com ele via `initialize`, e `compare` só é chamado a partir do **segundo** frame.

---

## 11. Alertas

### 11.1 Protocolo

```python
class Notifier(Protocol):
    name: str
    enabled: bool
    severity_min: int
    cooldown_s: float

    def notify(self, result: ComparisonResult, frame: Frame) -> None: ...
```

**Regras**:
- `severity_min`: o notificador só dispara se a severidade da mudança for >= este valor.
- `cooldown_s`: após disparar, o notificador é silenciado por N segundos, independentemente de novas mudanças.
- `frame` é passado completo para permitir anexar a imagem do ROI (Telegram) ou logar contexto.

### 11.2 Notificadores do protótipo

**Som (`sound.py`)**:
- Biblioteca: `simpleaudio` (multiplataforma, WAV).
- **Não usar** `playsound` (abandonado).

**Popup (`popup.py`)**:
- Biblioteca: `plyer.notification`.
- Fallback documentado: `windows-toasts` (Windows), `pync` (macOS), `notify-send` via DBus (Linux).

**Telegram (`telegram.py`)**:
- Envio via `httpx` (ou `requests`) para `https://api.telegram.org/bot<token>/sendPhoto` ou `sendMessage`.
- **Anexar o screenshot do ROI** no momento do alerta — essencial para validar falsos positivos.
- Serializar `rgb` → PNG em memória (`PIL.Image.fromarray(...).save(buf, format="PNG")`).
- Timeout curto (5 s) para não travar o loop.

### 11.3 Encadeamento

```python
class AlertChain:
    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers
        self._last_fired: dict[str, float] = {}

    def dispatch(self, result: ComparisonResult, frame: Frame) -> None:
        now = time.time()
        for n in self.notifiers:
            if not n.enabled:
                continue
            if result.severity < n.severity_min:
                continue
            last = self._last_fired.get(n.name, 0.0)
            if now - last < n.cooldown_s:
                continue
            try:
                n.notify(result, frame)
                self._last_fired[n.name] = now
            except Exception as e:
                log.error("notifier %s failed: %s", n.name, e)
```

**Regra**: falha em um notificador **não** impede os demais. Cada um tem seu próprio `try`.

### 11.4 Ações pseudo-humanas (opt-in, `actions/`)

Reação **separada** dos alertas: avaliada depois do `AlertChain.dispatch` quando
`result.changed`, sem alterar o `DispatchOutcome` nem o re-arm dos alertas. Só
executa quando **armada**; por padrão fica em **ensaio** (dry-run), que registra o
que faria e grava evidências, sem clicar.

- **Gatilho**: `changed` (único suportado), `when.severity_min` e filtros de OCR
  (`text_any`/`text_all`/`text_regex`, case-insensitive por padrão). Filtros de
  texto exigem `mode: advanced` (validação recusa nos demais modos).
- **Passos**: `activate`/`click`/`move`/`type`/`key`/`wait`; `ref` é `roi`
  (relativo a `frame.absolute_rect`), `window` (`frame.window_rect`) ou `screen`.
  Clique exige `activate` antes (foco explícito + verificação `isActive`). Como o
  `SetForegroundWindow` do Windows é assíncrono/bloqueado (foreground lock), o foco
  é confirmado com pequenas pausas (~0,5 s no total antes de abortar); o motivo
  distingue `activate recusado` de `foco não confirmou` (`focus_changed: ...`).
- **Cooldown**: um gatilho ignorado por `cooldown_s` **não** vai para o JSONL (para
  não poluir), mas é publicado no log ao vivo como `skipped -> cooldown`.
- **Execução síncrona na thread do loop**: captura/comparação pausam durante a
  sequência; `settle_s` ao final. Limites `max_per_min`/`max_per_session`.
- **Re-arm**: `rebaseline: false` por padrão (o baseline permanece após a ação);
  `rebaseline: true` opt-in repete o gatilho (relatório/página). Re-arm manual em
  runtime (tray/botão/hotkey `rearm`, via `MonitorSession.request_rebaseline()`).
- **Ensaio x armado**: `ArmingController` com estados `disarmed`/`armed`/`timed`;
  estado só em memória, começa desarmado a cada sessão. `Esc` aborta na hora.
- **Agendador**: fora da janela de horário a ação é suspensa
  (`suspended_schedule`); monitoramento e alertas seguem.
- **Auditoria**: `logs/actions.jsonl` (ensaio, execução, suspensão, motivo,
  duração e caminhos das evidências).
- **Criação pela GUI**: `gui/action_editor.py` (`Nova ação...`/`Editar...`/`Remover
  ação`) grava em `overrides.actions` do JSON de seleção. Como `resolve_actions`
  lê os overrides antes do perfil, isso funciona também com config v1 (`targets:`),
  sem migração. A validação reusa `parse_actions` (clique exige `activate`,
  `text_*` exige `mode: advanced`), então as regras do YAML valem na janela;
  ações do perfil/YAML são somente leitura na GUI.
- **Localizador de posição**: `gui/locator.py::run_locator` (botão "Localizar
  posição do mouse..." nos passos `click`/`move`) mostra uma caixa seguindo o
  cursor; Enter/clique esquerdo confirma, Esc/clique direito cancela. Devolve o
  ponto global **lógico** (mesma base do `Frame`) e converte pelo `ref` via
  `overlay_geometry.resolve_ref_point` (`roi`→`absolute_rect`, `window`→
  `window_rect`, `screen`→origem); sem base, cai para `screen`. Difere do
  countdown: aqui o foco é necessário para capturar o Enter.
- **Seleção por sessão**: checklist na GUI (e `--actions` no CLI, one-shot) reduz
  o subconjunto por **nome de ação**; aplica só no próximo `build_target`. O estado
  fica em `state.json["action_selection"][seleção]` (chave ausente = todas, lista
  vazia = nenhuma). `resolve_actions` mantém a validação OCR/mode; o filtro apenas
  subtrai nomes (nunca reabilita `enabled: false`).
- **Log ao vivo**: cada gatilho emite um payload efêmero (`ActionDispatcher.on_event`
  → `MonitorSession.on_action` → `kind: "action_event"` na fila da GUI, distinto de
  `action` = comandos de tray/hotkey); a fonte de verdade continua sendo o JSONL.
- **Contagem de 3s**: fluxos avulsos (`test-action --armed`, `record-actions` e o
  botão "Executar ação (3s)" da GUI) usam `gui/countdown.py::run_countdown` — overlay
  Qt sem borda, always-on-top e `WindowDoesNotAcceptFocus`, **sem** `activateWindow`
  (a janela-alvo pode ser focada durante a contagem); clique cancela. Instanciado por
  `gui/qt_app.py::ensure_app` com `QEventLoop` (chamável de dentro da GUI). O disparo
  automático do loop **não** tem contagem. Fallback textual no console sem Qt/display.
- **Backend**: `pynput` como extra opcional (`pip install -e ".[input]"`), import
  preguiçoso em `platform/input.py`; sem ele, hotkeys caem para tray-only e a
  execução real falha com mensagem clara. Wayland/elevação seguem fora de escopo.

---

## 12. Configuração

### 12.1 Schema YAML v2 (config global por perfil)

O YAML deixou de ser uma lista de targets e passou a ser **configuração global**. Os alvos vivem
em arquivos de seleção JSON (`app-data/selections/*.json`); o YAML define perfis, alertas, atalhos,
agendador e evidências.

```yaml
version: 2
profile: default                 # perfil ativo; trocavel com --profile
profiles:
  default:
    defaults:
      mode: "advanced"           # "light" | "default" | "advanced"
      poll_interval_s: 2.0
      rearm: true
      compare_options:
        light:    { threshold: 12.0 }
        default:  { hash_size: 8, threshold: 6 }
        advanced: { similarity_threshold: 0.92, psm: 6, lang: "por+eng", upscale: 2,
                    tesseract_cmd: null }
    alerts:
      - { type: "sound",   enabled: true, severity_min: 1, cooldown_s: 30, file: "alert.wav" }
      - { type: "popup",   enabled: true, severity_min: 1, cooldown_s: 30 }
      - { type: "telegram", enabled: true, severity_min: 2, cooldown_s: 60,
          bot_token_env: "TELEGRAM_BOT_TOKEN", chat_id: "123456789",
          attach_roi: true }
  trabalho:
    defaults: { mode: "default", poll_interval_s: 1.0 }
ui:
  hotkeys: { arm: "<ctrl>+<alt>+a", disarm: "<ctrl>+<alt>+d", toggle: "<ctrl>+<alt>+space",
             rearm: "<ctrl>+<alt>+r", abort: "<esc>" }
  arm_durations_min: [1, 5, 15, 30]
schedule: { enabled: false, days: [mon, tue, wed, thu, fri], windows: ["08:00-12:00"], timezone: local }
evidence: { enabled: false, dir: null, keep_per_target: 50, max_total_mb: 200,
            on_baseline: true, on_change: true, per_step: false }
```

**Regras**:
- Tokens e segredos **nunca** no YAML. Usar variáveis de ambiente (`bot_token_env`).
- `profile` inexistente é `ConfigError`; `version` > 2 é `ConfigError`.
- `version` ausente com `targets:` é o v1 legado: carrega por uma versão, com aviso, e é
  convertido por `migrate-config` (backup `config.yaml.bak`, uma seleção JSON por target).
- `TargetConfig` continua sendo o contrato interno do runtime; o perfil + a seleção são resolvidos
  para ele por `persistence.selection.build_target`.

### 12.2 Perfis e defaults

Perfis nomeados (`profiles.<nome>.defaults` + `.alerts`) permitem alternar conjuntos de parâmetros
com `--profile`. A troca **aplica no próximo start** (não ao vivo). O perfil ativo também é gravado
em `state.json`.

### 12.3 Seleção JSON e overrides

Cada seleção é um JSON v2; `overrides` é opcional e **substitui** (não soma) os valores do perfil
para aquele alvo: `mode`, `masks`, `poll_interval_s`, `rearm` e, adiante, `alerts`/`actions`.
Seleções `version: 1` continuam carregando sem overrides.

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
  "overrides": { "poll_interval_s": 1.5, "rearm": false }
}
```

`window_title_hint` é apenas hint humano; o lookup usa `window_handle`. `roi_relative` é a fonte de
verdade para reconstruir a ROI a cada tick.

### 12.4 Estado, app-data e gravação

`platform/paths.py` centraliza `app_home()`, `config_path()`, `selections_dir()`, `logs_dir()` e
`state_path()`. `state.json` guarda `{"last_selection": "...", "profile": "...",
"action_selection": {"<seleção>": ["nome-da-acao", ...]}}` e é atualizado ao iniciar `run`/GUI com
sucesso (a chave `action_selection` é opcional e retrocompatível: ausente = todas as ações). O YAML é regravado de forma atômica (temp + `os.replace`) com
backup `config.yaml.bak`; `state.json` é atômico, sem backup.

A pasta de prints efetiva vem de `evidence/recorder.py::captures_dir(options)` (`evidence.dir`
quando configurado, senão `%TEMP%/screen_watch/captures`) e `ensure_captures_dir` a cria se faltar;
`show-paths` imprime-a como `capturas:` (com nota de override). Abrir pasta/arquivo é feito
exclusivamente por `platform/shell.py::open_path` (best-effort): `os.startfile` no Windows,
`open`/`xdg-open` nos demais, devolvendo `False` com `log.warning` quando não há
associação/utilitário — o botão "Abrir pasta de prints" da GUI e "Abrir YAML" usam esse helper.

Ligar/desligar os prints do loop não depende do YAML: `app.effective_evidence_options(config)` parte
do `evidence` do YAML (v2) e aplica o toggle de runtime `state.json["evidence_enabled"]` (checkbox
"Gravar prints" na GUI), que tem precedência — funciona também com config v1. O caminho avulso
(`run_actions` usado por `test-action --armed` e pelo botão "Executar ação (3s)") sempre grava print
quando recebe um `recorder` (`force_enabled=True`), respeitando `per_step` e registrando os caminhos
na auditoria.

### 12.5 Agendador, perfis na UI e gravador

- **Perfis na UI**: seletor na janela + submenu no tray; a troca vale no próximo start e persiste em
  `state.json.profile` (`--profile` no CLI).
- **Agendador** (`scheduler/schedule.py::is_open`, função pura): fora da janela de horário apenas as
  ações são suspensas (`suspended_schedule`); captura, comparação e alertas seguem.
- **Gravador** (`actions/recorder.py` + `record-actions`): com o extra `input`, captura cliques/teclas
  (F10 encerra), converte coordenadas absolutas para `ref: roi`/`window`/`screen` e gera um snippet de
  `actions:` com `when` comentado. Padrão: contagem de 3s e gravação automática
  (`before_start`/`auto_start=True`; a contagem roda na thread principal, antes dos listeners do
  `pynput`); `--no-countdown` mantém o `F9` explícito.
- **Seleção de ações na UI**: checklist "Ações da sessão" (`describe_action`/`describe_actions` em
  `actions/summary.py`) + contador "N de M"; persiste por nome de seleção
  (`actions/selection.py::load_action_selection`/`save_action_selection`) e vale no próximo start.
  No CLI, `--actions a,b|all|none` (one-shot, não persiste, precede o salvo) e `list-actions` para
  conferir; `run` imprime o resumo e as linhas ao vivo `[acao] <mode> <nome> -> ok|falhou|ensaio`.
- **Testes/validação**: `is_open` com relógio falso, conversão do gravador sem listener real e troca
  de perfil (próximo start).


---

## 13. Escada de teste (ordem obrigatória de implementação)

Implementar e validar **nesta ordem**. Cada passo é executável isoladamente antes de passar ao próximo.

1. **`step1_absolute_roi.py`** — ROI absoluta hardcoded, imprime hash a cada 1 s. Sem janela, sem mouse, sem GUI. **Objetivo**: validar que a captura funciona, medir Hz real.
2. **`step2_anchored_roi.py`** — adiciona ancoragem via `pywinctl` (Modelo B). Imprime `window_rect` atual + `abs_rect` + hash. Mover a janela e confirmar que a ROI segue. **Objetivo**: validar DPI e multi-monitor.
3. **`step3_selection_overlay.py`** — overlay PyQt6, seleção por mouse, dump do JSON de seleção. **Objetivo**: validar conversão lógico↔físico.
4. **Carregamento de JSON** — carregar o JSON do passo 3 e rodar captura ancorada.
5. **Máscara** — adicionar máscara e confirmar que mexer na área mascarada não altera o hash.
6. **Comparação** — plugar `ComparePipeline`. Testar com as três estratégias separadamente antes de compor.
7. **Alertas locais** — som + popup.
8. **Telegram** — webhook com imagem anexada.
9. **GUI completa** — janela principal, tray, edição de config.

**Não pular etapas.** Em particular, **não** começar pela GUI. O custo de depurar DPI/multi-monitor através da GUI é ordens de magnitude maior do que via script.

---

## 14. Armadilhas conhecidas (para a IA implementadora)

Cada item abaixo é uma armadilha **real** que já foi discutida e resolvida. Não reintroduzir.

1. **Wayland**: `mss` não captura. Detectar e avisar. Não tentar contornar no protótipo.
2. **DPI awareness fora de ordem**: se `SetProcessDpiAwareness` for chamado depois de `mss` ou Qt, não tem efeito. Chamar primeiro.
3. **`window_title_hint` como chave**: nunca. Usar `window_handle`.
4. **`time.sleep` no loop**: nunca. Usar `Event.wait`, subtraindo tempo de trabalho.
5. **Comparação dentro do `try` de captura**: nunca. Separação de responsabilidades.
6. **Primeiro frame como mudança**: nunca. É baseline.
7. **`setMask` no overlay**: nunca. Usar `CompositionMode_Clear`.
8. **Reconsultar `window.getRect()` depois do I/O**: nunca. Capturar imediatamente após o drag.
9. **`hash_size=16` como default**: nunca. 8.
10. **OCR a cada tick**: nunca. Só no pipeline avançado, com curto-circuito.
11. **`playsound`**: abandonado. Usar `simpleaudio`.
12. **`pygetwindow`**: abandonado. Usar `pywinctl`.
13. **Token no YAML**: nunca. Variável de ambiente.
14. **Criar `mss.mss()` a cada tick**: nunca. Instância reutilizada.
15. **Confiar em `devicePixelRatio()` como 1.0**: nunca. Testar em 125/150/200%.

---

## 15. Dependências (protótipo)

Organizadas por camada. Versões mínimas indicativas — fixar em `pyproject.toml`.

| Camada | Pacote | Uso |
|---|---|---|
| Captura | `mss` | captura de tela |
| Captura | `numpy` | buffer canônico |
| Janela | `pywinctl` | localização e geometria de janela |
| Comparação | `Pillow` | ponte `numpy` ↔ `imagehash`/Tesseract |
| Comparação | `imagehash` | phash |
| Comparação | `pytesseract` | OCR (requer binário Tesseract instalado) |
| Comparação | `opencv-python` (opcional) | pré-processamento de OCR |
| GUI | `PyQt6` | overlay e janela principal |
| Tray | `pystray` | ícone de bandeja |
| Alertas | `simpleaudio` | som |
| Alertas | `plyer` | popup |
| Alertas | `httpx` | Telegram |
| Config | `PyYAML` | config |
| Log | `structlog` (opcional) | log estruturado |
| Build | `pyinstaller` | empacotamento |

**Requisitos externos**:
- **Tesseract** instalado no sistema (não vem com `pytesseract`). Documentar no README.
- No Windows, `Tesseract` precisa estar no `PATH` ou ter caminho configurável.

---

## 16. Contratos entre módulos (resumo executivo)

Para referência rápida da IA implementadora:

```
platform/dpi.set_dpi_awareness()   → chamar PRIMEIRO
platform/window.find_window_by_handle(handle) → WindowInfo | None

capture/resolver.resolve(window_info, roi_relative) → abs_rect (físico) | None
capture/backend.capture(abs_rect) → np.ndarray
capture/mask.apply_mask(rgb, masks) → np.ndarray
capture/frame.Frame(rgb, ..., sequence)

compare/protocol.CompareStrategy.initialize(baseline: Frame)
compare/protocol.CompareStrategy.compare(current: Frame) → ComparisonResult
compare/pipeline.ComparePipeline.compare(current) → ComparisonResult

alerts/chain.AlertChain.dispatch(result, frame) → None

scheduler/loop.MonitorLoop(sink=callable, interval_s=float).start()/.stop()
```

**Fluxo de dados**:
```
MonitorLoop._tick
  → resolver.resolve
  → backend.capture
  → mask.apply_mask
  → Frame
  → sink(frame)
      → ComparePipeline.compare
      → AlertChain.dispatch
```

---

## 17. Glossário

- **ROI** — Region of Interest; o retângulo monitorado dentro da janela.
- **Baseline** — primeiro frame capturado em uma sessão; referência para comparação.
- **Modelo B** — ancoragem por origem da janela: `abs = roi_relative + window_rect.topLeft()`.
- **Pipeline** — composição de estratégias de comparação com curto-circuito.
- **Frame** — dataclass imutável com `rgb` (numpy) e metadados de captura.
- **Tick** — uma iteração do loop de captura.
- **DPR** — device pixel ratio; fator entre espaço lógico e físico.
- **Chrome** — elementos não-cliente de uma janela (barra de título, bordas).

---

## 18. Notas finais para a IA implementadora

1. **Leia este documento inteiro antes de escrever código.** Muitas decisões aqui parecem arbitrárias isoladamente, mas têm motivação registrada.
2. **Siga a escada de teste (§13) na ordem.** Ela existe para reduzir o espaço de busca de bugs.
3. **Se algo aqui parecer errado ou insuficiente, registre como comentário/issue — não mude silenciosamente.** Decisões foram tomadas com trade-offs explícitos.
4. **Toda dependência de SO fica em `platform/`.** Nunca importe `pywinctl` fora dessa pasta.
5. **A comparação nunca toca em tela, janela, ou sono.** Se sua implementação precisar de qualquer um desses, o design foi violado.
6. **Primeiro frame é baseline.** Se seu código dispara alerta no primeiro tick, há bug.
7. **Se um teste falhar em 125% ou 150% de escala no Windows, isso é o bug mais importante do projeto.** Priorize antes de qualquer feature.
8. **Documente cada experimento empírico** (thresholds, hash_size, psm) com o contexto em que foi ajustado. Os defaults são pontos de partida, não verdades.