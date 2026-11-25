# Delivery: export settings, platform limits, phone legibility

## The final encode (`encode-final.py`)

| Setting | Value | Why |
|---|---|---|
| Container | MP4, `+faststart` | accepted everywhere; starts playing before fully loaded |
| Video | H.264 High, yuv420p, progressive, closed GOP, keyframe every 2 s, BT.709 tagged | X developer docs require High/4:2:0/no open GOP |
| Size | 1920x1080 (fit + black pad if the aspect differs) | 1080p is the highest size every X source accepts |
| Frame rate | 30 (default), `--fps 60` on request | X's help pages disagree (40 vs 60 fps max); 30 is inside every published limit. Test 60 with one post first. |
| Rate | CRF 18, max 12 Mb/s, buffer 24 Mb/s, preset slow | well under X's 25 Mb/s maximum, clean source for X's re-encode |
| Audio | AAC-LC 48 kHz stereo 192 kb/s; **no track** when silent | silent loops should carry no audio |
| Options | `--captions WORDS.json`, `--gif OUT.gif` (preview only; large), `--max-mb N` | |

Measured: a 27 s 1080p30 screen demo encodes in about 3.5 s and is about 9 MB.

## Platform notes (X, late 2026; check if it matters)

- Length: free accounts 140 s, Premium much longer. File size 512 MB free. A 15–120 s demo is
  always inside the limits.
- Videos of 60 s or less loop automatically: a first and last frame that join cleanly helps.
- Feeds autoplay muted: design for silent viewing; burn captions when there is voice.
- X re-encodes every upload and softens small text. Legibility comes from zooming, not bitrate.
- An `.srt` can be attached on the web composer if the user wants sidecar captions.
- 4K uploads: not documented officially. Do not deliver 4K.
- Landing pages and blogs: the same MP4 works; a short silent MP4 beats a GIF on size and quality.

## Phone legibility

A 16:9 video in a phone feed is about 310 points wide. A 1920 px frame is then scaled to about
0.16 pt per pixel: text must be about 50 px tall in the 1920x1080 output to read at 8 pt.

- On-phone cap height (pt) is roughly text_px x zoom x 310 / capture_width.
- **OpenScreen enlarges a capture at most 2x**: a constant in its zoom code clamps any zoom
  deeper than 2 / (magnification at rest) without a word. At rest the capture is fitted into
  the frame minus padding (polished: 1843x1037), so a 1280 px capture stops near x1.45 and a
  2560 px one near x2.77. That would cap 14 px UI text on a 1x screen at about 4.5 pt.
- So a capture narrower than 2400 px is zoomed from a **2x upscaled working copy**
  (`<take>.x2.mp4` beside the take; lanczos, libx264 CRF 10, timestamps and audio passed
  through, telemetry copied). `edit.py build` (run by `export.py`) makes it once per take and
  only when a zoom needs it; plain look never does. Measured on a 41 s 1280x752 take: 3.7 s,
  6.3 MB (the take itself is 6.6 MB), about 56 dB PSNR against the lanczos frame. A x3 zoom
  then renders at x2.77 instead of x1.38 and 14 px text reaches about 9 pt. The text is a
  smooth upscale, softer than a real Retina capture, but readable.
- Zoom so the region that matters is about 30–38% of the capture width (x2.6–3.3) when its
  text matters; titles read at x2–2.5. `edit.py summary` shows the depth that will render.
- A smaller window gives bigger text unzoomed.
- Keep important UI away from the frame edges.
- Always look at `phone-preview.py DRAFT --at T1,T2 -o phone.png` (frames scaled to 620 px,
  a 2x phone; `--density 3` is the best case, `--density 1` the harsh case) and at
  `frames.py DRAFT --count 12 --sheet-only`. `--text-px N --source-width W --zoom Z` prints
  the estimated on-phone size.
- Square (1:1) or 4:5 versions get about twice the feed area: set `"aspect": "1:1"` in
  edit.json; the view follows the cursor.
