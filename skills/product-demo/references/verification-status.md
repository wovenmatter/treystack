# Verification status

Tested on macOS 27.3, Apple silicon, one external 3440x1440 display at 1x (no Retina screen),
OpenScreen 2.3.0, ffmpeg 9.0.2 (Homebrew), python 3.9.6, whisper.cpp 1.9.5. The subject was an
ffplay window playing generated app-like footage; nobody touched the mouse during takes.

**Real** = a real OpenScreen capture of an on-screen window. **Synthetic** = generated footage,
telemetry or audio only. **Unverified** = not run.

## Recording

| Item | Status |
|---|---|
| `sources.py` lists windows, displays, microphones (about 1.2 s) | Real |
| `record-start.py` window take; refuses no-match and ambiguous titles (incl. a title that is all of one window's and part of another's) and a second start in the same or another folder | Real |
| `record-stop.py`: stop + pack into the demo folder, originals removed (0.7 s); nothing running; a folder that does not exist | Real |
| `--duration` take collected as `already-ended`; window closed mid-take collected with a warning | Real |
| `--mic` records the default microphone (a Bluetooth mic) into one AAC track | Real (ambient room sound only, no speech) |
| `--cursor system` writes no telemetry file | Real |
| Recorder force-killed: raw video salvaged | Earlier component test only |
| `waiting` status during a first-run permission prompt; first-run prompts on a fresh Mac | Unverified (prompts were already answered) |
| Window capture size on a Retina display (expected about 2x) | Unverified |
| Minimised / other-Space / partly off-screen windows | Unverified |

## Telemetry and zooms

| Item | Status |
|---|---|
| Telemetry: v2 format, about 23 samples/s, `cx`/`cy` clamped to 0–1 of the window incl. title bar, `visible:false` outside | Real |
| Click / mouseup events | Unverified in the merged skill (no one clicked during takes); an earlier component test saw them |
| `plan-zooms.py` clusters and view clamping | Real samples with three injected clicks |
| `plan-zooms.py` ignores clicks outside the recorded window | Tested only by construction |
| Zoom depth cap (2 output px per capture px; with padding 10 a 1280x720 view stops at x1.38, 2560x1440 at x2.77; deeper values render identically) | Real 1280 px takes + synthetic 1280/1920/2560 px footage; formula matches OpenScreen's source |
| 2x working copy for takes under 2440 px: a x3 zoom renders at x2.74 instead of x1.38; 14 px text readable at phone width | Real 41 s 1x take, renders compared |
| Working copy alignment: all 1334 frame timestamps identical; a moving tick within 1 frame; drawn cursor and zoom focus on the same button in both renders | Real take + injected test telemetry |
| Working copy made once per take (3.7 s for 41 s, 6.3 MB) and reused; plain look makes none | Real; selftest checks both |
| Zoom holds end 1.2 s before the kept footage ends; summary warns otherwise | Real |
| `hide_cursor`; blur follows zooms | Real |
| Drawn cursor position and timing vs the video | Unverified: the pointer stayed outside the window |
| Zoom focus with `crop` (focus is relative to the cropped frame, like blur) | Synthetic take, large crop: the zoom shows its target |

## Editing and export

| Item | Status |
|---|---|
| `edit.py new` → schemaVersion-4 document → export 1920x1080 30 fps | Real (27.4 s draft in 2.9 s, length matched the summary exactly; four more end-to-end runs) |
| `edit.py` refuses unknown or misspelled fields and invalid JSON | Real |
| Polished and plain looks; plain with `crop`; the summary's inset crop hides rounded corners | Real |
| Blur placement with and without `crop` | Real (annotations are relative to the cropped frame) |
| `propose-cuts.py` idle detection (changed-pixel method) | Real: both frozen stretches found within 0.4 s |
| `propose-cuts.py` narration mode (silent AND idle) | Real video + synthetic speech |
| `frames.py`, `phone-preview.py` | Real |
| Phone legibility thresholds for real anti-aliased UI fonts | Unverified (calibrated on a bitmap font) |
| Multi-take `keep` with reordering | Synthetic only |
| 120 s capture with heavy motion: export time | Unverified |

## Audio and delivery

| Item | Status |
|---|---|
| `fetch-music.py` Mixkit list + download + licence file; Incompetech list | Real network |
| `add-music.py` on a real draft | Real |
| Narration captions via the project, mapped through cuts (within about 0.1 s); A/V sync through cuts (about 20 ms) | Real video + synthetic speech (`say`, test input only) |
| `mix-voice.py` narration with ducked music | Real draft + synthetic speech |
| `record-dub.py` capture, countdown, sync measurement | Real (332 and 540 frames timed, under 1 ms jitter); nobody spoke |
| Dub sync with a real voice; one-time clap test | **Unverified: needs a human speaking** |
| Dub captions via `encode-final.py --captions` | Synthetic voice |
| `encode-final.py` X preset; silent drafts get no audio track | Real |
| 60 fps delivery accepted by X | Unverified |

## Mode B (agent drives)

| Item | Status |
|---|---|
| `pointer.py check` fails with the exact Accessibility switch and exit 3 | Real (the host app lacks Accessibility) |
| Eased pointer moves, clicks, typing recorded into telemetry; driving with a harness tool | **Unverified** |

## Only a human can check
1. Capture size and sharpness on a Retina display, and whether upscaled 1x text reads well
   enough on a real phone.
2. A real voice through `record-dub.py`, plus the one-time clap test.
3. Mode B: grant Accessibility to the shell's app, then drive a take with `pointer.py`.
4. First-run permission prompts on a Mac where Openscreen was never granted anything.
5. That nothing private is on screen in the final video.
