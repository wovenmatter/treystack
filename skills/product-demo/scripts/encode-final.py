#!/usr/bin/env python3
"""Final delivery encode for X and similar social platforms.

usage: encode-final.py INPUT OUT.mp4 [--width 1920] [--height 1080] [--fps 30|60]
                       [--crf 18] [--maxrate 12M] [--bufsize 24M] [--preset slow]
                       [--audio-bitrate 192k] [--no-audio]
                       [--captions WORDS.json]
                       [--gif OUT.gif] [--gif-width 720] [--gif-fps 15] [--max-mb N]

Video: H.264 High profile, yuv420p, BT.709 tagged, capped CRF (quality-targeted but never above
--maxrate), keyframe every 2 s with closed GOPs, constant frame rate --fps, scaled to fit --width x --height and
padded (black) if the aspect differs. +faststart (moov atom first) for progressive playback.
Audio: AAC-LC 48 kHz stereo; copied untouched if it already is AAC 48 kHz (it was loudness-
normalised upstream). Silent videos get NO audio track: input without audio, an input
audio track that is digital silence (max level below -80 dBFS), or --no-audio.
--captions  burn captions from transcribe.py word JSON (times on THIS video's timeline, e.g. a
            dub) in this same encode: 2-5 words at a time, bold white on a dark box, 7.8% of the
            frame height, rendered by macOS AppKit (osascript), since Homebrew ffmpeg has no
            drawtext/libass. For live narration put captions in edit.json instead.
--gif       also write an animated GIF preview (palette-optimised); cheap but large files.
--max-mb    after encoding, warn (exit 3) if the file is larger than this many MB.
Platform limits (max size, bitrate, length, fps) change: pass them as parameters.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as av  # noqa: E402


END_PUNCT = ".?!;:,"


def chunk_words(words, max_words=5, max_chars=32, gap=0.35):
    """Group words into caption chunks of up to max_words / max_chars.

    First split into phrases at punctuation and pauses > gap, then cut each phrase into the
    fewest roughly equal chunks that respect the limits (so no orphan last word)."""
    phrases, cur = [], []
    for w in words:
        if cur and w["start"] - cur[-1]["end"] > gap:
            phrases.append(cur); cur = []
        cur.append(w)
        if w["word"][-1:] in END_PUNCT:
            phrases.append(cur); cur = []
    if cur:
        phrases.append(cur)
    out = []
    for ph in phrases:
        n = len(ph)
        k = max(1, -(-n // max_words))
        while True:
            size = -(-n // k)
            parts = [ph[i:i + size] for i in range(0, n, size)]
            if all(len(" ".join(x["word"] for x in p)) <= max_chars for p in parts) or size == 1:
                break
            k += 1
        out.extend(parts)
    return out


def timed_chunks(words, duration, max_words=5, max_chars=32, hold=0.25, min_dur=0.7):
    chunks = chunk_words(words, max_words, max_chars)
    res = []
    for i, c in enumerate(chunks):
        start = c[0]["start"]
        nxt = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else duration
        end = min(max(c[-1]["end"] + hold, start + min_dur), nxt, duration)
        res.append({"text": " ".join(w["word"] for w in c), "start": start, "end": end})
    return res


def build_caption_track(words_json, width, height, duration, workdir, font_frac=0.078,
                        bottom_frac=0.10, max_words=5, max_chars=32):
    """Render PNGs and write an ffconcat list. Returns (list_path, chunks)."""
    with open(words_json) as f:
        words = json.load(f)["words"]
    chunks = timed_chunks(words, duration, max_words, max_chars)
    items = [{"text": "", "file": os.path.join(workdir, "blank.png")}]
    for i, c in enumerate(chunks):
        c["file"] = os.path.join(workdir, "cap%04d.png" % i)
        items.append({"text": c["text"], "file": c["file"]})
    spec = {"width": width, "height": height, "font_px": round(height * font_frac),
            "bottom_px": round(height * bottom_frac), "max_width_frac": 0.86, "items": items}
    if shutil.which("osascript") is None:
        av.die("osascript not found: caption rendering needs macOS (JXA/AppKit)")
    p = av.render_text_pngs(spec, os.path.join(workdir, "spec.json"))
    if p.returncode != 0:
        av.die("caption render failed: " + p.stderr.strip())
    blank = items[0]["file"]
    # "framerate 1000": an image otherwise gets a 1/25 s clock, which rounds every caption
    # start and end to 40 ms (a frame or two off at 60 fps)
    show = lambda png, secs: ["file '%s'" % png, "option framerate 1000", "duration %.3f" % secs]  # noqa: E731
    lines, t = ["ffconcat version 1.0"], 0.0
    for c in chunks:
        if c["start"] > t + 0.001:
            lines += show(blank, c["start"] - t)
        lines += show(c["file"], c["end"] - c["start"])
        t = c["end"]
    lines += show(blank, max(0.04, duration - t)) + ["file '%s'" % blank, "option framerate 1000"]
    list_path = os.path.join(workdir, "captions.ffconcat")
    with open(list_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return list_path, chunks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input"); ap.add_argument("out")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--maxrate", default="12M")
    ap.add_argument("--bufsize", default="24M")
    ap.add_argument("--preset", default="slow")
    ap.add_argument("--audio-bitrate", default="192k")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--captions")
    ap.add_argument("--gif")
    ap.add_argument("--gif-width", type=int, default=720)
    ap.add_argument("--gif-fps", type=float, default=15)
    ap.add_argument("--max-mb", type=float)
    a = ap.parse_args()
    av.ensure_parent(a.out)
    av.need(av.FFMPEG, av.FFPROBE)

    W, H = a.width, a.height
    info = av.media_info(a.input)
    dur, audio = info["duration"], info["audio"]
    # silent videos carry no audio track (see the header)
    db = av.max_volume_db(a.input) if audio and not a.no_audio else None
    if db is None or db < -80:
        audio = None

    vf = ("[0:v:0]scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos:out_color_matrix=bt709,"
          "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=%s" % (W, H, W, H, a.fps))
    inputs = ["-i", a.input]
    td = None
    if a.captions:
        td = tempfile.mkdtemp(prefix="captions-")
        lst, chunks = build_caption_track(a.captions, W, H, dur, td)
        inputs += ["-f", "concat", "-safe", "0", "-i", lst]
        vf += "[base];[1:v]format=rgba[cap];[base][cap]overlay=0:0:eof_action=repeat:format=auto"
    vf += ",format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[v]"

    cmd = [av.FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-stats", "-y"] + inputs + [
        "-filter_complex", vf, "-map", "[v]",
        "-c:v", "libx264", "-preset", a.preset, "-crf", str(a.crf), "-maxrate", a.maxrate,
        "-bufsize", a.bufsize, "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-g", str(int(round(a.fps * 2))), "-flags", "+cgop", "-keyint_min", str(int(round(a.fps))), "-sc_threshold", "0",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
        "-r", "%s" % a.fps]
    if audio:
        cmd += ["-map", "0:a:0"]
        if audio["codec"] == "aac" and audio["sample_rate"] == "48000" and audio["channels"] == 2:
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-c:a", "aac", "-b:a", a.audio_bitrate, "-ar", "48000", "-ac", "2"]
    cmd += ["-t", "%.6f" % dur, "-movflags", "+faststart", a.out]
    try:
        av.run(cmd)
    finally:
        if td:
            shutil.rmtree(td, ignore_errors=True)
    size_mb = os.path.getsize(a.out) / 1e6
    kbps = os.path.getsize(a.out) * 8 / 1000 / max(dur, 0.001)
    print("wrote %s  %dx%d@%g  %.2fs  %.1f MB  %.0f kb/s avg" % (a.out, W, H, a.fps, av.duration(a.out), size_mb, kbps))

    if a.gif:
        av.ensure_parent(a.gif)
        gf = ("fps=%s,scale=%d:-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff:max_colors=128[p];"
              "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" % (a.gif_fps, a.gif_width))
        av.run([av.FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", a.out,
                 "-vf", gf, "-loop", "0", a.gif])
        print("wrote %s  %.1f MB" % (a.gif, os.path.getsize(a.gif) / 1e6))

    if a.max_mb and size_mb > a.max_mb:
        sys.stderr.write("warning: %.1f MB exceeds --max-mb %.1f; lower --crf/--maxrate or --fps\n"
                         % (size_mb, a.max_mb))
        sys.exit(3)


if __name__ == "__main__":
    main()
