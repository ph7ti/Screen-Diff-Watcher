# Evidence (prints)

**English** · [Português (Brasil)](Evidencias.md)

Evidence is **disabled by default**. When enabled, the app records prints of the **whole
window** (without masks) on the baseline and on every detected change:

```
%TEMP%\screen_watch\captures\<target>\<YYYYMMDD-HHMMSS-mmm>_<baseline|change>.png
```

The `<target>` is the selection file name (e.g.: `painel`). Action runs record with the
`_action` suffix (or `_action-<step>`).

## How to enable

**From the window (simplest)**: the **Record captures (evidence)** checkbox persists in
`state.json["evidence_enabled"]` and applies **without editing the YAML** — including with config v1
(`targets:`). It takes **precedence** over the `evidence:` section of the YAML.

**From the config (v2)**:

```yaml
evidence:
  enabled: true
  dir: null              # null = %TEMP%/screen_watch/captures
  keep_per_target: 50    # keeps the N most recent ones per target
  max_total_mb: 200      # total cap (all targets)
  on_baseline: true      # record a print of the baseline
  on_change: true        # record a print of every change
  per_step: false        # in the actions: one print per step (in addition to the run print)
```

**Retention** prunes the folder after each write: by count (`keep_per_target`) and by size
(`max_total_mb`).

## Where they live

- Default: `%TEMP%/screen_watch/captures` (outside the repository — the prints stay **only on your
  machine**).
- With `evidence.dir` configured, the prints go there.
- `python -m screen_watch show-paths` shows the effective folder on the `captures:` line (with a note
  when there is an override).

The **Captures** button in the window opens the effective folder in the file manager,
creating it if it does not exist yet; **if the loop prints are off, it warns in the log**.
Opening a folder/file always goes through `platform/shell.py::open_path` (`os.startfile` on Windows,
`open`/`xdg-open` on the others); if there is no association/utility, the GUI just logs
"open manually: <path>".

## Generate prints right away (without waiting for a real event)

These flows **always** record, even with loop evidence off:

```powershell
python -m screen_watch test-evidence --selection painel    # baseline+change; prints the paths
python -m screen_watch test-action --selection painel --armed   # print of the action run
```

The window's **Run action (3s)** button also records a print when running. In the actions, with
`per_step: true`, one print per step is recorded and the paths appear in the audit
(`logs/actions.jsonl`).

## Failures

Failures when writing (permission, disk, window off-screen) only generate `log.warning`; monitoring
continues.

## Related

- [Configuration](Configuration.md) — the `evidence:` section and `state.json`
- [GUI and tray](GUI-and-Tray.md) — checkbox and print buttons
- [doc/00 §11.5](../doc/00-Architecture_and_Specification.md) — design decisions
