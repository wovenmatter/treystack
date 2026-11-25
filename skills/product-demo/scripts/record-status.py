#!/usr/bin/env python3
"""Is a recording from DEMO_DIR running, and for how long?

usage: record-status.py DEMO_DIR [--json]

Prints e.g. "recording 00:42 (take-20260101-120000, My App)" or "not recording".
status: recording | waiting (capture not begun, usually a permission prompt) | ended (finished
by itself; run record-stop.py to collect) | died (no done event; record-stop.py salvages) | idle.
Exit 0 while recording or waiting, 1 otherwise. Reads files and `ps` only.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402


def main(argv):
    if "-h" in argv or "--help" in argv or not argv:
        print(__doc__.strip())
        return 0 if argv else 1
    demo = os.path.abspath(os.path.expanduser(argv[0]))
    try:
        st = json.load(open(os.path.join(demo, ".recording.json")))
    except (OSError, ValueError):
        st = None
    res = {"status": "idle"}
    if st:
        alive = bool(c.recorders(st.get("app") or c.require_app(), st["marker"]))
        evs = c.read_events(st.get("stdoutLog"))
        done = c.done_event(evs)
        started = any(e.get("message") == "Recording started" for e in evs)
        status = ("recording" if started else "waiting") if alive else ("ended" if done else "died")
        t0 = st.get("startedAt") or st.get("launchedAt")
        res = {"status": status, "pid": st.get("pid"), "take": st.get("take"),
               "source": st.get("sourceName") or st.get("source"),
               "elapsedSec": round(c.now() - t0, 1) if t0 and alive else None}
        if done is not None:
            res["durationMs"] = done.get("durationMs")
    if "--json" in argv:
        print(json.dumps(res))
    elif res["status"] == "idle":
        print("not recording")
    else:
        e = res.get("elapsedSec")
        clock = "%02d:%02d " % divmod(int(e), 60) if e is not None else ""
        print("%s %s(%s, %s)" % (res["status"], clock, res["take"], res["source"]))
    return 0 if res["status"] in ("recording", "waiting") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
