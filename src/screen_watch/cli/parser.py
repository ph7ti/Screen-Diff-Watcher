"""Parser do CLI (`screen-watch`)."""

from __future__ import annotations

import argparse

from screen_watch.cli.commands import (
    _cmd_compare_modes,
    _cmd_edit_selection,
    _cmd_features,
    _cmd_gui,
    _cmd_init_config,
    _cmd_list_actions,
    _cmd_list_selections,
    _cmd_list_windows,
    _cmd_migrate_config,
    _cmd_probe_dpi,
    _cmd_record_actions,
    _cmd_remove_selection,
    _cmd_rename_selection,
    _cmd_run,
    _cmd_select,
    _cmd_select_manual,
    _cmd_show_paths,
    _cmd_test_action,
    _cmd_test_alert,
    _cmd_test_evidence,
    _cmd_validate_config,
    _cmd_validate_i18n,
)
from screen_watch.platform.paths import config_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="screen-watch", description="Screen Diff Watcher")
    parser.add_argument("--verbose", action="store_true", help="debug log")
    parser.add_argument(
        "--language",
        default=None,
        help="GUI language: a discovered tag (e.g. pt-BR, en-US) or 'auto' (default: auto)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Argumentos compartilhados por `run`/`test-*`/`list-actions`/`compare-modes`.
    selection_args = argparse.ArgumentParser(add_help=False)
    selection_args.add_argument("--config", default=str(config_path()))
    selection_args.add_argument("--profile", default=None, help="active profile (default: the one from YAML)")
    selection_args.add_argument("--selection", default=None, help="selection JSON (name or path)")

    p_init = sub.add_parser("init-config", help="create a default config YAML")
    p_init.add_argument("--path", default=str(config_path()))
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=_cmd_init_config)

    p_val = sub.add_parser("validate-config", help="validate the config YAML and (optionally) selections")
    p_val.add_argument("--config", default=str(config_path()))
    p_val.add_argument(
        "--selections", action="store_true", help="also validate selection overrides"
    )
    p_val.set_defaults(func=_cmd_validate_config)

    p_sel = sub.add_parser("list-selections", help="list the selections in app-data")
    p_sel.add_argument("--json", action="store_true", help="JSON output (for scripting)")
    p_sel.set_defaults(func=_cmd_list_selections)

    p_rm = sub.add_parser("remove-selection", help="delete one or more selection JSON files")
    p_rm.add_argument("names", nargs="+", metavar="NAME")
    p_rm.set_defaults(func=_cmd_remove_selection)

    p_rn = sub.add_parser(
        "rename-selection", help="rename a selection (new slug + display name)"
    )
    p_rn.add_argument("old", metavar="OLD", help="current name or path")
    p_rn.add_argument("name", metavar="NAME", help="new display name (the file uses its slug)")
    p_rn.set_defaults(func=_cmd_rename_selection)

    p_edit = sub.add_parser(
        "edit-selection",
        help="edit a selection JSON headless (mode/ROI/masks/overrides)",
    )
    p_edit.add_argument("name", metavar="NAME", help="selection name or path")
    p_edit.add_argument("--mode", choices=("light", "default", "advanced"))
    p_edit.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    p_edit.add_argument(
        "--mask",
        type=int,
        nargs=4,
        action="append",
        metavar=("X", "Y", "W", "H"),
        help="repeatable; replaces the effective masks",
    )
    p_edit.add_argument("--clear-masks", action="store_true")
    p_edit.add_argument("--poll-interval-s", type=float, dest="poll_interval_s", metavar="SECONDS")
    p_edit.add_argument("--rearm", dest="rearm", action="store_true", default=None)
    p_edit.add_argument("--no-rearm", dest="rearm", action="store_false")
    p_edit.add_argument("--text-watch", dest="text_watch", metavar="TEXT")
    p_edit.add_argument(
        "--text-expect", choices=("appears", "disappears"), default="appears"
    )
    p_edit.add_argument("--clear-text-watch", action="store_true")
    p_edit.add_argument(
        "--clear-override",
        action="append",
        choices=("mode", "poll_interval_s", "rearm", "masks", "text_watch"),
        metavar="KEY",
    )
    p_edit.set_defaults(func=_cmd_edit_selection)

    p_mig = sub.add_parser("migrate-config", help="convert YAML v1 (targets) to v2 + selections")
    p_mig.add_argument("--path", default=str(config_path()))
    p_mig.add_argument("--dry-run", action="store_true", help="only prints the plan")
    p_mig.set_defaults(func=_cmd_migrate_config)

    p_list = sub.add_parser("list-windows", help="list windows (handle, title, rect)")
    p_list.set_defaults(func=_cmd_list_windows)

    p_paths = sub.add_parser("show-paths", help="show where config/selections/state/logs are")
    p_paths.set_defaults(func=_cmd_show_paths)

    p_gui = sub.add_parser("gui", help="open the minimal GUI with tray")
    p_gui.add_argument("--config", default=str(config_path()))
    p_gui.add_argument("--profile", default=None, help="active profile (default: the one from YAML)")
    p_gui.set_defaults(func=_cmd_gui)

    p_probe = sub.add_parser("probe-dpi", help="print mss/Qt monitors and window rect (P1)")
    p_probe.set_defaults(func=_cmd_probe_dpi)

    p_feat = sub.add_parser(
        "features", help="environment diagnostics (version, OCR, input, sound, tray, monitors)"
    )
    p_feat.add_argument("--json", action="store_true", help="JSON output (for CI/automation)")
    p_feat.set_defaults(func=_cmd_features)

    p_i18n = sub.add_parser(
        "validate-i18n", help="validate language catalogs (keys, errors, help, _meta)"
    )
    p_i18n.set_defaults(func=_cmd_validate_i18n)

    p_run = sub.add_parser("run", help="start monitoring the selection", parents=[selection_args])
    p_run.add_argument(
        "--actions",
        default=None,
        help="action subset (a,b; 'all'/'none'); one-shot, not persisted",
    )
    p_run.set_defaults(func=_cmd_run)

    p_test = sub.add_parser(
        "test-alert", help="fire a synthetic alert with the current ROI", parents=[selection_args]
    )
    p_test.add_argument(
        "--list", action="store_true", help="list the configured alerts (id/type/state/destination)"
    )
    p_test.add_argument(
        "--only", default=None, metavar="ID", help="send the test to a single alert id"
    )
    p_test.set_defaults(func=_cmd_test_alert)

    p_ev = sub.add_parser(
        "test-evidence",
        help="write a sample baseline+change on the current ROI (evidence)",
        parents=[selection_args],
    )
    p_ev.set_defaults(func=_cmd_test_evidence)

    p_act = sub.add_parser(
        "test-action",
        help="rehearse/execute the selection actions on the current ROI (Phase 2)",
        parents=[selection_args],
    )
    p_act.add_argument("--armed", action="store_true", help="actually execute (default: rehearsal)")
    p_act.add_argument(
        "--actions",
        default=None,
        help="action subset (a,b; 'all'/'none'); one-shot, not persisted",
    )
    p_act.add_argument(
        "--no-countdown", action="store_true", help="skip the 3s countdown before executing"
    )
    p_act.set_defaults(func=_cmd_test_action)

    p_listact = sub.add_parser(
        "list-actions",
        help="list the resolved selection actions and the saved subset",
        parents=[selection_args],
    )
    p_listact.set_defaults(func=_cmd_list_actions)

    p_rec = sub.add_parser(
        "record-actions", help="record clicks/keys and generate an actions: snippet (Phase 3)"
    )
    p_rec.add_argument("--selection", default=None, help="selection JSON (name or path)")
    p_rec.add_argument("--name", default=None, help="action name in the snippet (default: stem)")
    p_rec.add_argument("--out", default=None, help="output file (default: stdout)")
    p_rec.add_argument(
        "--no-countdown",
        action="store_true",
        help="do not count 3s before recording (requires F9 to start)",
    )
    p_rec.set_defaults(func=_cmd_record_actions)

    p_cmp = sub.add_parser(
        "compare-modes",
        help="measure score/severity/time per mode on the current ROI (calibration)",
        parents=[selection_args],
    )
    p_cmp.add_argument(
        "--delay", type=float, default=5.0, help="seconds between baseline and sample"
    )
    p_cmp.add_argument("--repeat", type=int, default=1, help="compare repetitions per mode")
    p_cmp.add_argument("--modes", default="light,default,advanced")
    p_cmp.set_defaults(func=_cmd_compare_modes)

    p_select = sub.add_parser(
        "select-manual", help="write a selection JSON from coordinates (no overlay)"
    )
    p_select.add_argument("--handle", type=int, required=True, help="window handle")
    p_select.add_argument("--roi", type=int, nargs=4, required=True, metavar=("X", "Y", "W", "H"))
    p_select.add_argument("--name", default=None, help="file name (default: target-<handle>)")
    p_select.add_argument("--title", default="", help="window title hint")
    p_select.add_argument("--mode", default="advanced", choices=("light", "default", "advanced"))
    p_select.set_defaults(func=_cmd_select_manual)

    p_overlay = sub.add_parser("select", help="interactive overlay selection (drag on screen)")
    p_overlay.add_argument("--handle", type=int, required=True, help="target window handle")
    p_overlay.add_argument("--name", default=None, help="file name (default: target-<handle>)")
    p_overlay.add_argument(
        "--mode", default="advanced", choices=("light", "default", "advanced")
    )
    p_overlay.set_defaults(func=_cmd_select)

    return parser
