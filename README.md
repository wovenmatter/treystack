# treystack

The agent skills I use every day.

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

## Make them yours

These are starting points. Edit them. Put personal settings in your
`CLAUDE.md` or `AGENTS.md` so you can update the skills without losing them.

## License

[MIT](LICENSE)
