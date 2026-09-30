# Pseudo-human actions (opt-in)

**English** · [Português (Brasil)](Acoes-Pseudo-Humanas.md)

Actions are a **reaction separate from alerts**: they are only evaluated after a detected change,
**do not change** the alert outcome or the re-arm, and are **opt-in and disarmed by default** — in
rehearsal mode the app only records what it would do (and writes evidence), without clicking. Actual execution requires
**arming** (tray, hotkeys or "Arm for N min").

- Input backend: **`pynput`**, optional extra (`pip install -e ".[input]"`). Without it, the actions
  remain in rehearsal and the global hotkeys are unavailable (the GUI warns and becomes tray-only).
- Execution is **synchronous on the loop thread**: capture/comparison pause during the sequence.
- Each trigger becomes a line in `logs/actions.jsonl` (rehearsal, execution, suspension, reason, duration
  and evidence paths).

## Configure in the YAML

```yaml
profiles:
  default:
    actions:
      - name: reprocessar
        enabled: true
        severity_min: 1
        cooldown_s: 30
        when:
          changed: true
          text_any: ["erro", "falha"]   # requires mode: advanced (OCR)
        settle_s: 1.5
        rebaseline: false               # default: baseline remains after the action
        max_per_min: 6
        max_per_session: 100
        steps:
          - activate: true              # required when there are clicks
          - click: { x: 380, y: 40, ref: roi, button: left, clicks: 1 }
          - wait:  { ms: 400 }
          - key:   { keys: "ctrl+s" }
          - type:  { text: "abc", interval_ms: 60 }
```

### Action fields

| Field | Default | Role |
|---|---|---|
| `name` | — (required) | unique name in the set |
| `enabled` | `true` | disable without removing |
| `severity_min` | `1` | minimum severity of the change to fire |
| `when.severity_min` | — | takes precedence over `severity_min` when present |
| `when.changed` | `true` | only supported value (`false` is an error) |
| `when.text_any` / `text_all` / `text_regex` | empty | filters over the OCR text; require `mode: advanced` |
| `case_sensitive` | `false` | sensitivity of the text filters |
| `cooldown_s` | `30` | minimum interval between fires of this action |
| `settle_s` | `1.5` | pause at the end of the sequence |
| `rebaseline` | `false` | `true` re-arms the baseline after running (the trigger can repeat) |
| `max_per_min` | `6` | cap in a moving 60 s window |
| `max_per_session` | `100` | cap per session |

### Steps

| Step | Fields | Notes |
|---|---|---|
| `activate` | — | focuses the target window and confirms `isActive`; **required before `click`** |
| `click` | `x`, `y`, `ref`, `button` (`left`/`right`/`middle`), `clicks` | moves the mouse to the point and clicks |
| `move` | `x`, `y`, `ref` | only moves the cursor |
| `key` | `keys` (e.g.: `"ctrl+s"`) | presses the combination and releases it in reverse order |
| `type` | `text`, `interval_ms` | types character by character; without `interval_ms`, uses `humanize.key_interval_ms` |
| `wait` | `ms` | pause (with `humanize.wait_jitter_ms` jitter) |

- `ref` is relative to the **ROI** (`roi`, base `frame.absolute_rect`), to the **window** (`window`, base
  `frame.window_rect`) or absolute on the screen (`screen`).
- **Focus**: on Windows, `SetForegroundWindow` can be asynchronous/blocked (foreground lock); the
  app retries activation and rechecks focus for ~0.5 s before aborting. The reason in the log
  distinguishes `activate recusado` from `foco nao confirmou` (`focus_changed: ...`); these runtime
  fragments are currently kept in Portuguese.
- Between steps, the runner rechecks arming and a pending `Esc` (`aborted`/`disarmed_during_run`).

### Limits and behavior

- A trigger blocked by `cooldown_s` appears in the live log as `skipped -> cooldown` and does **not**
  go to the JSONL (so as not to pollute the audit).
- `max_per_min`/`max_per_session` are checked before executing (`rate_limited`).
- Outside the **scheduler** window, the action is suspended (`suspended_schedule`); monitoring and alerts
  continue normally.

## Arming/disarming

- States: `disarmed` (rehearsal, default), `armed` and `timed` (`Arm for N min`). The state lives
  **only in memory** and starts disarmed on each session.
- **Tray**: "Arm actions"/"Disarm actions"/"Arm for N min".
- **Window**: **Arm actions**/**Disarm**/**Arm for…** buttons (enabled only with a running session).
- **Global hotkeys** (extra `input`), defaults: `arm` `<ctrl>+<alt>+a`, `disarm`
  `<ctrl>+<alt>+d`, `toggle` `<ctrl>+<alt>+<space>`, `rearm` `<ctrl>+<alt>+r`, `abort` `Esc`.
  Invalid combos are ignored individually (they do not bring down the others).
- `Esc` aborts right away and goes back to rehearsal.

## Test without waiting for a real event

```powershell
python -m screen_watch test-action --selection painel            # rehearsal (default)
python -m screen_watch test-action --selection painel --armed    # actually executes (3s countdown)
python -m screen_watch test-action --selection painel --armed --no-countdown   # without countdown
python -m screen_watch list-actions --selection painel           # check without starting
```

With `--armed`, a 3 s countdown appears at the top of the screen (Qt overlay **without stealing focus**) so you can
focus the target window; a click on the overlay cancels. The automatic firing of `run` does **not** have a
countdown. The window has the equivalent **Run action (3s)** button, which uses the subset marked in the
checklist.

## Create actions from the window

The button column next to the checklist has **New action…**, **Edit…** and **Remove Action**:

- **New action…** opens a form with name, `enabled`, `severity_min` (trigger), `cooldown_s`,
  `settle_s`, `rebaseline` and the list of steps. On confirm, the app validates with the **same YAML
  parser** (`parse_actions`): clicks require an `activate` step before them and text filters require
  `mode: advanced`; errors appear in a translated dialog.
- **Step order**: use **Up**/**Down**, drag and drop, **Edit step** (loads the step
  into the form; the button becomes **Save change** with **Cancel**) or **Duplicate step**.
- **Locate mouse position…** (in `click`/`move` steps): a box following the cursor appears
  with the values already in the chosen `ref` (plus the absolute one); move the mouse to the point and press
  **Enter** to fill `x`/`y` (**Esc** or right click cancels). The conversion uses the same base
  as the firing (see `ref` above); if the window/ROI is not available, it falls back to `screen` and warns.
- Actions created from the window are written to `overrides.actions` of the **selection JSON**
  (`selections/<name>.json`) — they work **even with `config.yaml` v1**. Each selection has its own
  set; without an override, the selection inherits the profile actions. Profile/YAML actions are read-only
  in the GUI (edit the YAML).

## Select actions per session

Below the selection list, the checklist **"Session actions (apply on next start)"** shows
all resolved actions with the counter "N of M selected":

- **no saved choice** → all enabled actions run;
- **empty list (everything unchecked)** → none run: the session **only monitors** (alerts continue).

The choice is **per selection name** and persists in `state.json["action_selection"][selection]`; the change
applies **on the next start**. In the CLI, `--actions a,b|all|none` overrides the saved subset **without
persisting** (one-shot):

```powershell
python -m screen_watch run --selection painel --actions reprocessar,confirmar
python -m screen_watch run --selection painel --actions none
```

## Action recorder (`record-actions`)

With the `input` extra, `record-actions` listens for clicks and keys and generates a snippet ready to paste into
`actions:`:

```powershell
python -m screen_watch record-actions --selection painel --out snippet.yaml
```

Default flow: 3 s countdown (same overlay without focus) → recording starts automatically → `F10`
ends it. Use `--no-countdown` to go back to the manual `F9` (time to get ready without the overlay). A
click on the overlay cancels the countdown. Clicks are converted from absolute coordinates to
`ref: roi`/`window` (or `screen` if they fall outside the window) and the snippet already includes an `activate` step
and the commented `when` block, so you can review it before arming.

The countdown runs on the **main thread**, before creating the `pynput` listeners. Without Qt/display
(headless/Wayland), the countdown falls back to the console (`3... 2... 1...`) and continues. Caveat: on Wayland
capture/input remain limited; elevation (UAC) is not bypassed.

## Audit and live log

- **Audit** (`logs/actions.jsonl`, source of truth): each line has `ts`, `mode`
  (`rehearsal`/`armed`/`skipped`), `action`, `steps`, `executed`, `duration_s`, `reason` and
  `evidence` (print paths).
- **Live log**: in the CLI, one line per trigger
  (`[action] rehearsal|armed <name> -> ok|failed (reason)`); in the GUI, the same event appears in the log
  (`kind: action_event`). It is ephemeral and respects `cooldown_s`; the audit remains the source
  of truth.

## Related

- [Configuration](Configuration.md) — `humanize`, profiles, overrides
- [GUI and tray](GUI-and-Tray.md) — the arming buttons and the editor
- [Alerts](Alerts.md) — the reaction that runs before the actions
- [doc/00 §11.4](../doc/00-Architecture_and_Specification.md) — design decisions
