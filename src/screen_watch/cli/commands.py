"""Subcomandos e helpers do CLI (`screen-watch`).

Movidos de `__main__.py` para manter o entry point enxuto. Cada handler faz seus
imports localmente para nao puxar dependencias opcionais no import do pacote.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from screen_watch.errors import AppError
from screen_watch.naming import slugify
from screen_watch.platform.dpi import is_wayland
from screen_watch.platform.paths import config_path

log = logging.getLogger("screen_watch")

MIN_ROI_SIDE = 10


class CapturedSelection(NamedTuple):
    path: Path
    roi_relative: tuple[int, int, int, int]


def _cmd_init_config(args: argparse.Namespace) -> int:
    from pathlib import Path

    from screen_watch.config.loader import default_config_dict, save_config
    from screen_watch.platform.paths import ensure_dirs

    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"already exists: {path} (use --force to overwrite)")
        return 1
    ensure_dirs()
    save_config(path, default_config_dict())
    print(f"config created at: {path}")

    from screen_watch.platform.paths import package_family_name

    if package_family_name():
        print("(Store/MSIX Python: real app-data path, visible outside the package)")
    return 0


def _cmd_validate_config(args: argparse.Namespace) -> int:
    from screen_watch.config.loader import ConfigError, load_config

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"invalid config: {exc}")
        return 1
    if config.legacy:
        print("warning: YAML v1 (targets); run 'migrate-config' for the v2 format")
        print(f"ok: {len(config.targets)} legacy target(s)")
    else:
        print(f"ok: {len(config.profiles)} profile(s); active={config.profile!r}")

    if getattr(args, "selections", False):
        return _validate_selections()
    return 0


def _validate_selections() -> int:
    from screen_watch.config.loader import ConfigError, parse_actions, parse_overrides
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
        except (ConfigError, OSError, ValueError) as exc:
            print(f"invalid selection {path.name}: {exc}")
            failures += 1
    print(f"ok: {len(paths) - failures}/{len(paths)} valid selection(s)")
    return 1 if failures else 0


def _cmd_list_selections(args: argparse.Namespace) -> int:
    from screen_watch.errors import ConfigError
    from screen_watch.persistence.selection import effective_masks, load_selection
    from screen_watch.platform.paths import load_state, selections_dir

    last = str(load_state().get("last_selection") or "")
    paths = sorted(selections_dir().glob("*.json"))
    if not paths:
        print("no selection found (use 'select' or 'select-manual')")
        return 0
    as_json = bool(getattr(args, "json", False))
    rows: list[dict[str, object]] = []
    for path in paths:
        marker = "  (last)" if path.name == last else ""
        try:
            selection = load_selection(path)
        except (ConfigError, OSError, ValueError) as exc:
            if as_json:
                rows.append({"file": path.name, "error": str(exc), "last": path.name == last})
                continue
            print(f"{path.name}  unreadable ({exc}){marker}")
            continue
        name = (
            selection.name
            or selection.app_name
            or selection.window_title_hint
            or path.stem
        )
        if as_json:
            rows.append(
                {
                    "file": path.name,
                    "name": selection.name,
                    "label": name,
                    "window_handle": selection.window_handle,
                    "roi_relative": list(selection.roi_relative),
                    "mode": selection.mode,
                    "masks": len(effective_masks(selection)),
                    "overrides": sorted((selection.overrides or {}).keys()),
                    "last": path.name == last,
                }
            )
            continue
        x, y, w, h = selection.roi_relative
        print(f"{path.name}  {name} — {x},{y} {w}x{h} — {selection.mode}{marker}")
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


def _cmd_remove_selection(args: argparse.Namespace) -> int:
    """Remove selecoes por nome/caminho; limpa `last_selection` quando apontava para elas."""
    from screen_watch.config.loader import ConfigError
    from screen_watch.persistence.selection import forget_last_selection

    removed = 0
    failures = 0
    for value in args.names:
        try:
            path = _resolve_selection_path(value)
        except (ConfigError, OSError) as exc:
            print(f"error: {exc}")
            failures += 1
            continue
        try:
            path.unlink()
        except OSError as exc:
            print(f"error: could not remove {path}: {exc}")
            failures += 1
            continue
        forget_last_selection(path.name)
        print(f"removed: {path}")
        removed += 1
    print(f"removed {removed} selection(s)")
    return 1 if failures else 0


def _cmd_rename_selection(args: argparse.Namespace) -> int:
    """Renomeia (slug + nome de exibicao) reusando a logica validada da GUI."""
    from screen_watch.config.loader import ConfigError
    from screen_watch.persistence.selection import plan_rename, rename_selection
    from screen_watch.platform.paths import ensure_dirs, selections_dir

    try:
        old = _resolve_selection_path(args.old)
        ensure_dirs()
        destination = plan_rename(selections_dir(), old, args.name)
        selection = rename_selection(old, destination, name=args.name)
    except (ConfigError, OSError) as exc:
        print(f"error: {exc}")
        return 1
    print(f"renamed: {old.name} -> {destination.name} ({selection.name!r})")
    return 0


def _cmd_edit_selection(args: argparse.Namespace) -> int:
    """Edita uma selecao headless (modo/ROI/mascaras/overrides), sem tocar no YAML."""
    from dataclasses import replace as dataclass_replace

    from screen_watch.config.loader import (
        MIN_POLL_INTERVAL_S,
        ConfigError,
        parse_text_watch,
    )
    from screen_watch.persistence.selection import (
        clear_masks,
        clear_override,
        dump_selection,
        load_selection,
        set_masks,
        set_mode_where_lives,
        set_override,
        set_override_text_watch,
    )
    from screen_watch.platform.window import find_window_by_handle

    edits = (
        args.mode
        or args.roi
        or args.mask
        or args.clear_masks
        or args.poll_interval_s is not None
        or args.rearm is not None
        or args.text_watch
        or args.clear_text_watch
        or args.clear_override
    )
    if not edits:
        print("nothing to edit: pass at least one option (see --help)")
        return 2
    if args.mask and args.clear_masks:
        print("error: use either --mask or --clear-masks, not both")
        return 1
    if args.text_watch and args.clear_text_watch:
        print("error: use either --text-watch or --clear-text-watch, not both")
        return 1

    try:
        path = _resolve_selection_path(args.name)
        selection = load_selection(path)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 1

    if args.mode:
        selection = set_mode_where_lives(selection, args.mode)
    if args.roi:
        x, y, w, h = (int(value) for value in args.roi)
        if w < MIN_ROI_SIDE or h < MIN_ROI_SIDE:
            print(f"invalid ROI: {w}x{h}; minimum {MIN_ROI_SIDE}x{MIN_ROI_SIDE}")
            return 1
        origin = selection.origin_at_selection
        try:
            info = find_window_by_handle(selection.window_handle)
        except RuntimeError:
            info = None
        if info is not None:
            origin = (info.rect[0], info.rect[1])
        selection = dataclass_replace(
            selection, roi_relative=(x, y, w, h), origin_at_selection=origin
        )
        # Regra doc/00 §12.3: a regiao mudou; as mascaras eram relativas a ROI antiga.
        selection = clear_masks(selection)
    if args.clear_masks:
        selection = clear_masks(selection)
    elif args.mask is not None:
        selection = set_masks(
            selection, [tuple(int(value) for value in item) for item in args.mask]
        )
    if args.clear_text_watch:
        selection = set_override_text_watch(selection, None)
    elif args.text_watch:
        watch = parse_text_watch(
            {"text": args.text_watch, "expect": args.text_expect}, "overrides.text_watch"
        )
        selection = set_override_text_watch(selection, watch)
    if args.poll_interval_s is not None:
        if args.poll_interval_s < MIN_POLL_INTERVAL_S:
            print(
                f"invalid --poll-interval-s: {args.poll_interval_s} "
                f"(minimum {MIN_POLL_INTERVAL_S})"
            )
            return 1
        selection = set_override(selection, "poll_interval_s", float(args.poll_interval_s))
    if args.rearm is not None:
        selection = set_override(selection, "rearm", bool(args.rearm))
    for key in args.clear_override or ():
        selection = clear_override(selection, key)

    try:
        dump_selection(path, selection)
    except OSError as exc:
        print(f"error: could not write {path}: {exc}")
        return 1
    print(f"selection updated: {path}")
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
        print(f"migration aborted: {exc}")
        return 1

    ensure_dirs()
    conflicts = [
        target.name
        for target in targets
        if (selections_dir() / f"{target.name}.json").exists()
    ]
    if conflicts:
        print(
            "migration aborted: selections with these names already exist: "
            + ", ".join(conflicts)
            + " (remove or rename them first)"
        )
        return 1

    if args.dry_run:
        print(f"[dry-run] {len(targets)} selection(s) would be written to {selections_dir()}:")
        for target in targets:
            print(f"  - {target.name}.json")
        print(f"[dry-run] config v2 would be written to {path} (backup .bak)")
        return 0

    for target in targets:
        dump_selection(selections_dir() / f"{target.name}.json", from_target_config(target))
    save_config(path, new_dict)
    print(f"migrated: {len(targets)} selection(s) + {path} v2 (backup .bak)")
    return 0


def _cmd_show_paths(_args: argparse.Namespace) -> int:
    from screen_watch.config.loader import ConfigError, load_config
    from screen_watch.evidence.recorder import captures_dir
    from screen_watch.platform import paths

    family = paths.package_family_name()
    print(f"packaged (Store/MSIX): {family or 'no'}")
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
    print(f"captures: {captures_dir(options)}{note}")
    return 0


def _cmd_list_windows(_args: argparse.Namespace) -> int:
    from screen_watch.platform.window import list_windows

    try:
        windows = list_windows()
    except RuntimeError as exc:
        print(str(exc))
        return 1
    if not windows:
        print("no window found")
        return 0
    for info in windows:
        state = "minimized" if info.is_minimized else "ok"
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
            raise ConfigError(f"selection not found: {candidate}")
        named = selections_dir() / f"{value}.json"
        if named.exists():
            return named
        raise ConfigError(f"selection not found: {named}")

    last = load_state().get("last_selection")
    if last:
        candidate = selections_dir() / str(last)
        if candidate.exists():
            return candidate
    available = sorted(path.stem for path in selections_dir().glob("*.json"))
    if available:
        raise ConfigError(
            "no selection given and no 'last_selection'; available: "
            + ", ".join(available)
        )
    raise ConfigError("no selection available; create one with 'select' or 'select-manual'")


def _action_filter_for(args: argparse.Namespace, name: str):
    """Filtro de acoes: `--actions` (one-shot) > subconjunto salvo da selecao > todas."""
    from screen_watch.actions.selection import load_action_selection, parse_action_names

    raw = getattr(args, "actions", None)
    if raw is not None:
        return parse_action_names(raw)
    return load_action_selection(name)


def _resolve_run_target(args: argparse.Namespace):
    """Target resolvido a partir de uma selecao + perfil + agendador (doc, secao 12)."""
    from screen_watch.app import profile_from_config
    from screen_watch.config.loader import ConfigError
    from screen_watch.persistence.selection import build_target, load_selection

    path = _resolve_selection_path(getattr(args, "selection", None))
    try:
        selection = load_selection(path)
    except (ConfigError, OSError, ValueError) as exc:
        raise ConfigError(f"invalid selection ({path}): {exc}") from exc
    config = _load_config_or_none(args.config)
    name = path.stem
    profile = profile_from_config(config, getattr(args, "profile", None), name)
    schedule = getattr(config, "schedule", None) if config is not None else None
    return build_target(
        selection,
        profile,
        name=name,
        schedule=schedule,
        action_filter=_action_filter_for(args, name),
    )


def _load_config_or_none(config_path):
    from screen_watch.config.loader import ConfigError, load_config

    try:
        return load_config(config_path)
    except ConfigError as exc:
        # Um config existente porem invalido cai para os defaults; avisar evita
        # "perder" o perfil em silencio (ex.: um `type` de alerta desconhecido).
        if Path(config_path).exists():
            print(f"warning: invalid config, using defaults: {exc}", file=sys.stderr)
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
            "Wayland detected: capture via mss is not supported. "
            "Run on X11 or Wayland with XWayland and XDG_SESSION_TYPE=x11."
        )
        return 2

    from screen_watch.app import MonitorSession, build_loop
    from screen_watch.config.loader import ConfigError
    from screen_watch.platform.window import find_window_by_handle

    try:
        target = _resolve_run_target(args)
    except ConfigError as exc:
        print(f"error: {exc}")
        return 1

    _remember_state(target.name, getattr(args, "profile", None))
    info = find_window_by_handle(target.window_handle)
    _check_monitor_scales(info.rect if info is not None else None)

    from screen_watch.alerts.gate import load_gate
    from screen_watch.app import evidence_recorder

    recorder = evidence_recorder(_load_config_or_none(args.config))
    # Snooze/mute gravados pela GUI valem tambem para um `run` headless ate expirar.
    session = MonitorSession(
        target, recorder=recorder, on_action=_print_action_event, gate=load_gate()
    )
    loop = build_loop(target, session, on_event=_print_event, on_error=_print_error)
    display = target.label or target.name
    print(f"monitoring {display!r} (handle={target.window_handle}) every {target.poll_interval_s}s")
    _print_actions_summary(target)
    loop.start()
    try:
        while loop.running:
            loop.join(timeout=1.0)
    except KeyboardInterrupt:
        print("shutting down...")
    finally:
        loop.stop(timeout=5.0)
    return 0


def _capture_target_roi(target):
    """Captura a ROI atual do target (RGB mascarado) + retangulo fisico + janela."""
    from screen_watch.capture.mask import apply_mask
    from screen_watch.capture.mss_backend import MssCaptureBackend
    from screen_watch.capture.roi import resolve_window_roi

    info, abs_rect = resolve_window_roi(target.window_handle, target.roi_relative)

    backend = MssCaptureBackend()
    try:
        rgb = backend.capture(abs_rect)
    finally:
        backend.close()
    return apply_mask(rgb, target.masks), abs_rect, info


def _capture_frame(target, sequence: int):
    """Captura a ROI atual e monta o `Frame` (reusado pelos comandos de teste)."""
    import time

    from screen_watch.capture.frame import Frame

    rgb, abs_rect, info = _capture_target_roi(target)
    frame = Frame(
        rgb=rgb,
        timestamp=time.time(),
        absolute_rect=abs_rect,
        window_rect=info.rect,
        window_handle=info.handle,
        sequence=sequence,
    )
    return frame, abs_rect, info


def _cmd_test_alert(args: argparse.Namespace) -> int:
    from screen_watch.alerts.chain import DispatchOutcome
    from screen_watch.alerts.log import JsonlNotifier
    from screen_watch.alerts.test_send import list_alert_targets, send_test
    from screen_watch.app import build_alert_chain
    from screen_watch.compare.protocol import ComparisonResult
    from screen_watch.config.loader import ConfigError
    from screen_watch.platform.paths import alerts_log_path

    try:
        target = _resolve_run_target(args)
    except ConfigError as exc:
        print(f"error: {exc}")
        return 1
    if not target.alerts:
        print(f"selection {target.name!r} has no alerts configured")
        return 1

    if getattr(args, "list", False):
        for uid, alert_type, enabled, severity_min, destination in list_alert_targets(target):
            state = "enabled" if enabled else "disabled"
            print(f"{uid}  type={alert_type}  {state}  severity_min={severity_min}  -> {destination}")
        return 0

    only = getattr(args, "only", None)
    if only is not None:
        outcome = send_test(target, only)
        print(outcome.message)
        return 0 if outcome.ok else 1

    try:
        frame, abs_rect, info = _capture_frame(target, 1)
    except Exception as exc:
        print(f"failed to capture ROI: {exc}")
        return 1

    result = ComparisonResult(
        changed=True,
        score=1.0,
        threshold=0.5,
        strategy="test-alert",
        severity=3,
        detail={"synthetic": True},
    )
    chain = build_alert_chain(target.alerts, target.name)
    outcome = chain.dispatch(result, frame)
    log_path = alerts_log_path()
    # So grava a linha extra se a config nao tiver um notificador `log` (evita duplicar).
    if not any(alert.type == "log" for alert in target.alerts):
        JsonlNotifier(path=log_path).notify(result, frame)

    print(f"target={target.name!r} handle={target.window_handle} roi={abs_rect}")
    for name, message in chain.last_errors:
        print(f"error: alert {name!r} failed: {message}")
    print(f"outcome: {outcome.value}")
    print(f"jsonl: {log_path}")
    return 0 if outcome is DispatchOutcome.FIRED and not chain.last_errors else 1


def _cmd_test_evidence(args: argparse.Namespace) -> int:
    """Grava baseline+change de exemplo no ROI atual (valida a secao `evidence`)."""
    from screen_watch.app import evidence_recorder
    from screen_watch.config.loader import ConfigError

    try:
        target = _resolve_run_target(args)
    except ConfigError as exc:
        print(f"error: {exc}")
        return 1
    try:
        frame, _abs_rect, info = _capture_frame(target, 1)
    except Exception as exc:
        print(f"failed to capture ROI: {exc}")
        return 1

    recorder = evidence_recorder(_load_config_or_none(args.config), force_enabled=True)
    if recorder is None:
        print("evidence unavailable")
        return 1
    baseline = recorder.capture(frame, "baseline", target.name)
    change = recorder.capture(frame, "change", target.name)
    print(f"target={target.name!r} window={info.rect}")
    print(f"baseline: {baseline}")
    print(f"change:   {change}")
    return 0 if baseline is not None and change is not None else 1


def _cmd_test_action(args: argparse.Namespace) -> int:
    """Executa/ensaias as acoes da selecao sobre o ROI atual (plano, F2-T9)."""
    from screen_watch.actions.once import run_actions
    from screen_watch.app import evidence_recorder
    from screen_watch.config.loader import ConfigError

    try:
        target = _resolve_run_target(args)
    except ConfigError as exc:
        print(f"error: {exc}")
        return 1
    if not target.actions:
        print(f"selection {target.name!r} has no actions configured")
        return 1
    try:
        frame, _, _ = _capture_frame(target, 1)
    except Exception as exc:
        print(f"failed to capture ROI: {exc}")
        return 1

    recorder = evidence_recorder(_load_config_or_none(args.config), force_enabled=True)

    countdown = None
    if args.armed and not getattr(args, "no_countdown", False):
        from screen_watch.gui.countdown import run_countdown  # noqa: PLC0415

        countdown = run_countdown

    code, lines = run_actions(
        target,
        frame,
        armed=bool(args.armed),
        recorder=recorder,
        countdown=countdown,
    )
    for line in lines:
        print(line)
    return code


def _cmd_record_actions(args: argparse.Namespace) -> int:
    """Grava cliques/teclas do usuario e gera um snippet de `actions:` (plano, F3-T4)."""
    from screen_watch.actions.recorder import (
        RecordingCancelled,
        record_interactively,
    )
    from screen_watch.capture.resolver import resolve
    from screen_watch.config.loader import ConfigError
    from screen_watch.persistence.selection import load_selection
    from screen_watch.platform.input import InputUnavailable
    from screen_watch.platform.window import find_window_by_handle

    value = getattr(args, "selection", None)
    try:
        path = _resolve_selection_path(value)
        selection = load_selection(path)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 1

    info = find_window_by_handle(selection.window_handle)
    if info is None or not info.exists:
        print("window not found; redo the selection (the handle changes when the app restarts)")
        return 1
    abs_rect = resolve(info, selection.roi_relative)
    if abs_rect is None:
        print("invalid ROI (outside the window or degenerate)")
        return 1

    no_countdown = bool(getattr(args, "no_countdown", False))

    def before_start() -> None:
        from screen_watch.gui.countdown import run_countdown  # noqa: PLC0415

        if not run_countdown():
            raise RecordingCancelled("countdown cancelled")

    try:
        if no_countdown:
            recorder = record_interactively(roi_rect=abs_rect, window_rect=info.rect)
        else:
            recorder = record_interactively(
                roi_rect=abs_rect,
                window_rect=info.rect,
                before_start=before_start,
                auto_start=True,
            )
    except RecordingCancelled:
        print("countdown cancelled; recording aborted")
        return 1
    except InputUnavailable as exc:
        print(str(exc))
        return 1

    snippet = recorder.to_yaml(args.name or path.stem)
    if args.out:
        Path(args.out).write_text(snippet, encoding="utf-8")
        print(f"snippet written to: {args.out}")
    else:
        print(snippet)
    return 0


def _cmd_compare_modes(args: argparse.Namespace) -> int:
    """Mede score/severidade/tempo de cada modo no ROI atual (calibracao, Etapa D)."""
    import time

    from screen_watch.app import build_pipeline
    from screen_watch.compare.pipeline import MODE_STAGES
    from screen_watch.config.loader import ConfigError

    try:
        target = _resolve_run_target(args)
    except ConfigError as exc:
        print(f"error: {exc}")
        return 1

    modes = [m.strip() for m in str(args.modes).split(",") if m.strip()]
    invalid = [m for m in modes if m not in MODE_STAGES]
    if not modes or invalid:
        print(f"invalid modes: {invalid or modes}; use one of {tuple(MODE_STAGES)}")
        return 1

    try:
        baseline, abs_rect, _ = _capture_frame(target, 1)
    except Exception as exc:
        print(f"failed to capture ROI: {exc}")
        return 1

    print(f"target={target.name!r} handle={target.window_handle} roi={abs_rect} mode={target.mode}")
    print(f"baseline captured; waiting {args.delay:.1f}s (change the panel now)...")
    time.sleep(max(0.0, args.delay))

    try:
        sample, _, _ = _capture_frame(target, 2)
    except Exception as exc:
        print(f"failed to capture sample: {exc}")
        return 1

    print("")
    print(f"{'mode':<9} {'changed':<8} {'score':>10} {'threshold':>10} {'sev':>4} {'ms':>8}")
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
            print(f"{mode:<9} error: {exc}")
    return 0


def _cmd_select_manual(args: argparse.Namespace) -> int:
    """Selecao por coordenadas. O `select` interativo (overlay) e a Etapa B."""
    from screen_watch.persistence.selection import Selection, dump_selection
    from screen_watch.platform.paths import ensure_dirs, selections_dir
    from screen_watch.platform.window import find_window_by_handle, friendly_app_name

    x, y, w, h = (int(v) for v in args.roi)
    if w < MIN_ROI_SIDE or h < MIN_ROI_SIDE:
        print(f"invalid ROI: {w}x{h}; minimum {MIN_ROI_SIDE}x{MIN_ROI_SIDE}")
        return 1

    try:
        info = find_window_by_handle(int(args.handle))
    except RuntimeError as exc:
        print(str(exc))
        return 1
    if info is None:
        print(f"warning: window handle={args.handle} not found; origin recorded as (0, 0)")
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
    name = args.name or slugify(app_name or title or f"target-{args.handle}") or "target"
    path = selections_dir() / f"{name}.json"
    dump_selection(path, selection)
    print(f"selection written to: {path} (origin={origin})")
    return 0


def overlay_relative_roi(handle: int):
    """Overlay -> `(roi_relative, window_info)`, reusado pelo CLI e pela GUI.

    Levanta `runtime.selection_cancelled` quando o usuario cancela; os demais
    `runtime.*` (janela sumiu/minimizou ou ROI fora da janela) sobem como
    `AppError`. Ver doc 7.1, passo 5: `getRect()` e consultado imediatamente
    apos soltar o mouse.
    """
    from screen_watch.gui.overlay import run_selection
    from screen_watch.gui.overlay_geometry import fits_in_window, to_physical, to_relative
    from screen_watch.platform.window import find_window_by_handle

    result = run_selection()
    if result is None:
        raise AppError(code="runtime.selection_cancelled")

    info = find_window_by_handle(int(handle))
    if info is None or not info.exists:
        raise AppError(
            code="runtime.window_missing_after_selection", params={"handle": handle}
        )

    physical = to_physical(
        result.global_logical,
        screen_origin=result.screen_origin,
        device_pixel_ratio=result.device_pixel_ratio,
    )
    relative = to_relative(physical, (info.rect[0], info.rect[1]))
    # Regra: a ROI tem de caber inteiramente na janela. Fora dela o `resolve` a cada
    # tick capturaria uma area alheia a janela (ex.: outro monitor), produzindo prints
    # e alertas sem relacao com o alvo.
    if not fits_in_window(relative, (info.rect[2], info.rect[3])):
        raise AppError(
            code="runtime.roi_outside_window",
            params={"roi": relative, "window": (info.rect[2], info.rect[3])},
        )
    return relative, info


def capture_selection_for_window(
    handle: int, *, name: str | None = None, mode: str = "advanced"
) -> CapturedSelection:
    """Overlay -> selection JSON relativo a janela (reusado pelo CLI e pela GUI)."""
    from screen_watch.persistence.selection import Selection, dump_selection
    from screen_watch.platform.paths import ensure_dirs, selections_dir
    from screen_watch.platform.window import friendly_app_name

    relative, info = overlay_relative_roi(handle)
    app_name = friendly_app_name(info.handle, info.title)
    ensure_dirs()
    selection = Selection(
        window_handle=int(handle),
        origin_at_selection=(info.rect[0], info.rect[1]),
        roi_relative=relative,
        window_title_hint=info.title,
        app_name=app_name,
        mode=mode,
    )
    file_name = name or slugify(app_name or info.title or f"target-{handle}") or "target"
    path = selections_dir() / f"{file_name}.json"
    dump_selection(path, selection)
    return CapturedSelection(path=path, roi_relative=relative)


def _cmd_select(args: argparse.Namespace) -> int:
    """Selecao interativa por overlay (arrastar na tela)."""
    if is_wayland():
        print("Wayland detected: the Qt overlay is not supported in this prototype.")
        return 2

    try:
        captured = capture_selection_for_window(
            int(args.handle), name=args.name, mode=args.mode
        )
    except AppError as exc:
        print(str(exc))
        return 1

    print(f"selection written to: {captured.path} (roi_relative={captured.roi_relative})")
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
        print("warning: PyQt6 missing; could not measure monitor scale")
        return

    print("scale per monitor (OK = 100%, no ROI drift risk):")
    for line in describe_scales(scales):
        print(line)

    if window_rect is None:
        return
    current = monitor_for_rect(scales, window_rect)
    if current is not None and not current.is_suitable:
        options = ", ".join(repr(s.name) for s in suitable_monitors(scales)) or "none"
        print(
            f"WARNING: the window is on monitor {current.name!r} at {current.scale_percent}%; "
            f"the ROI may drift. Suitable monitors (100%): {options}."
        )


def _cmd_probe_dpi(_args: argparse.Namespace) -> int:
    from screen_watch.capture.mss_backend import open_mss

    print("mss.monitors (physical space):")
    with open_mss() as sct:
        for index, monitor in enumerate(sct.monitors):
            print(f"  [{index}] {monitor}")

    from screen_watch.platform.window import list_windows

    print("windows (first 8, logical rect via pywinctl):")
    for info in list_windows()[:8]:
        print(
            f"  handle={info.handle} rect={info.rect} "
            f"minimized={info.is_minimized} title={info.title!r}"
        )

    _check_monitor_scales(None)
    return 0


def _tesseract_info() -> dict[str, object]:
    """Caminho do Tesseract + idiomas instalados (`--list-langs`). Nunca levanta."""
    from screen_watch.platform.tesseract import resolve_tesseract_cmd

    cmd = resolve_tesseract_cmd()
    if cmd is None:
        return {"path": None, "languages": [], "error": "not found"}
    info: dict[str, object] = {"path": cmd, "languages": [], "error": None}
    try:
        proc = subprocess.run(
            [cmd, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        info["error"] = str(exc)
        return info
    lines = (proc.stdout or "").splitlines()
    info["languages"] = [
        line.strip() for line in lines if line.strip() and " " not in line.strip() and ":" not in line
    ]
    if proc.returncode != 0:
        info["error"] = (proc.stderr or "").strip() or f"exit {proc.returncode}"
    return info


def _monitors_info() -> list[dict[str, object]] | None:
    from screen_watch.platform.display import list_monitor_scales

    try:
        scales = list_monitor_scales()
    except Exception:
        return None
    if scales is None:
        return None
    return [
        {"name": scale.name, "scale_percent": scale.scale_percent, "primary": scale.is_primary}
        for scale in scales
    ]


def collect_features() -> dict[str, object]:
    """Diagnostico do ambiente (versao, app-data, OCR, entrada, som, tray, telas)."""
    from screen_watch import __version__
    from screen_watch.platform import audio, paths
    from screen_watch.platform.input import available as input_available

    try:
        import pystray  # noqa: F401, PLC0415

        tray_available = True
    except Exception:
        tray_available = False

    try:
        import paho.mqtt.client  # noqa: F401, PLC0415

        mqtt_available = True
    except Exception:
        mqtt_available = False

    config_file = paths.config_path()
    return {
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "python": sys.version.split()[0],
        "app_home": str(paths.app_home()),
        "config": str(config_file),
        "config_exists": config_file.exists(),
        "selections": len(list(paths.selections_dir().glob("*.json"))),
        "tesseract": _tesseract_info(),
        "input": {"available": input_available()},
        "sound": audio.backend_info(),
        "sounds_dir": str(paths.sounds_dir()),
        "tray": {"pystray": tray_available},
        "mqtt": {"available": mqtt_available},
        "monitors": _monitors_info(),
    }


def _print_features(info: dict[str, object]) -> None:
    origin = "bundle" if info["frozen"] else "source"
    print(f"screen-watch {info['version']} ({origin})")
    print(f"executable: {info['executable']} (Python {info['python']})")
    print(f"app_home: {info['app_home']}")
    config_state = "exists" if info["config_exists"] else "missing"
    print(f"config: {info['config']} ({config_state})")
    print(f"selections: {info['selections']}")

    tesseract = info["tesseract"]
    if tesseract["path"]:
        langs = ", ".join(tesseract["languages"]) or "none"
        print(f"tesseract: {tesseract['path']} — languages: {langs}")
    else:
        print(f"tesseract: unavailable ({tesseract['error']})")

    entrada = "available" if info["input"]["available"] else "unavailable (extra 'input')"
    print(f"input (pynput): {entrada}")

    sound = info["sound"]
    layers: list[str] = []
    if sound["available"]:
        layers.append(str(sound["backend"]))
    if sound.get("qt"):
        layers.append("qt")
    if sound.get("miniaudio"):
        layers.append("miniaudio")
    formats = ", ".join(sound.get("formats", [])) or "none"
    print(f"sound: {', '.join(layers) or 'none'} (formats: {formats})")
    print(f"sounds dir: {info['sounds_dir']}")

    tray = "available" if info["tray"]["pystray"] else "unavailable"
    print(f"tray (pystray): {tray}")

    mqtt = "available" if info["mqtt"]["available"] else "unavailable (extra 'mqtt')"
    print(f"mqtt (paho-mqtt): {mqtt}")

    monitors = info["monitors"]
    if monitors is None:
        print("monitors: unavailable (no display or PyQt6)")
    else:
        print(f"monitors: {len(monitors)}")
        for monitor in monitors:
            primary = " (primary)" if monitor["primary"] else ""
            print(f"  - {monitor['name']} scale {monitor['scale_percent']}%{primary}")


def _cmd_features(args: argparse.Namespace) -> int:
    info = collect_features()
    if getattr(args, "json", False):
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        _print_features(info)
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    if is_wayland():
        print("Wayland detected: the Qt GUI is not supported in this prototype.")
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
    print(f"[event] {name}: {payload}")


def _print_error(exc: Exception) -> None:
    print(f"[error] {exc}", file=sys.stderr)


def _print_action_event(payload: dict) -> None:
    action = payload.get("action") or "?"
    mode = payload.get("mode") or "?"
    if mode == "armed":
        result = "ok" if payload.get("executed") else f"failed ({payload.get('reason') or '?'})"
    elif mode == "rehearsal":
        result = "rehearsal"
    else:
        result = payload.get("reason") or "?"
    print(f"[action] {mode} {action} -> {result}")


def _print_actions_summary(target) -> None:
    from screen_watch.actions.summary import describe_actions

    if not target.actions:
        print("actions: none selected (the session only monitors)")
        return
    lines = describe_actions(target.actions)
    print(f"actions ({len(lines)}):")
    for line in lines:
        print(f"  {line}")


def _cmd_list_actions(args: argparse.Namespace) -> int:
    """Lista as acoes resolvidas da selecao, marcando o subconjunto salvo (doc, 11.4)."""
    from screen_watch.actions.selection import load_action_selection
    from screen_watch.actions.summary import describe_actions
    from screen_watch.app import profile_from_config
    from screen_watch.config.loader import ConfigError
    from screen_watch.persistence.selection import load_selection, resolve_actions

    try:
        path = _resolve_selection_path(getattr(args, "selection", None))
        selection = load_selection(path)
        config = _load_config_or_none(args.config)
        profile = profile_from_config(config, getattr(args, "profile", None), path.stem)
        actions = resolve_actions(selection, profile)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 1

    if not actions:
        print(f"selection {path.stem!r} has no actions configured")
        return 0
    saved = load_action_selection(path.stem)
    for line in describe_actions(actions, saved):
        print(line)
    return 0


def _cmd_validate_i18n(_args: argparse.Namespace) -> int:
    """Valida os catalogos: chaves, codigos de erro, ajuda e `_meta` (F7)."""
    from screen_watch import i18n
    from screen_watch.errors import ERROR_CODES

    locales = i18n.available_locales()
    fallback = i18n.FALLBACK_LANGUAGE
    fallback_keys = set(i18n.catalog_keys(fallback))
    print(f"locales discovered: {', '.join(locales)}")
    problems = 0

    for locale in locales:
        path = i18n._CATALOG_DIR / f"{locale}.json"  # noqa: SLF001 - diagnostico
        keys = set(i18n.catalog_keys(locale))
        missing = sorted(fallback_keys - keys)
        extra = sorted(keys - fallback_keys)
        if missing:
            print(f"{locale}: {len(missing)} missing key(s): {', '.join(missing[:5])}...")
            problems += 1
        if extra:
            print(f"{locale}: {len(extra)} extra key(s): {', '.join(extra[:5])}...")
            problems += 1
        meta = i18n.locale_meta(locale)
        if not meta:
            print(f"{locale}: _meta missing/invalid")
            problems += 1
            continue
        if str(meta.get("code")) != locale:
            print(f"{locale}: _meta.code != {locale!r}")
            problems += 1
        if not meta.get("name"):
            print(f"{locale}: _meta.name missing")
            problems += 1
        if not isinstance(meta.get("version"), int):
            print(f"{locale}: _meta.version must be an integer")
            problems += 1
        if not path.is_file():
            problems += 1

    for code in ERROR_CODES:
        key = f"error.{code}"
        for locale in locales:
            if key not in i18n.catalog_keys(locale):
                print(f"{locale}: missing {key}")
                problems += 1

    try:
        from screen_watch.gui.help import HELP_KEYS  # noqa: PLC0415

        for key in HELP_KEYS:
            for suffix in ("titulo", "proposito", "exemplo"):
                full = f"help.{key}.{suffix}"
                for locale in locales:
                    if full not in i18n.catalog_keys(locale):
                        print(f"{locale}: missing {full}")
                        problems += 1
    except Exception as exc:  # pragma: no cover - ambiente sem Qt
        print(f"warning: could not validate help.*: {exc}")

    if problems:
        print(f"validate-i18n: {problems} problem(s)")
        return 1
    print("validate-i18n: ok")
    return 0


def _resolve_language(args: argparse.Namespace) -> None:
    """Aplica a precedencia `--language` > state.json > ui.language > auto."""
    from screen_watch.i18n import resolve_language  # noqa: PLC0415
    from screen_watch.platform.paths import load_state  # noqa: PLC0415

    cli = getattr(args, "language", None)
    state = load_state().get("language")
    state_language = state if isinstance(state, str) and state else None
    config_language = None
    if not cli and not state_language:
        config = _load_config_or_none(getattr(args, "config", config_path()))
        candidate = getattr(getattr(config, "ui", None), "language", None)
        config_language = candidate if isinstance(candidate, str) else None
    resolve_language(cli=cli, state=state_language, config=config_language)
