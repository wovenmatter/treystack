"""Shared helpers for the product-demo scripts. Python 3.9+ stdlib only, macOS.

Not a public API: imported by the sibling scripts only.

OpenScreen launch rules (verified with OpenScreen 2.3.0):
- Capture (`sources`, `record`) works only when launched through LaunchServices:
  `open -n -a /Applications/Openscreen.app --stdout F --stderr G --args ...`. macOS then checks
  Screen Recording / Accessibility / Microphone against Openscreen itself. Run as a child of a
  terminal or agent, the check is made against that hosting app and fails with
  "Failed to get sources".
- `open` always exits 0, does not pass the environment, resolves arguments after `--args`
  with cwd "/" (so only absolute paths work) and does not return the app's PID. The recorder
  PID is found with `ps` by the unique `--project` path.
- `export`, `info` and `pack` need no capture permission: run the real binary directly to get
  live NDJSON and real exit codes. Never use the Homebrew `openscreen` symlink (it crashes).
"""

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
HERE = os.path.dirname(os.path.abspath(__file__))

# Delivery loudness: -14 LUFS integrated, -1.5 dBTP; wide LRA keeps loudnorm in linear mode.
DEFAULT_LUFS = -14.0
DEFAULT_TP = -1.5
DEFAULT_LRA = 20.0

# OpenScreen never enlarges the capture past 2 output pixels per capture pixel (the constant
# MAX_SOURCE_MAGNIFICATION in its zoom-scale code, measured on a 1080p frame): a zoom deeper
# than 2 / (magnification at rest) is clamped without a word. At rest the capture is
# contain-fitted into the frame minus its padding (fit = 1 - padding% x 0.4). So a 1280 px
# capture stops near x1.45 and a 2560 px one near x2.77. A capture narrower than UPSCALE_BELOW
# is therefore zoomed from a 2x lanczos-upscaled working copy (same timestamps, same
# normalised telemetry): see working_copy.
UPSCALE_BELOW = 2400


def max_zoom(view_width, view_height=None, padding=10):
    """Deepest zoom OpenScreen renders for a capture (or crop) of this size in a 1920x1080 frame."""
    view_height = view_height or view_width * 9 / 16.0
    fit = 1 - min(100, max(0, padding)) / 100.0 * 0.4
    rest = min(1920 * fit / view_width, 1080 * fit / view_height)
    return max(1.0, min(5.0, int(2.0 / rest * 100) / 100.0))


def upscale_factor(width):
    """2 when a capture this wide is zoomed from an upscaled working copy, else 1."""
    return 2 if width and width < UPSCALE_BELOW else 1


def working_copy_path(video):
    root, _ = os.path.splitext(video)
    return root + ".x2.mp4"


def working_copy(video, log=sys.stderr):
    """2x upscaled copy of a take for deep zooms, beside it; reused while the take is unchanged.

    Timestamps are passed through untouched (the capture is variable frame rate), audio is
    copied, and the cursor telemetry sidecar is copied as is (it is normalised 0-1, so it fits
    any size). libx264 CRF 10 keeps UI text visually lossless (about 56 dB PSNR against the
    lanczos frame) at about the size of the original take, in about 0.1x real time."""
    out = working_copy_path(video)
    st = os.stat(video)
    stamp = {"source": os.path.basename(video), "size": st.st_size, "mtime": int(st.st_mtime)}
    stamp_path = out + ".json"
    try:
        fresh = os.path.exists(out) and json.load(open(stamp_path)) == stamp
    except (OSError, ValueError):
        fresh = False
    if not fresh:
        log.write("upscaling %s 2x for deeper zooms (once per take)...\n" % os.path.basename(video))
        tmp = out + ".tmp.mp4"
        run([FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", video, "-map", "0",
             "-vf", "scale=iw*2:ih*2:flags=lanczos", "-fps_mode", "passthrough", "-enc_time_base", "demux",
             "-c:v", "libx264", "-preset", "fast", "-crf", "10", "-pix_fmt", "yuv420p",
             "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
             "-c:a", "copy", "-movflags", "+faststart", tmp])
        os.replace(tmp, out)
        with open(stamp_path, "w") as fh:
            json.dump(stamp, fh)
    tel, tel_out = video + ".cursor.json", out + ".cursor.json"
    if os.path.exists(tel) and (not os.path.exists(tel_out) or os.path.getmtime(tel) > os.path.getmtime(tel_out)):
        shutil.copyfile(tel, tel_out)
    return out


SCREEN_PERMISSION_MSG = (
    "macOS refused screen capture. Turn on Openscreen in System Settings > Privacy & Security > "
    "Screen & System Audio Recording (the switch for 'Openscreen' itself, not for your terminal), "
    "then run this again. If it is already on, toggle it off and on once.")
MIC_PERMISSION_MSG = (
    "Microphone: answer the macOS prompt for Openscreen if one is on screen, or turn on "
    "Openscreen in System Settings > Privacy & Security > Microphone.")
ACCESSIBILITY_MSG = (
    "Clicks and cursor shapes are only recorded when Openscreen is on in System Settings > "
    "Privacy & Security > Accessibility.")

# AI-provider keys are removed from the environment of directly run OpenScreen commands
# (they are unused by the CLI commands this skill runs; removing them is defence in depth).
STRIP_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
             "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")


# ----------------------------------------------------------------------------- basics

def _excepthook(kind, value, tb, _default=sys.excepthook):
    """Plain one-line message (no traceback) for the expected failures: unreadable or missing files."""
    if issubclass(kind, (RuntimeError, FileNotFoundError)) and not os.environ.get("DEMO_VERBOSE"):
        sys.stderr.write("error: %s\n" % (value if kind is RuntimeError else
                                           "file not found: %s" % getattr(value, "filename", value)))
        sys.exit(1)
    _default(kind, value, tb)


sys.excepthook = _excepthook

def die(msg, code=1, as_json=False, **extra):
    if as_json:
        print(json.dumps(dict({"ok": False, "error": msg}, **extra)))
    else:
        sys.stderr.write("error: %s\n" % msg)
    sys.exit(code)


def ensure_parent(path):
    """Create the folder an output file goes into (e.g. DEMO/audio/), so callers need no mkdir."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    return path


def need(*tools):
    for t in tools:
        if shutil.which(t) is None:
            die("%s not found on PATH (brew install ffmpeg)" % t, 127)


def run(cmd, capture=False):
    """Run a command; on failure print its stderr tail and exit with its code."""
    if os.environ.get("DEMO_VERBOSE"):
        sys.stderr.write("+ " + " ".join(cmd) + "\n")
    # stdin closed: ffmpeg reads stdin for keystrokes and can stall when it is a socket or pipe
    p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE, universal_newlines=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr[-4000:])
        die("command failed: %s" % os.path.basename(cmd[0]), p.returncode)
    return p


# ----------------------------------------------------------------------------- ffprobe

def probe(path):
    if not os.path.exists(path):
        die("file not found: %s" % os.path.abspath(path))
    p = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
            capture=True)
    return json.loads(p.stdout)


def _rate(s):
    num, _, den = (s or "0/1").partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def media_info(path):
    """{width, height, fps, codec, duration, audio_tracks, audio:{codec,sample_rate,channels}|None,
    size}. duration prefers the video stream. Raises RuntimeError when unreadable."""
    if not os.path.exists(path):
        raise RuntimeError("file not found: %s" % os.path.abspath(path))
    try:
        d = json.loads(subprocess.run(
            [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=60).stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        raise RuntimeError("cannot probe %s: %s" % (path, e))
    if not d.get("streams"):
        raise RuntimeError("no media streams in %s" % path)
    fmt = d.get("format", {})
    info = {"duration": float(fmt.get("duration") or 0), "size": int(fmt.get("size") or 0),
            "audio_tracks": 0, "audio": None, "width": None, "height": None, "fps": 0.0, "codec": None}
    for st in d["streams"]:
        if st.get("codec_type") == "video" and info["width"] is None:
            info.update(width=int(st["width"]), height=int(st["height"]), codec=st.get("codec_name"),
                        fps=round(_rate(st.get("avg_frame_rate")) or _rate(st.get("r_frame_rate")), 3))
            if st.get("duration"):
                info["duration"] = float(st["duration"])
        elif st.get("codec_type") == "audio":
            info["audio_tracks"] += 1
            if info["audio"] is None:
                info["audio"] = {"codec": st.get("codec_name"), "sample_rate": st.get("sample_rate"),
                                 "channels": st.get("channels")}
    return info


def duration(path):
    return media_info(path)["duration"]


def describe(path):
    """One-line summary: 1920x1080 h264 30fps 24.03s 12.1 MB audio aac."""
    i = media_info(path)
    v = "%sx%s %s %.0ffps " % (i["width"], i["height"], i["codec"], i["fps"]) if i["width"] else ""
    return "%s%.2fs %.1f MB audio %s" % (v, i["duration"], i["size"] / 1e6,
                                         i["audio"]["codec"] if i["audio"] else "none")


def max_volume_db(path, seconds=None):
    """Peak level (dB) of the first audio track (volumedetect); -inf for digital silence;
    None when there is no audio."""
    cmd = [FFMPEG, "-nostdin", "-hide_banner", "-nostats"]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd += ["-i", path, "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    m = re.search(r"max_volume: (-?[0-9.]+|-inf) dB", p.stderr)
    if not m:
        return None
    return float("-inf") if m.group(1) == "-inf" else float(m.group(1))


# ----------------------------------------------------------------------------- loudness

def parse_loudnorm(stderr):
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)
    if not m:
        die("could not parse loudnorm output")
    return json.loads(m[-1])


def measure_loudness(inputs, filtergraph, out_label, lufs=DEFAULT_LUFS, tp=DEFAULT_TP, lra=DEFAULT_LRA):
    """loudnorm pass 1 on [out_label]. inputs: list of ffmpeg input-arg lists."""
    fg = "%s;[%s]loudnorm=I=%s:TP=%s:LRA=%s:print_format=json[__m]" % (filtergraph, out_label, lufs, tp, lra)
    cmd = [FFMPEG, "-hide_banner", "-nostats"]
    for i in inputs:
        cmd += i
    cmd += ["-filter_complex", fg, "-map", "[__m]", "-f", "null", "-"]
    return parse_loudnorm(run(cmd).stderr)


def loudnorm_pass2(meas, lufs=DEFAULT_LUFS, tp=DEFAULT_TP, lra=DEFAULT_LRA):
    return ("loudnorm=I=%s:TP=%s:LRA=%s:measured_I=%s:measured_TP=%s:measured_LRA=%s:"
            "measured_thresh=%s:offset=%s:linear=true:print_format=json,aresample=48000"
            % (lufs, tp, lra, meas["input_i"], meas["input_tp"], meas["input_lra"],
               meas["input_thresh"], meas["target_offset"]))


def verify_loudness(path):
    p = run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0",
             "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    m = parse_loudnorm(p.stderr)
    return {"lufs": float(m["input_i"]), "true_peak": float(m["input_tp"])}


def loudness_gain_db(inputs, filtergraph, out_label, target):
    i = float(measure_loudness(inputs, filtergraph, out_label)["input_i"])
    return 0.0 if i < -70 else target - i


# ----------------------------------------------------------------------------- OpenScreen

def find_app():
    for c in (os.environ.get("OPENSCREEN_APP", ""), "/Applications/Openscreen.app",
              os.path.expanduser("~/Applications/Openscreen.app")):
        if c and os.path.isfile(os.path.join(c, "Contents", "MacOS", "Openscreen")):
            return c
    return None


def app_binary(app):
    return os.path.join(app, "Contents", "MacOS", "Openscreen")


def require_app(as_json=False):
    app = find_app()
    if not app:
        die("Openscreen.app not found (looked in /Applications and ~/Applications; set "
            "OPENSCREEN_APP to its path). Install: brew install --cask openscreen", 2, as_json)
    return app


def direct_env():
    return {k: v for k, v in os.environ.items() if k not in STRIP_ENV}


def launch_capture(app, args, stdout_path, stderr_path, wait=False):
    """Start an OpenScreen capture command through LaunchServices. All paths absolute."""
    cmd = ["open", "-n"] + (["-W"] if wait else []) + [
        "-a", app, "--stdout", stdout_path, "--stderr", stderr_path, "--args"] + list(args)
    return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True)


def read_events(path):
    events = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("{"):
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        pass
    except (FileNotFoundError, TypeError):
        pass
    return events


def done_event(events):
    for e in reversed(events):
        if e.get("event") == "done":
            return e
    return None


def explain_error(text):
    if not text:
        return "OpenScreen failed without a message (see the stderr log)."
    if "Failed to get sources" in text:
        return SCREEN_PERMISSION_MSG
    low = text.lower()
    if "microphone" in low and ("denied" in low or "permission" in low):
        return MIC_PERMISSION_MSG + " (" + text + ")"
    return text.replace("Error: ", "", 1)


def tail(path, n=5):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip() for l in f if l.strip()]
        return " | ".join(lines[-n:])
    except OSError:
        return ""


def get_sources(app, timeout=30):
    """The `sources` payload, or RuntimeError with a plain message."""
    tmp = tempfile.mkdtemp(prefix="pdemo-sources-")
    out, err = os.path.join(tmp, "out.ndjson"), os.path.join(tmp, "err.log")
    try:
        proc = launch_capture(app, ["sources", "--json"], out, err, wait=True)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("OpenScreen did not answer `sources` within %ss." % timeout)
        done = done_event(read_events(out))
        if not done:
            raise RuntimeError("OpenScreen `sources` produced no result. stderr: " + tail(err, 3))
        if not done.get("success"):
            raise RuntimeError(explain_error(done.get("error", "")))
        return done["sources"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ps_table():
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if pid.isdigit():
            rows.append((int(pid), cmd.strip()))
    return rows


def recorders(app, marker=None):
    """[(pid, cmd)] of running OpenScreen `record` processes (optionally containing marker)."""
    prefix = app_binary(app) + " record"
    return [(p, c) for p, c in ps_table() if c.startswith(prefix) and (marker is None or marker in c)]


def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def run_openscreen(args, timeout=600):
    """Run a non-capture OpenScreen command (info/pack/export) directly. Returns
    (returncode, events, stdout, stderr)."""
    app = require_app()
    r = subprocess.run([app_binary(app)] + list(args), capture_output=True, text=True,
                       env=direct_env(), stdin=subprocess.DEVNULL, timeout=timeout)
    evs = []
    for line in r.stdout.splitlines():
        if line.startswith("{"):
            try:
                evs.append(json.loads(line))
            except ValueError:
                pass
    return r.returncode, evs, r.stdout, r.stderr


# ----------------------------------------------------------------------------- telemetry

CLICK_KINDS = ("click", "double-click", "right-click", "middle-click")


def telemetry_path(video):
    return video + ".cursor.json"


def load_samples(path):
    with open(path) as fh:
        d = json.load(fh)
    s = d if isinstance(d, list) else d.get("samples", [])
    return sorted(({"t": x["timeMs"] / 1000.0, "x": float(x.get("cx", 0.5)), "y": float(x.get("cy", 0.5)),
                    "k": x.get("interactionType", "move"), "v": x.get("visible", True)} for x in s),
                  key=lambda q: q["t"])


# ----------------------------------------------------------------------------- raster (no Pillow,
# no drawtext): a 5x7 bitmap font on RGB byte buffers, PNG written with zlib.

_FONT_SRC = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "J": ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    ",": [".....", ".....", ".....", ".....", ".##..", "..#..", ".#..."],
    ":": [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    "_": [".....", ".....", ".....", ".....", ".....", ".....", "#####"],
    "+": [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    "=": [".....", ".....", "#####", ".....", "#####", ".....", "....."],
    "/": [".....", "....#", "...#.", "..#..", ".#...", "#....", "....."],
    "%": ["##...", "##..#", "...#.", "..#..", ".#...", "#..##", "...##"],
    "#": [".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#."],
    "@": [".###.", "#...#", "#.###", "#.#.#", "#.###", "#....", ".###."],
    "(": ["...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."],
    ")": [".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."],
    "!": ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
    "?": [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
    ">": [".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."],
    "<": ["...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."],
    "'": ["..#..", "..#..", ".#...", ".....", ".....", ".....", "....."],
    '"': [".#.#.", ".#.#.", ".....", ".....", ".....", ".....", "....."],
    "*": [".....", "#.#.#", ".###.", "#####", ".###.", "#.#.#", "....."],
    "$": ["..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."],
    "&": [".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"],
    "[": [".###.", ".#...", ".#...", ".#...", ".#...", ".#...", ".###."],
    "]": [".###.", "...#.", "...#.", "...#.", "...#.", "...#.", ".###."],
}
FONT = {ch: [[c == "#" for c in row] for row in rows] for ch, rows in _FONT_SRC.items()}
GLYPH_W, GLYPH_H = 5, 7


class Canvas:
    """An RGB image as a bytearray, row-major, 3 bytes per pixel."""

    def __init__(self, width, height, color=(0, 0, 0)):
        self.w, self.h = int(width), int(height)
        self.buf = bytearray(bytes(color) * (self.w * self.h))

    @classmethod
    def from_rgb(cls, width, height, data):
        c = cls.__new__(cls)
        c.w, c.h, c.buf = int(width), int(height), bytearray(data)
        return c

    def rect(self, x, y, w, h, color):
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(self.w, int(x + w)), min(self.h, int(y + h))
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.buf[i:i + len(row)] = row

    def frame(self, x, y, w, h, color, t=2):
        self.rect(x, y, w, t, color)
        self.rect(x, y + h - t, w, t, color)
        self.rect(x, y, t, h, color)
        self.rect(x + w - t, y, t, h, color)

    def text(self, x, y, text, scale=2, color=(255, 255, 255), bg=None, pad=0):
        """Draw text (upper-cased; unknown characters become '?') with its top-left at (x, y)."""
        if bg is not None:
            tw, th = text_size(text, scale)
            self.rect(x - pad, y - pad, tw + 2 * pad, th + 2 * pad, bg)
        cy = y
        for line in text.split("\n"):
            cx = x
            for ch in line.upper():
                glyph = FONT.get(ch, FONT["?"])
                for gy, row in enumerate(glyph):
                    for gx, on in enumerate(row):
                        if on:
                            self.rect(cx + gx * scale, cy + gy * scale, scale, scale, color)
                cx += (GLYPH_W + 1) * scale
            cy += (GLYPH_H + 2) * scale

    def paste(self, other, x, y):
        for yy in range(other.h):
            ty = y + yy
            if ty < 0 or ty >= self.h:
                continue
            sx0, sx1 = max(0, -x), min(other.w, self.w - x)
            if sx1 <= sx0:
                continue
            si, ti = (yy * other.w + sx0) * 3, (ty * self.w + x + sx0) * 3
            n = (sx1 - sx0) * 3
            self.buf[ti:ti + n] = other.buf[si:si + n]

    def write_png(self, path):
        raw = bytearray()
        stride = self.w * 3
        for yy in range(self.h):
            raw.append(0)
            raw += self.buf[yy * stride:(yy + 1) * stride]

        def chunk(tag, data):
            body = tag + data
            return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

        with open(path, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))

    def write_ppm(self, path):
        with open(path, "wb") as fh:
            fh.write(b"P6\n%d %d\n255\n" % (self.w, self.h))
            fh.write(self.buf)


def text_size(text, scale):
    lines = text.split("\n")
    return (max(0, max(len(l) for l in lines) * (GLYPH_W + 1) * scale - scale),
            max(0, len(lines) * (GLYPH_H + 2) * scale - 2 * scale))


def grab_frame(path, t, width, height=None, crop=None):
    """One decoded frame at t seconds as a Canvas scaled to width (crop = x, y, w, h first)."""
    vf = []
    if crop:
        x, y, w, h = crop
        vf.append("crop=%d:%d:%d:%d" % (w, h, x, y))
    vf.append("scale=%d:%s:flags=lanczos" % (width, height if height else -2))
    data = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-ss", "%.3f" % max(0.0, t), "-i", path, "-frames:v", "1",
                           "-vf", ",".join(vf), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True).stdout
    if not data:
        raise RuntimeError("no frame decoded at t=%.3f from %s" % (t, path))
    if height is None:
        height = len(data) // (width * 3)
    return Canvas.from_rgb(width, height, data[: width * height * 3])


def now():
    return time.time()


def ffprobe_info(path):
    """(width, height, duration_s, fps) of the first video stream."""
    i = media_info(path)
    if not i["width"]:
        raise RuntimeError("no video stream in %s" % path)
    return i["width"], i["height"], i["duration"], i["fps"]


def has_stream(path, kind):
    return any(s.get("codec_type") == kind for s in probe(path)["streams"])


def video_fps(path):
    return media_info(path)["fps"] or 30.0
