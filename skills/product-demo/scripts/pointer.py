#!/usr/bin/env python3
"""Scripted pointer for mode B (the agent drives the app): eased moves, clicks, typing.

usage: pointer.py check
       pointer.py move X Y [--ms 700]          ease the real pointer to screen point X,Y
       pointer.py click X Y [--ms 700] [--double] [--right]
       pointer.py drag X1 Y1 X2 Y2 [--ms 900]
       pointer.py type TEXT
       pointer.py key KEY                      e.g. return, esc, tab, arrow-down
       pointer.py where                        print the pointer position

Coordinates are global screen points (top-left of the main display is 0,0). Moves are real
pointer movements (smoothstep-eased, about 60 steps per second) so OpenScreen's cursor
telemetry records them and click zooms work. Uses cliclick (brew install cliclick).

macOS only lets this work when the app hosting the shell (your terminal, or the agent's
desktop app) is allowed under System Settings > Privacy & Security > Accessibility. Without
it cliclick does nothing and reports success; this script detects that and exits 3 with the
exact switch to turn on. Granting Accessibility to cliclick or Openscreen is not enough.
"""
import os
import shutil
import subprocess
import sys
import time

DENIED = ("Accessibility privileges not enabled", "not allowed to send keystrokes", "not trusted")


def host_app():
    hint = os.environ.get("TERM_PROGRAM") or os.environ.get("__CFBundleIdentifier")
    return "the app that runs this shell" + (" (%s)" % hint if hint else "")


def fail_access():
    sys.stderr.write(
        "error: macOS blocked scripted pointer control. Turn on %s in System Settings > Privacy & "
        "Security > Accessibility, then restart it and try again. (Allowing cliclick or Openscreen "
        "is not enough: macOS checks the app hosting the shell.) Until then the user performs the "
        "demo (mode A), or use your harness's own desktop-control tool if it has one.\n" % host_app())
    sys.exit(3)


def cli(*args):
    exe = shutil.which("cliclick")
    if not exe:
        sys.exit("error: cliclick not found (brew install cliclick)")
    r = subprocess.run([exe] + list(args), capture_output=True, text=True)
    text = r.stdout + r.stderr
    if any(d in text for d in DENIED):
        fail_access()
    if r.returncode != 0:
        sys.exit("error: cliclick failed: %s" % text.strip())
    return r.stdout.strip()


def where():
    x, y = cli("p").split(",")
    return float(x), float(y)


def at(x, y):
    """cliclick coordinates. A bare leading minus means a relative move, so absolute negative
    values (a display left of or above the main one) need the "=" prefix."""
    return ",".join(("=%d" if v < 0 else "%d") % v for v in (round(x), round(y)))


def ease_to(x, y, ms, verb="m"):
    """verb "m" moves; "dm" continues a drag (apps ignore plain moves while the button is down)."""
    x0, y0 = where()
    steps = max(2, int(ms / 16))
    for i in range(1, steps + 1):
        u = i / float(steps)
        u = u * u * (3 - 2 * u)
        cli("%s:%s" % (verb, at(x0 + (x - x0) * u, y0 + (y - y0) * u)))
        time.sleep(ms / 1000.0 / steps)
    if abs(where()[0] - x) > 2 or abs(where()[1] - y) > 2:
        fail_access()  # cliclick reported success but the pointer did not move


def opt(args, name, default):
    if name in args:
        i = args.index(name)
        v = args[i + 1]
        del args[i:i + 2]
        return float(v)
    return default


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 1
    cmd, args = argv[0], argv[1:]
    ms = opt(args, "--ms", 700)
    flags = {f for f in ("--double", "--right") if f in args}
    args = [x for x in args if x not in flags]
    if cmd == "check":
        x, y = where()
        moved = False
        for dx in (3, -3):  # at a screen edge the pointer can only move inwards
            cli("m:" + at(x + dx, y))
            moved = moved or abs(where()[0] - (x + dx)) <= 1
        cli("m:" + at(x, y))
        if not moved:
            fail_access()
        print("ok")
    elif cmd == "where":
        print("%d,%d" % where())
    elif cmd == "move":
        ease_to(float(args[0]), float(args[1]), ms)
    elif cmd == "click":
        ease_to(float(args[0]), float(args[1]), ms)
        time.sleep(0.12)
        cli(("rc:" if "--right" in flags else "dc:" if "--double" in flags else "c:") + ".")
    elif cmd == "drag":
        ease_to(float(args[0]), float(args[1]), ms / 2)
        cli("dd:.")
        ease_to(float(args[2]), float(args[3]), ms, "dm")
        cli("du:.")
    elif cmd == "type":
        cli("-w", "40", "t:" + " ".join(args))
    elif cmd == "key":
        cli("kp:" + args[0])
    else:
        sys.exit("error: unknown command %r (see --help)" % cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
