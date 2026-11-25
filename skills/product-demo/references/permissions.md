# Permissions and troubleshooting

Preflight never checks permissions. Each one surfaces the first time it is needed, and the
scripts name the exact switch. Tell the user plainly; never change settings for them.

| Feature | App that needs it | System Settings > Privacy & Security > | Symptom when missing |
|---|---|---|---|
| Recording a window | **Openscreen** | Screen & System Audio Recording | sources/record-start: "macOS refused screen capture..." (OpenScreen's "Failed to get sources") |
| System audio | Openscreen | Screen & System Audio Recording | silent audio track |
| Live narration (`--mic`) | **Openscreen** | Microphone | first use: a prompt, record-start says `waiting`; denied: a silent track, record-stop warns |
| Clicks and cursor shapes in telemetry | **Openscreen** | Accessibility | record-stop warns "no clicks in the telemetry"; no click zooms |
| Dub (`record-dub.py`) | **the app running the shell** (terminal or agent app) | Microphone | exits 4 after 12 s: "microphone did not open" |
| Mode B scripted pointer (`pointer.py`) | **the app running the shell** | Accessibility | exits 3 with the switch to turn on. Granting cliclick or Openscreen is not enough. |

After turning a switch on, macOS often requires quitting and reopening the app concerned
(for the shell's app: restart the terminal or agent app). If a switch is on but capture still
fails, toggle it off and on once.

## Troubleshooting

| Problem | Fix |
|---|---|
| `no on-screen window title contains ...` | The window is minimised, on another Space, behind a full-screen app, or titled differently. The message lists open windows. |
| `"X" matches 2 windows` | Use a longer part of the title. |
| `a recording from this folder is already running` / `previous take has not been collected` | `record-stop.py DEMO` (collects or salvages it). |
| record-start `waiting` | A permission prompt is on screen. Ask the user to answer it; `record-status.py DEMO` shows when capture begins; `record-stop.py DEMO` cancels. |
| Telemetry has 0 visible samples | The pointer never entered the window: no drawn cursor, no click zooms. Fine for plain, or add zooms by hand. |
| Export fails with a validation message | Usually a hand-edited edit.json field; `edit.py summary edit.json` names the problem. |
| Output not 1920x1080 | Check `"aspect": "16:9"` and the default `--quality good`. |
| Captions too small | `"captions": {"style": {"fontSize": 72}}`. |
| Sped-up stretch sounds like chatter | Do not speed up speech; cut instead. |
| `pointer.py check` exits 3 | See the table above; meanwhile the user performs (mode A). |

## First run on a new Mac (not verified end to end)

1. `brew install --cask openscreen ffmpeg` (optional: `whisper-cpp`, `cliclick`).
2. The first `sources.py` or `record-start.py` triggers the Screen Recording request for
   Openscreen; the user allows it in System Settings and may need to run the command again.
3. Turn on Accessibility for Openscreen to get click telemetry (needed for click zooms).
4. `scripts/selftest.sh` checks the editing half without any permission.
