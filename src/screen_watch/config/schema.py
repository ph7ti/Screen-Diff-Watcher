"""Dataclasses de configuracao (doc, secao 12).

`TargetConfig` continua sendo o contrato interno do runtime
(`MonitorSession`/`build_loop`); a config global v2 (perfis) e resolvida para
ele a partir de uma selecao (`persistence.selection.build_target`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from screen_watch.actions.protocol import ActionSpec

Rect = tuple[int, int, int, int]
Point = tuple[int, int]

VALID_MODES = ("light", "default", "advanced")
VALID_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
VALID_TEXT_WATCH_EXPECTS = ("appears", "disappears")
VALID_ALERT_TYPES = (
    "sound",
    "popup",
    "telegram",
    "log",
    "webhook",
    "http_post",
    "syslog",
)
VALID_ALERT_METHODS = ("POST", "PUT", "PATCH")
VALID_SYSLOG_PROTOCOLS = ("udp", "tcp")
VALID_SYSLOG_FACILITIES = (
    "kern",
    "user",
    "mail",
    "daemon",
    "auth",
    "syslog",
    "lpr",
    "news",
    "uucp",
    "cron",
    "authpriv",
    "ftp",
    "ntp",
    "security",
    "console",
    "solaris-cron",
    "local0",
    "local1",
    "local2",
    "local3",
    "local4",
    "local5",
    "local6",
    "local7",
)
VALID_SYSLOG_LEVELS = (
    "emergency",
    "alert",
    "critical",
    "error",
    "warning",
    "notice",
    "informational",
    "debug",
)


@dataclass(frozen=True)
class LightOptions:
    threshold: float = 12.0


@dataclass(frozen=True)
class DefaultOptions:
    hash_size: int = 8
    threshold: int = 6


@dataclass(frozen=True)
class TextWatchOptions:
    """Filtro de presenca de texto na ROI (somente no modo `advanced`).

    Com um `text_watch` ativo o OCR roda a cada tick (sem o gate de phash) e o
    alerta dispara somente na transicao escolhida.
    """

    text: str = ""
    expect: str = "appears"
    case_sensitive: bool = False
    ignore_accents: bool = True


@dataclass(frozen=True)
class AdvancedOptions:
    similarity_threshold: float = 0.92
    psm: int = 6
    lang: str = "por+eng"
    upscale: int = 2
    # Caminho do executavel do Tesseract quando ele nao esta no PATH.
    tesseract_cmd: str | None = None
    # Filtro por presenca de texto (`None` = so o diff de OCR normal).
    text_watch: TextWatchOptions | None = None


@dataclass(frozen=True)
class CompareOptions:
    light: LightOptions = field(default_factory=LightOptions)
    default: DefaultOptions = field(default_factory=DefaultOptions)
    advanced: AdvancedOptions = field(default_factory=AdvancedOptions)


@dataclass(frozen=True)
class WebhookOptions:
    """Opcoes do canal `webhook` (POST JSON para uma URL de webhook)."""

    url: str = ""
    url_env: str = ""
    method: str = "POST"
    headers: tuple[tuple[str, str], ...] = ()
    payload: dict[str, Any] | None = None
    payload_raw: str = ""
    timeout_s: float = 5.0
    verify_tls: bool = True


@dataclass(frozen=True)
class HttpPostOptions:
    """Opcoes do canal `http_post` (URL completa ou host/port/path/scheme)."""

    url: str = ""
    url_env: str = ""
    scheme: str = "http"
    host: str = ""
    port: int = 0
    path: str = ""
    method: str = "POST"
    headers: tuple[tuple[str, str], ...] = ()
    payload: dict[str, Any] | None = None
    payload_raw: str = ""
    timeout_s: float = 5.0
    verify_tls: bool = True


@dataclass(frozen=True)
class SyslogOptions:
    """Opcoes do canal `syslog` (informativo; sem imagem)."""

    host: str = ""
    port: int = 514
    protocol: str = "udp"
    facility: str = "local0"
    app_name: str = "screen-diff-watcher"
    payload_raw: str = ""
    severity_map: tuple[tuple[int, str], ...] = ()
    timeout_s: float = 5.0
    append_nul: bool = False


AlertChannelOptions = WebhookOptions | HttpPostOptions | SyslogOptions


@dataclass(frozen=True)
class AlertOptions:
    type: str
    enabled: bool = True
    severity_min: int = 1
    cooldown_s: float = 30.0
    file: str = "alert.mp3"
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id: str = ""
    attach_roi: bool = True
    # Usado apenas pelo notificador `log` (jsonl); vazio = app-data/logs/alerts.jsonl.
    path: str = ""
    # Identificador estavel do alerta (chave de cooldown e selecao do teste de envio).
    id: str = ""
    # Opcoes aninhadas dos canais novos (webhook/http_post/syslog).
    options: AlertChannelOptions | None = None


@dataclass(frozen=True)
class HumanizeOptions:
    """Ruido pseudo-humano (doc, secao 12.2); `seed` so para testes deterministicos."""

    mouse_steps: int = 24
    key_interval_ms: int = 60
    jitter_px: int = 3
    wait_jitter_ms: int = 150
    seed: int | None = None


@dataclass(frozen=True)
class GlobalDefaults:
    """Valores padrao de um perfil (doc, secao 12.2)."""

    mode: str = "advanced"
    poll_interval_s: float = 2.0
    rearm: bool = True
    compare_options: CompareOptions = field(default_factory=CompareOptions)
    humanize: HumanizeOptions = field(default_factory=HumanizeOptions)


@dataclass(frozen=True)
class ProfileOptions:
    """Um perfil nomeado: defaults + alertas + acoes."""

    defaults: GlobalDefaults = field(default_factory=GlobalDefaults)
    alerts: tuple[AlertOptions, ...] = ()
    actions: tuple[ActionSpec, ...] = ()


@dataclass(frozen=True)
class EvidenceOptions:
    enabled: bool = False
    dir: str | None = None
    keep_per_target: int = 50
    max_total_mb: int = 200
    on_baseline: bool = True
    on_change: bool = True
    per_step: bool = False


@dataclass(frozen=True)
class UiOptions:
    hotkeys: tuple[tuple[str, str], ...] = ()
    arm_durations_min: tuple[int, ...] = (1, 5, 15, 30)
    # Idioma da GUI: "auto" (locale do SO) ou uma tag descoberta em i18n/*.json.
    language: str = "auto"

    def hotkey(self, name: str, default: str = "") -> str:
        for key, value in self.hotkeys:
            if key == name:
                return value
        return default


@dataclass(frozen=True)
class ScheduleOptions:
    enabled: bool = False
    days: tuple[str, ...] = ()
    windows: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetConfig:
    name: str
    window_handle: int
    roi_relative: Rect
    origin_at_selection: Point | None = None
    window_title_hint: str = ""
    mode: str = "advanced"
    poll_interval_s: float = 2.0
    rearm: bool = True
    masks: tuple[Rect, ...] = ()
    compare_options: CompareOptions = field(default_factory=CompareOptions)
    alerts: tuple[AlertOptions, ...] = ()
    actions: tuple[ActionSpec, ...] = ()
    humanize: HumanizeOptions = field(default_factory=HumanizeOptions)
    schedule: ScheduleOptions = field(default_factory=ScheduleOptions)
    # Nome de exibicao da selecao (a GUI grava; `name` continua sendo o arquivo).
    label: str = ""


@dataclass(frozen=True)
class AppConfig:
    """Config global v2. `targets`/`legacy` sobrevivem apenas para o YAML v1."""

    version: int = 2
    profile: str = "default"
    profiles: dict[str, ProfileOptions] = field(default_factory=dict)
    evidence: EvidenceOptions = field(default_factory=EvidenceOptions)
    ui: UiOptions = field(default_factory=UiOptions)
    schedule: ScheduleOptions = field(default_factory=ScheduleOptions)
    targets: tuple[TargetConfig, ...] = ()
    legacy: bool = False

    def get_target(self, name: str) -> TargetConfig | None:
        for target in self.targets:
            if target.name == name:
                return target
        return None

    def resolve(self, name: str | None = None) -> ProfileOptions:
        """Perfil ativo/explicito; `KeyError` claro se nao existir."""
        profile_name = name or self.profile
        profile = self.profiles.get(profile_name)
        if profile is None:
            raise KeyError(f"profile inexistente: {profile_name!r}")
        return profile
