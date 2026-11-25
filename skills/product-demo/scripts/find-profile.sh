#!/bin/bash
# find-profile.sh [START_DIR]
# Print the path of the user's demo-profile.md, or exit 1 with no output when there is none.
# Looks in START_DIR (default: the current folder), then each parent folder, then for a
# path to a demo-profile.md named in a CLAUDE.md or AGENTS.md (in those same folders,
# ~/.claude/CLAUDE.md, ~/.codex/AGENTS.md). Reads files only.
case "${1:-}" in -h|--help) sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 0;; esac
d=$(cd "${1:-.}" 2>/dev/null && pwd) || exit 1
dirs=()
while :; do
  dirs+=("$d")
  [ -f "$d/demo-profile.md" ] && { echo "$d/demo-profile.md"; exit 0; }
  [ "$d" = "/" ] && break
  d=$(dirname "$d")
done
for f in "${dirs[@]/%//CLAUDE.md}" "${dirs[@]/%//AGENTS.md}" "$HOME/.claude/CLAUDE.md" "$HOME/.codex/AGENTS.md"; do
  [ -f "$f" ] || continue
  # A path with spaces must be wrapped in backticks or double quotes.
  p=$(grep -oE '[`"](~|/)[^`"<>]*demo-profile\.md[`"]' "$f" | head -n 1 | tr -d '`"')
  [ -n "$p" ] || p=$(grep -oE '(~|/)[^ `"()<>]*demo-profile\.md' "$f" | head -n 1)
  [ -n "$p" ] || continue
  p="${p/#\~/$HOME}"
  [ -f "$p" ] && { echo "$p"; exit 0; }
done
exit 1
