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
    target = a.lufs + a.volume
    chain = av.music_chain(1, dur, a.fade_in, a.fade_out, "mus")
    inputs = [["-i", a.video], av.music_input(a.music, a.start)]
    meas = av.measure_loudness(inputs, chain, "mus", lufs=target, tp=a.tp)
    fg = chain + ";[mus]" + av.loudnorm_pass2(meas, lufs=target, tp=a.tp) + "[aout]"
    av.mux_audio(inputs, fg, dur, a.out)


if __name__ == "__main__":
    main()
