#!/usr/bin/env python3
"""Make synthetic "screen recording" footage plus matching cursor telemetry, for testing
the edit/export pipeline without a real capture.

The clip looks like an app window: a title bar, a sidebar, a 3x3 grid of labelled panels
(P1..P9) with large, medium and small text, a pixel ruler on the edges, a big per-second
source-time readout (SRC 00:12) and a sliding tick on a time ruler (sub-second time).
A magenta square marker moves along the scripted cursor path; at each click the clicked
button flashes green for 0.6 s and the audio track beeps (1 kHz), so trims, speed-ups,
zoom targets, the rendered cursor position and audio sync can all be checked by eye.

Writes:
  <out>.mp4               the clip (H.264 + AAC)
  <out>.mp4.cursor.json   OpenScreen-style telemetry (version 2) for the same path
  <out>.plan.json         ground truth: panel boxes, click times/positions

Usage:
  make-test-footage.py OUT_BASENAME [--width 2560 --height 1440 --fps 60 --duration 50]
                       [--sample-ms 33] [--no-marker]
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Canvas  # noqa: E402

BG = (243, 244, 247)
INK = (24, 26, 32)
MUTED = (110, 115, 128)
PANEL = (255, 255, 255)
ACCENT = (40, 92, 230)


def layout(W, H):
    """Panel and button boxes in source pixels, scaled from a 2560x1440 design."""
    sx, sy = W / 2560.0, H / 1440.0
    side = int(320 * sx)
    top = int(110 * sy)
    gx0, gy0 = side + int(60 * sx), top + int(60 * sy)
    gw, gh = W - gx0 - int(60 * sx), H - gy0 - int(130 * sy)
    gap = int(30 * sx)
    pw, ph = (gw - 2 * gap) // 3, (gh - 2 * gap) // 3
    panels = []
    for r in range(3):
        for c in range(3):
            n = r * 3 + c + 1
            x, y = gx0 + c * (pw + gap), gy0 + r * (ph + gap)
            bw, bh = int(pw * 0.42), int(ph * 0.16)
            panels.append({
                "name": "P%d" % n, "x": x, "y": y, "w": pw, "h": ph,
                "button": {"x": x + pw - bw - int(24 * sx), "y": y + ph - bh - int(24 * sy), "w": bw, "h": bh},
            })
    return {"sidebar_w": side, "titlebar_h": top, "panels": panels, "scale": sx}


def draw_base(W, H, lay):
    s = lay["scale"]
    k = lambda v: max(1, int(round(v * s)))  # noqa: E731
    c = Canvas(W, H, BG)
    # title bar
    c.rect(0, 0, W, lay["titlebar_h"], (230, 232, 237))
    for i, col in enumerate([(237, 106, 94), (245, 191, 79), (98, 197, 84)]):
        c.rect(k(30) + i * k(40), k(40), k(24), k(24), col)
    c.text(k(170), k(34), "DEMO APP  -  SYNTHETIC TEST FOOTAGE", scale=k(5), color=INK)
    # sidebar
    c.rect(0, lay["titlebar_h"], lay["sidebar_w"], H, (235, 237, 242))
    for i, item in enumerate(["INBOX", "PROJECTS", "REPORTS", "SETTINGS", "BILLING", "TEAM"]):
        y = lay["titlebar_h"] + k(50) + i * k(80)
        c.text(k(40), y, item, scale=k(4), color=INK if i else ACCENT)
        c.text(k(40), y + k(38), "%d NEW ITEMS" % (i * 3 + 2), scale=k(2), color=MUTED)
    # panels
    for p in lay["panels"]:
        c.rect(p["x"], p["y"], p["w"], p["h"], PANEL)
        c.frame(p["x"], p["y"], p["w"], p["h"], (210, 213, 220), t=k(2))
        c.text(p["x"] + k(24), p["y"] + k(22), p["name"], scale=k(10), color=INK)
        c.text(p["x"] + k(140), p["y"] + k(30), "TITLE TEXT 28PX", scale=k(4), color=INK)
        c.text(p["x"] + k(140), p["y"] + k(70), "SUBTITLE 21PX %s" % p["name"], scale=k(3), color=MUTED)
        for li in range(4):
            c.text(p["x"] + k(24), p["y"] + k(120) + li * k(26),
                   "BODY 14PX ROW %d %s ABCDEFGH 0123456789" % (li + 1, p["name"]), scale=k(2), color=INK)
        b = p["button"]
        c.rect(b["x"], b["y"], b["w"], b["h"], ACCENT)
        c.text(b["x"] + k(20), b["y"] + (b["h"] - k(28)) // 2, "BUTTON " + p["name"], scale=k(4), color=(255, 255, 255))
    # pixel rulers (source coordinates)
    step = 256 if W >= 2000 else 160
    for x in range(0, W, step):
        c.rect(x, H - k(24), k(2), k(24), MUTED)
        c.text(x + k(6), H - k(22), "X%d" % x, scale=k(2), color=MUTED)
    for y in range(0, H, step):
        c.rect(W - k(24), y, k(24), k(2), MUTED)
        c.text(W - k(130), y + k(6), "Y%d" % y, scale=k(2), color=MUTED)
    return c


def cursor_script(lay, duration):
    """Waypoints (t, x, y, clicks) in source pixels. Generic enough for any duration >= 30."""
    P = {p["name"]: p for p in lay["panels"]}

    def btn(n, dx=0.5, dy=0.5):
        b = P[n]["button"]
        return b["x"] + b["w"] * dx, b["y"] + b["h"] * dy

    W = lay["panels"][2]["x"] + lay["panels"][2]["w"]
    H = lay["panels"][8]["y"] + lay["panels"][8]["h"]
    cx, cy = W * 0.55, H * 0.5
    f = duration / 50.0
    # (time, target, click?) ; times scaled to the duration
    plan = [
        (0.0, (cx, cy), False), (2.5, (cx, cy), False),
        (4.0, btn("P1"), True), (6.5, btn("P1"), False),
        (8.5, btn("P5"), True), (11.0, btn("P5", 0.3), False),
        (13.0, btn("P3"), True), (13.6, btn("P3", 0.55), True),  # double tap cluster
        (16.0, btn("P3", 0.6), False),
        (24.0, btn("P3", 0.62, 0.6), False),  # long idle: candidate for cut / speed-up
        (26.0, btn("P7"), True), (27.5, btn("P7", 0.3), True), (29.0, btn("P7", 0.7), True),
        (32.0, btn("P7", 0.7), False),
        (36.0, btn("P9"), True), (38.5, btn("P9"), False),
        (41.0, btn("P2"), True), (43.5, btn("P2"), False),
        (46.0, btn("P8"), True), (50.0, btn("P8"), False),
    ]
    return [(t * f, x, y, clk) for t, (x, y), clk in plan]


def ease(u):
    return u * u * (3 - 2 * u)


def position_at(script, t):
    for (t0, x0, y0, _), (t1, x1, y1, _) in zip(script, script[1:]):
        if t0 <= t <= t1:
            u = 0 if t1 == t0 else ease((t - t0) / (t1 - t0))
            return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
    return script[-1][1], script[-1][2]


def piecewise_expr(script, axis):
    """ffmpeg expression for the marker centre along one axis (smoothstep between waypoints)."""
    idx = 1 if axis == "x" else 2
    expr = "%.2f" % script[-1][idx]
    for (t0, *a), (t1, *b) in reversed(list(zip(script, script[1:]))):
        v0, v1 = a[idx - 1], b[idx - 1]
        if t1 <= t0:
            continue
        u = "((t-%.4f)/%.4f)" % (t0, t1 - t0)
        seg = "(%.2f+(%.2f)*(%s*%s*(3-2*%s)))" % (v0, v1 - v0, u, u, u)
        expr = "if(lt(t,%.4f),%s,%s)" % (t1, seg, expr)
    return expr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="output basename (without .mp4)")
    ap.add_argument("--width", type=int, default=2560)
    ap.add_argument("--height", type=int, default=1440)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--duration", type=float, default=50.0)
    ap.add_argument("--sample-ms", type=float, default=33.0, help="telemetry sample interval (OpenScreen uses ~33)")
    ap.add_argument("--no-marker", action="store_true", help="do not draw the magenta cursor marker into the video")
    a = ap.parse_args()
    if a.duration < 30:
        sys.exit("--duration must be >= 30")
    W, H, D = a.width, a.height, a.duration
    lay = layout(W, H)
    script = cursor_script(lay, D)
    clicks = [(t, x, y) for t, x, y, c in script if c]
    tmp = tempfile.mkdtemp(prefix="testfootage-")
    base = os.path.join(tmp, "base.ppm")
    draw_base(W, H, lay).write_ppm(base)
    s = lay["scale"]
    # per-second readout images
    tw, th = int(560 * s), int(100 * s)
    for sec in range(int(math.ceil(D)) + 1):
        c = Canvas(tw, th, (20, 22, 28))
        c.text(int(20 * s), int(22 * s), "SRC %02d:%02d" % (sec // 60, sec % 60), scale=max(1, int(8 * s)), color=(255, 230, 90))
        c.write_ppm(os.path.join(tmp, "ts%04d.ppm" % sec))
    ruler_x0, ruler_w = int(400 * s), W - int(400 * s) - int(620 * s)
    ruler_y = H - int(110 * s)
    filters = []
    # time ruler (static part is drawn by drawbox; labels every 5 s)
    filters.append("[0:v]drawbox=x=%d:y=%d:w=%d:h=%d:color=0xC8CCD6:t=fill" % (ruler_x0, ruler_y + int(18 * s), ruler_w, int(8 * s)))
    for i, (t, x, y) in enumerate(clicks):
        p = min(lay["panels"], key=lambda q: abs(q["button"]["x"] + q["button"]["w"] / 2 - x) + abs(q["button"]["y"] + q["button"]["h"] / 2 - y))
        b = p["button"]
        filters.append("drawbox=x=%d:y=%d:w=%d:h=%d:color=0x22C55E@0.85:t=fill:enable='between(t,%.3f,%.3f)'" % (b["x"], b["y"], b["w"], b["h"], t, t + 0.6))
    filters[-1] += "[bg]"
    chain = ",".join(filters)
    tick = "[bg][2:v]overlay=x='%d+t*%f':y=%d:eval=frame[a]" % (ruler_x0, ruler_w / D, ruler_y)
    stamp = "[a][1:v]overlay=x=%d:y=%d[b]" % (W - tw - int(150 * s), int(5 * s))
    graph = [chain, tick, stamp]
    last = "b"
    if not a.no_marker:
        m = int(28 * s)
        xe, ye = piecewise_expr(script, "x"), piecewise_expr(script, "y")
        graph.append("[b][3:v]overlay=x='%s-%d':y='%s-%d':eval=frame[c]" % (xe, m // 2, ye, m // 2))
        graph.append("[c][4:v]overlay=x='%s-%d':y='%s-%d':eval=frame[d]" % (xe, m // 2 - int(5 * s), ye, m // 2 - int(5 * s)))
        last = "d"
    graph.append("[%s]format=yuv420p[v]" % last)
    # audio: 1 kHz beep 120 ms at each click, silence elsewhere
    vol = "+".join("between(t,%.3f,%.3f)" % (t, t + 0.12) for t, _, _ in clicks) or "0"
    m = int(28 * s)
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y",
           "-loop", "1", "-framerate", str(a.fps), "-t", str(D), "-i", base,
           "-framerate", "1", "-i", os.path.join(tmp, "ts%04d.ppm"),
           "-f", "lavfi", "-i", "color=c=0xE11D48:s=%dx%d:r=%d" % (int(6 * s) or 2, int(44 * s), a.fps),
           "-f", "lavfi", "-i", "color=c=black:s=%dx%d:r=%d" % (m, m, a.fps),
           "-f", "lavfi", "-i", "color=c=0xFF00FF:s=%dx%d:r=%d" % (m - 2 * int(5 * s), m - 2 * int(5 * s), a.fps),
           "-f", "lavfi", "-i", "sine=f=1000:r=48000:d=%s" % D,
           "-filter_complex", ";".join(graph) + ";[5:a]volume='if(%s,0.6,0)':eval=frame[aout]" % vol,
           "-map", "[v]", "-map", "[aout]", "-t", str(D), "-r", str(a.fps),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-g", str(a.fps * 2),
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", a.out + ".mp4"]
    subprocess.run(cmd, check=True)
    # telemetry
    samples = []
    t = 0.0
    step = a.sample_ms / 1000.0
    click_set = sorted(t for t, _, _ in clicks)
    ci = 0
    pending_up = None
    while t <= D + 1e-6:
        x, y = position_at(script, t)
        kind = "move"
        if ci < len(click_set) and t >= click_set[ci]:
            kind, pending_up, ci = "click", click_set[ci] + 0.1, ci + 1
        elif pending_up is not None and t >= pending_up:
            kind, pending_up = "mouseup", None
        samples.append({"timeMs": round(t * 1000, 1), "cx": round(x / W, 5), "cy": round(y / H, 5),
                        "visible": True, "interactionType": kind, "cursorType": "arrow"})
        t += step
    with open(a.out + ".mp4.cursor.json", "w") as fh:
        json.dump({"version": 2, "provider": "none", "samples": samples, "assets": []}, fh)
    with open(a.out + ".plan.json", "w") as fh:
        json.dump({"width": W, "height": H, "fps": a.fps, "duration": D,
                   "panels": lay["panels"], "clicks": [{"t": round(t, 3), "x": round(x), "y": round(y)} for t, x, y in clicks],
                   "waypoints": [{"t": round(t, 3), "x": round(x), "y": round(y), "click": c} for t, x, y, c in script]},
                  fh, indent=1)
    print(a.out + ".mp4")


if __name__ == "__main__":
    main()
