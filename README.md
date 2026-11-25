# treystack

The agent skills I use every day. They work in Claude Code and Codex.

## Skills

| Skill | Say | What it does |
|---|---|---|
| [product-demo](skills/product-demo) | "record a demo of my app" | Records an app on screen (you perform, or the agent drives) and hands back a short, cut 1080p demo video for X, a landing page or a blog. Zooms, speed-ups, blur, music, narration or dub, captions. macOS. |

## Install

```bash
git clone https://github.com/wovenmatter/treystack
cp -R treystack/skills/* ~/.claude/skills/   # Claude Code
cp -R treystack/skills/* ~/.codex/skills/    # Codex
```

## Layout

Each skill lives in its own folder under `skills/`:

```
skills/
  <skill-name>/
    SKILL.md      # frontmatter (name, description) + instructions
    scripts/      # optional helpers the skill calls
    references/   # optional detail the skill reads only when needed
```

## Requirements

**product-demo** runs on macOS and needs:

```bash
brew install --cask openscreen   # screen capture and rendering, used only through its CLI
brew install ffmpeg              # includes ffprobe and ffplay
brew install whisper-cpp         # optional: captions from your voice
brew install cliclick            # optional: the agent drives the app itself
```

On first use macOS asks you to allow **Openscreen** under System Settings > Privacy & Security:
Screen & System Audio Recording (to record a window), Accessibility (to record clicks, which
drive the automatic zooms) and Microphone (only if you narrate while recording). Recording a
dub over the finished cut, or letting the agent drive the pointer, needs Microphone or
Accessibility for the app that runs your agent or terminal. Run
`skills/product-demo/scripts/selftest.sh` to check the editing half without recording anything.

## Make them yours

These are starting points. Edit them. Put personal settings in your
`CLAUDE.md` or `AGENTS.md` so you can update the skills without losing them.

## License

[MIT](LICENSE)
