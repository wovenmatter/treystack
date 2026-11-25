# Audio modes

Never a synthetic or text-to-speech voice. Choose one mode per run.

| Mode | When it is recorded | How it gets into the video | Captions |
|---|---|---|---|
| silent (default) | nothing | nothing; encode-final writes no audio track | rarely useful |
| music | after the cut | `add-music.py DRAFT MUSIC OUT [--volume -6] [--start S]` | no |
| live narration | with the screen (`record-start.py --mic`) | cut together with the video by OpenScreen; then `mix-voice.py DRAFT - OUT [--music F]` | `edit.json` `captions` from `transcribe.py` on the **take** |
| dub | after the final cut, last step | `record-dub.py CUT voice.wav`, then `mix-voice.py CUT voice.wav OUT [--music F]` | `encode-final.py --captions` from `transcribe.py` on **voice.wav** |

## Music

- User's own file: any format ffmpeg reads. If they want a commercial song, they supply the
  file; never download from streaming or video sites.
- Fetched: `fetch-music.py DEMO [--source mixkit|incompetech] [--mood positive] [--list]
  [--pick N]` downloads one track to `DEMO/audio/music.mp3` and writes
  `DEMO/audio/music-licence.txt` (title, source page, file URL, licence, required credit, date).
  - Mixkit (default): Mixkit Stock Music Free License, social and commercial use allowed, no
    attribution required. Do not bulk-download (their terms forbid it).
  - Incompetech (Kevin MacLeod): CC BY 4.0; the credit line in the licence file **must** be
    published with the video (post text, reply, or page caption). Tell the user.
- Prefer a track at least as long as the video: shorter tracks loop with a hard cut.
- Levels: everything is normalised to -14 LUFS integrated, -1.5 dBTP (two-pass loudnorm).
  `--volume` is relative to that target (-6 is a quiet bed).

## Live narration

- `--mic` records the default input (or `--mic-device NAME`) into the take's audio track.
  The first time, macOS asks for Microphone access **for Openscreen** and the recorder waits
  (record-start reports `waiting`). A denied microphone gives a silent track, not an error;
  record-stop warns about digital silence.
- `propose-cuts.py` in narration mode cuts only pauses that are both silent and visually idle,
  so screen action during a pause is kept. Speed-ups over speech sound like chatter
  (`edit.py summary` warns).
- `transcribe.py TAKE.mp4 audio/words.json` (whisper.cpp, `base.en` by default; about 0.3 s for
  20 s of speech on Apple silicon). Word starts are accurate to about 60 ms on test speech.
  The model is fetched once with `--download` (about 148 MB) into `~/.cache/whisper.cpp`.
- `mix-voice.py DRAFT - OUT` uses the draft's own audio: 80 Hz high-pass, gentle compression,
  optional `--denoise`, levelled; `--music F` adds a bed ducked under the voice
  (`--duck light|normal|strong`, about 8/13/25 dB).

## Dub

The steps are in SKILL.md (step 9). Details:
- The microphone permission is for the app running the shell (terminal or agent app), not
  Openscreen. If it does not open within 12 s the script exits 4 with the switch to turn on.
- Sync is measured on every run: the capture and every displayed frame are timestamped on the
  same host clock. The result is `voice.wav` (exactly the cut's length) plus
  `voice.sync.json`. A recording that is digital silence exits 5; very quiet input warns
  (wrong device?). `--device :1` etc. picks another input.
- **One-time clap test** (recommended, especially with Bluetooth or wireless mics, which add
  30–150 ms): clap on the first frame after the countdown, find the clap in voice.wav
  (`ffmpeg -i voice.wav -af silencedetect=n=-30dB:d=0.05 -f null -`), and pass the difference
  as `--extra-offset-ms` on later runs (positive = voice later). Remember it in the profile.

## Captions

- Ask about captions only when there is voice. They matter: feeds autoplay muted.
- Narration: OpenScreen burns them from the project (default 64 px at 1080; set
  `captions.style.fontSize`).
- Dub: `encode-final.py --captions` renders 2–5-word chunks with macOS AppKit through
  `osascript` (Homebrew ffmpeg has no drawtext or libass), bold white on a dark box, 7.8% of
  the frame height.
- Read the transcript before burning it: fix misheard product names in words.json.
