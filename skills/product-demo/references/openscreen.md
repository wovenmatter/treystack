# OpenScreen: how the scripts drive it, and its pitfalls

Written against OpenScreen 2.3.0 (`brew install --cask openscreen`). Only the CLI commands
`sources`, `record`, `export`, `info` and `pack` are used. The GUI, the built-in AI assistant
and `openscreen mcp` are not part of this skill.

## Launching

| Command | How | Why |
|---|---|---|
| `sources`, `record` | `open -n -a /Applications/Openscreen.app --stdout F --stderr G --args ...` | macOS attributes Screen Recording, Microphone and Accessibility to the app that launched a process. Run as a child of a terminal or agent, capture fails with "Failed to get sources" (really: the terminal lacks the permission). Through `open`, Openscreen itself is responsible. |
| `export`, `info`, `pack` | the real binary `/Applications/Openscreen.app/Contents/MacOS/Openscreen` run directly | No capture permission needed; real exit codes and live progress. |

Rules the scripts follow (in `scripts/_common.py`):
- `open` always exits 0. Success is read from the `done` event in the NDJSON stdout file.
- Arguments after `--args` are resolved with the working directory `/`: pass absolute paths only.
- `open` passes no environment and does not return the recorder's PID. The PID is found with
  `ps` by the take's unique `--project` path. Signals go to that PID, never to `open`.
- Always `-n`, or macOS may hand the arguments to an already running copy of the app.
- Never use the Homebrew `openscreen` symlink: it crashes.
- `OPENSCREEN_APP` overrides the app location (default `/Applications`, then `~/Applications`).

## Recording

- `record-start.py` checks the window title against `sources` first: OpenScreen silently picks
  one window when a title matches several, and a title contained in another window's title can
  never be targeted alone. Only on-screen windows are listed (not minimised windows, other
  Spaces, or windows behind a full-screen app).
- Stop is SIGINT to the recorder (about 0.5 s to finish). If the window closes mid-take, the
  recorder finishes by itself and `record-stop.py` still collects the take. If the recorder is
  killed, the raw video usually survives and `record-stop.py` salvages it.
- Output: an H.264 MP4 with a **variable frame rate** (frames only when the picture changes,
  up to 60), the full window including its title bar (a 1600x1000 window gives 1600x1032).
  On a Retina screen expect about double the pixel size (not verified). Zooms: the export
  never enlarges the capture more than 2x (`MAX_SOURCE_MAGNIFICATION`), so a capture narrower
  than 2400 px is zoomed from a 2x upscaled working copy (`delivery.md`, Phone legibility).
  The project document gives the copy as the asset (path and doubled size); every position
  in it is normalised, so nothing else changes, and OpenScreen finds the telemetry at
  `<copy>.cursor.json`. The drawn cursor and blur blocks are sized in output pixels, so they
  look the same from either file.
- Audio: none unless `--mic` and/or `--system-audio`; then **one** AAC track mixing both, in
  the same MP4.
- `<video>.cursor.json`: cursor telemetry, about 23 samples per second, `cx`/`cy` in 0–1 of the
  captured window (clamped; `visible: false` when the pointer is outside it), and
  `interactionType` `move`, `click` (then `mouseup`), `double-click`, `right-click`. Clicks need
  Accessibility for Openscreen. With `--cursor system` no telemetry is written at all: no drawn
  cursor, no click zooms.
- The project `record` writes is the simple v2 format with `aspectRatio: "auto"`. The skill
  does not edit it; `edit.py` builds its own project.
- `record-stop.py` runs `pack` to copy the take into `DEMO/takes/<take>/` and deletes the
  originals from `~/Library/Application Support/openscreen/recordings/`. OpenScreen also keeps a
  `media-links.registry.json` there that grows by about 175 KB per take and is never pruned;
  it is safe to delete when no recordings are left in that folder.

## Project format and export

- `edit.py build` writes a schemaVersion-4 document (the draft the app's own migration
  produces). The v2 format silently drops zoom `customScale` and `hideCursor` and cannot carry
  captions or several clips, so it is not used.
- Set `aspectRatio` always: missing or `auto` gives odd sizes (1752x1080).
- Annotations are positioned in percent of the **cropped** footage; edit.py converts take
  pixels accordingly. Document annotations need a `style` object.
- `export --quality good` + 16:9 = exactly 1920x1080; `--fps 30` default here. A 27 s draft
  from a real 39 s window capture took 2.9 s. Every export adds an AAC track, silent if the
  take had none (about -91 dB); `encode-final.py` drops it.
- Harmless stderr noise on export: "Could not approve session paths", logs in French,
  `atempo` warnings when a speed region exists.

## Privacy

An audit of OpenScreen 2.3.0 found no code path that uploads recordings, frames, cursor
telemetry or audio; they stay on the machine. AI-provider API keys are removed from the
environment of directly run commands (they are not used by these commands).
