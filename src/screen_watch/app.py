"""Orquestracao: monta pipeline + cadeia de alertas + loop a partir da config.

Regra nao negociavel (doc, secao 10.6): o primeiro frame e baseline, nunca mudanca.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from screen_watch.alerts.chain import AlertChain, DispatchOutcome
from screen_watch.alerts.protocol import Notifier
from screen_watch.capture.frame import Frame
from screen_watch.compare.pipeline import MODE_STAGES, ComparePipeline
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.schema import AlertOptions, CompareOptions, TargetConfig
from screen_watch.scheduler.loop import MonitorLoop, MonitorTarget

log = logging.getLogger(__name__)

ResultCallback = Callable[[ComparisonResult, DispatchOutcome], None]

# Desfechos em que o baseline re-arma (alerta efetivo ou inutil). Em cooldown o
# baseline fica parado para a mudanca nao ser perdida (plano, secao 2).
_REARM_OUTCOMES = (
    DispatchOutcome.FIRED,
    DispatchOutcome.BELOW_MIN,
    DispatchOutcome.NONE_ENABLED,
)


def build_pipeline(mode: str, options: CompareOptions) -> ComparePipeline:
    if mode not in MODE_STAGES:
        raise ValueError(f"modo invalido: {mode!r}; use um de {MODE_STAGES}")

    stages = []
    for stage_name in MODE_STAGES[mode]:
        if stage_name == "light":
            from screen_watch.compare.light import MeanColorStrategy  # noqa: PLC0415

            stages.append(MeanColorStrategy(threshold=options.light.threshold))
        elif stage_name == "default":
            from screen_watch.compare.default import PerceptualHashStrategy  # noqa: PLC0415

            stages.append(
                PerceptualHashStrategy(
                    hash_size=options.default.hash_size, threshold=options.default.threshold
                )
            )
        elif stage_name == "advanced":
            from screen_watch.compare.advanced import OCRTextDiffStrategy  # noqa: PLC0415

            stages.append(
                OCRTextDiffStrategy(
                    similarity_threshold=options.advanced.similarity_threshold,
                    psm=options.advanced.psm,
                    lang=options.advanced.lang,
                    upscale=options.advanced.upscale,
                    tesseract_cmd=options.advanced.tesseract_cmd,
                )
            )
    return ComparePipeline(stages)


def build_notifier(options: AlertOptions) -> Notifier | None:
    if options.type == "sound":
        from screen_watch.alerts.sound import SoundNotifier  # noqa: PLC0415

        return SoundNotifier(
            file=options.file,
            enabled=options.enabled,
            severity_min=options.severity_min,
            cooldown_s=options.cooldown_s,
        )
    if options.type == "popup":
        from screen_watch.alerts.popup import PopupNotifier  # noqa: PLC0415

        return PopupNotifier(
            enabled=options.enabled,
            severity_min=options.severity_min,
            cooldown_s=options.cooldown_s,
        )
    if options.type == "telegram":
        from screen_watch.alerts.telegram import TelegramNotifier  # noqa: PLC0415

        return TelegramNotifier(
            chat_id=options.chat_id,
            bot_token_env=options.bot_token_env,
            enabled=options.enabled,
            severity_min=options.severity_min,
            cooldown_s=options.cooldown_s,
            attach_roi=options.attach_roi,
        )
    if options.type == "log":
        from screen_watch.alerts.log import JsonlNotifier  # noqa: PLC0415

        return JsonlNotifier(
            path=options.path or None,
            enabled=options.enabled,
            severity_min=options.severity_min,
            cooldown_s=options.cooldown_s,
        )
    log.warning("tipo de alerta desconhecido ignorado: %s", options.type)
    return None


def build_alert_chain(alerts: tuple[AlertOptions, ...]) -> AlertChain:
    notifiers = [n for n in (build_notifier(a) for a in alerts) if n is not None]
    return AlertChain(notifiers)


def default_alerts() -> tuple[AlertOptions, ...]:
    """Alertas locais usados quando nao ha um target no YAML (som + popup + log)."""
    return (
        AlertOptions(type="sound", severity_min=1, cooldown_s=30.0),
        AlertOptions(type="popup", severity_min=1, cooldown_s=30.0),
        AlertOptions(type="log", severity_min=1, cooldown_s=0.0),
    )


class MonitorSession:
    """Sink do `MonitorLoop`: baseline no 1o frame, comparacao + alerta nos demais.

    Edge-triggered: quando `target.rearm` e True, o baseline avanca apos um alerta
    efetivo (ou inutil), de modo que a mesma mudanca nao dispara de novo. Em
    `SUPPRESSED_COOLDOWN` e `FAILED` o baseline e mantido para a mudanca nao se
    perder (falhas re-tentam respeitando o cooldown/backoff).
    """

    def __init__(self, target: TargetConfig, on_result: ResultCallback | None = None) -> None:
        self.target = target
        self.pipeline = build_pipeline(target.mode, target.compare_options)
        self.chain = build_alert_chain(target.alerts)
        self.rearm = bool(target.rearm)
        self._on_result = on_result
        self._initialized = False

    def __call__(self, frame: Frame) -> None:
        if not self._initialized:
            self.pipeline.initialize(frame)  # primeiro frame = baseline
            self._initialized = True
            return
        result = self.pipeline.compare(frame)
        if not result.changed:
            return
        outcome = self.chain.dispatch(result, frame)
        if self._on_result is not None:
            self._on_result(result, outcome)
        if self.rearm and outcome in _REARM_OUTCOMES:
            self.pipeline.initialize(frame)


def build_loop(target: TargetConfig, session: MonitorSession, **kwargs: object) -> MonitorLoop:
    monitor_target = MonitorTarget(
        window_handle=target.window_handle,
        roi_relative=target.roi_relative,
        masks=target.masks,
    )
    return MonitorLoop(sink=session, interval_s=target.poll_interval_s, target=monitor_target, **kwargs)
