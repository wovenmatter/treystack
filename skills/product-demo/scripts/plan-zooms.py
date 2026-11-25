#!/usr/bin/env python3
"""Propose zoom regions from cursor telemetry, sized so UI text stays readable on a phone.

Reads OpenScreen cursor telemetry (<video>.cursor.json: {"samples": [{timeMs, cx, cy,
interactionType}]}, cx/cy in 0..1 of the captured frame) and plans one zoom per cluster
of clicks:

  * clicks closer than --gap seconds that fit in one view share a zoom;
  * the zoom holds from --lead s before the first click (OpenScreen ramps in BEFORE a
    zoom's start, so the view is already settled at the click) to --tail s after the last,
    and keeps holding while the cursor dwells near the cluster (typing, reading);
  * the view is --width-frac of the capture width (default 0.33, i.e. ~640 px of a 1920
    capture, ~x3) or wider if the cluster needs it (never wider than --max-frac);
  * the centre is clamped so the view stays inside the frame;
  * clicks in the first --skip-start s and the last --skip-end s are ignored (the click
    that stopped the recording).

Prints the zooms as JSON in the edit-file format (paste into "zooms", or use --write to
replace the "zooms" of an edit file), and a readable table on stderr.

Usage:
  plan-zooms.py (--edit edit.json [--write] [--source NAME] | VIDEO) [--width-frac 0.33]
                [--gap 2.5] [--follow]
With --edit, the edit file's source is planned, clicks inside removed footage are dropped,
and --write stores the result in it (a .bak copy is kept). A bare VIDEO is planned for the
polished look.
"""

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402
from edit import Spec  # noqa: E402


def plan(samples, W, H, dur, a, kept=None, box=None):
    """Zooms for a W x H capture; box = (x, y, w, h) is the part the frame shows (the crop)."""
    bx, by, bw, bh = box or (0, 0, W, H)

    def inside(s):
        t, px, py = s["t"], s["x"] * W, s["y"] * H
        return (bx <= px <= bx + bw and by <= py <= by + bh
                and (kept is None or any(lo <= t <= hi for lo, hi in kept)))

    # clicks outside the captured area are clamped to its edge and flagged visible=false
    clicks = [s for s in samples if s["k"] in c.CLICK_KINDS and s["v"] and a.skip_start <= s["t"] <= dur - a.skip_end and inside(s)]
    # never plan deeper than OpenScreen renders: it enlarges a capture at most 2x, and a narrow
    # capture is zoomed from a 2x upscaled working copy (edit.py builds it)
    vw_min = min(bw, max(a.width_frac * bw, a.min_view))
    vw_max = max(a.max_frac * bw, vw_min)
    clusters = []
    for k in clicks:
        px, py = k["x"] * W, k["y"] * H
        if clusters:
            cl = clusters[-1]
            nx0, nx1 = min(cl["x0"], px), max(cl["x1"], px)
            ny0, ny1 = min(cl["y0"], py), max(cl["y1"], py)
            need_w = max(nx1 - nx0, (ny1 - ny0) * bw / bh) * (1 + 2 * a.margin)
            if k["t"] - cl["t1"] <= a.gap and need_w <= vw_max:
                cl.update(x0=nx0, x1=nx1, y0=ny0, y1=ny1, t1=k["t"], n=cl["n"] + 1)
                continue
        clusters.append({"t0": k["t"], "t1": k["t"], "x0": px, "x1": px, "y0": py, "y1": py, "n": 1})

    zooms = []
    for cl in clusters:
        cx, cy = (cl["x0"] + cl["x1"]) / 2, (cl["y0"] + cl["y1"]) / 2
        need = max(cl["x1"] - cl["x0"], (cl["y1"] - cl["y0"]) * bw / bh) * (1 + 2 * a.margin)
        vw = min(vw_max, max(vw_min, need))
        vh = vw * bh / bw
        cx = min(max(cx, bx + vw / 2), bx + bw - vw / 2)
        cy = min(max(cy, by + vh / 2), by + bh - vh / 2)
        start = max(a.min_start, cl["t0"] - a.lead)
        end = cl["t1"] + a.tail
        # keep holding while the cursor stays near the cluster (dwell: typing, reading)
        # the cursor "leaves" when it exits the zoomed view (shrunk by the dwell radius)
        rx, ry = max(0.0, vw / 2 - a.dwell_radius * bw), max(0.0, vh / 2 - a.dwell_radius * bw)
        left_at = cl["t1"] + a.max_hold
        for s in samples:
            if s["t"] <= cl["t1"]:
                continue
            if s["t"] > cl["t1"] + a.max_hold:
                break
            if abs(s["x"] * W - cx) > rx or abs(s["y"] * H - cy) > ry:
                left_at = s["t"]
                break
        end = max(end, left_at)
        end = max(min(end, cl["t1"] + a.max_hold, dur - a.skip_end), start + a.min_hold)
        # the last kept footage must leave OpenScreen about 1.2 s to zoom back out; this limit
        # comes last so nothing above can push the hold past it
        last = max([min(hi, dur) for lo, hi in kept if lo < dur] or [dur]) if kept else dur
        end = min(end, last - 1.2)
        if end - start < 0.5:
            sys.stderr.write("skipped the click(s) at %.2fs: too close to the end to zoom in and out\n" % cl["t0"])
            continue
        zooms.append({"from": round(start, 2), "to": round(end, 2), "center": [round(cx), round(cy)],
                      "width": round(vw), "clicks": cl["n"]})
    # resolve overlaps: trim the earlier zoom so the next starts cleanly (OpenScreen pans
    # between zooms closer than 1.5 s instead of zooming out and back in)
    for z0, z1 in zip(zooms, zooms[1:]):
        if z0["to"] > z1["from"] - 0.1:
            z0["to"] = round(max(z0["from"] + 0.5, z1["from"] - 0.1), 2)
    return zooms


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?", help="video with telemetry at <video>.cursor.json (instead of --edit)")
    ap.add_argument("--width-frac", type=float, default=0.33, help="view width as share of capture width (default 0.33)")
    ap.add_argument("--max-frac", type=float, default=0.6, help="widest view a cluster may need (default 0.6)")
    ap.add_argument("--margin", type=float, default=0.12, help="margin around a cluster, share of its size")
    ap.add_argument("--gap", type=float, default=2.5, help="max seconds between clicks of one zoom")
    ap.add_argument("--lead", type=float, default=0.4, help="hold starts this long before the first click")
    ap.add_argument("--tail", type=float, default=1.2, help="hold lasts this long after the last click")
    ap.add_argument("--min-hold", type=float, default=1.5)
    ap.add_argument("--max-hold", type=float, default=6.0, help="longest hold after the last click (dwell)")
    ap.add_argument("--dwell-radius", type=float, default=0.04, help="cursor within this share of width = dwelling")
    ap.add_argument("--min-start", type=float, default=1.2, help="no zoom hold before this time (ramp needs room)")
    ap.add_argument("--skip-start", type=float, default=0.5)
    ap.add_argument("--skip-end", type=float, default=1.0)
    ap.add_argument("--follow", action="store_true", help="mark zooms to follow the cursor (focusMode auto)")
    ap.add_argument("--edit", help="edit file: plan its source, drop clicks in removed footage")
    ap.add_argument("--source", help="source name in the edit file (default: first)")
    ap.add_argument("--write", action="store_true", help="replace the edit file's zooms with the plan")
    a = ap.parse_args()

    # deepest zoom that renders: the unzoomed view is the crop if any; narrow captures zoom
    # from edit.py's 2x working copy; padding comes from the look (polished 10 by default)
    if a.edit:
        spec = Spec(a.edit)
        src = a.source or spec.default
        if src not in spec.sources:
            sys.exit("no source %r in %s" % (src, a.edit))
        S = spec.sources[src]
        video, W, H, dur = S["path"], S["width"], S["height"], S["duration"]
        kept = [(lo, hi) for name, lo, hi in spec.keep if name == src]
        box = spec.crop_box(src)
        f = c.upscale_factor(W)
        cap = spec.cap(src, f)
        a.min_view = spec.view_size(src)[0] / cap
    elif a.video:
        spec, kept, video = None, None, a.video
        W, H, dur, _ = c.ffprobe_info(video)
        box = (0, 0, W, H)
        f = c.upscale_factor(W)
        cap = c.max_zoom(W * f, H * f, 10)
        a.min_view = W / cap
    else:
        sys.exit("give --edit edit.json or a VIDEO")
    tel = video + ".cursor.json"
    if not os.path.exists(tel):
        sys.exit("no telemetry: %s" % tel)
    samples = c.load_samples(tel)
    zooms = plan(samples, W, H, dur, a, kept, box)
    for z in zooms:
        if a.follow:
            z["follow"] = True
        if spec and len(spec.sources) > 1:
            z["source"] = src
    sys.stderr.write("capture %dx%d, %.1fs, %d clicks -> %d zoom(s)\n" % (
        W, H, dur, sum(1 for s in samples if s["k"] in c.CLICK_KINDS), len(zooms)))
    for i, z in enumerate(zooms):
        sys.stderr.write("  %d. %6.2f-%6.2fs  x%.2f  view %d px (%d%%)  centre %s  %d click(s)\n" % (
            i + 1, z["from"], z["to"], box[2] / z["width"], z["width"], 100 * z["width"] / box[2], z["center"], z["clicks"]))
    if zooms and box[2] * a.width_frac < a.min_view:
        sys.stderr.write("note: zooms on a %d px capture stop at x%.2f (OpenScreen enlarges at most 2x%s), so the"
                         " views are wider than --width-frac asks\n"
                         % (W, cap, ", even from the 2x working copy" if f > 1 else ""))
    out = [{k: v for k, v in z.items() if k != "clicks"} for z in zooms]
    if a.write:
        if not a.edit:
            sys.exit("--write needs --edit")
        shutil.copyfile(a.edit, a.edit + ".bak")
        # replace this source's zooms only; other sources keep theirs
        spec.raw["zooms"] = [z for z in spec.raw.get("zooms") or [] if spec.src(z) != src] + out
        with open(a.edit, "w") as fh:
            json.dump(spec.raw, fh, indent=2)
        sys.stderr.write("wrote %d zoom(s) into %s\n" % (len(out), a.edit))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
