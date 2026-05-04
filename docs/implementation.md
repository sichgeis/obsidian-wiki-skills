# Implementation Notes

## Behavior

The Codex skill writes long-lived repository knowledge into an Obsidian vault under:

```text
{vault_path}/{wiki_dir}/{project-name}/
```

The script supports:

- `scan`: list Markdown documents for the active project, optionally filtered by query terms.
- `read`: print a vault-relative or absolute document path.
- `create`: create a new Markdown document with frontmatter, title heading, tags, and redacted content.
- `update`: append content or replace a named heading section.

All writes go through `scripts/obsidian_wiki.py`; agents should not edit wiki documents directly.

## Codex Adaptation

The implementation follows the Forge skill behavior but changes Codex-specific paths:

- Global install path: `/Users/christian/.codex/skills/obsidian-wiki`
- Project override config: `.codex/obsidian-wiki.json`
- Installed command examples in `SKILL.md` use the Codex global skill path.

## Configuration

Config precedence:

1. `OBSIDIAN_VAULT_PATH` overrides only `vault_path`.
2. `.codex/obsidian-wiki.json` overrides skill defaults for the active project.
3. `config.json` in the installed skill directory provides local defaults.

The script rejects writes outside the configured vault root.

## Installation

`Taskfile.dev.yml` copies only runtime files into Codex's global skills directory:

- `SKILL.md`
- `config.json`
- `scripts/obsidian_wiki.py`

Repository docs, examples, and development files are intentionally not installed as part of the skill runtime.
