#!/usr/bin/env python3
"""Render a draft with OpenScreen's headless export.

usage: export.py EDIT.json|PROJECT.openscreen -o OUT.mp4 [--fps 30|60|24]
                 [--quality good|medium|source] [--timeout S] [--quiet]

- Given edit.json it first rebuilds the project (edit.py build), so "edit the JSON, run
  export.py" is the whole re-render loop.
- Runs the real app binary directly (real exit code, live progress). `open -a` would hide
  failures and the Homebrew shim crashes. Override the app with OPENSCREEN_APP.
- --quality good (default) with aspect 16:9 gives exactly 1920x1080. Default fps 30.
- Progress goes to stderr every 10%. On success prints: OUT  (wall s)  WxH codec fps dur size audio.
- Exit code: 0 ok, the app's code (or 1) on failure with its message, 124 timeout, 130 Ctrl-C.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402


def main():
    ap =argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--quality", choices=["medium", "good", "source"], default="good")
    ap.add_argument("--fps", choices=["24", "30", "60"], default="30")
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    project = os.path.abspath(a.project)
    if not os.path.exists(project):
        c.die("not found: %s" % project, 2)
    if project.endswith(".json"):
        r = subprocess.run([sys.executable, os.path.join(c.HERE, "edit.py"), "build", project],
                           capture_output=True, text=True)
        sys.stderr.write(r.stderr)
        if r.returncode != 0:
            return r.returncode
        project = r.stdout.strip().splitlines()[-1]
    app = c.require_app()
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = [c.app_binary(app), "export", project, "--json", "--out", out, "--quality", a.quality,
           "--fps", a.fps]
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=c.direct_env(),
                            stdin=subprocess.DEVNULL, start_new_session=True)
    errs = []

    def pump():
        for line in proc.stderr:
            errs.append(line)
    th = threading.Thread(target=pump, daemon=True)
    th.start()

    def kill(sig=signal.SIGTERM):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass
    timed_out = []
    timer = threading.Timer(a.timeout, lambda: (timed_out.append(1), kill()))
    timer.start()
    done, err_msg, bucket = None, None, -1
    try:
        for line in proc.stdout:
            try:
                ev = json.loads(line.strip())
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            kind = ev.get("event")
            if kind == "progress" and not a.quiet:
                pct = ev.get("percentage", 0) or 0
                if int(pct // 10) > bucket:
                    bucket = int(pct // 10)
                    sys.stderr.write("progress %3d%%  %.0fs\n" % (pct, time.time() - t0))
            elif kind == "error":
                err_msg = ev.get("message")
            elif kind == "done":
                done = ev
    except KeyboardInterrupt:
        kill()
        proc.wait()
        return 130
    finally:
        timer.cancel()
    rc = proc.wait()
    th.join(timeout=5)
    elapsed = time.time() - t0
    if timed_out:
        kill(signal.SIGKILL)
        c.die("export timed out after %.0fs" % a.timeout, 124)
    if not (rc == 0 and done and done.get("success")):
        msg = (done or {}).get("error") or err_msg or "".join(errs[-20:]).strip() or "no result from the app"
        sys.stderr.write("error: export failed (exit %d after %.1fs):\n%s\n" % (rc, elapsed, msg))
        return rc or 1
    outp = done.get("outputPath") or out
    try:
        text = c.describe(outp)
    except RuntimeError as e:
        c.die("export reported success but the output is unreadable: %s" % e)
    print("%s  (%.1fs)  %s" % (outp, elapsed, text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
