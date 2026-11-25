#!/usr/bin/env python3
"""Sample frames from a video so an agent can "watch" it cheaply.

Picks timestamps from any mix of:
  --every N            one frame every N seconds (starting at --start, default 0)
  --at T1,T2,...       explicit times in seconds (also accepts mm:ss.s)
  --clicks             every click in the cursor telemetry (<video>.cursor.json, or --telemetry)
  --count N            N frames spread evenly over the video

Writes PNGs named f_<seconds>.png (each labelled with its timestamp in the corner unless
--no-label), and with --sheet a contact sheet (sheet_01.png, ...) of labelled thumbnails.
Prints one line per output file. Needs only ffmpeg/ffprobe and python3 (no drawtext needed:
labels are drawn by a built-in bitmap font).

Usage examples:
  frames.py rec.mp4 --every 5 --width 640 --out frames/
  frames.py rec.mp4 --count 24 --sheet --cols 4 --thumb 480 --out frames/
  frames.py rec.mp4 --clicks --offset -0.2 --out frames/   # just before each click
  frames.py draft.mp4 --at 3.5,12,00:41.2 --width 1920 --out check/
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Canvas, ffprobe_info, grab_frame, text_size  # noqa: E402


def parse_time(s):
    s = s.strip()
    if ":" in s:
        parts = [float(p) for p in s.split(":")]
        v = 0.0
        for p in parts:
            v = v * 60 + p
        return v
    return float(s)


def fmt_time(t):
    return "%d:%04.1f" % (int(t // 60), t % 60)


def load_clicks(path):
    with open(path) as fh:
        data = json.load(fh)
    samples = data if isinstance(data, list) else data.get("samples", [])
    out = []
    for s in samples:
        kind = s.get("interactionType", "move")
        if kind in ("click", "double-click", "right-click", "middle-click"):
            out.append((s["timeMs"] / 1000.0, s.get("cx"), s.get("cy"), kind))
    return out


def label(canvas, text, scale):
    tw, th = text_size(text, scale)
    pad = scale * 2
    canvas.text(pad * 2, pad * 2, text, scale=scale, color=(255, 255, 0), bg=(0, 0, 0), pad=pad)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", default="frames", help="output directory (created)")
    ap.add_argument("--every", type=float, help="seconds between frames")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, help="stop at this time (default: video end)")
    ap.add_argument("--at", help="comma-separated timestamps (s or mm:ss.s)")
    ap.add_argument("--count", type=int, help="N frames spread evenly")
    ap.add_argument("--clicks", action="store_true", help="add a frame at every telemetry click")
    ap.add_argument("--telemetry", help="cursor telemetry json (default <video>.cursor.json)")
    ap.add_argument("--offset", type=float, default=0.0, help="shift click frames by this many seconds")
    ap.add_argument("--mark", action="store_true", help="draw a red box at each click position on click frames")
    ap.add_argument("--width", type=int, default=640, help="width of single frames (px), default 640")
    ap.add_argument("--sheet", action="store_true", help="also/only build contact sheets")
    ap.add_argument("--sheet-only", action="store_true", help="write contact sheets but not single frames")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--rows", type=int, default=4, help="rows per sheet (more frames -> more sheets)")
    ap.add_argument("--thumb", type=int, default=480, help="thumbnail width in sheets (px)")
    ap.add_argument("--no-label", action="store_true")
    a = ap.parse_args()

    W, H, dur, fps = ffprobe_info(a.video)
    end = min(a.end, dur) if a.end else dur
    last = max(0.0, end - (1.0 / fps if fps else 0.05))
    items = []  # (t, note, click_xy)
    if a.every:
        t = a.start
        while t <= last + 1e-6:
            items.append((t, "", None))
            t += a.every
    if a.count:
        n = max(1, a.count)
        span = last - a.start
        for i in range(n):
            items.append((a.start + (span * (i + 0.5) / n), "", None))
    if a.at:
        for s in a.at.split(","):
            if s.strip():
                items.append((parse_time(s), "", None))
    if a.clicks:
        tel = a.telemetry or a.video + ".cursor.json"
        if not os.path.exists(tel):
            sys.exit("no telemetry at %s (pass --telemetry)" % tel)
        for t, cx, cy, kind in load_clicks(tel):
            items.append((t + a.offset, kind.upper(), (cx, cy)))
    if not items:
        items = [(a.start + (last - a.start) * (i + 0.5) / 12, "", None) for i in range(12)]
    items = sorted({(round(min(max(t, 0.0), last), 3), n, xy) for t, n, xy in items}, key=lambda x: x[0])

    os.makedirs(a.out, exist_ok=True)
    written = []
    thumbs = []
    for t, note, xy in items:
        need_w = a.width if not a.sheet_only else a.thumb
        img = grab_frame(a.video, t, need_w)
        if a.mark and xy and xy[0] is not None:
            bx, by = int(xy[0] * img.w), int(xy[1] * img.h)
            r = max(6, img.w // 60)
            img.frame(bx - r, by - r, 2 * r, 2 * r, (255, 0, 0), t=max(2, img.w // 400))
        text = fmt_time(t) + ("  " + note if note else "")
        if not a.sheet_only:
            single = Canvas.from_rgb(img.w, img.h, img.buf)
            if not a.no_label:
                label(single, text, max(2, img.w // 320))
            p = os.path.join(a.out, "f_%08.3f%s.png" % (t, "_" + note.lower() if note else ""))
            single.write_png(p)
            written.append(p)
        if a.sheet or a.sheet_only:
            th = img if img.w == a.thumb else grab_frame(a.video, t, a.thumb)
            if a.mark and xy and xy[0] is not None and th is not img:
                bx, by = int(xy[0] * th.w), int(xy[1] * th.h)
                r = max(6, th.w // 60)
                th.frame(bx - r, by - r, 2 * r, 2 * r, (255, 0, 0), t=2)
            if not a.no_label:
                label(th, text, max(2, th.w // 240))
            thumbs.append(th)
    if thumbs:
        per = a.cols * a.rows
        gap = 6
        for si in range(0, len(thumbs), per):
            chunk = thumbs[si:si + per]
            tw, thh = chunk[0].w, chunk[0].h
            rows = (len(chunk) + a.cols - 1) // a.cols
            cols = min(a.cols, len(chunk))
            sheet = Canvas(cols * tw + (cols + 1) * gap, rows * thh + (rows + 1) * gap, (40, 40, 40))
            for i, th in enumerate(chunk):
                r, c = divmod(i, a.cols)
                sheet.paste(th, gap + c * (tw + gap), gap + r * (thh + gap))
            p = os.path.join(a.out, "sheet_%02d.png" % (si // per + 1))
            sheet.write_png(p)
            written.append(p)
    for p in written:
        print(p)


if __name__ == "__main__":
    main()
