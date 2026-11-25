#!/bin/bash
# selftest.sh [WORK_DIR]
# Checks the editing half of the skill on this machine without recording anything and without
# any permission: makes synthetic app footage with cursor telemetry, then runs
# edit.py new -> plan-zooms.py -> propose-cuts.py -> export.py (plain, then polished from the
# 2x working copy a 1x-sized take gets) ->
# frames.py -> phone-preview.py -> add-music.py (a generated tone) -> encode-final.py.
# Prints one line per step and "selftest ok" at the end (exit 0), or the failing step (exit 1).
# Takes about 30 s. WORK_DIR defaults to a new temporary folder (kept, path printed).
case "${1:-}" in -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0;; esac
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
W=${1:-$(mktemp -d "${TMPDIR:-/tmp}/product-demo-selftest.XXXXXX")}
mkdir -p "$W/takes/take-1" "$W/drafts" "$W/audio" "$W/check"
cd "$W" || exit 1
step() { local name=$1; shift; local t0=$SECONDS
  if "$@" > "$W/check/$name.log" 2>&1; then printf 'ok    %-14s %3ss\n' "$name" $((SECONDS - t0))
  else printf 'FAIL  %-14s (log: %s)\n' "$name" "$W/check/$name.log"; tail -5 "$W/check/$name.log"; exit 1; fi; }
expect() { local name=$1 file=$2 want=$3
  got=$(ffprobe -v error -show_entries stream=width,height -of csv=p=0:s=x "$file" | head -1)
  [ "$got" = "$want" ] && printf 'ok    %-14s %s\n' "$name" "$got" || { printf 'FAIL  %-14s got %s, want %s\n' "$name" "$got" "$want"; exit 1; }; }

echo "selftest in $W"
step preflight   "$HERE/preflight.sh"
step footage     python3 "$HERE/make-test-footage.py" takes/take-1/take --width 1280 --height 720 --fps 30 --duration 30
# real silent takes have no audio track; OpenScreen adds a silent one that encode-final must drop
step mute        ffmpeg -nostdin -v error -y -i takes/take-1/take.mp4 -an -c copy takes/take-1/take-silent.mp4
mv takes/take-1/take-silent.mp4 takes/take-1/take.mp4
step edit-new    python3 "$HERE/edit.py" new takes/take-1/take.mp4 -o edit.json
step zooms       python3 "$HERE/plan-zooms.py" --edit edit.json --write
step cuts        python3 "$HERE/propose-cuts.py" --edit edit.json --write
step summary     python3 "$HERE/edit.py" summary edit.json
grep -q "phone-legible" check/summary.log || { echo "FAIL  summary has no phone-legible zoom"; exit 1; }
sed 's/"look": "polished"/"look": "plain"/' edit.json > edit-plain.json
step export-plain python3 "$HERE/export.py" edit-plain.json -o drafts/plain.mp4 --quiet
expect plain drafts/plain.mp4 1920x1080
[ ! -e takes/take-1/take.x2.mp4 ] && echo "ok    plain          no upscaled copy" || { echo "FAIL  plain look made an upscaled copy"; exit 1; }
step export      python3 "$HERE/export.py" edit.json -o drafts/polished.mp4 --quiet
expect polished drafts/polished.mp4 1920x1080
expect upscaled takes/take-1/take.x2.mp4 2560x1440
step frames      python3 "$HERE/frames.py" drafts/polished.mp4 --count 8 --sheet-only --out check/frames
step phone       python3 "$HERE/phone-preview.py" drafts/polished.mp4 --at 5,12 -o check/phone.png
step tone        ffmpeg -nostdin -v error -y -f lavfi -i "sine=f=330:d=40" -f lavfi -i "sine=f=495:d=40" -filter_complex amix=inputs=2 -ac 2 audio/music.m4a
step music       python3 "$HERE/add-music.py" drafts/polished.mp4 audio/music.m4a drafts/music.mp4 --volume -6
step final       python3 "$HERE/encode-final.py" drafts/music.mp4 final.mp4
expect final final.mp4 1920x1080
step final-silent python3 "$HERE/encode-final.py" drafts/polished.mp4 final-silent.mp4
[ -z "$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 final-silent.mp4)" ] \
  && echo "ok    silent-final   no audio track" || { echo "FAIL  silent final has an audio track"; exit 1; }
echo "look at: $W/check/frames/sheet_01.png and $W/check/phone.png"
echo "selftest ok"
