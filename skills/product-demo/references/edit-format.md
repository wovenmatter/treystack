# edit.json

One small JSON file per demo, in the demo folder. It is the source of truth: `export.py`
rebuilds the OpenScreen project from it on every render, so changing the demo means changing
this file and re-exporting.

**Units.** Times are seconds in the source take (the recorded video, not the output). Boxes
and points are pixels of the take video. A window capture includes the window's title bar,
so a 1600x1000 window gives a 1600x1032 video and y coordinates include the bar.

## Complete example

```json
{
  "sources": {"main": "takes/take-1/recording-1700000000000.mp4"},
  "look": "polished",
  "aspect": "16:9",
  "cut": [[0, 1.8], [17.0, 23.0], [37.3, 39.3]],
  "speed": [{"from": 30, "to": 35, "x": 4}],
  "zooms": [
    {"from": 2.1, "to": 3.7, "center": [562, 365], "width": 528},
    {"from": 8.6, "to": 10.2, "center": [1010, 635], "scale": 3, "hide_cursor": true},
    {"from": 24.0, "to": 29.0, "center": [800, 500], "width": 640, "follow": true}
  ],
  "blur": [{"from": 0, "to": 40, "box": [1150, 400, 300, 40], "type": "mosaic"}],
  "crop": {"main": [0, 32, 1600, 1000]},
  "captions": {"words": "audio/words.json", "style": {"fontSize": 64}},
  "text": [{"from": 0, "to": 2.5, "text": "Export in one click", "y": 8, "size": 64}],
  "style": {"padding": 10, "background": "#0f172a"}
}
```

## Fields

| Field | Meaning |
|---|---|
| `sources` | name -> video path (relative to edit.json). `edit.py new` fills it. Several takes are allowed. |
| `look` | `polished`: window on a wallpaper, padding 10, rounded corners, shadow, cursor drawn larger and smoothed, zooms. `plain`: edge to edge, black bars if the capture is not 16:9, small cursor, zooms ignored. |
| `aspect` | `16:9` (default; gives exactly 1920x1080), `1:1`, `4:5`, `9:16` or `W:H`. Non-16:9 shapes follow the cursor. |
| `cut` | removed source ranges `[from, to]`. Single source only. |
| `keep` | instead of `cut`: kept ranges in output order; `[from, to]` or `["take2", from, to]` to mix and reorder takes. |
| `speed` | `{from, to, x}` source range played x times faster (0.25–16). Audio is time-stretched; avoid speeding over speech (`summary` warns). |
| `zooms` | `{from, to, center:[x,y], width}` (visible source width) or `scale` (1–5). `from`–`to` is the **hold**: OpenScreen zooms in before `from` (about 0.9–1.2 s) and out after `to`. Zooms less than 1.5 s apart pan instead of zooming out. `follow: true` tracks the cursor; `hide_cursor: true` hides it during the zoom. |
| `blur` | `{from, to, box:[x,y,w,h]}` in take pixels; `type` `mosaic` (default) or `blur`; `shape` `rectangle`/`oval`; `intensity`, `block`. Stays on its target through zooms and crops. |
| `crop` | per source `[x,y,w,h]`, e.g. `[0, 32, W, H-32]` removes the title bar. |
| `captions` | `{"words": file}`: transcribe.py output or `[{"text","start","end"}]`, times in the take's source time (narration). Burned in by OpenScreen and mapped through cuts and speed changes. `style` passes caption keys through (`fontSize` px at 1080, default 64; `color`, `maxWordsPerLine`...). For a dub, use `encode-final.py --captions` instead. |
| `text` | frame-space title cards `{from, to, text, x, y, w, h (percent), size, color, bg}`; times on the output timeline before speed changes. |
| `style` | overrides of the look: `background` (`/wallpapers/wallpaper1..18.jpg`, `#rrggbb` or a CSS gradient), `padding` 0–100, `radius`, `shadow`, `cursor_size` 1.5–6, `cursor_smoothing`, `show_cursor`, `motion_blur`, `fill`. |
| `allow_zooms_in_plain` | `true` keeps zooms with the plain look. |

## Commands

- `edit.py new TAKE_DIR [TAKE_DIR ...]` writes `DEMO/edit.json` (refuses to overwrite).
- `propose-cuts.py --edit edit.json --write` replaces `cut` and `speed` (keeps `edit.json.bak`).
- `plan-zooms.py --edit edit.json --write` replaces `zooms` (keeps `edit.json.bak`).
- `edit.py summary edit.json`: timeline, output length, zoom verdicts (`phone-legible` when the
  zoom shows at most about 38% of the capture width), warnings. Each zoom shows the depth that
  will actually render: OpenScreen never enlarges the capture past 2x, so takes narrower than
  2400 px are zoomed from a 2x upscaled working copy (`<take>.x2.mp4`, made by `edit.py build`
  once per take, only when a zoom needs it); coordinates in edit.json stay in take pixels.
  It also warns when the last zoom has no time to zoom out before the end, and in the plain
  look suggests a crop that hides a window's rounded bottom corners.
- `edit.py` refuses unknown fields (typos) and names the nearest valid one.
- `edit.py build edit.json` writes `edit.openscreen` (export.py does this for you).

## Zoom sizing

`plan-zooms.py` makes each view 33% of the capture width (about x3) by default, holds from
0.4 s before the first click to 1.2 s after the last (longer while the cursor stays near),
and keeps the view inside the frame. Clicks outside the recorded window are ignored. For
body text use about x3; titles read at x2–2.5. OpenScreen renders at most about x2.8 for a
16:9 window (from the upscaled copy on a 1x screen), and the planner never plans deeper than
what renders; it also ends each hold 1.2 s before the end of the kept footage so the zoom can
release. See `delivery.md` for the legibility arithmetic.
