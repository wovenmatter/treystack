#!/usr/bin/env python3
"""Start an OpenScreen recording in the background; return as soon as capture has begun.

usage: record-start.py DEMO_DIR (--window TITLE | --display N) [--mic | --mic-device NAME]
                       [--system-audio] [--cursor editable-overlay|system] [--duration S]
                       [--name TAKE] [--no-check] [--wait S] [--json]

  DEMO_DIR        demo folder; the take goes to DEMO_DIR/takes/<TAKE>/ and a state file
                  DEMO_DIR/.recording.json exists while it runs.
  --window TITLE  record the on-screen window whose title contains TITLE (case-insensitive).
                  The title is checked against the window list first: no match, or more than
                  one match, is refused (OpenScreen would silently pick one).
  --display N     record display N (see sources.py). Default when no --window: 0.
  --mic / --mic-device NAME   also record a microphone (mixed into the take's audio track).
  --system-audio  also record system audio (mixed into the same track).
  --cursor MODE   editable-overlay (default: pointer stored as data and drawn at export, needed
                  for the smoothed cursor and click zooms) or system (pointer burned in).
  --duration S    stop by itself after S seconds (otherwise stop with record-stop.py).
  --name TAKE     take folder name (default take-YYYYmmdd-HHMMSS).
  --no-check      skip the window-list check (saves about a second).
  --wait S        how long to wait for capture to begin (default 20).
  --json          print the result as one JSON object.

Exit codes: 0 recording (or status "waiting": a permission prompt is probably on screen),
1 failed to start (the message names the System Settings switch when it is a permission),
2 Openscreen.app missing, 3 a recording is already running or the last take is uncollected.
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

STATE = ".recording.json"


def save_state(demo, st):
    tmp = os.path.join(demo, STATE + ".tmp")
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, os.path.join(demo, STATE))


def load_state(demo):
    try:
        with open(os.path.join(demo, STATE)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def parse(argv):
    if "-h" in argv or "--help" in argv or not argv:
        print(__doc__.strip())
        sys.exit(0 if argv else 1)
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("demo_dir")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--window")
    g.add_argument("--display", type=int)
    p.add_argument("--mic", action="store_true")
    p.add_argument("--mic-device")
    p.add_argument("--system-audio", action="store_true")
    p.add_argument("--cursor", choices=["editable-overlay", "system"], default="editable-overlay")
    p.add_argument("--duration", type=float)
    p.add_argument("--name")
    p.add_argument("--no-check", action="store_true")
    p.add_argument("--wait", type=float, default=20.0)
    p.add_argument("--json", action="store_true")
    return p.parse_args(argv)


def out(res, as_json):
    if as_json:
        print(json.dumps(res))
    else:
        for k, v in res.items():
            if k != "ok":
                print("%s: %s" % (k, v))


def main(argv):
    a = parse(argv)
    j = a.json
    app = c.require_app(j)
    demo = os.path.abspath(os.path.expanduser(a.demo_dir))
    os.makedirs(demo, exist_ok=True)

    st = load_state(demo)
    if st and st.get("pid") and c.recorders(app, st.get("marker")):
        c.die("a recording from this folder is already running (pid %s, take %s); stop it with "
              "record-stop.py first" % (st["pid"], st.get("take")), 3, j)
    if st:
        c.die("the previous take (%s) has not been collected; run record-stop.py %s first"
              % (st.get("take"), demo), 3, j)
    others = c.recorders(app)
    if others:
        folders = sorted({os.path.dirname(os.path.dirname(os.path.dirname(m.group(1))))
                          for m in (re.search(r"--project (.+?/takes/[^/]+/take\.openscreen)", cmd) for _, cmd in others)
                          if m})
        c.die("another OpenScreen command-line recording is already running (pid %s)%s"
              % (", ".join(str(p) for p, _ in others),
                 "; stop it with record-stop.py %s" % " / ".join(folders) if folders else ""), 3, j)

    if a.window and not a.no_check:
        try:
            names = [w.get("name", "") for w in c.get_sources(app).get("windows", [])]
        except RuntimeError as e:
            c.die(str(e), 1, j)
        hits = [n for n in names if a.window.lower() in n.lower()]
        if not hits:
            c.die('no on-screen window title contains "%s". Minimised windows, windows on another '
                  "Space or behind a full-screen app cannot be recorded. Open windows: %s"
                  % (a.window, "; ".join(names) or "(none)"), 1, j, windows=names)
        if len(hits) > 1:
            exact = [n for n in hits if n.lower() == a.window.lower()]
            hint = ("; it is the whole title of one window and part of another's, so OpenScreen cannot "
                    "pick it alone: close or rename the other window" if exact else
                    "; use a longer part of the title")
            c.die('"%s" matches %d windows (%s)%s' % (a.window, len(hits), "; ".join(hits), hint),
                  1, j, matches=hits)

    take = a.name or time.strftime("take-%Y%m%d-%H%M%S")
    take_dir = os.path.join(demo, "takes", take)
    project = os.path.join(take_dir, "take.openscreen")
    if os.path.exists(project):
        c.die("take folder already holds a project: " + take_dir, 1, j)
    os.makedirs(take_dir, exist_ok=True)
    out_log = os.path.join(take_dir, "record.ndjson")
    err_log = os.path.join(take_dir, "record.stderr.log")
    for p in (out_log, err_log):
        open(p, "w").close()

    args = ["record", "--json", "--project", project, "--cursor", a.cursor]
    args += ["--window", a.window] if a.window else ["--display", str(a.display or 0)]
    if a.mic_device:
        args += ["--mic-device", a.mic_device]
    elif a.mic:
        args.append("--mic")
    if a.system_audio:
        args.append("--system-audio")
    if a.duration:
        args += ["--duration", str(a.duration)]

    state = {"status": "starting", "pid": None, "marker": project, "take": take, "takeDir": take_dir,
             "project": project, "stdoutLog": out_log, "stderrLog": err_log,
             "source": {"window": a.window} if a.window else {"display": a.display or 0},
             "mic": bool(a.mic or a.mic_device), "systemAudio": a.system_audio, "cursor": a.cursor,
             "duration": a.duration, "launchedAt": c.now(), "startedAt": None, "app": app}
    save_state(demo, state)

    opener = c.launch_capture(app, args, out_log, err_log)
    try:
        opener.wait(timeout=15)
    except Exception:  # noqa: BLE001
        pass
    if opener.returncode not in (0, None):
        os.remove(os.path.join(demo, STATE))
        c.die("could not launch Openscreen: " + (opener.stderr.read().strip() or "open failed"), 1, j)

    deadline = time.time() + max(a.wait, 3)
    pid, result = None, None
    while time.time() < deadline:
        if not pid:
            hit = c.recorders(app, project)
            if hit:
                pid = state["pid"] = hit[0][0]
                save_state(demo, state)
        evs = c.read_events(out_log)
        if any(e.get("event") == "log" and e.get("message") == "Recording started" for e in evs):
            result = "recording"
            break
        d = c.done_event(evs)
        if d is not None:
            result = "done" if d.get("success") else "failed"
            break
        if pid and not c.pid_alive(pid):
            time.sleep(0.3)
            if c.done_event(c.read_events(out_log)) is None:
                result = "died"
                break
        time.sleep(0.15)

    evs = c.read_events(out_log)
    if result == "recording":
        src = next((e["message"] for e in evs if e.get("event") == "log"
                    and e.get("message", "").startswith("Recording source:")), "")
        state.update(status="recording", startedAt=c.now(), sourceName=src.replace("Recording source: ", ""))
        save_state(demo, state)
        res = {"ok": True, "status": "recording", "pid": pid, "take": take, "takeDir": take_dir,
               "source": state["sourceName"]}
        if state["mic"]:
            res["note"] = "mic on: if the take turns out silent, " + c.MIC_PERMISSION_MSG
        out(res, j)
        return 0
    if result == "done":
        save_state(demo, dict(state, status="ended"))
        out({"ok": True, "status": "ended", "take": take,
             "note": "recording ended immediately; run record-stop.py %s to collect it" % demo}, j)
        return 0
    if result in ("failed", "died"):
        os.remove(os.path.join(demo, STATE))
        d = c.done_event(evs) or {}
        msg = c.explain_error(d.get("error") or next(
            (e.get("message") for e in evs if e.get("event") == "error"), "")) if evs else \
            "Openscreen exited without output. stderr: " + c.tail(err_log, 3)
        c.die(msg, 1, j, take=take, stderrLog=err_log)
    state["status"] = "waiting"
    save_state(demo, state)
    hint = c.MIC_PERMISSION_MSG if state["mic"] else \
        "Openscreen has not started capturing yet; a macOS permission prompt may be on screen."
    out({"ok": True, "status": "waiting", "pid": pid, "take": take, "takeDir": take_dir,
         "note": hint + " The recorder is still running; check with record-status.py, or cancel "
                        "with record-stop.py."}, j)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
