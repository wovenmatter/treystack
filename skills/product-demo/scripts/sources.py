#!/usr/bin/env python3
"""List what OpenScreen can record: windows, displays, microphones.

usage: sources.py [--json] [--timeout SECONDS]

Prints a compact list to show the user. --json prints
{"ok":true, "windows":[titles], "displays":[{index,name}], "microphones":[labels],
 "microphoneLabelsUnavailable":bool}.
Only on-screen windows are listed: minimised windows, windows on another Space or behind a
full-screen app are missing. Takes about a second (OpenScreen runs headless, no window).
Exit 0 on success, 1 on failure with a plain message (for example which permission to turn on).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0
    as_json = "--json" in argv
    timeout = float(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else 30
    app = c.require_app(as_json)
    try:
        src = c.get_sources(app, timeout=timeout)
    except RuntimeError as e:
        c.die(str(e), 1, as_json)
    windows = [w.get("name", "") for w in src.get("windows", [])]
    displays = [{"index": d.get("index"), "name": d.get("name")} for d in src.get("displays", [])]
    mics = [m.get("label", "") for m in src.get("microphones", []) if m.get("deviceId") != "default"] \
        or [m.get("label", "") for m in src.get("microphones", [])]
    if as_json:
        print(json.dumps({"ok": True, "windows": windows, "displays": displays, "microphones": mics,
                          "microphoneLabelsUnavailable": src.get("microphoneLabelsUnavailable", False)}))
        return 0
    print("Windows (record with --window '<part of title>'):")
    for w in windows or ["(none on screen)"]:
        print("  - " + w)
    print("Displays (record with --display <n>):")
    for d in displays:
        print("  %s: %s" % (d["index"], d["name"]))
    print("Microphones (record with --mic or --mic-device '<part of name>'):")
    if src.get("microphoneLabelsUnavailable"):
        print("  (names hidden until Openscreen has Microphone permission)")
    for m in mics or ["(none)"]:
        print("  - " + m)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
