#!/usr/bin/env python3
"""The demo's edit file (edit.json) and the OpenScreen project built from it.

edit.json is the single source of truth for a demo. The .openscreen project is a build
artifact: edit the JSON, rebuild, re-export. Full format: references/edit-format.md.

usage:
  edit.py new TAKE [TAKE ...] [-o DEMO_DIR/edit.json] [--look polished|plain] [--aspect 16:9]
        Starter edit file that keeps every take whole. TAKE is a take folder
        (DEMO_DIR/takes/<take>), its take.openscreen, or a video file.
  edit.py build edit.json [-o project.openscreen]
        Compile to an OpenScreen project (schemaVersion-4 document; default edit.openscreen
        next to edit.json).
  edit.py summary edit.json
        Timeline, output length, zoom legibility verdicts and warnings.

Times are SECONDS IN THE SOURCE TAKE; boxes and points are SOURCE PIXELS (of the take video,
which for a window capture includes the window's title bar).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

DEPTH_SCALES = {1: 1.25, 2: 1.5, 3: 1.8, 4: 2.2, 5: 3.5, 6: 5.0}

LOOKS = {
    # window on a background, rounded corners, shadow, smoothed enlarged cursor, zooms
    "polished": {"background": "/wallpapers/wallpaper11.jpg", "padding": 10, "radius": 24, "shadow": 0.6,
                 "cursor_size": 3.0, "cursor_smoothing": 0.3, "show_cursor": True, "motion_blur": 0.2,
                 "click_bounce": 1.0},
    # straight capture: edge to edge, no framing, no zooms
    "plain": {"background": "#000000", "padding": 0, "radius": 0, "shadow": 0.0,
              "cursor_size": 1.5, "cursor_smoothing": 0.0, "show_cursor": True, "motion_blur": 0.0,
              "click_bounce": 0.0},
}

# Fields edit.py understands; anything else is a typo and is refused rather than silently ignored.
FIELDS = {
    "": {"sources", "look", "aspect", "cut", "keep", "speed", "zooms", "blur", "crop", "captions", "text",
         "style", "allow_zooms_in_plain"},
    "zooms": {"from", "to", "center", "width", "scale", "follow", "hide_cursor", "source"},
    "speed": {"from", "to", "x", "source"},
    "blur": {"from", "to", "box", "type", "shape", "intensity", "block", "source"},
    "text": {"from", "to", "text", "x", "y", "w", "h", "size", "color", "bg"},
    "captions": {"words", "style", "source", "language", "pause"},
    "style": set(LOOKS["polished"]) | {"fill"},
}


def check_fields(raw):
    import difflib

    def bad(where, key, allowed):
        near = difflib.get_close_matches(key, sorted(allowed), 1)
        die('unknown field "%s"%s%s; allowed: %s (see references/edit-format.md)'
            % (key, " in " + where if where else "", ' (did you mean "%s"?)' % near[0] if near else "",
               ", ".join(sorted(allowed))))

    for k in raw:
        if k not in FIELDS[""]:
            bad("", k, FIELDS[""])
    for sect in ("captions", "style"):
        for k in (raw.get(sect) or {}) if isinstance(raw.get(sect), dict) else ():
            if k not in FIELDS[sect]:
                bad('"%s"' % sect, k, FIELDS[sect])
    for sect in ("zooms", "speed", "blur", "text"):
        for i, item in enumerate(raw.get(sect) or []):
            if not isinstance(item, dict):
                die('"%s" item %d must be an object (see references/edit-format.md)' % (sect, i + 1))
            for k in item:
                if k not in FIELDS[sect]:
                    bad('"%s" item %d' % (sect, i + 1), k, FIELDS[sect])
            missing = [k for k in (("from", "to", "x") if sect == "speed" else ("box",) if sect == "blur"
                                   else ("from", "to", "text") if sect == "text" else ("from", "to"))
                       if k not in item]
            if missing:
                die('"%s" item %d is missing %s' % (sect, i + 1, ", ".join('"%s"' % m for m in missing)))


def die(msg):
    c.die(msg, 2)


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def ms(sec):
    return int(round(sec * 1000))


def fmt(sec):
    sign = "-" if sec < 0 else ""
    sec = abs(sec)
    return "%s%d:%05.2f" % (sign, int(sec // 60), sec % 60)


def resolve_take(path):
    """A take folder, a .openscreen project or a video -> the video path."""
    path = os.path.abspath(os.path.expanduser(path))
    if os.path.isdir(path):
        path = os.path.join(path, "take.openscreen")
    if path.endswith(".openscreen"):
        if not os.path.exists(path):
            die("no take.openscreen in %s (run record-stop.py first?)" % os.path.dirname(path))
        d = load_json(path)
        v = (d.get("media") or {}).get("screenVideoPath")
        if not v and d.get("assets"):
            v = d["assets"][0].get("originalPath")
        if not v:
            die("cannot find the video in %s" % path)
        if not os.path.exists(v):  # moved folder: fall back to a same-named file beside it
            v = os.path.join(os.path.dirname(path), os.path.basename(v))
        return v
    return path


def load_words(spec_dir, src):
    """Word timings: transcribe.py output {"words":[{word,start,end}]} or [{text,start,end}]."""
    data = load_json(os.path.join(spec_dir, src)) if isinstance(src, str) else src
    if isinstance(data, dict):
        data = data.get("words", [])
    out = []
    for w in data or []:
        text = str(w.get("text", w.get("word", ""))).strip()
        if text:
            out.append({"start": float(w["start"]), "end": float(w["end"]), "text": text})
    return out


class Spec:
    """A parsed, validated edit file with probed sources."""

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.dir = os.path.dirname(self.path)
        try:
            self.raw = r = load_json(path)
        except ValueError as e:
            die("%s is not valid JSON: %s" % (path, e))
        check_fields(r)
        if not isinstance(r.get("sources"), dict) or not r["sources"]:
            die('"sources" must be an object of name -> video path')
        self.sources = {}
        for name, p in r["sources"].items():
            ap = p if os.path.isabs(p) else os.path.normpath(os.path.join(self.dir, p))
            if not os.path.exists(ap):
                die("source %r not found: %s" % (name, ap))
            try:
                info = c.media_info(ap)
            except RuntimeError as e:
                die(str(e))
            if not info["width"]:
                die("no video stream in %s" % ap)
            self.sources[name] = dict(info, path=ap)
        self.default = next(iter(self.sources))
        self.look = r.get("look", "polished")
        if self.look not in LOOKS:
            die('"look" must be one of %s' % ", ".join(LOOKS))
        self.aspect = r.get("aspect", "16:9")
        self.style = dict(LOOKS[self.look])
        self.style.update(r.get("style") or {})
        self.keep = self._keep_ranges()
        self._check_ranges()

    def src(self, item):
        name = item.get("source", self.default) if isinstance(item, dict) else self.default
        if name not in self.sources:
            die("unknown source %r" % name)
        return name

    def _keep_ranges(self):
        r = self.raw
        if r.get("keep") and r.get("cut"):
            die('use "keep" or "cut", not both')
        out = []
        if r.get("keep"):
            for k in r["keep"]:
                if (not isinstance(k, list) or len(k) not in (2, 3)
                        or not all(isinstance(v, (int, float)) for v in k[-2:])):
                    die('"keep" items are [from, to] or ["source", from, to], not %s' % json.dumps(k))
                name, a, b = k if len(k) == 3 else (self.default, k[0], k[1])
                if name not in self.sources:
                    die("keep: unknown source %r" % name)
                out.append((name, float(a), float(b)))
        elif len(self.sources) > 1:
            if r.get("cut"):
                die('"cut" works with a single source; use "keep" for several')
            return [(n, 0.0, s["duration"]) for n, s in self.sources.items()]
        else:
            name = self.default
            dur = self.sources[name]["duration"]
            t = 0.0
            for k in r.get("cut") or []:
                if not isinstance(k, list) or len(k) != 2 or not float(k[0]) < float(k[1]):
                    die('"cut" items are [from, to] with from before to, not %s' % json.dumps(k))
                if float(k[0]) >= dur:
                    die('cut %s starts after the end of the take (%.3f s)' % (json.dumps(k), dur))
            for a, b in sorted((float(a), float(b)) for a, b in (r.get("cut") or [])):
                a, b = max(0.0, a), min(dur, b)
                if a > t:
                    out.append((name, t, a))
                t = max(t, b)
            if t < dur:
                out.append((name, t, dur))
        for name, a, b in out:
            if not (0 <= a < b <= self.sources[name]["duration"] + 0.05):
                die("range %s [%.3f, %.3f] is outside 0..%.3f or empty" % (name, a, b, self.sources[name]["duration"]))
        return [(n, a, min(b, self.sources[n]["duration"])) for n, a, b in out]

    def _check_ranges(self):
        r, seen = self.raw, []
        for sp in r.get("speed") or []:
            n, a, b, x = self.src(sp), float(sp["from"]), float(sp["to"]), float(sp["x"])
            if not 0.25 <= x <= 16:
                die('speed "x" must be between 0.25 and 16 (OpenScreen\'s range), not %g' % x)
            if not a < b:
                die('speed %g-%g: "from" must be before "to"' % (a, b))
            if any(m == n and a < hi and lo < b for m, lo, hi in seen):
                die("speed regions overlap at %g-%g; give each stretch one speed" % (a, b))
            seen.append((n, a, b))
        for n, box in (r.get("crop") or {}).items():
            if n not in self.sources:
                die('crop: unknown source %r (sources: %s)' % (n, ", ".join(self.sources)))
            S = self.sources[n]
            if not (isinstance(box, list) and len(box) == 4 and box[0] >= 0 and box[1] >= 0 and box[2] > 0
                    and box[3] > 0 and box[0] + box[2] <= S["width"] and box[1] + box[3] <= S["height"]):
                die('crop %r must be [x, y, w, h] inside the %dx%d take, not %s'
                    % (n, S["width"], S["height"], json.dumps(box)))
        if r.get("captions"):
            self.src(r["captions"])

    def crop_box(self, name):
        """(x, y, w, h) in capture px of what the frame shows unzoomed: the crop, else the whole take."""
        S = self.sources[name]
        return tuple((self.raw.get("crop") or {}).get(name) or (0, 0, S["width"], S["height"]))

    def clips(self):
        """[(name, srcA, srcB, timelineA)] on the raw (pre-speed) timeline."""
        t, res = 0.0, []
        for name, a, b in self.keep:
            res.append((name, a, b, t))
            t += b - a
        return res

    def map_range(self, name, a, b):
        """Source range -> raw-timeline (start, end) pieces, one per clip it overlaps."""
        pieces = []
        for cname, ca, cb, t0 in self.clips():
            lo, hi = max(a, ca), min(b, cb)
            if cname == name and hi > lo:
                pieces.append((t0 + lo - ca, t0 + hi - ca))
        return pieces

    def output_duration(self):
        total = sum(b - a for _, a, b in self.keep)
        for sp in self.raw.get("speed") or []:
            x = float(sp["x"])
            for lo, hi in self.map_range(self.src(sp), float(sp["from"]), float(sp["to"])):
                total -= (hi - lo) - (hi - lo) / x
        return total

    def view_size(self, name):
        """(width, height) in capture px of what the frame shows unzoomed (the crop if any)."""
        _, _, w, h = self.crop_box(name)
        return float(w), float(h)

    def cap(self, name, k=1):
        """Deepest zoom OpenScreen renders for this source, from a k-times upscaled copy."""
        w, h = self.view_size(name)
        return c.max_zoom(w * k, h * k, float(self.style["padding"]))

    def zooms_on(self):
        return bool(self.raw.get("zooms")) and (self.look != "plain" or bool(self.raw.get("allow_zooms_in_plain")))

    def upscale(self, name):
        """2 when this source's zooms render from a 2x upscaled working copy (they ask deeper than
        OpenScreen's cap for the capture itself), else 1. Plain look and zoom-free edits pay nothing."""
        k = c.upscale_factor(self.sources[name]["width"])
        if k == 1 or not self.zooms_on() or self.aspect != "16:9":
            return 1
        cap = self.cap(name)
        return k if any(self.zoom_scale(z) > cap + 0.01 for z in self.raw["zooms"] if self.src(z) == name) else 1

    def max_zoom(self, name):
        """Deepest zoom that will really render for this source (after any upscaling)."""
        return self.cap(name, self.upscale(name))

    def zoom_scale(self, z):
        vw = self.view_size(self.src(z))[0]
        scale = float(z["scale"]) if "scale" in z else (vw / float(z["width"]) if "width" in z else 2.2)
        return max(1.0, min(5.0, scale))


def build_document(spec):
    """The OpenScreen project as a schemaVersion-4 document (the draft OpenScreen's own v2
    migration produces; the app upgrades and validates it on load). The simple v2 project that
    `record` writes loses zoom customScale and hideCursor and cannot carry captions or several
    clips."""
    now = "2026-01-01T00:00:00.000Z"
    names = list(spec.sources)
    aid = {n: "asset_%d" % (i + 1) for i, n in enumerate(names)}
    assets = []
    for n in names:
        S, k = spec.sources[n], spec.upscale(n)
        # every position in the document is normalised (focus, crop, blur), so only the video
        # file and its size change when a source renders from its upscaled working copy
        path = c.working_copy(S["path"]) if k > 1 else S["path"]
        assets.append({"id": aid[n], "kind": "video", "label": os.path.basename(path),
                       "originalPath": path, "durationSec": round(S["duration"], 3),
                       "video": {"codec": S["codec"], "width": S["width"] * k, "height": S["height"] * k,
                                 "fps": S["fps"]},
                       "cameraTrack": None})
    crops = spec.raw.get("crop") or {}
    clips = []
    for i, (n, a, b, t0) in enumerate(spec.clips()):
        cl = {"id": "clip_%d" % (i + 1), "assetId": aid[n], "sourceStartSec": round(a, 3), "sourceEndSec": round(b, 3),
              "timelineStartSec": round(t0, 3), "timelineEndSec": round(t0 + b - a, 3), "wordRefs": [],
              "origin": "user", "reason": ""}
        if n in crops:
            x, y, w, h = crops[n]
            S = spec.sources[n]
            cl["cropRegion"] = {"x": x / S["width"], "y": y / S["height"], "width": w / S["width"], "height": h / S["height"]}
        clips.append(cl)

    zooms = []
    if spec.raw.get("zooms") and not spec.zooms_on():
        sys.stderr.write("note: look=plain ignores %d zoom(s)\n" % len(spec.raw["zooms"]))
    else:
        for i, z in enumerate(spec.raw.get("zooms") or []):
            n = spec.src(z)
            # OpenScreen reads a zoom's focus in the CROPPED footage, like annotations below
            ox, oy, fw, fh = spec.crop_box(n)
            cx, cy = z.get("center", [ox + fw / 2.0, oy + fh / 2.0])
            scale = spec.zoom_scale(z)
            depth = min(DEPTH_SCALES, key=lambda d: abs(DEPTH_SCALES[d] - scale))
            for j, (lo, hi) in enumerate(spec.map_range(n, float(z["from"]), float(z["to"]))):
                r = {"id": "zoom-%d-%d" % (i + 1, j + 1), "startMs": ms(lo), "endMs": ms(hi), "depth": depth,
                     "focus": {"cx": min(1, max(0, (cx - ox) / fw)), "cy": min(1, max(0, (cy - oy) / fh))},
                     "focusMode": "auto" if z.get("follow") else "manual", "source": "manual"}
                if abs(DEPTH_SCALES[depth] - scale) > 1e-6:
                    r["customScale"] = round(scale, 2)
                if z.get("hide_cursor"):
                    r["hideCursor"] = True
                zooms.append(r)

    annotations = []
    for i, bl in enumerate(spec.raw.get("blur") or []):
        n = spec.src(bl)
        S = spec.sources[n]
        x, y, w, h = bl["box"]
        # OpenScreen places annotations in % of the CROPPED footage (verified on a real take)
        ox, oy, fw, fh = spec.crop_box(n)
        x, y = x - ox, y - oy
        for j, (lo, hi) in enumerate(spec.map_range(n, float(bl.get("from", 0)), float(bl.get("to", S["duration"])))):
            annotations.append({
                "id": "blur-%d-%d" % (i + 1, j + 1), "startMs": ms(lo), "endMs": ms(hi), "type": "blur", "content": "",
                "position": {"x": 100.0 * x / fw, "y": 100.0 * y / fh},
                "size": {"width": 100.0 * w / fw, "height": 100.0 * h / fh},
                "style": {}, "zIndex": 10 + i,
                "blurData": {"type": bl.get("type", "mosaic"), "shape": bl.get("shape", "rectangle"),
                             "color": "white", "intensity": bl.get("intensity", 16), "blockSize": bl.get("block", 16)}})
    for i, tx in enumerate(spec.raw.get("text") or []):
        # frame-space text card; times on the raw output timeline (before speed changes)
        annotations.append({
            "id": "text-%d" % (i + 1), "startMs": ms(tx["from"]), "endMs": ms(tx["to"]), "type": "text",
            "content": tx["text"], "textContent": tx["text"], "space": "frame",
            "position": {"x": tx.get("x", 10), "y": tx.get("y", 8)}, "size": {"width": tx.get("w", 80), "height": tx.get("h", 12)},
            "style": {"color": tx.get("color", "#ffffff"), "backgroundColor": tx.get("bg", "#000000"),
                      "fontSize": tx.get("size", 56), "fontWeight": "bold"}, "zIndex": 50 + i})

    speed = []
    for i, sp in enumerate(spec.raw.get("speed") or []):
        for j, (lo, hi) in enumerate(spec.map_range(spec.src(sp), float(sp["from"]), float(sp["to"]))):
            speed.append({"id": "speed-%d-%d" % (i + 1, j + 1), "startMs": ms(lo), "endMs": ms(hi), "speed": float(sp["x"])})

    st = spec.style
    editor = {
        "aspectRatio": spec.aspect, "wallpaper": st["background"],
        "padding": st["padding"], "borderRadius": st["radius"], "shadowIntensity": st["shadow"],
        "motionBlurAmount": st["motion_blur"], "cursorShow": bool(st["show_cursor"]),
        "cursorSize": st["cursor_size"], "cursorSmoothing": st["cursor_smoothing"],
        "cursorClickBounce": st.get("click_bounce", 1.0), "speedRegions": speed,
        "exportQuality": "good", "exportFormat": "mp4",
    }
    if st.get("fill") or (spec.aspect not in ("16:9", "auto") and st.get("fill") is not False):
        editor["formatFollowCursor"] = True

    transcripts = []
    cap = spec.raw.get("captions")
    if cap:
        n = spec.src(cap)
        tr = {"assetId": aid[n], "language": cap.get("language", "en"), "segments": [], "words": []}
        seg, seg_i = None, 0
        for k, w in enumerate(load_words(spec.dir, cap.get("words"))):
            a, b = w["start"], max(w["start"], w["end"])
            if seg is None or a - seg["endSec"] > float(cap.get("pause", 0.6)):
                seg_i += 1
                seg = {"id": "seg_%d" % seg_i, "kind": "speech", "startSec": a, "endSec": b, "text": "", "wordIds": []}
                tr["segments"].append(seg)
            wid = "w_%d" % (k + 1)
            tr["words"].append({"id": wid, "segmentId": seg["id"], "startSec": round(a, 3), "endSec": round(b, 3), "text": w["text"]})
            seg["wordIds"].append(wid)
            seg["endSec"] = round(max(seg["endSec"], b), 3)
            seg["text"] = (seg["text"] + " " + w["text"]).strip()
        transcripts.append(tr)
        # OpenScreen's default caption size is small in a phone feed; 64 px at 1080 reads well
        editor["captions"] = dict({"enabled": True, "fontSize": 64}, **(cap.get("style") or {}))

    return {
        "schemaVersion": 4,
        "project": {"id": "proj_demo", "title": os.path.basename(spec.dir) or "Demo",
                    "createdAt": now, "updatedAt": now, "primaryAssetId": aid[spec.default]},
        "assets": assets, "transcript": None, "transcripts": transcripts,
        "timeline": {"clips": clips, "gaps": [], "trimRanges": [], "muteRanges": [], "speedRanges": [], "captionRanges": []},
        "annotations": annotations, "zoomRanges": zooms, "legacyEditor": editor,
    }


def summarize_spec(spec):
    L = ["Edit file: %s" % spec.path]
    for n, s in spec.sources.items():
        L.append("  source %-8s %dx%d %.1f fps %s  %s" % (n, s["width"], s["height"], s["fps"], fmt(s["duration"]), s["path"]))
        cw, ch = spec.view_size(n)
        if abs(cw / float(ch) - 16 / 9.0) > 0.02 and spec.aspect == "16:9":
            L.append("   note: %s%s is %.3f:1, not 16:9; plain look will show bars (use \"crop\" or style.fill)"
                     % (n, " (cropped)" if n in (spec.raw.get("crop") or {}) else "", cw / float(ch)))
    st = spec.style
    L.append("Look: %s  aspect %s  background %s  padding %s  cursor %s (size %s)"
             % (spec.look, spec.aspect, st["background"], st["padding"], "on" if st["show_cursor"] else "off", st["cursor_size"]))
    L.append("Timeline (source range -> position on the output before speed changes):")
    for i, (n, a, b, t0) in enumerate(spec.clips()):
        L.append("  %2d. %-8s %s - %s  (%5.2fs)  at %s" % (i + 1, n, fmt(a), fmt(b), b - a, fmt(t0)))
    words = load_words(spec.dir, spec.raw["captions"].get("words")) if spec.raw.get("captions") else []
    for sp in spec.raw.get("speed") or []:
        L.append("Speed x%s: %s %s - %s" % (sp["x"], spec.src(sp), fmt(sp["from"]), fmt(sp["to"])))
        if any(w["start"] < float(sp["to"]) and w["end"] > float(sp["from"]) for w in words):
            L.append("   WARNING: this speed-up covers speech; sped-up voice sounds like chatter")
    capped = set()
    for i, z in enumerate(spec.raw.get("zooms") or []):
        n = spec.src(z)
        vw = spec.view_size(n)[0]
        asked = spec.zoom_scale(z)
        sc = min(asked, spec.max_zoom(n)) if spec.aspect == "16:9" else asked
        frac = 1.0 / sc
        verdict = "phone-legible" if frac <= 0.38 else ("borderline" if frac <= 0.5 else "too wide for phone text")
        if spec.aspect != "16:9":  # the cap and the upscaled copy are only worked out for 16:9
            verdict = "depth as asked; what renders in %s is not known, check the draft" % spec.aspect
        L.append("Zoom %d: %s %s - %s  x%.2f%s  shows ~%d of %d px (%.0f%%) -> %s%s%s"
                 % (i + 1, n, fmt(z["from"]), fmt(z["to"]), sc, " (x%.2f asked)" % asked if sc < asked - 0.01 else "",
                    vw / sc, vw, frac * 100, verdict,
                    "  follow-cursor" if z.get("follow") else "  at %s" % (z.get("center"),),
                    "  cursor hidden" if z.get("hide_cursor") else ""))
        if sc < asked * 0.9:
            capped.add(n)
        pieces = spec.map_range(n, float(z["from"]), float(z["to"]))
        if not pieces:
            L.append("   WARNING: zoom %d falls entirely in removed footage" % (i + 1))
        # 1.19, not 1.2: plan-zooms ends a zoom exactly 1.2 s before the end, rounded to 0.01 s
        elif spec.zooms_on() and sum(b - a for _, a, b in spec.keep) - pieces[-1][1] < 1.19:
            L.append("   WARNING: zoom %d is still zoomed in when the video ends (zooming out takes about"
                     " 1.2 s): end it earlier or keep more footage after it" % (i + 1))
    for n in spec.sources:
        if spec.upscale(n) > 1:
            L.append("   note: %s's zooms render from a 2x upscaled working copy (%s, made once by export.py)"
                     % (n, os.path.basename(c.working_copy_path(spec.sources[n]["path"]))))
    for n in sorted(capped):
        L.append("   WARNING: OpenScreen enlarges a capture at most 2x, so %s's zooms stop at x%.2f; text"
                 " will be smaller than planned" % (n, spec.max_zoom(n)))
    if spec.raw.get("zooms") and not spec.zooms_on():
        L.append("NOTE: look=plain drops the zooms")
    if spec.look == "plain":
        for n, S in spec.sources.items():
            take = os.path.join(os.path.dirname(S["path"]), "take.json")
            try:
                is_window = "window" in (load_json(take).get("source") or {})
            except (OSError, ValueError):
                is_window = False
            if not is_window:
                continue
            # macOS windows have rounded bottom corners (about 13 px at 1x); edge to edge they show
            # as small black triangles. Inset the crop by that much, keeping 16:9.
            r = 13 * (2 if S["width"] >= c.UPSCALE_BELOW else 1)
            x, y, w, h = spec.crop_box(n)
            nh = min(h, S["height"] - y - r) if y + h > S["height"] - r else h
            nw = int(round(nh * 16 / 9.0))
            if nw <= w and (y + h > S["height"] - r):
                L.append("   note: plain look shows %s's rounded bottom window corners as black triangles; to hide"
                         ' them use "crop": {"%s": [%d, %d, %d, %d]} (16:9, trims about %d px)'
                         % (n, n, x + (w - nw) // 2, y, nw, nh, r))
    for i, bl in enumerate(spec.raw.get("blur") or []):
        L.append("Blur %d: %s %s - %s box %s" % (i + 1, spec.src(bl), fmt(bl.get("from", 0)),
                                                 fmt(bl.get("to", spec.sources[spec.src(bl)]["duration"])), bl["box"]))
    if spec.raw.get("captions"):
        L.append("Captions: %d words" % len(words))
    d = spec.output_duration()
    L.append("Output duration: %s (%.2fs)" % (fmt(d), d))
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("new", help="starter edit file from one or more takes")
    p.add_argument("takes", nargs="+")
    p.add_argument("-o", "--out")
    p.add_argument("--look", default="polished", choices=list(LOOKS))
    p.add_argument("--aspect", default="16:9")
    p = sub.add_parser("build", help="edit file -> .openscreen project")
    p.add_argument("edit")
    p.add_argument("-o", "--out")
    p = sub.add_parser("summary", help="describe an edit file")
    p.add_argument("edit")
    a = ap.parse_args()

    if a.cmd == "new":
        videos = [resolve_take(t) for t in a.takes]
        if not a.out:
            # takes live in DEMO_DIR/takes/<take>/; the edit file goes in DEMO_DIR
            first = os.path.dirname(videos[0])
            demo = os.path.dirname(os.path.dirname(first)) if os.path.basename(os.path.dirname(first)) == "takes" else first
            a.out = os.path.join(demo, "edit.json")
        out_dir = os.path.dirname(os.path.abspath(a.out))
        srcs = {}
        for i, v in enumerate(videos):
            try:
                c.media_info(v)
            except RuntimeError as e:
                die(str(e))
            srcs["main" if i == 0 else "take%d" % (i + 1)] = os.path.relpath(os.path.abspath(v), out_dir)
        spec = {"sources": srcs, "look": a.look, "aspect": a.aspect, "cut": [], "speed": [], "zooms": [], "blur": []}
        if len(srcs) > 1:
            spec.pop("cut")
        if os.path.exists(a.out):
            die("%s already exists (edit it, or pass -o for a new file)" % a.out)
        with open(a.out, "w") as fh:
            json.dump(spec, fh, indent=2)
        print(a.out)
    elif a.cmd == "build":
        spec = Spec(a.edit)
        out = a.out or os.path.splitext(spec.path)[0] + ".openscreen"
        with open(out, "w") as fh:
            json.dump(build_document(spec), fh, indent=1)
        print(out)
    elif a.cmd == "summary":
        print(summarize_spec(Spec(a.edit)))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
