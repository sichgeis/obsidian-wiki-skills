# Obsidian Wiki Codex Skill

This repository is the source of truth for the local Codex `obsidian-wiki` skill.

The skill persists codebase knowledge into an Obsidian vault as per-repository wiki documents. It mirrors the behavior of the related Claude and Forge skills while using Codex-specific installation and project override paths.

## Layout

- `SKILL.md`: Codex skill manifest and operating instructions.
- `scripts/obsidian_wiki.py`: deterministic scan/read/create/update tool for wiki documents.
- `config.json`: local default configuration used by the installed skill.
- `config.example.json`: portable configuration template.
- `docs/`: project documentation for maintainers.
- `Taskfile.dev.yml`: local development tasks.

## Install

Run:

```bash
task -t Taskfile.dev.yml install
```

The install task copies runtime files into:

```text
/Users/christian/.codex/skills/obsidian-wiki
```

Restart Codex after installing or changing the skill so the skill manifest is reloaded.

## Verify

Run:

```bash
task -t Taskfile.dev.yml verify
```

You can also run the installed script directly:

```bash
python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py --help
```

## Configuration

Configuration resolves in this order:

1. `OBSIDIAN_VAULT_PATH`
2. project-local `.codex/obsidian-wiki.json`
3. installed skill-local `config.json`

Default configuration targets:

```text
/Users/christian/vault/Hypatos/Wiki
```

## Update Workflow

1. Edit the source files in this repository.
2. Run `task -t Taskfile.dev.yml install`.
3. Start a new Codex session.

The installed skill is a copied directory, so repository changes are not reflected globally until the install task runs again.
