# treystack

The agent skills I use every day. They work in Claude Code and Codex.

## Skills

| Skill | Say | What it does |
|---|---|---|
| _coming soon_ | | |

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
```

## Make them yours

These are starting points. Edit them. Put personal settings in your
`CLAUDE.md` or `AGENTS.md` so you can update the skills without losing them.

## License

[MIT](LICENSE)
