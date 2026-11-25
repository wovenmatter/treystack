#!/usr/bin/env python3
"""Play a (silent) cut for the user and record the microphone over it, in sync. macOS only.

usage: record-dub.py VIDEO VOICE_OUT.wav [--device :default] [--countdown 3]
                     [--player-width 1280] [--extra-offset-ms 0]

1. Starts microphone capture first (ffmpeg avfoundation, device ":default" or e.g. ":1"; list
   devices with: ffmpeg -f avfoundation -list_devices true -i "").
2. Builds a muted playback copy of VIDEO (720p, fast) with a 3-2-1 countdown lead-in on the
   first frame, and plays it in an ffplay window. The video is always muted so the mic does
   not pick it up. Playback stops by itself at the end; the capture stops with it.
3. Sync: avfoundation stamps audio with the host clock (CLOCK_UPTIME_RAW) and the script
   timestamps every decoded frame ffplay reports (showinfo) on the same clock, so the
   capture offset of video time 0 is measured on every run, not assumed. Display lag of ~2
   frames is added; --extra-offset-ms adjusts further (+ = voice later).
4. Writes VOICE_OUT.wav (48 kHz mono, exactly the video's length, aligned to video t=0) and
   VOICE_OUT.sync.json with the measured numbers. Then lay it on the cut with mix-voice.py.
Needs: ffmpeg, ffplay, osascript (countdown digits), microphone permission for the app that
runs this shell (macOS asks once; System Settings > Privacy & Security > Microphone).
"""
import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as av  # noqa: E402

CLK = time.CLOCK_UPTIME_RAW  # same clock as CoreMedia host time / avfoundation timestamps


def now():
    return time.clock_gettime(CLK)


def build_playback(video, out, countdown, width, td):
    """Muted copy with N-second countdown (big digits on a frozen first frame)."""
    info = av.media_info(video)
    W = width
    H = int(round(W * info["height"] / info["width"] / 2) * 2)
    fps = info["fps"] or 30.0
    inputs = ["-i", video]
    fg = "[0:v:0]scale=%d:%d,fps=%g,tpad=start_duration=%g:start_mode=clone,format=yuv420p" % (W, H, fps, countdown)
    if countdown > 0 and shutil.which("osascript"):
        items = [{"text": str(countdown - i), "file": os.path.join(td, "cd%d.png" % i)} for i in range(int(countdown))]
        spec = {"width": W, "height": H, "font_px": int(H * 0.30), "bottom_px": int(H * 0.30),
                "box_alpha": 0.55, "items": items}
        if av.render_text_pngs(spec, os.path.join(td, "cd.json")).returncode == 0:
            fg += "[b0]"
            for i, it in enumerate(items):
                # -itsoffset: digit i is on screen from second i to i + 1
                inputs += ["-loop", "1", "-t", "1", "-itsoffset", str(i), "-i", it["file"]]
                fg += ";[b%d][%d:v]overlay=enable='between(t,%d,%d)':eof_action=pass[b%d]" % (i, i + 1, i, i + 1, i + 1)
            fg += ";[b%d]null" % len(items)
    fg += "[v]"
    av.run([av.FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y"] + inputs +
            ["-filter_complex", fg, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "ultrafast",
             "-crf", "23", out])
    return fps


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("voice_out")
    ap.add_argument("--device", default=":default")
    ap.add_argument("--countdown", type=int, default=3)
    ap.add_argument("--player-width", type=int, default=1280)
    ap.add_argument("--extra-offset-ms", type=float, default=0.0)
    ap.add_argument("--open-timeout", type=float, default=12.0)
    ap.add_argument("--test-beep-at", type=float, help=argparse.SUPPRESS)  # test aid: afplay a beep at video time S
    a = ap.parse_args()
    av.ensure_parent(a.voice_out)
    av.need(av.FFMPEG, av.FFPROBE, "ffplay")
    dur = av.duration(a.video)
    td = tempfile.mkdtemp(prefix="dub-")
    try:
        play = os.path.join(td, "play.mp4")
        sys.stderr.write("preparing muted playback copy...\n")
        fps = build_playback(a.video, play, a.countdown, a.player_width, td)

        if a.test_beep_at is not None:
            av.run([av.FFMPEG, "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                     "sine=f=1000:d=0.15:r=48000", os.path.join(td, "beep.wav")])
        raw = os.path.join(td, "mic.wav")
        cap = subprocess.Popen([av.FFMPEG, "-hide_banner", "-y", "-f", "avfoundation", "-i", a.device,
                                "-c:a", "pcm_s24le", raw], stdin=subprocess.PIPE,
                               stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)
        cap_start, cap_err = [None], []

        def read_cap():
            for line in cap.stderr:
                cap_err.append(line)
                m = re.search(r"start: ([0-9.]+)", line)
                if m and cap_start[0] is None:
                    cap_start[0] = float(m.group(1))
        threading.Thread(target=read_cap, daemon=True).start()
        t_open = now()
        while cap_start[0] is None and cap.poll() is None and now() - t_open < a.open_timeout:
            time.sleep(0.02)
        if cap_start[0] is None:
            cap.kill()
            av.die("microphone did not open within %.0f s (device %s).\n"
                    "  If macOS showed a microphone prompt, allow it for the app running this terminal "
                    "and retry.\n  Otherwise: System Settings > Privacy & Security > Microphone, enable "
                    "that app.\n  ffmpeg said: %s" % (a.open_timeout, a.device, "".join(cap_err)[-600:].strip()), 4)
        sys.stderr.write("mic open. Get ready: the countdown is on screen; start talking after it.\n")

        player = subprocess.Popen(["ffplay", "-hide_banner", "-an", "-autoexit", "-noborder",
                                   "-window_title", "Recording voice - talk over the video",
                                   "-x", str(a.player_width), "-vf", "showinfo", play],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                  universal_newlines=True, bufsize=1)
        samples, beep_done = [], False
        for line in player.stderr:
            if "Parsed_showinfo" in line and " n:" in line:
                t = now()
                m = re.search(r"pts_time:([0-9.]+)", line)
                if m:
                    pts = float(m.group(1))
                    samples.append((pts, t))
                    if a.test_beep_at is not None and not beep_done and pts >= a.countdown + a.test_beep_at:
                        beep_done = True
                        subprocess.Popen(["afplay", "-v", "0.15", os.path.join(td, "beep.wav")])
        player.wait()
        time.sleep(0.3)
        try:
            cap.communicate(input="q", timeout=5)
        except subprocess.TimeoutExpired:
            cap.kill()
        if len(samples) < 10:
            av.die("player reported too few frames; was a display available?")
        # Steady-state host-time of pts 0 (skip the initial decode burst), plus display lag.
        steady = [t - p for p, t in samples if p > 0.5]
        pts0_host = statistics.median(steady) + 2.0 / fps
        content0_host = pts0_host + a.countdown
        offset = content0_host - cap_start[0] + a.extra_offset_ms / 1000.0
        if offset < 0:
            av.die("capture started after the video (offset %.3f s); cannot align" % offset)
        av.run([av.FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", raw, "-af",
                 "atrim=start=%.6f,asetpts=N/SR/TB,apad,atrim=0:%.6f" % (offset, dur),
                 "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", a.voice_out])
        maxdb = av.max_volume_db(a.voice_out)
        if maxdb is None or maxdb == float("-inf"):
            maxdb = -999.0
        jitter = statistics.pstdev(steady) if len(steady) > 2 else 0.0
        sync = {"capture_start_host": cap_start[0], "video_t0_host": content0_host,
                "offset_into_capture_s": round(offset, 4), "frame_clock_jitter_s": round(jitter, 4),
                "frames_seen": len(samples), "voice_max_dbfs": maxdb, "device": a.device}
        with open(os.path.splitext(a.voice_out)[0] + ".sync.json", "w") as f:
            json.dump(sync, f, indent=1)
        print("wrote %s  (%.2fs, offset into capture %.3fs, frame-clock jitter %.1f ms, max %.1f dBFS)"
              % (a.voice_out, dur, offset, jitter * 1000, maxdb))
        if maxdb < -80:
            sys.stderr.write("warning: the recording is digital silence: the microphone is blocked or muted.\n"
                             "  Allow microphone access for the app running this terminal (System Settings >"
                             " Privacy & Security > Microphone) and retry.\n")
            sys.exit(5)
        elif maxdb < -45:
            sys.stderr.write("warning: the recording is very quiet (max %.1f dBFS): wrong input device?\n" % maxdb)
    finally:
        shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    main()
