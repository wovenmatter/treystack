#!/usr/bin/env python3
"""Fetch ONE royalty-free music track into a demo folder, with its licence and source.

usage: fetch-music.py DEMO_DIR [--source mixkit|incompetech] [--mood MOOD] [--list]
                      [--pick N] [--min-sec 60]

  --source mixkit       (default) Mixkit Stock Music Free License: commercial and social-media
                        use allowed, no attribution required, no bulk downloading.
                        --mood is a Mixkit mood page: positive, dynamic, friendly, ... (see
                        https://mixkit.co/free-stock-music/).
  --source incompetech  Kevin MacLeod, CC BY 4.0: free commercial use but the credit line
                        MUST be published with the video (post text, reply, or page caption).
                        --mood matches the catalogue's "feel" (Bright, Uplifting, Driving, ...).
  --mood                defaults to positive (mixkit) or Bright (incompetech).
  --list                show the candidates (title, length) and download nothing.
  --pick N              take candidate N from --list (default 1).
  --min-sec S           skip tracks shorter than S seconds (default 60) where length is known.

Writes DEMO_DIR/audio/music.mp3 and DEMO_DIR/audio/music-licence.txt (title, source page,
file URL, licence, required credit, date). Never use this for commercial songs: if the user
wants a specific song, they supply the audio file.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh) product-demo-skill"}
MIXKIT = "https://mixkit.co/free-stock-music/mood/%s/"
INCOMPETECH_JSON = "https://incompetech.com/music/royalty-free/pieces.json"
INCOMPETECH_MP3 = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"


def get(url, binary=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def mixkit(mood, min_sec):
    page = MIXKIT % urllib.parse.quote(mood.lower())
    html = get(page)
    out, seen = [], set()
    # the listing embeds JSON-LD MusicRecording objects: name, byArtist, duration, url, license
    for m in re.finditer(r'\{"@id":"[^"]*","@type":"MusicRecording",(.*?)"url":"(https://assets\.mixkit\.co/music/\d+/\d+\.mp3)"', html):
        if m.group(2) in seen:
            continue
        seen.add(m.group(2))
        name = re.search(r'"name":"([^"]+)"', m.group(1))
        artist = re.search(r'"byArtist":"([^"]+)"', m.group(1))
        dur = re.search(r'"duration":"PT(?:(\d+)M)?(?:(\d+)S)?"', m.group(1))
        secs = int(dur.group(1) or 0) * 60 + int(dur.group(2) or 0) if dur else None
        if secs is not None and secs < min_sec:
            continue
        title = (name.group(1) if name else "Mixkit track") + (" by " + artist.group(1) if artist else "")
        out.append({"title": title, "url": m.group(2), "page": page, "seconds": secs,
                    "licence": "Mixkit Stock Music Free License (https://mixkit.co/license/#musicFree)",
                    "credit": "none required (optional: Music: %s via Mixkit)" % title})
    return out


def incompetech(feel, min_sec):
    pieces = json.loads(get(INCOMPETECH_JSON))
    out = []
    for p in pieces:
        if feel and feel.lower() not in str(p.get("feel", "")).lower():
            continue
        secs = None
        parts = [int(x) for x in re.findall(r"\d+", str(p.get("length", "")))]
        if parts:
            secs = 0
            for x in parts:  # "00:05:07" or "5:07"
                secs = secs * 60 + x
        if secs is not None and secs < min_sec:
            continue
        title = p.get("title", "").strip()
        out.append({"title": title, "seconds": secs,
                    "url": INCOMPETECH_MP3 + urllib.parse.quote(p.get("filename", "")),
                    "page": "https://incompetech.com/music/royalty-free/music.html",
                    "licence": "Creative Commons Attribution 4.0 (http://creativecommons.org/licenses/by/4.0/)",
                    "credit": '"%s" Kevin MacLeod (incompetech.com)\nLicensed under Creative Commons: '
                              'By Attribution 4.0 License\nhttp://creativecommons.org/licenses/by/4.0/' % title})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("demo_dir")
    ap.add_argument("--source", choices=["mixkit", "incompetech"], default="mixkit")
    ap.add_argument("--mood", help="default: positive (mixkit), Bright (incompetech)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--pick", type=int, default=1)
    ap.add_argument("--min-sec", type=float, default=60)
    a = ap.parse_args()
    a.mood = a.mood or ("positive" if a.source == "mixkit" else "Bright")
    try:
        cands = mixkit(a.mood, a.min_sec) if a.source == "mixkit" else incompetech(a.mood, a.min_sec)
    except Exception as e:  # noqa: BLE001
        sys.exit("error: could not read the %s catalogue (%s). Try the other --source, or ask the user "
                 "for a music file." % (a.source, e))
    if not cands:
        sys.exit("error: no tracks found for %r on %s" % (a.mood, a.source))
    if a.list:
        for i, t in enumerate(cands[:30], 1):
            print("%2d. %s%s" % (i, t["title"], "  (%d:%02d)" % divmod(t["seconds"], 60) if t["seconds"] else ""))
        return 0
    t = cands[min(max(a.pick, 1), len(cands)) - 1]
    d = os.path.join(os.path.abspath(a.demo_dir), "audio")
    os.makedirs(d, exist_ok=True)
    mp3 = os.path.join(d, "music.mp3")
    data = get(t["url"], binary=True)
    if len(data) < 50000:
        sys.exit("error: download from %s is too small to be a track (%d bytes)" % (t["url"], len(data)))
    with open(mp3, "wb") as f:
        f.write(data)
    with open(os.path.join(d, "music-licence.txt"), "w") as f:
        f.write("Title: %s\nSource page: %s\nFile: %s\nLicence: %s\nRequired credit: %s\nRetrieved: %s\n"
                % (t["title"], t["page"], t["url"], t["licence"], t["credit"], datetime.date.today().isoformat()))
    print("wrote %s (%.1f MB): %s" % (mp3, len(data) / 1e6, t["title"]))
    print("credit: " + t["credit"].replace("\n", " / "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
