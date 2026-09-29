"""Entry point: `python -m screen_watch <comando>`.

`set_dpi_awareness()` e a primeira coisa executada, antes de qualquer backend de
captura, janela Qt ou chamada a `pywinctl` (doc, secao 5.1).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import NamedTuple

from screen_watch.platform.dpi import is_wayland, set_dpi_awareness
from screen_watch.platform.paths import config_path

log = logging.getLogger("screen_watch")

MIN_ROI_SIDE = 10


class CapturedSelection(NamedTuple):
    path: Path
    roi_relative: tuple[int, int, int, int]
    fits_window: bool


def _cmd_init_config(args: argparse.Namespace) -> int:
    from pathlib import Path

    from screen_watch.config.loader import default_config_dict, save_config
    from screen_watch.platform.paths import ensure_dirs

    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"ja existe: {path} (use --force para sobrescrever)")
        return 1
    ensure_dirs()
    save_config(path, default_config_dict())
    print(f"config criada em: {path}")

    from screen_watch.platform.paths import package_family_name

    if package_family_name():
        print("(Python da Store/MSIX: caminho real de app-data, visivel fora do pacote)")
    return 0


def _cmd_validate_config(args: argparse.Namespace) -> int:
    from screen_watch.config.loader import ConfigError, load_config

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config invalida: {exc}")
        return 1
    if config.legacy:
        print("aviso: YAML v1 (targets); rode 'migrate-config' para o formato v2")
        print(f"ok: {len(config.targets)} target(s) legado(s)")
    else:
        print(f"ok: {len(config.profiles)} perfil(is); ativo={config.profile!r}")

    if getattr(args, "selections", False):
        return _validate_selections()
    return 0


def _validate_selections() -> int:
    from screen_watch.config.loader import parse_actions, parse_overrides
    from screen_watch.persistence.selection import load_selection
    from screen_watch.platform.paths import selections_dir

    paths = sorted(selections_dir().glob("*.json"))
    failures = 0
    for path in paths:
        try:
            selection = load_selection(path)
            overrides = parse_overrides(selection.overrides)
            actions_raw = overrides.get("actions")
            if actions_raw is not None:
                mode = overrides.get("mode", selection.mode)
                parse_actions(actions_raw, "overrides.actions", mode=mode)
        except (OSError, ValueError) as exc:
            print(f"selecao invalida {path.name}: {exc}")
            failures += 1
    print(f"ok: {len(paths) - failures}/{len(paths)} selecao(oes) validas")
    return 1 if failures else 0


def _cmd_list_selections(_args: argparse.Namespace) -> int:
    from screen_watch.persistence.selection import load_selection
    from screen_watch.platform.paths import load_state, selections_dir

    last = str(load_state().get("last_selection") or "")
    paths = sorted(selections_dir().glob("*.json"))
    if not paths:
        print("nenhuma selecao encontrada (use 'select' ou 'select-manual')")
        return 0
    for path in paths:
        marker = "  (ultima)" if path.name == last else ""
        try:
            selection = load_selection(path)
        except (OSError, ValueError) as exc:
            print(f"{path.name}  ilegivel ({exc}){marker}")
            continue
        name = selection.app_name or selection.window_title_hint or path.stem
        x, y, w, h = selection.roi_relative
        print(f"{path.name}  {name} — {x},{y} {w}x{h} — {selection.mode}{marker}")
    return 0


def _cmd_migrate_config(args: argparse.Namespace) -> int:
    from screen_watch.config.loader import (
        ConfigError,
        load_config_dict,
        migrate_config_dict,
        save_config,
    )
    from screen_watch.persistence.selection import dump_selection, from_target_config
    from screen_watch.platform.paths import ensure_dirs, selections_dir

    path = Path(args.path)
    try:
        new_dict, targets = migrate_config_dict(load_config_dict(path))
    except ConfigError as exc:
        print(f"migracao abortada: {exc}")
        return 1

    ensure_dirs()
    conflicts = [
        target.name
        for target in targets
        if (selections_dir() / f"{target.name}.json").exists()
    ]
    if conflicts:
        print(
            "migracao abortada: ja existem selecoes com estes nomes: "
            + ", ".join(conflicts)
            + " (remova ou renomeie antes)"
        )
        return 1

    if args.dry_run:
        print(f"[dry-run] {len(targets)} selecao(oes) seriam gravadas em {selections_dir()}:")
        for target in targets:
            print(f"  - {target.name}.json")
        print(f"[dry-run] config v2 seria gravada em {path} (backup .bak)")
        return 0

    for target in targets:
        dump_selection(selections_dir() / f"{target.name}.json", from_target_config(target))
    save_config(path, new_dict)
    print(f"migrado: {len(targets)} selecao(oes) + {path} v2 (backup .bak)")
    return 0


def _cmd_show_paths(_args: argparse.Namespace) -> int:
    from screen_watch.config.loader import ConfigError, load_config
    from screen_watch.evidence.recorder import captures_dir
    from screen_watch.platform import paths

    family = paths.package_family_name()
    print(f"empacotado (Store/MSIX): {family or 'nao'}")
    print(f"app_home: {paths.app_home()}")
    print(f"config: {paths.config_path()}")
    print(f"selections: {paths.selections_dir()}")
    print(f"state: {paths.state_path()}")
    print(f"logs: {paths.logs_dir()}")

    options = None
    try:
        options = load_config(paths.config_path()).evidence
    except ConfigError:
        options = None
    note = " (override evidence.dir)" if getattr(options, "dir", None) else ""
    print(f"capturas: {captures_dir(options)}{note}")
    return 0


def _cmd_list_windows(_args: argparse.Namespace) -> int:
    from screen_watch.platform.window import list_windows

    try:
        windows = list_windows()
    except RuntimeError as exc:
        print(str(exc))
        return 1
    if not windows:
        print("nenhuma janela encontrada")
        return 0
    for info in windows:
        state = "minimizada" if info.is_minimized else "ok"
        x, y, w, h = info.rect
        print(f"{info.handle!s:>12}  {state:<11}  {x},{y} {w}x{h}  {info.title!r}")
    return 0


def _resolve_selection_path(value: str | None) -> Path:
    """Nome (em `selections/`) ou caminho; sem valor usa `state.json.last_selection`."""
    from screen_watch.config.loader import ConfigError
    from screen_watch.platform.paths import load_state, selections_dir

    if value:
        candidate = Path(value)
        if candidate.exists():
            return candidate
        if candidate.suffix.lower() == ".json":
            raise ConfigError(f"selecao nao encontrada: {candidate}")
        named = selections_dir() / f"{value}.json"
        if named.exists():
            return named
        raise ConfigError(f"selecao nao encontrada: {named}")

    last = load_state().get("last_selection")
    if last:
        candidate = selections_dir() / str(last)
        if candidate.exists():
            return candidate
    available = sorted(path.stem for path in selections_dir().glob("*.json"))
    if available:
        raise ConfigError(
            "nenhuma selecao informada e sem 'last_selection'; disponiveis: "
            + ", ".join(available)
        )
    raise ConfigError("nenhuma selecao disponivel; crie uma com 'select' ou 'select-manual'")


def _resolve_run_target(args: argparse.Namespace):
    """Target resolvido a partir de uma selecao + perfil + agendador (doc, secao 12)."""
    from screen_watch.app import profile_from_config
    from screen_watch.config.loader import ConfigError
    from screen_watch.persistence.selection import build_target, load_selection

    deprecated = getattr(args, "target", None)
    if deprecated and not getattr(args, "selection", None):
        print("aviso: --target esta deprecado; use --selection NOME")

    path = _resolve_selection_path(getattr(args, "selection", None) or deprecated)
    try:
        selection = load_selection(path)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"selecao invalida ({path}): {exc}") from exc
    config = _load_config_or_none(args.config)
    name = path.stem
    profile = profile_from_config(config, getattr(args, "profile", None), name)
    schedule = getattr(config, "schedule", None) if config is not None else None
    return build_target(selection, profile, name=name, schedule=schedule)


def _load_config_or_none(config_path):
    from screen_watch.config.loader import ConfigError, load_config

    try:
        return load_config(config_path)
    except ConfigError:
        return None


def _remember_state(selection_name: str, profile_name: str | None = None) -> None:
    from screen_watch.platform.paths import update_state

    fields: dict[str, object] = {"last_selection": f"{selection_name}.json"}
    if profile_name:
        fields["profile"] = profile_name
    update_state(**fields)


def _cmd_run(args: argparse.Namespace) -> int:
    if is_wayland():
        print(
            "Wayland detectado: a captura via mss nao e suportada. "
            "Rode em X11 ou Wayland com XWayland e XDG_SESSION_TYPE=x11."
        )
        return 2

    from screen_watch.app import MonitorSession, build_loop
    from screen_watch.config.loader import ConfigError
    from screen_watch.platform.window import find_window_by_handle

    try:
        target = _resolve_run_target(args)
    except ConfigError as exc:
        print(f"erro: {exc}")
        return 1

    _remember_state(target.name, getattr(args, "profile", None))
    info = find_window_by_handle(target.window_handle)
    _check_monitor_scales(info.rect if info is not None else None)

    from screen_watch.app import evidence_recorder

    recorder = evidence_recorder(_load_config_or_none(args.config))
    session = MonitorSession(target, recorder=recorder)
    loop = build_loop(target, session, on_event=_print_event, on_error=_print_error)
    print(f"monitorando {target.name!r} (handle={target.window_handle}) a cada {target.poll_interval_s}s")
    loop.start()
    try:
        while loop.running:
            loop.join(timeout=1.0)
    except KeyboardInterrupt:
        print("encerrando...")
    finally:
        loop.stop(timeout=5.0)
    return 0


def _capture_target_roi(target):
    """Captura a ROI atual do target (RGB mascarado) + retangulo fisico + janela."""
    from screen_watch.capture.mask import apply_mask
    from screen_watch.capture.mss_backend import MssCaptureBackend
    from screen_watch.capture.resolver import resolve
    from screen_watch.platform.window import find_window_by_handle

    info = find_window_by_handle(target.window_handle)
    if info is None or not info.exists:
        raise RuntimeError(
            f"janela nao encontrada: handle={target.window_handle}. "
            "Rode 'list-windows' e refaca a selecao (o handle muda ao reiniciar o app)."
        )
    if info.is_minimized:
        raise RuntimeError("janela minimizada: nao ha ROI para capturar")
    abs_rect = resolve(info, target.roi_relative)
    if abs_rect is None:
        raise RuntimeError("ROI invalida (fora da janela ou degenerada)")

    backend = MssCaptureBackend()
    try:
        rgb = backend.capture(abs_rect)
    finally:
        backend.close()
    return apply_mask(rgb, target.masks), abs_rect, info


def _cmd_test_alert(args: argparse.Namespace) -> int:
    import time

    from screen_watch.alerts.chain import DispatchOutcome
    from screen_watch.alerts.log import JsonlNotifier, default_log_path
    from screen_watch.app import build_alert_chain
    from screen_watch.capture.frame import Frame
    from screen_watch.compare.protocol import ComparisonResult
    from screen_watch.config.loader import ConfigError

    try:
        target = _resolve_run_target(args)
    except ConfigError as exc:
        print(f"erro: {exc}")
        return 1
    if not target.alerts:
        print(f"selecao {target.name!r} nao tem alertas configurados")
        return 1

    try:
        rgb, abs_rect, info = _capture_target_roi(target)
    except Exception as exc:
        print(f"falha ao capturar ROI: {exc}")
        return 1

    frame = Frame(
        rgb=rgb,
        timestamp=time.time(),
        absolute_rect=abs_rect,
        window_rect=info.rect,
        window_handle=info.handle,
        sequence=1,
    )
    result = ComparisonResult(
        changed=True,
        score=1.0,
        threshold=0.5,
        strategy="test-alert",
        severity=3,
        detail={"synthetic": True},
    )
    chain = build_alert_chain(target.alerts)
    outcome = chain.dispatch(result, frame)
    log_path = default_log_path()
    # So grava a linha extra se a config nao tiver um notificador `log` (evita duplicar).
    if not any(alert.type == "log" for alert in target.alerts):
        JsonlNotifier(path=log_path).notify(result, frame)

    print(f"target={target.name!r} handle={target.window_handle} roi={abs_rect}")
    print(f"desfecho: {outcome.value}")
    print(f"jsonl: {log_path}")
    return 0 if outcome is DispatchOutcome.FIRED else 1


def _cmd_test_evidence(args: argparse.Namespace) -> int:
    """Grava baseline+change de exemplo no ROI atual (valida a secao `evidence`)."""
    import time

    from screen_watch.app import evidence_recorder
    from screen_watch.capture.frame import Frame
    from screen_watch.config.loader import ConfigError

    try:
        target = _resolve_run_target(args)
    except ConfigError as exc:
        print(f"erro: {exc}")
        return 1
    try:
        rgb, abs_rect, info = _capture_target_roi(target)
    except Exception as exc:
        print(f"falha ao capturar ROI: {exc}")
        return 1

    frame = Frame(
        rgb=rgb,
        timestamp=time.time(),
        absolute_rect=abs_rect,
        window_rect=info.rect,
        window_handle=info.handle,
        sequence=1,
    )
    recorder = evidence_recorder(_load_config_or_none(args.config), force_enabled=True)
    if recorder is None:
        print("evidencias indisponiveis")
        return 1
    baseline = recorder.capture(frame, "baseline", target.name)
    change = recorder.capture(frame, "change", target.name)
    print(f"alvo={target.name!r} janela={info.rect}")
    print(f"baseline: {baseline}")
    print(f"change:   {change}")
    return 0 if baseline is not None and change is not None else 1


def _cmd_test_action(args: argparse.Namespace) -> int:
    """Executa/ensaias as acoes da selecao sobre o ROI atual (plano, F2-T9)."""
    import time

    from screen_watch.actions.arming import ArmingController
    from screen_watch.actions.audit import ActionAudit
    from screen_watch.actions.runner import ActionRunner, describe_step
    from screen_watch.app import evidence_recorder
    from screen_watch.capture.frame import Frame
    from screen_watch.config.loader import ConfigError

    try:
        target = _resolve_run_target(args)
    except ConfigError as exc:
        print(f"erro: {exc}")
        return 1
    if not target.actions:
        print(f"selecao {target.name!r} nao tem acoes configuradas")
        return 1
    try:
        rgb, abs_rect, info = _capture_target_roi(target)
    except Exception as exc:
        print(f"falha ao capturar ROI: {exc}")
        return 1

    frame = Frame(
        rgb=rgb,
        timestamp=time.time(),
        absolute_rect=abs_rect,
        window_rect=info.rect,
        window_handle=info.handle,
        sequence=1,
    )
    recorder = evidence_recorder(_load_config_or_none(args.config), force_enabled=True)
    audit = ActionAudit()
    arming = ArmingController()
    if args.armed:
        arming.arm()
    runner = ActionRunner(humanize=target.humanize)

    failures = 0
    mode = "armado" if args.armed else "ensaio (dry-run)"
    print(f"alvo={target.name!r} modo={mode}")
    for action in target.actions:
        if not action.enabled:
            print(f"[desabilitada] {action.name}")
            continue
        descriptions = [describe_step(step) for step in action.steps]
        if not arming.is_armed():
            evidence: list[str] = []
            if recorder is not None:
                path = recorder.record_action(frame, target.name)
                if path:
                    evidence.append(str(path))
            audit.record(
                {
                    "mode": "rehearsal",
                    "action": action.name,
                    "steps": descriptions,
                    "evidence": evidence,
                }
            )
            print(f"[ensaio] {action.name}: {', '.join(descriptions) or '(sem passos)'}")
            continue
        run = runner.run(action, frame, arming=arming)
        audit.record(
            {
                "mode": "armed",
                "action": action.name,
                "executed": run.executed,
                "steps": list(run.steps),
                "duration_s": round(run.duration_s, 3),
                "reason": run.reason,
            }
        )
        status = "ok" if run.executed else f"falhou ({run.reason})"
        print(f"[armado] {action.name}: {status}")
        if not run.executed:
            failures += 1
    print(f"auditoria: {audit.path}")
    return 0 if not failures else 1


def _cmd_record_actions(args: argparse.Namespace) -> int:
    """Grava cliques/teclas do usuario e gera um snippet de `actions:` (plano, F3-T4)."""
    from screen_watch.actions.recorder import record_interactively
    from screen_watch.capture.resolver import resolve
    from screen_watch.config.loader import ConfigError
    from screen_watch.persistence.selection import load_selection
    from screen_watch.platform.input import InputUnavailable
    from screen_watch.platform.window import find_window_by_handle

    value = getattr(args, "selection", None) or getattr(args, "target", None)
    try:
        path = _resolve_selection_path(value)
        selection = load_selection(path)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"erro: {exc}")
        return 1

    info = find_window_by_handle(selection.window_handle)
    if info is None or not info.exists:
        print("janela nao encontrada; refaca a selecao (o handle muda ao reiniciar o app)")
        return 1
    abs_rect = resolve(info, selection.roi_relative)
    if abs_rect is None:
        print("ROI invalida (fora da janela ou degenerada)")
        return 1

    try:
        recorder = record_interactively(roi_rect=abs_rect, window_rect=info.rect)
    except InputUnavailable as exc:
        print(str(exc))
        return 1

    snippet = recorder.to_yaml(args.name or path.stem)
    if args.out:
        Path(args.out).write_text(snippet, encoding="utf-8")
        print(f"snippet gravado em: {args.out}")
    else:
        print(snippet)
    return 0


def _cmd_compare_modes(args: argparse.Namespace) -> int:
    """Mede score/severidade/tempo de cada modo no ROI atual (calibracao, Etapa D)."""
    import time

    from screen_watch.app import build_pipeline
    from screen_watch.capture.frame import Frame
    from screen_watch.compare.pipeline import MODE_STAGES
    from screen_watch.config.loader import ConfigError

    try:
        target = _resolve_run_target(args)
    except ConfigError as exc:
        print(f"erro: {exc}")
        return 1

    modes = [m.strip() for m in str(args.modes).split(",") if m.strip()]
    invalid = [m for m in modes if m not in MODE_STAGES]
    if not modes or invalid:
        print(f"modos invalidos: {invalid or modes}; use um de {tuple(MODE_STAGES)}")
        return 1

    try:
        rgb_baseline, abs_rect, info = _capture_target_roi(target)
    except Exception as exc:
        print(f"falha ao capturar ROI: {exc}")
        return 1
    baseline = Frame(
        rgb=rgb_baseline,
        timestamp=time.time(),
        absolute_rect=abs_rect,
        window_rect=info.rect,
        window_handle=info.handle,
        sequence=1,
    )

    print(f"target={target.name!r} handle={target.window_handle} roi={abs_rect} mode={target.mode}")
    print(f"baseline capturado; aguardando {args.delay:.1f}s (altere o painel agora)...")
    time.sleep(max(0.0, args.delay))

    try:
        rgb_sample, abs_rect2, info2 = _capture_target_roi(target)
    except Exception as exc:
        print(f"falha ao capturar amostra: {exc}")
        return 1
    sample = Frame(
        rgb=rgb_sample,
        timestamp=time.time(),
        absolute_rect=abs_rect2,
        window_rect=info2.rect,
        window_handle=info2.handle,
        sequence=2,
    )

    print("")
    print(f"{'modo':<9} {'changed':<8} {'score':>10} {'threshold':>10} {'sev':>4} {'ms':>8}")
    for mode in modes:
        try:
            pipeline = build_pipeline(mode, target.compare_options)
            pipeline.initialize(baseline)
            result = None
            best_ms = None
            for _ in range(max(1, args.repeat)):
                started = time.perf_counter()
                result = pipeline.compare(sample)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                best_ms = elapsed_ms if best_ms is None else min(best_ms, elapsed_ms)
            print(
                f"{mode:<9} {str(result.changed):<8} {result.score:>10.4f} "
                f"{result.threshold:>10.4f} {result.severity:>4} {best_ms:>8.1f}"
            )
            if mode == "advanced" and result.detail:
                print(f"  baseline_text={result.detail.get('baseline_text')!r}")
                print(f"  current_text ={result.detail.get('current_text')!r}")
        except Exception as exc:
            print(f"{mode:<9} erro: {exc}")
    return 0


def _cmd_select_manual(args: argparse.Namespace) -> int:
    """Selecao por coordenadas. O `select` interativo (overlay) e a Etapa B."""
    from screen_watch.persistence.selection import Selection, dump_selection
    from screen_watch.platform.paths import ensure_dirs, selections_dir
    from screen_watch.platform.window import find_window_by_handle, friendly_app_name

    x, y, w, h = (int(v) for v in args.roi)
    if w < MIN_ROI_SIDE or h < MIN_ROI_SIDE:
        print(f"ROI invalida: {w}x{h}; minimo {MIN_ROI_SIDE}x{MIN_ROI_SIDE}")
        return 1

    try:
        info = find_window_by_handle(int(args.handle))
    except RuntimeError as exc:
        print(str(exc))
        return 1
    if info is None:
        print(f"aviso: janela handle={args.handle} nao encontrada; origem gravada como (0, 0)")
    origin = (info.rect[0], info.rect[1]) if info is not None else (0, 0)
    title = args.title or (info.title if info is not None else "")
    app_name = friendly_app_name(info.handle, title) if info is not None else ""

    ensure_dirs()
    selection = Selection(
        window_handle=int(args.handle),
        origin_at_selection=origin,
        roi_relative=(x, y, w, h),
        window_title_hint=title,
        app_name=app_name,
        mode=args.mode,
    )
    name = args.name or _slugify(app_name or title or f"target-{args.handle}")
    path = selections_dir() / f"{name}.json"
    dump_selection(path, selection)
    print(f"selection gravada em: {path} (origem={origin})")
    return 0


def _slugify(text: str) -> str:
    value = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    tokens = [token for token in value.split("-") if token]
    return "-".join(tokens) or "target"


def capture_selection_for_window(
    handle: int, *, name: str | None = None, mode: str = "advanced"
) -> CapturedSelection:
    """Overlay -> selection JSON relativo a janela (reusado pelo CLI e pela GUI)."""
    from screen_watch.gui.overlay import run_selection
    from screen_watch.gui.overlay_geometry import fits_in_window, to_physical, to_relative
    from screen_watch.persistence.selection import Selection, dump_selection
    from screen_watch.platform.paths import ensure_dirs, selections_dir
    from screen_watch.platform.window import find_window_by_handle, friendly_app_name

    result = run_selection()
    if result is None:
        raise RuntimeError("selecao cancelada")

    # Doc 7.1, passo 5: consultar getRect() imediatamente apos soltar.
    info = find_window_by_handle(int(handle))
    if info is None or not info.exists:
        raise RuntimeError(f"janela nao encontrada apos a selecao: handle={handle}")

    app_name = friendly_app_name(info.handle, info.title)
    physical = to_physical(
        result.global_logical,
        screen_origin=result.screen_origin,
        device_pixel_ratio=result.device_pixel_ratio,
    )
    relative = to_relative(physical, (info.rect[0], info.rect[1]))
    fits = fits_in_window(relative, (info.rect[2], info.rect[3]))

    ensure_dirs()
    selection = Selection(
        window_handle=int(handle),
        origin_at_selection=(info.rect[0], info.rect[1]),
        roi_relative=relative,
        window_title_hint=info.title,
        app_name=app_name,
        mode=mode,
    )
    file_name = name or _slugify(app_name or info.title or f"target-{handle}")
    path = selections_dir() / f"{file_name}.json"
    dump_selection(path, selection)
    return CapturedSelection(path=path, roi_relative=relative, fits_window=fits)


def _cmd_select(args: argparse.Namespace) -> int:
    """Selecao interativa por overlay (arrastar na tela)."""
    if is_wayland():
        print("Wayland detectado: o overlay Qt nao e suportado neste prototipo.")
        return 2

    try:
        captured = capture_selection_for_window(
            int(args.handle), name=args.name, mode=args.mode
        )
    except RuntimeError as exc:
        print(str(exc))
        return 1

    if not captured.fits_window:
        print("aviso: a ROI extrapola a janela (permitido, mas registrado)")
    print(f"selection gravada em: {captured.path} (roi_relative={captured.roi_relative})")
    return 0


def _check_monitor_scales(window_rect) -> None:
    """Verificacao de escala por monitor na inicializacao (mitigacao inicial do P1)."""
    from screen_watch.platform.display import (
        describe_scales,
        list_monitor_scales,
        monitor_for_rect,
        suitable_monitors,
    )

    scales = list_monitor_scales()
    if scales is None:
        print("aviso: PyQt6 ausente; nao foi possivel medir a escala dos monitores")
        return

    print("escala por monitor (OK = 100%, sem risco de drift da ROI):")
    for line in describe_scales(scales):
        print(line)

    if window_rect is None:
        return
    current = monitor_for_rect(scales, window_rect)
    if current is not None and not current.is_suitable:
        options = ", ".join(repr(s.name) for s in suitable_monitors(scales)) or "nenhum"
        print(
            f"ATENCAO: a janela esta no monitor {current.name!r} a {current.scale_percent}%; "
            f"a ROI pode sofrer deslocamento. Monitores adequados (100%): {options}."
        )


def _cmd_probe_dpi(_args: argparse.Namespace) -> int:
    from screen_watch.capture.mss_backend import open_mss

    print("mss.monitors (espaco fisico):")
    with open_mss() as sct:
        for index, monitor in enumerate(sct.monitors):
            print(f"  [{index}] {monitor}")

    from screen_watch.platform.window import list_windows

    print("janelas (primeiras 8, retangulo logico via pywinctl):")
    for info in list_windows()[:8]:
        print(
            f"  handle={info.handle} rect={info.rect} "
            f"minimized={info.is_minimized} title={info.title!r}"
        )

    _check_monitor_scales(None)
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    if is_wayland():
        print("Wayland detectado: a GUI Qt nao e suportada neste prototipo.")
        return 2

    from screen_watch.gui.main_window import run_gui

    return run_gui(args.config, profile=getattr(args, "profile", None))


def _configure_std_streams() -> None:
    """Titulos de janela podem ter qualquer Unicode; o console do Windows usa cp1252."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _print_event(name: str, payload: dict) -> None:
    print(f"[evento] {name}: {payload}")


def _print_error(exc: Exception) -> None:
    print(f"[erro] {exc}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="screen-watch", description="Screen Diff Watcher")
    parser.add_argument("--verbose", action="store_true", help="log de debug")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-config", help="cria um YAML de config padrao")
    p_init.add_argument("--path", default=str(config_path()))
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=_cmd_init_config)

    p_val = sub.add_parser("validate-config", help="valida o YAML de config e (opcional) selecoes")
    p_val.add_argument("--config", default=str(config_path()))
    p_val.add_argument(
        "--selections", action="store_true", help="valida tambem os overrides das selecoes"
    )
    p_val.set_defaults(func=_cmd_validate_config)

    p_sel = sub.add_parser("list-selections", help="lista as selecoes em app-data")
    p_sel.set_defaults(func=_cmd_list_selections)

    p_mig = sub.add_parser("migrate-config", help="converte YAML v1 (targets) em v2 + selecoes")
    p_mig.add_argument("--path", default=str(config_path()))
    p_mig.add_argument("--dry-run", action="store_true", help="so imprime o plano")
    p_mig.set_defaults(func=_cmd_migrate_config)

    p_list = sub.add_parser("list-windows", help="lista janelas (handle, titulo, rect)")
    p_list.set_defaults(func=_cmd_list_windows)

    p_paths = sub.add_parser("show-paths", help="mostra onde ficam config/selecoes/state/logs")
    p_paths.set_defaults(func=_cmd_show_paths)

    p_gui = sub.add_parser("gui", help="abre a GUI minima com tray")
    p_gui.add_argument("--config", default=str(config_path()))
    p_gui.add_argument("--profile", default=None, help="perfil ativo (default: o do YAML)")
    p_gui.set_defaults(func=_cmd_gui)

    p_probe = sub.add_parser("probe-dpi", help="imprime monitores mss/Qt e rect de janela (P1)")
    p_probe.set_defaults(func=_cmd_probe_dpi)

    p_run = sub.add_parser("run", help="inicia o monitoramento da selecao")
    p_run.add_argument("--config", default=str(config_path()))
    p_run.add_argument("--profile", default=None, help="perfil ativo (default: o do YAML)")
    p_run.add_argument("--selection", default=None, help="selecao JSON (nome ou caminho)")
    p_run.add_argument("--target", default=None, help="deprecado; alias de --selection")
    p_run.set_defaults(func=_cmd_run)

    p_test = sub.add_parser("test-alert", help="dispara um alerta sintetico com o ROI atual")
    p_test.add_argument("--config", default=str(config_path()))
    p_test.add_argument("--profile", default=None, help="perfil ativo (default: o do YAML)")
    p_test.add_argument("--selection", default=None, help="selecao JSON (nome ou caminho)")
    p_test.add_argument("--target", default=None, help="deprecado; alias de --selection")
    p_test.set_defaults(func=_cmd_test_alert)

    p_ev = sub.add_parser(
        "test-evidence", help="grava baseline+change de exemplo no ROI atual (evidencias)"
    )
    p_ev.add_argument("--config", default=str(config_path()))
    p_ev.add_argument("--profile", default=None, help="perfil ativo (default: o do YAML)")
    p_ev.add_argument("--selection", default=None, help="selecao JSON (nome ou caminho)")
    p_ev.add_argument("--target", default=None, help="deprecado; alias de --selection")
    p_ev.set_defaults(func=_cmd_test_evidence)

    p_act = sub.add_parser(
        "test-action", help="ensaias/executa as acoes da selecao no ROI atual (Fase 2)"
    )
    p_act.add_argument("--config", default=str(config_path()))
    p_act.add_argument("--profile", default=None, help="perfil ativo (default: o do YAML)")
    p_act.add_argument("--selection", default=None, help="selecao JSON (nome ou caminho)")
    p_act.add_argument("--target", default=None, help="deprecado; alias de --selection")
    p_act.add_argument("--armed", action="store_true", help="executa de verdade (default: ensaio)")
    p_act.add_argument("--dry-run", action="store_true", help="apenas ensaia (default)")
    p_act.set_defaults(func=_cmd_test_action)

    p_rec = sub.add_parser(
        "record-actions", help="grava cliques/teclas e gera um snippet de actions: (Fase 3)"
    )
    p_rec.add_argument("--selection", default=None, help="selecao JSON (nome ou caminho)")
    p_rec.add_argument("--target", default=None, help="deprecado; alias de --selection")
    p_rec.add_argument("--name", default=None, help="nome da acao no snippet (default: stem)")
    p_rec.add_argument("--out", default=None, help="arquivo de saida (default: stdout)")
    p_rec.set_defaults(func=_cmd_record_actions)

    p_cmp = sub.add_parser(
        "compare-modes", help="mede score/severidade/tempo por modo no ROI atual (calibracao)"
    )
    p_cmp.add_argument("--config", default=str(config_path()))
    p_cmp.add_argument("--profile", default=None, help="perfil ativo (default: o do YAML)")
    p_cmp.add_argument("--selection", default=None, help="selecao JSON (nome ou caminho)")
    p_cmp.add_argument("--target", default=None, help="deprecado; alias de --selection")
    p_cmp.add_argument(
        "--delay", type=float, default=5.0, help="segundos entre baseline e amostra"
    )
    p_cmp.add_argument("--repeat", type=int, default=1, help="repeticoes do compare por modo")
    p_cmp.add_argument("--modes", default="light,default,advanced")
    p_cmp.set_defaults(func=_cmd_compare_modes)

    p_select = sub.add_parser(
        "select-manual", help="grava um selection JSON a partir de coordenadas (sem overlay)"
    )
    p_select.add_argument("--handle", type=int, required=True, help="handle da janela")
    p_select.add_argument("--roi", type=int, nargs=4, required=True, metavar=("X", "Y", "W", "H"))
    p_select.add_argument("--name", default=None, help="nome do arquivo (default: target-<handle>)")
    p_select.add_argument("--title", default="", help="hint do titulo da janela")
    p_select.add_argument("--mode", default="advanced", choices=("light", "default", "advanced"))
    p_select.set_defaults(func=_cmd_select_manual)

    p_overlay = sub.add_parser("select", help="selecao interativa por overlay (arrastar na tela)")
    p_overlay.add_argument("--handle", type=int, required=True, help="handle da janela-alvo")
    p_overlay.add_argument("--name", default=None, help="nome do arquivo (default: target-<handle>)")
    p_overlay.add_argument(
        "--mode", default="advanced", choices=("light", "default", "advanced")
    )
    p_overlay.set_defaults(func=_cmd_select)

    return parser


def main(argv: list[str] | None = None) -> int:
    set_dpi_awareness()
    _configure_std_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
