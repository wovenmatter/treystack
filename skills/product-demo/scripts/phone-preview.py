#!/usr/bin/env python3
"""Show frames the way a phone shows an inline 16:9 video in a social feed, to judge
whether on-screen text is readable.

A phone feed plays a widescreen video about 310 pt wide. At 2x density that is 620 px, at
3x 930 px. This script scales each frame down to that width (high-quality downscale, the
way the player does) and stacks the results in a phone-width column with timestamps, so an
agent or a person can look at the PNG at 100% and ask: "can I read the UI text?".

Default density is 2x (620 px): a slightly pessimistic stand-in for what a viewer resolves
at arm's length. Use --density 3 for a best-case view and --density 1 for a harsh test.

Usage:
  phone-preview.py VIDEO --at 5,13.8,28 [-o phone.png] [--width-pt 310] [--density 2]
  phone-preview.py --image frame.png [-o phone.png]
  phone-preview.py VIDEO --at 5 --text-px 14 --source-width 2560 --zoom 3
        # also prints the estimated on-phone cap height of 14 px source text at zoom x3

Rule of thumb printed with --text-px (calibrated by eye on synthetic UI text, crisp font):
cap height under ~4.5 pt on the phone is unreadable, 4.5-6 pt is small but readable, 6 pt
and up is comfortable. Anti-aliased real UI fonts need the upper end. Always look at the PNG.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Canvas, ensure_parent, ffprobe_info, grab_frame, max_zoom, upscale_factor  # noqa: E402
from frames import parse_time  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?")
    ap.add_argument("--at", help="comma-separated timestamps in seconds")
    ap.add_argument("--image", action="append", help="use an image instead of a video frame (repeatable)")
    ap.add_argument("-o", "--out", default="phone-preview.png")
    ap.add_argument("--width-pt", type=float, default=310.0, help="inline player width in points (default 310)")
    ap.add_argument("--density", type=float, default=2.0, help="pixels per point (default 2)")
    ap.add_argument("--text-px", type=float, help="cap height of the smallest important text, in source px")
    ap.add_argument("--source-width", type=float, help="source capture width in px (for --text-px)")
    ap.add_argument("--zoom", type=float, default=1.0, help="zoom scale applied at that moment (for --text-px)")
    ap.add_argument("--frame-share", type=float, default=1.0,
                    help="share of the output width the recording occupies when not zoomed (padding), e.g. 0.9")
    a = ap.parse_args()
    ensure_parent(a.out)

    pw = int(round(a.width_pt * a.density))
    frames = []
    if a.image:
        for p in a.image:
            frames.append((os.path.basename(p), grab_frame(p, 0, pw)))
    elif a.video and a.at:
        ffprobe_info(a.video)
        for s in a.at.split(","):
            t = parse_time(s)
            frames.append(("%.2fs" % t, grab_frame(a.video, t, pw)))
    else:
        ap.error("give VIDEO --at T,... or --image FILE")

    margin = int(16 * a.density)
    gap = int(30 * a.density)
    col_w = pw + 2 * margin
    label_scale = max(1, int(a.density))
    total_h = margin + sum(f.h + gap for _, f in frames)
    sheet = Canvas(col_w, total_h, (0, 0, 0))
    y = margin
    for name, f in frames:
        sheet.text(margin, y - int(12 * a.density) + 2, name, scale=label_scale, color=(150, 150, 150))
        sheet.paste(f, margin, y)
        y += f.h + gap
    sheet.write_png(a.out)
    print(a.out)
    print("player: %.0f pt wide at %.0fx = %d px; column %d px wide" % (a.width_pt, a.density, pw, col_w))
    if a.text_px and a.source_width:
        cap = max_zoom(a.source_width * upscale_factor(a.source_width))  # narrow takes zoom from a 2x copy
        if a.zoom > cap + 0.01:
            print("note: OpenScreen renders at most x%.2f for a %d px capture; estimating at that zoom"
                  % (cap, a.source_width))
            a.zoom = cap
        pt = a.text_px * a.zoom * a.frame_share * a.width_pt / a.source_width
        verdict = "unreadable" if pt < 4.5 else ("small but readable" if pt < 6 else "comfortable")
        print("estimated on-phone cap height: %.1f pt (%s); 1 source px = %.3f pt" % (
            pt, verdict, a.zoom * a.frame_share * a.width_pt / a.source_width))
        if pt < 6:
            need = 6 * a.source_width / (a.text_px * a.frame_share * a.width_pt)
            print("zoom needed for ~6 pt: x%.2f (shows ~%d px of the source width)%s" % (
                need, a.source_width / need, "; beyond what OpenScreen renders for this capture"
                if need > cap + 0.01 else ""))


if __name__ == "__main__":
    main()
