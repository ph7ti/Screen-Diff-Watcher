# DPI and limitations

**English** · [Português (Brasil)](DPI-e-Limitacoes.md)

## Screen scaling (DPI)

With `set_dpi_awareness()` at process start (done by the CLI and the GUI), `pywinctl` and `mss` stay
in the **same physical space** — measured across **15/15 windows** (`pywinctl == GetWindowRect`). Therefore the
`resolver` uses the identity converter and there is **no drift** in the monitoring path, even on a
125% monitor. Qt's `device_pixel_ratio` (`1.25` on the primary) is from Qt's **logical** space.

The overlay, on the other hand, receives the drag in Qt logical coordinates and converts it to physical with
`gui/overlay_geometry.to_physical` before writing the selection.

The mouse **locator** ("Locate mouse position…" in the action editor) and the ROI **highlight**
("View region") sit on the same Qt ↔ physical boundary: since **v0.10.1** they convert too — the
locator returns the **physical** point (`QCursor.pos()` is logical; it is anchored on the monitor
under the cursor, origin + dpr) and the highlight converts the physical rect to logical before
painting. Before that fix, actions created with the locator clicked at **logical** coordinates on
scaled monitors (e.g., ~192×120 px off at the center of a 1920×1200 @ 125% screen, growing toward the
bottom-right corner).

When starting `run`, the app checks each monitor, marks the suitable ones (`OK`, 100%) and warns if the
target window is on a monitor with scaling. `probe-dpi` and `scripts/probe_dpi.py` show the matrix
(physical mss × logical Qt × scale).

> If a test fails at 125% or 150% scaling on Windows, that is the most important bug in the project —
> prioritize it before any feature.

## Known (accepted) limitations

- **Wayland**: `mss` does not capture. The app warns and ends `run`; there is no Wayland backend in the
  prototype. Run on X11.
- **Occluded window**: `mss` captures screen pixels, not the window surface. If another window
  covers the ROI, the frame will contain the overlapping window. **It is not a bug to fix** — it is a
  fundamental limitation of the capture APIs.
- **Multiple ROIs (GUI only)**: each session is its own thread, capture backend and preview/calibration
  buffers, and `advanced` mode (OCR) multiplies CPU per session. `ui.max_sessions` (default 4, range
  1..16) caps it; the CLI `run` monitors a single selection.
- **macOS and ARM out of the build**: there is no installer or validation; the build is Windows x64 + Linux
  amd64.
- **Tray on GNOME**: may not appear without a tray extension; the window keeps working.
- **Sound on Linux**: the CLI/`run` plays WAV/MP3/OGG/FLAC through the bundled `miniaudio`; the GUI
  depends on the GStreamer plugins; formats without a decoder (M4A/AAC in the CLI) fall back to an
  external player (`paplay`/`aplay`/`ffplay`) and, without one, to `beep` (the alert never breaks).
- **SmartScreen**: the installers are not signed; Windows will warn (signing out of
  scope).
- **Elevation (UAC)**: the actions do not bypass elevation; to interact with elevated apps, run the app
  in an equivalent context.
- **Minimized or closed window**: the loop emits `target_unavailable` and keeps retrying when it
  comes back.

## Robustness (Step H)

- **Negative/off-screen coordinates**: the ROI is clipped against the virtual desktop
  (`mss.monitors[0]`). When there is clipping, the loop emits `capture_clipped`; when the ROI is 100%
  off-screen, it emits `roi_off_screen` and skips the tick — without breaking the loop.
- **Repeated failures**: identical consecutive errors (e.g.: missing Tesseract, missing token) are
  reported once, not on every tick.
- **Stop**: `stop()` signals the event and calls `join`; `backend.close()` runs in the worker's
  `finally`.
- **Backend on the right thread**: `mss` is not thread-safe; the instance is created and closed inside the
  loop thread.

## Related

- [Usage (CLI)](CLI-Usage.md) — `probe-dpi`, loop events
- [doc/00 §5.1 and §7.6](../doc/00-Architecture_and_Specification.md) — design decisions
