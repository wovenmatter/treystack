#!/usr/bin/env python3
"""Stop the recording started by record-start.py and gather the take into the demo folder.

usage: record-stop.py DEMO_DIR [--timeout SECONDS] [--keep-originals] [--kill]

Sends SIGINT to the recorder and waits for its `done` event (default timeout 60 s; SIGTERM
half way), then runs `openscreen pack` into DEMO_DIR/takes/<take>/ so the take is
self-contained (video, <video>.cursor.json telemetry, take.openscreen with rewritten paths)
and deletes the originals from OpenScreen's recordings folder (unless --keep-originals).
Also collects a recording that already ended (--duration reached, window closed) and salvages
the raw video of a recorder that died. --kill force-kills a recorder that ignores signals.

Prints one JSON object: {ok, status, take, takeDir, project, video, cursor, durationMs,
video_info:{width,height,fps,duration,audio_tracks}, telemetry:{samples,hz,clicks}, warnings}.
status: stopped | already-ended | salvaged | nothing-running | failed.
"""
import json
import os
import shutil
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

STATE = ".recording.json"


def signal_pid(pid, sig):
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass


def salvage_path(err_log):
    """The native helper logs the output path on stderr when capture starts."""
    try:
        text = open(err_log, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    key = '"outputPath":"'
    i = text.rfind(key)
    if i < 0:
        return None
    j = text.find('"', i + len(key))
    return text[i + len(key):j] if j > 0 else None


def copy_and_rewrite(project, video, cursor, take_dir):
    for p in (video, cursor):
        if p and os.path.exists(p):
            shutil.copy2(p, take_dir)
    try:
        d = json.load(open(project))
    except (OSError, ValueError):
        d = {"version": 2, "media": {}, "editor": {}}
    d.setdefault("media", {})["screenVideoPath"] = os.path.join(take_dir, os.path.basename(video))
    with open(project, "w") as f:
        json.dump(d, f, indent=2)


def telemetry_stats(path):
    try:
        s = c.load_samples(path)
    except (OSError, ValueError, KeyError):
        return None
    if len(s) < 2:
        return {"samples": len(s), "hz": 0, "clicks": 0, "visible": sum(1 for x in s if x["v"])}
    span = s[-1]["t"] - s[0]["t"]
    return {"samples": len(s), "hz": round((len(s) - 1) / span, 1) if span > 0 else 0,
            "clicks": sum(1 for x in s if x["k"] in c.CLICK_KINDS),
            "visible": sum(1 for x in s if x["v"])}


def main(argv):
    if "-h" in argv or "--help" in argv or not argv:
        print(__doc__.strip())
        return 0 if argv else 1
    demo = os.path.abspath(os.path.expanduser(argv[0]))
    timeout = float(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else 60.0
    keep, force = "--keep-originals" in argv, "--kill" in argv
    try:
        st = json.load(open(os.path.join(demo, STATE)))
    except (OSError, ValueError):
        if not os.path.isdir(demo):
            c.die("no such demo folder: %s" % demo, 1, True)
        res = {"ok": True, "status": "nothing-running", "note": "no recording was started from " + demo}
        app = c.find_app()
        others = c.recorders(app) if app else []
        if others:
            res["note"] += ("; but an OpenScreen recording is running (pid %s): pass the folder given to "
                            "record-start.py" % ", ".join(str(p) for p, _ in others))
        print(json.dumps(res))
        return 0
    app = st.get("app") or c.require_app(True)
    out_log, err_log = st["stdoutLog"], st["stderrLog"]
    warnings = []
    hit = c.recorders(app, st["marker"])
    pid = hit[0][0] if hit else None

    how = "already-ended"
    if pid:
        how = "stopped"
        signal_pid(pid, signal.SIGINT)
        t0, termed = time.time(), False
        while time.time() - t0 < timeout and c.pid_alive(pid):
            if not termed and time.time() - t0 > timeout / 2:
                signal_pid(pid, signal.SIGTERM)
                termed = True
                warnings.append("recorder ignored SIGINT; sent SIGTERM")
            time.sleep(0.2)
        if c.pid_alive(pid):
            if not force:
                print(json.dumps({"ok": False, "status": "failed", "pid": pid,
                                  "error": "recorder still running after %ss; run again with a longer "
                                           "--timeout, or --kill" % timeout}))
                return 1
            signal_pid(pid, signal.SIGKILL)
            warnings.append("recorder did not finish in %ss; force-killed" % timeout)
            time.sleep(0.5)

    evs = c.read_events(out_log)
    done = c.done_event(evs)
    warnings += [e.get("message", "") for e in evs if e.get("event") in ("warning", "error")]
    take_dir, project = st["takeDir"], st["project"]
    status = how
    if done and done.get("success"):
        video, cursor, duration_ms = done.get("screenVideoPath"), done.get("cursorDataPath"), done.get("durationMs")
        if how == "already-ended" and not st.get("duration"):
            warnings.append("the recording had ended before record-stop (window closed?)")
    else:
        video = salvage_path(err_log)
        try:
            info = c.media_info(video) if video and os.path.exists(video) else None
        except RuntimeError:
            info = None
        if not info:
            os.replace(os.path.join(demo, STATE), os.path.join(take_dir, "take.json"))
            err = (done or {}).get("error") or "recorder exited without a done event"
            print(json.dumps({"ok": False, "status": "failed", "error": c.explain_error(err),
                              "takeDir": take_dir, "stderrLog": err_log, "warnings": warnings}))
            return 1
        status, cursor = "salvaged", video + ".cursor.json"
        duration_ms = int(info["duration"] * 1000)
        with open(project, "w") as f:
            json.dump({"version": 2, "media": {"screenVideoPath": video}, "editor": {}}, f)
        warnings.append("recorder did not finish normally; built a minimal project around the raw video")

    pack_ok = False
    if os.path.exists(project):
        rc, pevs, so, se = c.run_openscreen(["pack", project, "--out", take_dir, "--json"])
        pd = c.done_event(pevs)
        pack_ok = rc == 0 and pd is not None and pd.get("success")
        if not pack_ok:
            warnings.append("pack failed (%s); copied files instead" % (so + se)[-200:])
    if not pack_ok:
        copy_and_rewrite(project, video, cursor, take_dir)

    new_video = os.path.join(take_dir, os.path.basename(video))
    new_cursor = c.telemetry_path(new_video)
    if not os.path.exists(new_cursor):
        new_cursor = None
    try:
        info = c.media_info(new_video)
    except RuntimeError:
        info = None
        warnings.append("gathered video is not readable by ffprobe")
    if info and not keep and os.path.realpath(new_video) != os.path.realpath(video) \
            and os.path.exists(video) and os.path.getsize(new_video) == os.path.getsize(video):
        for p in (video, cursor, video[:-4] + ".session.json"):
            if p and os.path.exists(p):
                os.remove(p)

    if info and (st.get("mic") or st.get("systemAudio")):
        if info["audio_tracks"] == 0:
            warnings.append("audio was requested but the take has no audio track")
        elif c.max_volume_db(new_video, 60) == float("-inf"):
            warnings.append("the take's audio is digital silence. " + (
                c.MIC_PERMISSION_MSG if st.get("mic") else "Nothing was playing."))
    tel = telemetry_stats(new_cursor) if new_cursor else None
    if tel is not None and st.get("cursor") == "editable-overlay":
        if not tel["visible"]:
            warnings.append("the pointer never entered the recorded area (no cursor to draw, no click zooms)")
        elif tel["samples"] > 50 and not tel["clicks"]:
            warnings.append("no clicks in the telemetry; if there were clicks: " + c.ACCESSIBILITY_MSG)

    st.update(status="collected", stoppedAt=c.now(), how=how)
    with open(os.path.join(take_dir, "take.json"), "w") as f:
        json.dump(st, f, indent=2)
    os.remove(os.path.join(demo, STATE))
    vi = {k: info[k] for k in ("width", "height", "fps", "duration", "audio_tracks")} if info else None
    print(json.dumps({"ok": True, "status": status, "take": st["take"], "takeDir": take_dir,
                      "project": project, "video": new_video, "cursor": new_cursor,
                      "durationMs": duration_ms, "video_info": vi, "telemetry": tel, "warnings": warnings}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
