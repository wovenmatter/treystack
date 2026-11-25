#!/bin/bash
# preflight.sh [--transcribe] [--drive]
# Cheapest check that the tools this skill needs exist. PATH lookups and file tests only:
# no network, launches nothing, does not check permissions (those surface when used).
# Prints "ok" (exit 0), or one "missing <tool>: <install hint>" line per missing tool (exit 1).
#   always:        Openscreen.app (or $OPENSCREEN_APP), ffmpeg, ffprobe, ffplay, python3
#   --transcribe:  whisper-cli and its model (narration captions, dub captions)
#   --drive:       cliclick (agent drives the app with a scripted pointer)
case "${1:-}" in -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0;; esac

missing=()
app=""
for c in "${OPENSCREEN_APP:-}" /Applications/Openscreen.app "$HOME/Applications/Openscreen.app"; do
  [ -n "$c" ] && [ -x "$c/Contents/MacOS/Openscreen" ] && { app=$c; break; }
done
[ -n "$app" ] || missing+=("Openscreen.app: brew install --cask openscreen (or set OPENSCREEN_APP)")
for t in ffmpeg ffprobe ffplay; do
  command -v $t >/dev/null 2>&1 || missing+=("$t: brew install ffmpeg")
done
command -v python3 >/dev/null 2>&1 || missing+=("python3: xcode-select --install")
for arg in "$@"; do case "$arg" in
  --transcribe)
    command -v whisper-cli >/dev/null 2>&1 || missing+=("whisper-cli: brew install whisper-cpp")
    m="${WHISPER_MODELS_DIR:-$HOME/.cache/whisper.cpp}/ggml-${WHISPER_MODEL:-base.en}.bin"
    [ -f "$m" ] || missing+=("whisper model $m: transcribe.py --download (one-time, about 148 MB from huggingface.co)");;
  --drive)
    command -v cliclick >/dev/null 2>&1 || missing+=("cliclick: brew install cliclick");;
esac; done

if [ ${#missing[@]} -eq 0 ]; then echo ok; exit 0; fi
printf 'missing %s\n' "${missing[@]}"
exit 1
