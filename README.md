# Obsidian Wiki Skill

This repository is the source of truth for the local `obsidian-wiki` Agent Skill.

The skill persists codebase knowledge into an Obsidian vault as per-repository wiki documents. The same skill package can be installed for Codex, Claude Code, and ForgeCode.

## Layout

- `SKILL.md`: agent-agnostic skill manifest and operating instructions.
- `scripts/obsidian_wiki.py`: deterministic scan/read/create/update tool for wiki documents.
- `config.json`: local default configuration used by the installed skill.
- `config.example.json`: portable configuration template.
- `docs/`: project documentation for maintainers.
- `Taskfile.yml`: local development tasks.

## Build

Run:

```bash
task build
```

The build task creates:

```text
dist/obsidian-wiki
```

Only runtime files are copied into the package.

## Install

Install for all supported agents:

```bash
task install
```

Or install one target:

```bash
task install:codex
task install:claude
task install:forge
```

The install targets copy the same built package into:

```text
~/.codex/skills/obsidian-wiki
~/.claude/skills/obsidian-wiki
~/.forge/skills/obsidian-wiki
```

Restart the target agent after installing or changing the skill so the skill manifest is reloaded.

## Verify

Run:

```bash
task verify
```

You can also run the built or installed script directly:

```bash
python dist/obsidian-wiki/scripts/obsidian_wiki.py --help
```

## Configuration

Configuration resolves in this order:

1. `OBSIDIAN_VAULT_PATH`
2. project-local `.agents/obsidian-wiki.json`
3. project-local `.codex/obsidian-wiki.json` for backward compatibility
4. project-local `.claude/obsidian-wiki.json` for backward compatibility
5. installed skill-local `config.json`

Default configuration targets:

```text
/Users/christian/vault/Hypatos/Wiki
```

## Update Workflow

1. Edit the source files in this repository.
2. Run `task verify`.
3. Run `task install`.
4. Start a new agent session.

The installed skill is a copied directory, so repository changes are not reflected globally until the install task runs again.
