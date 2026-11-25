---
name: product-demo
description: Record an app on screen and turn it into a short, cut demo video (16:9, 1080p, legible in a phone feed) for X, social, a landing page or a blog. Use when the user wants to record, capture, film or screen-record a product demo, a feature walkthrough or an app/website, or wants a screen recording cut, sped up, zoomed, captioned or scored into a short video. The user performs the demo while it records, or the agent drives the app. macOS, uses the OpenScreen CLI and ffmpeg. Never posts anything.
---

# Product demo

Capture an app, cut it into a 15–120 s demo, hand over an MP4. You never post it anywhere.

`$SKILL` below means this skill's folder; every script is in `$SKILL/scripts/`, takes `--help`,
and needs only python3 (3.9+), bash, ffmpeg and macOS. OpenScreen is used **only** through its
CLI commands `sources`, `record`, `export`, `info` and `pack`, always via these scripts. Never
open its GUI, never use its AI assistant, never run `openscreen mcp`.

## 1. Preflight (every run)

Run `$SKILL/scripts/preflight.sh`. It prints `ok` or one `missing <tool>: <install hint>` line
per tool. If something is missing, show the hints and ask before installing anything. Add
`--transcribe` when the run needs captions, `--drive` when you will drive the app (mode B).
Do not check permissions up front: they surface when used, with a message naming the switch
(see `references/permissions.md`).

## 2. Profile

Run `$SKILL/scripts/find-profile.sh`. It prints the path of the user's `demo-profile.md`
(current folder, then parents, then a path named in CLAUDE.md / AGENTS.md) or nothing. Read
it: defaults (destination, length, shape, look, audio, captions), the products they demo
(window title, how to launch, safe-data mode, things that must never appear) and where demo
folders go. No profile: use the neutral defaults below and offer once to create one from
`$SKILL/profile.example.md`. Only write preferences back to it when the user says yes.

## 3. Brief: one round of questions, never an interview

Use your harness's question tool if it has one, plain text otherwise. Ask everything in one go.
- **User arrived with a plan:** extract what they said; ask only what is missing (often 0–3).
- **User just ran the skill:** ask what the demo should show and the one thing a viewer
  should take away; who records (user performs = A, or you drive = B); which app/window;
  look (polished / plain); audio (silent / music / live narration / dub); captions (only if
  there is voice); length and shape; anything that must not appear.
- A profile answers some of these: state its defaults in one line ("polished, silent, 20-30 s
  for X, unless you say otherwise") instead of asking them again.

Neutral defaults: user records, polished, silent, 16:9 1920x1080, under 60 s, 30 fps.
Audio is **never** a synthetic or text-to-speech voice. Music is a file the user supplies or
a royalty-free track you fetch (step 9); never download songs from streaming or video sites.

Make the demo folder: `<demo root from profile, else the current folder>/<YYYY-MM-DD>-<slug>/`.
It will hold `takes/`, `edit.json`, `drafts/`, `audio/` and the final MP4. Re-runs reuse it.

## 4. Stage

1. `$SKILL/scripts/sources.py` lists recordable windows. Pick the window by a part of its
   title that matches only it (record-start refuses ambiguous titles).
2. Suggest a window size near 16:9 and not larger than needed, e.g. about 1280x720 points:
   a smaller window means larger text in the video. The window's title bar is recorded too.
3. Remind the user: turn on Do Not Disturb, close unrelated tabs and windows, use the
   product's safe-data mode if the profile names one, and check the title bar for file names.

## 5. Record

**Mode A (user performs, the usual case).**
`$SKILL/scripts/record-start.py DEMO --window "<title part>" [--mic] --name take-1`
returns once capture runs. Tell the user to perform now, at a calm pace; a fumbled step can
simply be redone (it gets cut). When they say done: `$SKILL/scripts/record-stop.py DEMO`.
It packs the take into `DEMO/takes/take-1/` and prints JSON with size, duration, telemetry
(sample rate, clicks) and warnings; read the warnings to the user. More takes: repeat with
`--name take-2`. Add `--mic` only for live narration. Status: `record-status.py DEMO`.
If record-start reports `waiting`, a permission prompt is probably on screen: tell the user.

**Mode B (you drive).** Use your harness's desktop-control tool if it has one that moves the
real pointer (needed for cursor telemetry and click zooms). Otherwise run
`$SKILL/scripts/pointer.py check` before anything else: it needs Accessibility for the app
hosting your shell, and when it exits 3, relay its message and fall back to mode A. Do not
look for another way around it. Then do a dry run off camera (walk every step, note the screen
coordinates), start recording as in mode A and drive with `pointer.py move`, `click`, `type`,
`key` (eased real pointer moves through cliclick).

## 6. Watch

1. `$SKILL/scripts/edit.py new DEMO/takes/take-1` writes `DEMO/edit.json` (the single source
   of truth; format in `references/edit-format.md`).
2. Narration only, first: `$SKILL/scripts/transcribe.py <take video> DEMO/audio/words.json`.
3. `$SKILL/scripts/propose-cuts.py --edit DEMO/edit.json --write` proposes cuts: idle stretches
   are sped up 4x and idle at the start or end is cut; with narration only pauses that are
   both silent and idle are cut (trim long pauses over moving screens by hand).
4. `$SKILL/scripts/frames.py <take video> --every 2 --sheet-only --out DEMO/watch` and look
   at the contact sheet; `--clicks` adds a frame at every click.
5. **Privacy pass:** look for anything the profile or brief says must not appear, plus
   notifications, names, emails, tokens and file paths. Hide them with a `blur` box or cut them.

## 7. Edit

- Polished: `$SKILL/scripts/plan-zooms.py --edit DEMO/edit.json --write` proposes one zoom
  per click cluster (about x2.8, readable on a phone). Drop or merge zooms that do not help.
  No clicks recorded means no planned zooms: add zooms by hand where the action is
  (`references/edit-format.md` has the fields).
- Adjust `cut`, `speed`, `zooms`, `blur`, `crop`, `captions` in edit.json by hand as needed.
- `$SKILL/scripts/edit.py summary DEMO/edit.json`: check the output length and that every
  zoom says `phone-legible` (it shows the depth that will really render), and read any WARNING
  lines. A take narrower than 2400 px (a 1x screen) is zoomed from a 2x upscaled copy that
  export.py makes once beside it (`*.x2.mp4`); nothing to do.

## 8. Draft (no approval step before it)

1. `$SKILL/scripts/export.py DEMO/edit.json -o DEMO/drafts/draft-1.mp4` (rebuilds the
   project, renders 1920x1080 30 fps; about 10x faster than real time).
2. Check your own work: `frames.py DEMO/drafts/draft-1.mp4 --count 12 --sheet-only --out
   DEMO/check` and `phone-preview.py DEMO/drafts/draft-1.mp4 --at <key moments> -o
   DEMO/check/phone.png`. Look at both. Fix what is wrong before showing anything.
3. Hand over the draft path with a short shot list: kept / cut / sped up / zoomed, and the
   output length. Say the user is the last check for anything private on screen.
4. Iterate on plain-English notes: edit edit.json, re-export as draft-2, and so on.

## 9. Audio (after the cut is settled)

- **Silent:** nothing to do (the final encode drops OpenScreen's silent track).
- **Music:** the user's file, or `$SKILL/scripts/fetch-music.py DEMO [--mood positive]`, which
  fetches one royalty-free track and writes `audio/music-licence.txt`; tell the user any
  required credit. Then `add-music.py <draft> <music> DEMO/drafts/draft-N-music.mp4` (music
  alone at -14 LUFS; add `--volume -6` only if the user wants it in the background).
- **Live narration:** captions come from the project: add
  `"captions": {"words": "audio/words.json"}` to edit.json and re-export. Then
  `mix-voice.py <draft> - <out>` (cleans up and levels the voice; `--music F` ducks a bed).
- **Dub (always last; changing the cut afterwards breaks sync):** tell the user a muted
  player will open with a 3-2-1 countdown and they talk over it, then
  `record-dub.py <final cut> DEMO/audio/voice.wav` and `mix-voice.py <final cut>
  DEMO/audio/voice.wav <out> [--music F]`. Captions: `transcribe.py DEMO/audio/voice.wav
  DEMO/audio/dub-words.json`, passed to encode-final as `--captions`. Sync and the one-time
  clap test: `references/audio.md`.

## 10. Final

`$SKILL/scripts/encode-final.py <last draft> DEMO/<YYYY-MM-DD>-<slug>.mp4 [--fps 60]
[--captions WORDS.json]`: H.264 High, 1920x1080, 30 fps (60 if asked), X-safe bitrate, no
audio track when silent. Report the path, duration and size it prints, plus any music credit.

## References (read when needed)
- `references/edit-format.md`: edit.json fields and a complete example.
- `references/openscreen.md`: how the scripts drive OpenScreen; pitfalls.
- `references/audio.md`: the four audio modes, loudness, dub sync, captions.
- `references/delivery.md`: export settings, X limits, phone legibility rules.
- `references/permissions.md`: permissions, first run, troubleshooting.
- `references/verification-status.md`: what has and has not been tested.
- `scripts/selftest.sh` checks the editing pipeline without recording (about 20 s).
