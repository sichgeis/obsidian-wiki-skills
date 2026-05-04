# Implementation Notes

## Behavior

The skill writes long-lived repository knowledge into an Obsidian vault under:

```text
{vault_path}/{wiki_dir}/{project-name}/
```

The script supports:

- `scan`: list Markdown documents for the active project, optionally filtered by query terms.
- `read`: print a vault-relative or absolute document path.
- `create`: create a new Markdown document with frontmatter, title heading, tags, and redacted content.
- `update`: append content or replace a named heading section.

All writes go through `scripts/obsidian_wiki.py`; agents should not edit wiki documents directly.

## Agent Package

The repository builds one agent-agnostic skill package. The same `SKILL.md`, `config.json`, and `scripts/obsidian_wiki.py` are copied to each supported agent location:

- Codex: `~/.codex/skills/obsidian-wiki`
- Claude Code: `~/.claude/skills/obsidian-wiki`
- ForgeCode: `~/.forge/skills/obsidian-wiki`

The skill instructions avoid agent-specific paths. Agents should resolve the script relative to the loaded skill directory.

## Configuration

Config precedence:

1. `OBSIDIAN_VAULT_PATH` overrides only `vault_path`.
2. `.agents/obsidian-wiki.json` overrides skill defaults for the active project.
3. `.codex/obsidian-wiki.json` is supported as a legacy project override.
4. `.claude/obsidian-wiki.json` is supported as a legacy project override.
5. `config.json` in the installed skill directory provides local defaults.

The script rejects writes outside the configured vault root.

## Installation

`Taskfile.yml` first builds `dist/obsidian-wiki`, then copies only runtime files into the selected agent skill directory:

- `SKILL.md`
- `config.json`
- `scripts/obsidian_wiki.py`

Repository docs, examples, and development files are intentionally not installed as part of the skill runtime.
