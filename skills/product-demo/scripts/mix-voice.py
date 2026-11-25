#!/usr/bin/env python3
"""Lay a voice track on a video, optionally with music ducked under it.

usage: mix-voice.py VIDEO VOICE OUT [--offset S] [--music FILE] [--music-start S]
                    [--music-db DB] [--duck strong|normal|light] [--no-clean] [--denoise]
                    [--lufs L] [--tp DB]

VOICE   audio (or video) file with the voice; "-" = use VIDEO's own audio track
        (live narration recorded with the screen).
--offset    seconds to shift the voice: +0.25 plays the voice 250 ms later, -0.25 earlier
            (the first 250 ms of the voice file are dropped).
--music     optional music bed; looped/trimmed to the video, faded in/out.
--music-db  bed level relative to the voice, before ducking (default -12 dB).
--duck      how hard the bed is pushed down while someone speaks (measured: light ~8 dB, normal ~13 dB, strong ~25 dB; default normal).
Voice clean-up (default on): 80 Hz high-pass, gentle 3:1 compression, loudness-matched.
--denoise   add light FFT denoise (afftdn) for noisy rooms.
Output: video stream copied, AAC 48 kHz stereo 192 kb/s, two-pass loudnorm to --lufs/--tp
(default -14 LUFS / -1.5 dBTP), duration = video duration, +faststart.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as av  # noqa: E402

STEM_REF = -16.0  # stems are balanced around this level before the final normalise
DUCK = {  # sidechaincompress settings; threshold is relative to a voice at STEM_REF
    "light": "threshold=0.05:ratio=3:attack=30:release=500:knee=4",
    "normal": "threshold=0.03:ratio=4:attack=20:release=600:knee=4",
    "strong": "threshold=0.01:ratio=12:attack=15:release=700:knee=4",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("voice"); ap.add_argument("out")
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--music")
    ap.add_argument("--music-start", type=float, default=0.0)
    ap.add_argument("--music-db", type=float, default=-12.0)
    ap.add_argument("--duck", choices=sorted(DUCK), default="normal")
    ap.add_argument("--no-clean", action="store_true")
    ap.add_argument("--denoise", action="store_true")
    ap.add_argument("--fade-in", type=float, default=1.0)
    ap.add_argument("--fade-out", type=float, default=2.0)
    ap.add_argument("--lufs", type=float, default=av.DEFAULT_LUFS)
    ap.add_argument("--tp", type=float, default=av.DEFAULT_TP)
    ap.add_argument("--solo-bed", action="store_true", help=argparse.SUPPRESS)  # test aid
    a = ap.parse_args()
    av.ensure_parent(a.out)
    av.need(av.FFMPEG, av.FFPROBE)

    dur = av.duration(a.video)
    inputs = [["-i", a.video]]
    if a.voice == "-":
        if not av.has_stream(a.video, "audio"):
            av.die("VOICE is '-' but the video has no audio track")
        vsrc = "0:a:0"
    else:
        inputs.append(["-i", a.voice])
        vsrc = "1:a:0"

    v = "[%s]aformat=sample_rates=48000:channel_layouts=mono" % vsrc
    if not a.no_clean:
        v += ",highpass=f=80"
        if a.denoise:
            v += ",afftdn=nr=10:nf=-40"
        v += ",acompressor=threshold=-20dB:ratio=3:attack=5:release=150:makeup=2"
    if a.offset > 0:
        v += ",adelay=%d:all=1" % round(a.offset * 1000)
    elif a.offset < 0:
        v += ",atrim=start=%.6f,asetpts=N/SR/TB" % -a.offset
    v += ",apad,atrim=0:%.6f,asetpts=N/SR/TB,aformat=channel_layouts=stereo" % dur
    voice_chain = v + "[vc]"
    gv = av.loudness_gain_db(inputs, voice_chain, "vc", STEM_REF)

    music_chain = None
    if a.music:
        inputs.append(["-ss", "%.3f" % a.music_start, "-stream_loop", "-1", "-i", a.music])
        mi = len(inputs) - 1
        fo, fi = min(a.fade_out, dur / 2), min(a.fade_in, dur / 2)
        music_chain = ("[%d:a:0]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:%.6f,"
                       "asetpts=N/SR/TB,afade=t=in:st=0:d=%.3f,afade=t=out:st=%.6f:d=%.3f[mc]"
                       % (mi, dur, fi, dur - fo, fo))
        gm = av.loudness_gain_db(inputs, music_chain, "mc", STEM_REF + a.music_db)

    fg = voice_chain + ";[vc]volume=%.2fdB[vg]" % gv
    if music_chain:
        fg += (";" + music_chain + ";[mc]volume=%.2fdB[mg];[vg]asplit[vm][vs];"
               "[mg][vs]sidechaincompress=%s[duck];%s"
               % (gm, DUCK[a.duck], "[vm]volume=0[vz];[vz][duck]amix=inputs=2:normalize=0:duration=first[mix]" if a.solo_bed else
                  "[vm][duck]amix=inputs=2:normalize=0:duration=first[mix]"))
    else:
        fg += ";[vg]anull[mix]"
    meas = av.measure_loudness(inputs, fg, "mix", lufs=a.lufs, tp=a.tp)
    fg += ";[mix]" + av.loudnorm_pass2(meas, lufs=a.lufs, tp=a.tp) + "[aout]"

    cmd = [av.FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    for i in inputs:
        cmd += i
    cmd += ["-filter_complex", fg, "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", "%.6f" % dur,
            "-movflags", "+faststart", a.out]
    av.run(cmd)
    r = av.verify_loudness(a.out)
    print("wrote %s  duration=%.2fs  loudness=%.1f LUFS  true_peak=%.1f dBTP"
          % (a.out, av.duration(a.out), r["lufs"], r["true_peak"]))


if __name__ == "__main__":
    main()
