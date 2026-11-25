#!/usr/bin/env python3
"""Propose cuts and speed-ups for a take and (with --write) put them in edit.json.

usage: propose-cuts.py (TAKE_VIDEO | --edit edit.json) [--write]
                       [--mode auto|idle|narration|silence] [--min-idle 2.0]
                       [--idle-action speed|cut] [--idle-speed 4] [--idle-pixels 25]
                       [--min-silence 0.7] [--pad 0.15] [--silence-db -35]

--mode idle       silent take: stretches where at most --idle-pixels pixels change from frame to
                  frame (measured on a 1280 px proxy) longer than --min-idle s are sped up (--idle-action speed, default
                  --idle-speed 4x) or cut, keeping 0.4 s of stillness either side. Idle stretches
                  at the very start or end of the take (before the demo begins, the click on
                  Stop) are always cut.
--mode narration  take with live narration: only pauses that are BOTH silent and idle are cut,
                  so on-screen action during a pause in speech is kept. Leading/trailing silence
                  is cut.
--mode silence    cut every pause in speech longer than --min-silence (threshold --silence-db
                  under the peak, --pad s of air kept). Use only when the screen does not matter.
--mode auto       (default) narration if the take has an audio track with sound, else idle.
With --edit, the edit file's main source is analysed; --write replaces its "cut" and "speed"
(a .bak copy is kept). Prints the proposal as JSON and a table of what would be removed on
stderr; it is a starting point: look at the frames and adjust.
"""
import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as av  # noqa: E402

EDGE = 0.4  # seconds of stillness kept either side of an idle stretch


def silences(path, rel_db, min_sil):
    """Pauses in speech, or None when the audio is (digital) silence."""
    peak = av.max_volume_db(path)
    if peak is None or peak < -60:
        return None
    return av.silence_ranges(path, max(-70.0, peak + rel_db), min_sil)


def freezes(path, info, min_px, min_idle):
    """Stretches of at least min_idle s in which no frame changes more than min_px pixels.

    Screen captures change locally (a caret, one typed character, a clock), so a mean-difference
    test such as freezedetect calls a busy UI frozen. Instead, on a 1280 px wide grey proxy at
    10 fps, count the pixels whose brightness changed by more than 40 levels since the previous
    frame (capture/encoder noise stays under that; measured: 0-3 px when frozen, 80+ px for a
    clock tick)."""
    W = 1280
    p = av.run([av.FFMPEG, "-nostdin", "-hide_banner", "-nostats", "-i", path, "-map", "0:v:0", "-vf",
                "fps=10,scale=%d:-2,format=gray,tblend=all_mode=difference,"
                "lut=y='if(gt(val\\,40)\\,255\\,0)',signalstats,metadata=print:key=lavfi.signalstats.YAVG" % W,
                "-f", "null", "-"])
    H = int(round(info["height"] * W / float(info["width"]) / 2) * 2)
    total = info["duration"]
    frames, t = [], None
    for line in p.stderr.splitlines():
        m = re.search(r"pts_time:([0-9.]+)", line)
        if m:
            t = float(m.group(1))
        m = re.search(r"YAVG=([0-9.]+)", line)
        if m and t is not None:
            frames.append((t, float(m.group(1)) / 255.0 * W * H))
    out, start = [], None
    for t, px in frames:
        if px <= min_px:
            if start is None:
                start = max(0.0, t - 0.1)
        else:
            if start is not None and t - start >= min_idle:
                out.append((start, t))
            start = None
    if start is not None and total - start >= min_idle:
        out.append((start, total))
    return out


def intersect(a_list, b_list):
    out = []
    for a0, a1 in a_list:
        for b0, b1 in b_list:
            lo, hi = max(a0, b0), min(a1, b1)
            if hi - lo > 0.05:
                out.append((lo, hi))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?")
    ap.add_argument("--edit")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--mode", choices=["auto", "idle", "narration", "silence"], default="auto")
    ap.add_argument("--min-silence", type=float, default=0.7)
    ap.add_argument("--pad", type=float, default=0.15)
    ap.add_argument("--silence-db", type=float, default=-35.0)
    ap.add_argument("--min-idle", type=float, default=2.0)
    ap.add_argument("--idle-action", choices=["speed", "cut"], default="speed")
    ap.add_argument("--idle-speed", type=float, default=4.0)
    ap.add_argument("--idle-pixels", type=float, default=25)
    a = ap.parse_args()
    av.need(av.FFMPEG, av.FFPROBE)
    edit = None
    if a.edit:
        with open(a.edit) as f:
            edit = json.load(f)
        if "keep" in edit:
            av.die("the edit file uses \"keep\"; propose-cuts writes \"cut\"/\"speed\" (single take only)")
        p = next(iter(edit["sources"].values()))
        a.input = p if os.path.isabs(p) else os.path.join(os.path.dirname(os.path.abspath(a.edit)), p)
    if not a.input:
        ap.error("give TAKE_VIDEO or --edit")
    if a.write and not edit:
        ap.error("--write needs --edit")
    info = av.media_info(a.input)
    total = info["duration"]
    mode = a.mode
    sil = None
    if mode in ("auto", "narration", "silence"):
        if info["audio_tracks"]:
            sil = silences(a.input, a.silence_db, a.min_silence)
        if sil is None:
            if mode != "auto":
                av.die("no audio (or only digital silence) in the take; use --mode idle")
            mode = "idle"
        elif mode == "auto":
            mode = "narration"

    cuts, speed, removed = [], [], []
    edge = lambda s, e: s <= 0.05 or e >= total - 0.05  # noqa: E731
    if mode in ("silence", "narration"):
        gaps = [(s + a.pad, e - a.pad) for s, e in sil if (e - a.pad) - (s + a.pad) > 0.1]
        gaps = [(0.0 if s <= a.pad + 0.01 else s, total if e >= total - a.pad - 0.01 else e) for s, e in gaps]
        if mode == "narration":
            fr = freezes(a.input, info, a.idle_pixels, a.min_silence)
            gaps = [g for g in gaps if edge(*g)] + [g for g in intersect(gaps, fr) if not edge(*g)]
            gaps = sorted(set(gaps))
        for s, e in gaps:
            cuts.append([round(s, 3), round(e, 3)])
            removed.append((s, e, "cut: silence" + ("" if mode == "silence" or edge(s, e) else " + idle")))
    else:
        for s, e in freezes(a.input, info, a.idle_pixels, a.min_idle):
            if edge(s, e):
                s2, e2 = (0.0 if s <= 0.05 else s + EDGE), (total if e >= total - 0.05 else e - EDGE)
                if e2 - s2 >= 0.3:
                    cuts.append([round(s2, 3), round(e2, 3)])
                    removed.append((s2, e2, "cut: idle at %s" % ("start" if s2 == 0 else "end")))
                continue
            s2, e2 = s + EDGE, e - EDGE
            if e2 - s2 < 0.5:
                continue
            if a.idle_action == "speed":
                speed.append({"from": round(s2, 3), "to": round(e2, 3), "x": a.idle_speed})
                removed.append((s2, e2, "sped up %gx: idle" % a.idle_speed))
            else:
                cuts.append([round(s2, 3), round(e2, 3)])
                removed.append((s2, e2, "cut: idle"))
    outdur = total - sum(e - s for s, e in cuts) - sum((p["to"] - p["from"]) * (1 - 1 / p["x"]) for p in speed)
    res = {"mode": mode, "source": a.input, "source_duration": round(total, 3), "cut": cuts, "speed": speed,
           "output_duration": round(outdur, 3)}
    sys.stderr.write("mode %s: %.1fs -> %.1fs\n" % (mode, total, outdur))
    for s, e, why in removed:
        sys.stderr.write("  %7.2f - %7.2f  (%5.2fs)  %s\n" % (s, e, e - s, why))
    if a.write:
        shutil.copyfile(a.edit, a.edit + ".bak")
        edit["cut"], edit["speed"] = cuts, speed
        with open(a.edit, "w") as f:
            json.dump(edit, f, indent=2)
        sys.stderr.write("wrote cut/speed into %s\n" % a.edit)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
