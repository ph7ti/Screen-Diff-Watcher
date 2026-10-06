"""Orquestracao: monta pipeline + cadeia de alertas + loop a partir da config.

Regra nao negociavel (doc, secao 10.6): o primeiro frame e baseline, nunca mudanca.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from screen_watch.alerts.chain import AlertChain, DispatchOutcome
from screen_watch.alerts.gate import AlertGate
from screen_watch.alerts.protocol import Notifier
from screen_watch.capture.frame import Frame
from screen_watch.compare.pipeline import MODE_STAGES, ComparePipeline
from screen_watch.compare.protocol import ComparisonResult
from screen_watch.config.loader import ConfigError
from screen_watch.config.schema import (
    AlertOptions,
    AppConfig,
    CompareOptions,
    EvidenceOptions,
    GlobalDefaults,
    ProfileOptions,
    TargetConfig,
)
from screen_watch.scheduler.loop import MonitorLoop, MonitorTarget

log = logging.getLogger(__name__)

ResultCallback = Callable[[ComparisonResult, DispatchOutcome], None]
FrameCallback = Callable[[Frame, bool], None]
CompareCallback = Callable[[ComparisonResult], None]

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

    watch = options.advanced.text_watch if mode == "advanced" else None
    if watch is not None and not watch.text.strip():
        watch = None  # texto vazio desliga o filtro (defensivo; o loader ja valida)

    stages = []
    for stage_name in MODE_STAGES[mode]:
        if watch is not None and stage_name == "default":
            # Com `text_watch` o gate de phash e bypassado: o OCR roda a cada tick e o
            # veredito do filtro e autoritativo (doc, secao 10.5). O ruido de OCR que
            # motivou o gate nao gera falso positivo aqui, pois o veredito e por
            # presenca, nao por similaridade.
            continue
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

            ocr = OCRTextDiffStrategy(
                similarity_threshold=options.advanced.similarity_threshold,
                psm=options.advanced.psm,
                lang=options.advanced.lang,
                upscale=options.advanced.upscale,
                tesseract_cmd=options.advanced.tesseract_cmd,
            )
            if watch is None:
                stages.append(ocr)
            else:
                from screen_watch.compare.text_watch import TextWatchStrategy  # noqa: PLC0415

                stages.append(
                    TextWatchStrategy(
                        ocr,
                        text=watch.text,
                        expect=watch.expect,
                        case_sensitive=watch.case_sensitive,
                        ignore_accents=watch.ignore_accents,
                    )
                )
    return ComparePipeline(stages)


def build_notifier(options: AlertOptions, target_name: str = "") -> Notifier | None:
    notifier = _build_notifier(options, target_name)
    if notifier is not None:
        # Chave de cooldown estavel e selecao do teste de envio (dois webhooks com
        # ids diferentes nao compartilham cooldown).
        notifier.uid = options.id or options.type
    return notifier


def _build_notifier(options: AlertOptions, target_name: str) -> Notifier | None:
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
    if options.type == "webhook":
        from screen_watch.alerts.http import WebhookNotifier  # noqa: PLC0415
        from screen_watch.config.schema import WebhookOptions  # noqa: PLC0415

        channel = options.options if isinstance(options.options, WebhookOptions) else WebhookOptions()
        return WebhookNotifier(
            channel,
            enabled=options.enabled,
            severity_min=options.severity_min,
            cooldown_s=options.cooldown_s,
            target_name=target_name,
        )
    if options.type == "http_post":
        from screen_watch.alerts.http import HttpPostNotifier  # noqa: PLC0415
        from screen_watch.config.schema import HttpPostOptions  # noqa: PLC0415

        channel = options.options if isinstance(options.options, HttpPostOptions) else HttpPostOptions()
        return HttpPostNotifier(
            channel,
            enabled=options.enabled,
            severity_min=options.severity_min,
            cooldown_s=options.cooldown_s,
            target_name=target_name,
        )
    if options.type == "syslog":
        from screen_watch.alerts.syslog import SyslogNotifier  # noqa: PLC0415
        from screen_watch.config.schema import SyslogOptions  # noqa: PLC0415

        channel = options.options if isinstance(options.options, SyslogOptions) else SyslogOptions()
        return SyslogNotifier(
            channel,
            enabled=options.enabled,
            severity_min=options.severity_min,
            cooldown_s=options.cooldown_s,
            target_name=target_name,
        )
    if options.type == "ntfy":
        from screen_watch.alerts.ntfy import NtfyNotifier  # noqa: PLC0415
        from screen_watch.config.schema import NtfyOptions  # noqa: PLC0415

        channel = options.options if isinstance(options.options, NtfyOptions) else NtfyOptions()
        return NtfyNotifier(
            channel,
            enabled=options.enabled,
            severity_min=options.severity_min,
            cooldown_s=options.cooldown_s,
            target_name=target_name,
        )
    if options.type == "smtp":
        from screen_watch.alerts.smtp import SmtpNotifier  # noqa: PLC0415
        from screen_watch.config.schema import SmtpOptions  # noqa: PLC0415

        channel = options.options if isinstance(options.options, SmtpOptions) else SmtpOptions()
        return SmtpNotifier(
            channel,
            enabled=options.enabled,
            severity_min=options.severity_min,
            cooldown_s=options.cooldown_s,
            target_name=target_name,
        )
    if options.type == "mqtt":
        from screen_watch.alerts.mqtt import MqttNotifier  # noqa: PLC0415
        from screen_watch.config.schema import MqttOptions  # noqa: PLC0415

        channel = options.options if isinstance(options.options, MqttOptions) else MqttOptions()
        return MqttNotifier(
            channel,
            enabled=options.enabled,
            severity_min=options.severity_min,
            cooldown_s=options.cooldown_s,
            target_name=target_name,
        )
    log.warning("unknown alert type ignored: %s", options.type)
    return None


def build_alert_chain(
    alerts: tuple[AlertOptions, ...],
    target_name: str = "",
    gate: AlertGate | None = None,
) -> AlertChain:
    notifiers = [
        n for n in (build_notifier(a, target_name) for a in alerts) if n is not None
    ]
    return AlertChain(notifiers, gate=gate)


def default_alerts() -> tuple[AlertOptions, ...]:
    """Alertas locais usados quando nao ha um target no YAML (som + popup + log)."""
    return (
        AlertOptions(type="sound", severity_min=1, cooldown_s=30.0),
        AlertOptions(type="popup", severity_min=1, cooldown_s=30.0),
        AlertOptions(type="log", severity_min=1, cooldown_s=0.0),
    )


def profile_from_config(
    config: AppConfig | None,
    profile_name: str | None = None,
    selection_name: str | None = None,
) -> ProfileOptions:
    """Resolve o perfil a usar, com fallback para o YAML v1 legado (doc, secao 12).

    Perfil explicito inexistente levanta `ConfigError` para o CLI/GUI mostrarem
    mensagem clara sem stacktrace.
    """
    if config is None or config.legacy or not config.profiles:
        return _legacy_profile(config, selection_name)
    name = profile_name or config.profile
    profile = config.profiles.get(name)
    if profile is None:
        raise ConfigError(code="config.profile_unknown", params={"name": name})
    return profile


def _legacy_profile(config: AppConfig | None, selection_name: str | None) -> ProfileOptions:
    if config is None or not config.targets:
        return ProfileOptions(alerts=default_alerts())
    target = config.get_target(selection_name) if selection_name else None
    if target is None:
        target = config.targets[0]
    return ProfileOptions(
        defaults=GlobalDefaults(
            mode=target.mode,
            poll_interval_s=target.poll_interval_s,
            rearm=target.rearm,
            compare_options=target.compare_options,
        ),
        alerts=target.alerts,
    )


def _state_evidence_toggle() -> bool | None:
    from screen_watch.platform.paths import load_state  # noqa: PLC0415

    value = load_state().get("evidence_enabled")
    return value if isinstance(value, bool) else None


def effective_evidence_options(config: AppConfig | None) -> EvidenceOptions:
    """Opcoes de evidencia efetivas: YAML (v2) + toggle de runtime da GUI.

    O toggle (`state.json["evidence_enabled"]`) tem precedencia e permite ligar/
    desligar prints pela janela, sem depender do YAML (funciona tambem com config
    v1). Sem toggle salvo, vale o `evidence.enabled` do YAML (default: desligado).
    """
    base = getattr(config, "evidence", None) if config is not None else None
    options = base if base is not None else EvidenceOptions()
    toggle = _state_evidence_toggle()
    if toggle is None:
        return options
    return replace(options, enabled=toggle)


def evidence_recorder(config: AppConfig | None, *, force_enabled: bool = False):
    """Recorder de evidencias efetivas (None se desligado)."""
    from screen_watch.evidence.recorder import EvidenceRecorder  # noqa: PLC0415

    return EvidenceRecorder.from_options(
        effective_evidence_options(config), force_enabled=force_enabled
    )


class MonitorSession:
    """Sink do `MonitorLoop`: baseline no 1o frame, comparacao + alerta nos demais.

    Edge-triggered: quando `target.rearm` e True, o baseline avanca apos um alerta
    efetivo (ou inutil), de modo que a mesma mudanca nao dispara de novo. Em
    `SUPPRESSED_COOLDOWN` e `FAILED` o baseline e mantido para a mudanca nao se
    perder (falhas re-tentam respeitando o cooldown/backoff).
    """

    def __init__(
        self,
        target: TargetConfig,
        on_result: ResultCallback | None = None,
        recorder: object | None = None,
        actions: object | None = None,
        on_action: Callable[[dict], None] | None = None,
        on_frame: FrameCallback | None = None,
        on_compare: CompareCallback | None = None,
        gate: AlertGate | None = None,
    ) -> None:
        self.target = target
        self.pipeline = build_pipeline(target.mode, target.compare_options)
        self.chain = build_alert_chain(target.alerts, target.name, gate=gate)
        self.rearm = bool(target.rearm)
        self.escalation = target.escalation
        self._on_result = on_result
        self._recorder = recorder
        self._on_frame = on_frame
        self._on_compare = on_compare
        self._initialized = False
        self._pending_rebaseline = False
        # Escalacao (doc, secao 11.3): FIRED mantem o baseline ate acknowledge().
        self._awaiting_ack = False
        if actions is None:
            from screen_watch.actions.dispatch import build_dispatcher  # noqa: PLC0415

            actions = build_dispatcher(target, recorder=recorder, on_event=on_action)
        self.actions = actions

    @property
    def awaiting_ack(self) -> bool:
        """True enquanto uma escalacao disparada espera o reconhecimento do usuario."""
        return self._awaiting_ack

    def __call__(self, frame: Frame) -> None:
        is_baseline = self._pending_rebaseline or not self._initialized
        if self._on_frame is not None:
            self._on_frame(frame, is_baseline)
        if self._pending_rebaseline:
            self._pending_rebaseline = False
            self._awaiting_ack = False
            self.pipeline.initialize(frame)
            self._initialized = True
            self._record("record_baseline", frame)
            return
        if not self._initialized:
            self.pipeline.initialize(frame)  # primeiro frame = baseline
            self._initialized = True
            self._record("record_baseline", frame)
            return
        result = self.pipeline.compare(frame)
        if self._on_compare is not None:
            self._on_compare(result)
        if self.actions is not None:
            # Gatilhos de tempo (doc, secao 11.4): avalia em todo frame
            # pos-baseline, mesmo sem mudanca; nunca no baseline.
            self.actions.on_tick(frame)
        if not result.changed:
            return
        outcome = self.chain.dispatch(result, frame)
        if (
            outcome is DispatchOutcome.FIRED
            and self.escalation.enabled
            and result.severity >= self.escalation.severity_min
        ):
            self._awaiting_ack = True
        if self._on_result is not None:
            self._on_result(result, outcome)
        # Evidencia atrelada a tentativa real de alerta: evita um print por tick
        # durante cooldown/snooze/escalacao (doc, secao 11.3/11.5).
        if outcome in (DispatchOutcome.FIRED, DispatchOutcome.FAILED):
            self._record("record_change", frame)
        rebaseline = False
        if self.actions is not None:
            rebaseline = bool(self.actions.on_result(result, frame))
        if rebaseline:
            self._awaiting_ack = False
            self.pipeline.initialize(frame)
        elif self._awaiting_ack:
            # Escalando: o baseline so avanca no acknowledge (ou no re-arm manual).
            return
        elif self.rearm and outcome in _REARM_OUTCOMES:
            self.pipeline.initialize(frame)

    def rebaseline_now(self, frame: Frame) -> None:
        """Re-arma o baseline manualmente (tray/botao/hotkey re-arm)."""
        self._awaiting_ack = False
        self.pipeline.initialize(frame)
        if self._on_frame is not None:
            self._on_frame(frame, True)

    def request_rebaseline(self) -> None:
        """Pede re-baseline no proximo frame (thread-safe; chamado pela GUI)."""
        self._awaiting_ack = False
        self._pending_rebaseline = True

    def acknowledge(self) -> None:
        """Reconhece a escalacao: zera o estado e re-arma o baseline (thread-safe)."""
        self._awaiting_ack = False
        self._pending_rebaseline = True

    def next_deadline_delay(self) -> float | None:
        """Deadline do proximo gatilho de tempo armado (doc, secao 3.5/11.4)."""
        if self.actions is None:
            return None
        return self.actions.next_deadline_delay()

    def _record(self, method: str, frame: Frame) -> None:
        if self._recorder is None:
            return
        callback = getattr(self._recorder, method, None)
        if callable(callback):
            callback(frame, self.target.name)


def build_loop(target: TargetConfig, session: MonitorSession, **kwargs: object) -> MonitorLoop:
    monitor_target = MonitorTarget(
        window_handle=target.window_handle,
        roi_relative=target.roi_relative,
        masks=target.masks,
    )
    if "deadline_provider" not in kwargs:
        provider = getattr(session, "next_deadline_delay", None)
        if callable(provider):
            kwargs["deadline_provider"] = provider
    return MonitorLoop(sink=session, interval_s=target.poll_interval_s, target=monitor_target, **kwargs)
