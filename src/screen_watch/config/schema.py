"""Dataclasses de configuracao (doc, secao 12.1)."""

from __future__ import annotations

from dataclasses import dataclass, field

Rect = tuple[int, int, int, int]
Point = tuple[int, int]


@dataclass(frozen=True)
class LightOptions:
    threshold: float = 12.0


@dataclass(frozen=True)
class DefaultOptions:
    hash_size: int = 8
    threshold: int = 6


@dataclass(frozen=True)
class AdvancedOptions:
    similarity_threshold: float = 0.92
    psm: int = 6
    lang: str = "por+eng"
    upscale: int = 2
    # Caminho do executavel do Tesseract quando ele nao esta no PATH.
    tesseract_cmd: str | None = None


@dataclass(frozen=True)
class CompareOptions:
    light: LightOptions = field(default_factory=LightOptions)
    default: DefaultOptions = field(default_factory=DefaultOptions)
    advanced: AdvancedOptions = field(default_factory=AdvancedOptions)


@dataclass(frozen=True)
class AlertOptions:
    type: str
    enabled: bool = True
    severity_min: int = 1
    cooldown_s: float = 30.0
    file: str = "alert.wav"
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id: str = ""
    attach_roi: bool = True
    # Usado apenas pelo notificador `log` (jsonl); vazio = app-data/logs/alerts.jsonl.
    path: str = ""


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


@dataclass(frozen=True)
class AppConfig:
    targets: tuple[TargetConfig, ...] = ()

    def get_target(self, name: str) -> TargetConfig | None:
        for target in self.targets:
            if target.name == name:
                return target
        return None


VALID_MODES = ("light", "default", "advanced")
