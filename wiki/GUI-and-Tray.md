# GUI and tray

**English** · [Português (Brasil)](GUI-e-Tray.md)

`python -m screen_watch gui` (or the installed shortcut; on Linux the command is
`screen-diff-watcher-gui`) opens the window, whose layout follows the `UI.txt` mockup.

## The window

The upper panel is a **2×2 grid** (Selections and Session actions on the left; Monitoring and
Detection and alerts on the right), with the Status + Log footer in a `QSplitter`:

- **Selections** (top-left): **New Target** / **Remove** / **Reload** / **Highlight selection** button
  row, the ROI legend, the list of `app-data/selections/*.json`, and the **Selection name** field +
  **Rename**. Each list item shows the **application name**, the **monitored region** and the **mode**
  (e.g. `Selection WhatsApp — Region 120,340 400x80 — advanced`); a selection with a **name** shows it
  as a prefix (`verificando download - Selection …`). **Double-click re-edits the region** (overlay);
  **Enter starts/stops**.
- **Monitoring** (top-right): a **two-column grid** — **Start**/Language, **Stop**/**Re-arm baseline**,
  Mode/Profile, **Arm actions**/**Disarm actions**, **Arm for…**/**Minimize to tray** — plus the
  **Record captures (evidence)** checkbox and the arming status. **Highlight selection** ("Ver local")
  lives in the Selections row above (it moved out of Monitoring).
- **Session actions (apply on next start)** (bottom-left): checklist with the resolved actions, the
  "N of M selected" counter and a horizontal button row (**New action…**, **Edit…**, **Remove Action**,
  **Run action**).
- **Detection and alerts** (bottom-right): the **Watch text** row (text, **Appears**/**Disappears**,
  **Match case**, **Ignore accents**; enabled **only in `advanced`** and written to
  `overrides.text_watch` of the **current selection**) and the **Alert sound** row (read-only
  `file: "..."` snippet; **Choose…** to preview, **Play** and **Copy path** — the selector **does not
  persist**). After **Choose…** a popup points to `config.yaml` and the active profile, with
  **Copy path and open YAML** / **Open YAML only** / **Close**. Switching the mode away from
  `advanced` clears the text-watch override. Details in [Alerts](Alerts.md) and the
  [v0.6.0 release notes](../doc/releases/v0.6.0.md).
- **Footer** (`QSplitter`): the **Status** group with status/last result and the **Log**, and the
  right column with **Captures** / **Test alert…** / **Open YAML**.

## Mode, profile and language

- The chosen **mode** applies to the next run and is written to the selection JSON.
- The **profile** (if there is more than one in the YAML) applies **on the next start** and is written to
  `state.json`; the tray has an equivalent submenu.
- The **language** is chosen in the selector and written to `state.json["language"]`; the change applies **on the
  next start**. The initial catalog has `pt-BR` and `en-US` (see [Languages](Languages.md)).

## Arming/disarming

Actions run in **rehearsal** by default (they only record what they would do). **Arm actions** actually runs them; **Arm for…** limits it by time and disarms by itself; **Disarm** goes back to rehearsal. The arming
buttons are only enabled with a running session (arming is per session and starts disarmed). Do not
confuse arming with **Re-arm baseline** (same column): that button only resets the comparison
baseline and has nothing to do with executing actions. `Esc` (hotkey `abort`) interrupts an action
in progress. Details in [Pseudo-human actions](Pseudo-Human-Actions.md).

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
- **Double-click** a selection to **re-edit its region** with the same overlay (the window is looked
  up by handle; if it is missing or minimized, use **New Target**). The re-edit preserves the
  **name**, the **mode** and the **overrides** and **clears the masks** (they were relative to the
  old ROI). It is blocked while the session is running.
- **Remove** deletes one or more selected selection JSONs (multi-select with Ctrl/Shift).

## Selection name and Highlight

- **Selection name**: type the display name below the list and confirm with **Rename** or **Enter**.
  The label shows it as a prefix (`verificando download - Selection App — Region …`) and the **file
  is renamed** to the slug of the name (`verificando download` → `verificando-download.json`; accents
  are normalized, max 60 chars). An existing name is **never overwritten** (a conflict warns and
  nothing changes) and renaming is blocked while the session runs. Scripts that use
  `--selection <name>` must be updated to the new file name after a rename; `list-selections` and
  `state.json:last_selection` follow the new name.
- **Highlight** ("Ver local" / **Highlight selection**): draws the selection ROI on screen for ~2 s.
  It **never paints inside the ROI** (dim layer only outside, border just outside the hole), never
  takes clicks/focus and auto-closes — so it can be used **while monitoring** to confirm what is
  being watched. The button lives in the **Selections** row.

## Mask editor

The **Edit masks…** button (Selections row) opens a transparent overlay per monitor over the target
window: the ROI border and the current masks are drawn; **left-drag adds** a mask, **right-click
removes** the mask under the cursor, **Enter saves** and **Esc cancels**. Masks are `[x, y, w, h]`
rectangles relative to the ROI (physical pixels), so they follow the window. The editor is **blocked
while the session runs** and saves the selection JSON atomically where the effective masks live:
`overrides.masks` if the key already exists, otherwise `masks`, otherwise it creates `overrides.masks`
(which has precedence). Typical masks: clock, spinner, cursor.

## Preview

While the session runs, the **Monitoring** group shows two downsampled thumbnails: the **baseline**
and the **latest captured frame**. They are copies made off the capture loop (the loop's image buffer
is never handed to Qt) and clear when the session stops; nothing is recorded.

## Calibration

The **Calibration…** button opens a live chart of the **score** and the **threshold** for **every**
comparison of the running session (not only the changes), with dots colored by severity. **Export
CSV…** saves the samples (timestamp, strategy, score, threshold, severity) for spreadsheet analysis
and **Clear** empties the view. It complements the CLI `compare-modes`. Thresholds live in the
profile `defaults.compare_options` — see [Configuration](Configuration.md).

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
