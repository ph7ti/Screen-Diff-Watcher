# GUI and tray

**English** · [Português (Brasil)](GUI-e-Tray.md)

`python -m screen_watch gui` (or the installed shortcut; on Linux the command is
`screen-diff-watcher-gui`) opens the window, whose layout follows the `UI.txt` mockup.

## The window

- **Monitoring column** (left): **Start** / **Stop** / **Re-arm** / **Minimize to tray**, the
  **Mode** (`light`/`default`/`advanced`), **Profile** and **Language** selectors, and the
  arming controls — **Arm actions**, **Disarm**, **Arm for…** — with the visible state.
- **Selections group** (right): list of `app-data/selections/*.json` and the ROI legend. Each item
  shows the **application name**, the **monitored region** and the **mode** (e.g.:
  `Selection WhatsApp — Region 120,340 400x80 — advanced`). Double-click starts/stops.
- **File actions row**: **New Target** / **Remove** / **Reload** / **Open YAML** /
  **Captures**, plus the **Record captures (evidence)** checkbox.
- **Session actions (apply on next start)**: checklist with the resolved actions, counter
  "N of M selected" and the button column (`New action…`, `Edit…`, `Remove Action`, `Arm Action`,
  `Run action`).
- **Footer**: status/last result and the **Log**, in a resizable `QSplitter`.

## Mode, profile and language

- The chosen **mode** applies to the next run and is written to the selection JSON.
- The **profile** (if there is more than one in the YAML) applies **on the next start** and is written to
  `state.json`; the tray has an equivalent submenu.
- The **language** is chosen in the selector and written to `state.json["language"]`; the change applies **on the
  next start**. The initial catalog has `pt-BR` and `en-US` (see [Languages](Languages.md)).

## Arming/disarming

Actions run in **rehearsal** by default (they only record what they would do). **Arm actions** actually runs them; **Arm for…** limits it by time and disarms by itself; **Disarm** goes back to rehearsal. The arming
buttons are only enabled with a running session (arming is per session and starts disarmed).
`Esc` (hotkey `abort`) interrupts an action in progress. Details in
[Pseudo-human actions](Pseudo-Human-Actions.md).

## Hover help

Hovering the mouse for ~2 s over any control shows a tooltip with **purpose and example** (text from the
language catalog, `help.<control>.*` keys).

## Prints (evidence)

The **Record captures (evidence)** checkbox controls the monitoring prints and persists in
`state.json["evidence_enabled"]` (it takes precedence over the YAML; it works even with config v1). The
**Run action** button always records a capture of the run. The **Captures** button opens the effective
folder in the file manager — if the loop prints are off, it warns in the log.
Details in [Evidence](Evidence.md).

## New Target (overlay)

- The window list uses the **Task Manager-style application name**
  (`FileDescription`/`ProductName` of the executable, with a fallback to the `.exe` name) and **hides
  windows that are not from active applications** (invisible, hidden by DWM, tool windows, child/auxiliary
  windows and untitled ones).
- The overlay opens **one window per monitor**: drag with the left button; right button cancels.
- **Remove** deletes one or more selected selection JSONs (multi-select with Ctrl/Shift).

## Actions editor

The **New action…**, **Edit…** and **Remove Action** buttons create/edit actions written to
`overrides.actions` of the selection JSON — that is, they work **even with config v1**, without migration.
There is reordering with Up/Down and drag&drop, step duplication and the **Locate mouse position…**
button to fill `x`/`y`. Step by step in
[Pseudo-human actions](Pseudo-Human-Actions.md).

## Tray

The tray icon offers: show/hide, minimize, start/stop, arm/disarm, profile selection
and quit. On GNOME it may not appear without a tray extension (the window keeps working).

## How it works inside

The loop runs in a separate thread; the GUI only receives events/results through a queue consumed by
`QTimer` — tray/hotkey callbacks never call Qt from inside the listener thread. **Stop**
ends the loop and closes the backend before exiting.
