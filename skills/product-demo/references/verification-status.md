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
| `record-stop.py` with nothing running, or a folder that does not exist | Real |
| `record-start.py` window take; refuses no-match and ambiguous titles (incl. a title that is all of one window's and part of another's); refuses a second start in the same or another folder | Real |
| `record-stop.py` stop + pack into the demo folder, originals removed (0.7 s) | Real |
| `--duration` take collected as `already-ended` | Real |
| `--mic` records the default microphone (a Bluetooth mic) into one AAC track in the take | Real (ambient room sound only, no speech) |
| `--cursor system` writes no telemetry file | Real |
| `record-start` `waiting` status during a first-run permission prompt | Unverified (prompts were already answered) |
| Window closed mid-take: recorder finishes, record-stop collects it with a warning | Real |
| Recorder force-killed: raw video salvaged | Earlier component test only, not re-run after merging |
| Window capture size on a Retina display (expected about 2x) | Unverified: needs a human with a Retina screen |
| First-run permission prompts on a fresh Mac | Unverified: needs a human on a new machine |
| Minimised / other-Space / partly off-screen windows | Unverified |

## Telemetry and zooms

| Item | Status |
|---|---|
| Real telemetry: v2 format, about 23 samples/s, `cx`/`cy` clamped to 0–1 of the window incl. title bar, `visible:false` outside | Real |
| Real click / mouseup events | Unverified in the merged skill (no one clicked during takes); an earlier component test saw them |
| `plan-zooms.py` on real telemetry | Real samples with three clicks injected (hybrid): correct clusters, view clamped inside the frame |
| `plan-zooms.py` ignores clicks outside the recorded window | Code path added; tested only by construction |
| Zoom depth cap: OpenScreen clamps a zoom to 2 output px per capture px (`MAX_SOURCE_MAGNIFICATION` in its source); with padding 10 a 1280x720 view stops at x1.38, 2560x1440 at x2.77; deeper values render identically | Real 1280 px takes + synthetic 1280/1920/2560 px footage, measured; formula matches the source |
| 2x upscaled working copy for takes under 2400 px: a x3 zoom renders at x2.74 (measured 3.94 output px per capture px, vs 1.98 from the original); 14 px text readable at phone width | Real 41 s 1x take, before/after renders compared |
| Working copy keeps alignment: every frame timestamp identical (1334/1334); a moving tick matched within 1 frame at 0.5–21.5 s; injected clicks put the drawn cursor and the zoom focus on the same button in both renders; cursor size unchanged | Real take + **injected test telemetry** (synthetic pointer path and two clicks in a copy of real telemetry) |
| Working copy made once per take (3.7 s for 41 s, 6.3 MB), reused on re-export; plain look makes none | Real; selftest checks both |
| Planner ends zoom holds 1.2 s before the kept footage ends; summary warns otherwise | Real |
| `hide_cursor`; blur follows zooms | Real |
| Drawn cursor (native sprite) position and timing vs the video | Unverified: the pointer stayed outside the window |
| Zoom focus combined with `crop` | Real; a small shift (under 2% of the frame) between cropped and uncropped renders was seen and not resolved |

## Editing and export

| Item | Status |
|---|---|
| `edit.py new` from a take folder → schemaVersion-4 document → export 1920x1080 30 fps | Real (27.4 s draft in 2.9 s; output length matched the summary exactly; again in four end-to-end runs, 15–20 s drafts in about 2 s) |
| `edit.py` refuses unknown or misspelled fields and invalid JSON | Real |
| polished and plain looks; plain with `crop` removing the title bar; summary's suggested inset crop hides the window's rounded bottom corners | Real |
| blur placement with and without `crop` | Real (bug found and fixed: annotations are relative to the cropped frame) |
| `propose-cuts.py` idle detection (changed-pixel method) | Real: both frozen stretches found to within 0.4 s |
| `propose-cuts.py` narration mode (silent AND idle) | Real video + synthetic speech |
| `frames.py`, `phone-preview.py` | Real |
| Phone legibility thresholds for real anti-aliased UI fonts | Unverified (calibrated on a bitmap font, also inside the real capture) |
| Multi-take `keep` with reordering | Synthetic only (component test) |
| 120 s capture with heavy motion: export time | Unverified |

## Audio and delivery

| Item | Status |
|---|---|
| `fetch-music.py` Mixkit list + one download + licence file; Incompetech list | Real network |
| `add-music.py` on a real draft (loudness to target, video copied) | Real |
| Captions from a transcript via the project, mapped through cuts | Real video + synthetic speech (`say`, test input only); re-transcribing the final put words within about 0.1 s of where the cuts map them |
| Narration A/V sync through cuts | Real video + synthetic speech: speech onsets within about 20 ms of expected |
| `mix-voice.py` narration (`-`) with ducked music | Real draft + synthetic speech |
| `record-dub.py` capture, countdown, sync measurement | Real (mic opened, 332 and 540 frames timed, under 1 ms jitter); nobody spoke |
| Dub sync with a real voice; one-time clap test | **Unverified: needs a human speaking** |
| Dub captions via `encode-final.py --captions` | Synthetic voice |
| `encode-final.py` X preset; silent drafts get no audio track | Real |
| 60 fps delivery accepted by X; upload behaviour | Unverified |

## Mode B (agent drives)

| Item | Status |
|---|---|
| `pointer.py check` fails with the exact Accessibility switch and exit 3 | Real (the host app lacks Accessibility) |
| Eased pointer moves, clicks, typing recorded into telemetry | **Unverified** |
| Driving with a harness desktop-control tool | Unverified |

## Only a human can check
1. Window capture size and sharpness on a Retina display (no upscaling there), and whether
   the upscaled 1x text is judged good enough by a person on a real phone.
2. A real voice through `record-dub.py`, plus the one-time clap test for the offset.
3. Mode B: grant Accessibility to the shell's app, then drive a take with `pointer.py`.
4. First-run permission prompts on a Mac where Openscreen was never granted anything.
5. That nothing private is on screen in the final video.
