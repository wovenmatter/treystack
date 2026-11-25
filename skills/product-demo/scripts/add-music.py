#!/usr/bin/env python3
"""Lay a music file under a video.

usage: add-music.py VIDEO MUSIC OUT [--start S] [--volume DB] [--fade-in S] [--fade-out S]
                    [--lufs L] [--tp DB]

- Music is looped if shorter than the video and trimmed to the video length.
- --start   seconds into the song to begin (default 0)
- --volume  dB relative to the loudness target (default 0 = music alone at --lufs;
            e.g. -6 for a quieter bed)
- Fades: default 1.0 s in, 2.0 s out (ending exactly at the video's last frame).
- Loudness: two-pass EBU R128 loudnorm, linear mode, default -14 LUFS / -1.5 dBTP.
- Output: video stream copied (not re-encoded), AAC-LC 48 kHz stereo 192 kb/s, +faststart.
  Any existing audio in VIDEO is replaced.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as av  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("music"); ap.add_argument("out")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--volume", type=float, default=0.0)
    ap.add_argument("--fade-in", type=float, default=1.0)
    ap.add_argument("--fade-out", type=float, default=2.0)
    ap.add_argument("--lufs", type=float, default=av.DEFAULT_LUFS)
    ap.add_argument("--tp", type=float, default=av.DEFAULT_TP)
    a = ap.parse_args()
    av.ensure_parent(a.out)
    av.need(av.FFMPEG, av.FFPROBE)

    dur = av.duration(a.video)
    fo = min(a.fade_out, dur / 2)
    fi = min(a.fade_in, dur / 2)
    target = a.lufs + a.volume
    # -ss before -stream_loop: seek once into the song; loops restart at the song's beginning.
    music_in = ["-ss", "%.3f" % a.start, "-stream_loop", "-1", "-i", a.music]
    chain = ("[1:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:%.6f,asetpts=N/SR/TB,"
             "afade=t=in:st=0:d=%.3f,afade=t=out:st=%.6f:d=%.3f[mus]" % (dur, fi, dur - fo, fo))
    inputs = [["-i", a.video], music_in]
    meas = av.measure_loudness(inputs, chain, "mus", lufs=target, tp=a.tp)
    fg = chain + ";[mus]" + av.loudnorm_pass2(meas, lufs=target, tp=a.tp) + "[aout]"
    cmd = [av.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", a.video] + music_in + [
        "-filter_complex", fg, "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-t", "%.6f" % dur, "-movflags", "+faststart", a.out]
    av.run(cmd)
    v = av.verify_loudness(a.out)
    print("wrote %s  duration=%.2fs  loudness=%.1f LUFS  true_peak=%.1f dBTP"
          % (a.out, av.duration(a.out), v["lufs"], v["true_peak"]))


if __name__ == "__main__":
    main()
