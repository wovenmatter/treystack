#!/usr/bin/env python3
"""Word-level transcript of a clip's speech, as JSON, using whisper.cpp (whisper-cli).

usage: transcribe.py INPUT OUT.json [--model base.en] [--models-dir DIR] [--lang en]
                     [--no-dtw] [--no-snap] [--download]

INPUT     any audio/video file ffmpeg can read (first audio stream is used)
--model   ggml model name: tiny.en | base.en (default) | small.en | medium.en | ...
--models-dir  where ggml-<model>.bin lives (default $WHISPER_MODELS_DIR or
              ~/.cache/whisper.cpp)
--no-dtw  skip whisper.cpp DTW token alignment (on by default: it runs with flash attention
          off and needs a model with a DTW preset: tiny/base/small/medium(.en), large-v1/2/3)
--no-snap do not snap word boundaries to detected speech (energy) regions
--download    fetch the model from Hugging Face if missing (one-time, needs network):
              https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-<model>.bin

Output JSON:
  {"model": "...", "duration": s, "text": "...",
   "words": [{"word": "Click", "start": 4.52, "end": 4.81, "p": 0.97}, ...]}
Times are seconds from the start of INPUT. Punctuation stays attached to its word.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as av  # noqa: E402

DTW_LAG = 0.10
HF = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-%s.bin"


def ensure_model(name, mdir, download):
    path = os.path.join(mdir, "ggml-%s.bin" % name)
    if os.path.exists(path):
        return path
    if not download:
        av.die("model not found: %s\n  fetch it once with --download, or:\n"
                "  mkdir -p %s && curl -L -o %s %s" % (path, mdir, path, HF % name), 2)
    os.makedirs(mdir, exist_ok=True)
    sys.stderr.write("downloading %s ...\n" % (HF % name))
    tmp = path + ".part"
    urllib.request.urlretrieve(HF % name, tmp)
    os.replace(tmp, path)
    return path


def speech_regions(wav):
    """Non-silent intervals [(start, end)] using a threshold 35 dB under the clip's peak."""
    peak = av.max_volume_db(wav)
    thr = max(-60.0, (peak if peak is not None else 0.0) - 35.0)
    total = av.duration(wav)
    regions, cur = [], 0.0
    for s0, e0 in av.silence_ranges(wav, thr, 0.20):
        if s0 > cur + 0.02:
            regions.append((cur, s0))
        cur = e0
    if cur < total - 0.02:
        regions.append((cur, total))
    return regions


def snap(words, regions):
    """Assign each word to the speech region it overlaps most (or the nearest), clamp it inside,
    and pin the first/last word of each region to the region edges. Whisper's own timestamps
    tend to stretch words across pauses; speech energy is a better boundary."""
    def pick(w):
        best, score = None, None
        for r in regions:
            ov = min(w["end"], r[1]) - max(w["start"], r[0])
            dist = 0 if ov > 0 else min(abs(w["start"] - r[1]), abs(w["end"] - r[0]))
            key = (ov if ov > 0 else -dist)
            if score is None or key > score:
                best, score = r, key
        return best
    groups = {}
    for w in words:
        groups.setdefault(pick(w), []).append(w)
    for r, ws in groups.items():
        for w in ws:
            w["start"] = round(min(max(w["start"], r[0]), r[1] - 0.05), 3)
            w["end"] = round(min(max(w["end"], w["start"] + 0.05), r[1]), 3)
        ws[0]["start"] = round(r[0], 3)
        ws[-1]["end"] = round(r[1], 3)
    for i in range(1, len(words)):  # keep monotonic
        if words[i]["start"] < words[i - 1]["start"]:
            words[i]["start"] = words[i - 1]["start"]
        if words[i - 1]["end"] > words[i]["start"] and words[i - 1]["end"] - words[i - 1]["start"] > 0.05:
            words[i - 1]["end"] = max(words[i - 1]["start"] + 0.05, words[i]["start"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input"); ap.add_argument("out")
    ap.add_argument("--model", default="base.en")
    ap.add_argument("--models-dir")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--no-dtw", dest="dtw", action="store_false")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--no-snap", action="store_true")
    ap.add_argument("--threads", type=int, default=min(8, os.cpu_count() or 4))
    a = ap.parse_args()
    av.ensure_parent(a.out)
    av.need(av.FFMPEG)
    cli = shutil.which("whisper-cli")
    if not cli:
        av.die("whisper-cli not found (brew install whisper-cpp)", 127)
    mdir = a.models_dir or os.environ.get("WHISPER_MODELS_DIR") or os.path.expanduser("~/.cache/whisper.cpp")
    model = ensure_model(a.model, mdir, a.download)

    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "in.wav")
        av.run([av.FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", a.input,
                 "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav])
        base = os.path.join(td, "w")
        cmd = [cli, "-m", model, "-f", wav, "-l", a.lang, "-t", str(a.threads),
               "-ojf", "-ml", "1", "-sow", "-np", "-of", base]
        if a.dtw:
            cmd += ["-dtw", a.model, "-nfa"]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if p.returncode != 0:
            sys.stderr.write(p.stderr[-3000:])
            av.die("whisper-cli failed", p.returncode)
        with open(base + ".json") as f:
            raw = json.load(f)
        speech = [] if a.no_snap else speech_regions(wav)

    words = []
    for seg in raw.get("transcription", []):
        toks = [t for t in seg.get("tokens", []) if not t["text"].startswith("[_")]
        text = "".join(t["text"] for t in toks).strip()
        if not text or (text.startswith("[") and text.endswith("]")):
            continue  # empty or non-speech marker like [BLANK_AUDIO]
        start, end = seg["offsets"]["from"] / 1000.0, seg["offsets"]["to"] / 1000.0
        if a.dtw:
            d = [t["t_dtw"] for t in toks if t.get("t_dtw", -1) >= 0]
            if d:  # DTW token times lag the acoustic onset by ~0.13 s on test speech
                start = max(0.0, d[0] / 100.0 - DTW_LAG)
        p = min([t["p"] for t in toks] or [0])
        # whisper sometimes emits punctuation as its own "word": glue it to the previous word
        if words and all(not c.isalnum() for c in text):
            words[-1]["word"] += text
            words[-1]["end"] = max(words[-1]["end"], end)
            continue
        words.append({"word": text, "start": round(start, 3), "end": round(end, 3), "p": round(p, 3)})
    if a.dtw:  # DTW gives starts; each word then ends where the next begins
        for i, w in enumerate(words[:-1]):
            w["end"] = round(max(w["start"] + 0.05, words[i + 1]["start"]), 3)
    if speech:
        snap(words, speech)
    out = {"model": a.model, "duration": round(av.duration(a.input), 3),
           "text": " ".join(w["word"] for w in words), "words": words}
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1)
    print("wrote %s  words=%d  text=%r" % (a.out, len(words), out["text"][:120]))


if __name__ == "__main__":
    main()
