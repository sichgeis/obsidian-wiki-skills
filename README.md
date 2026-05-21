# Obsidian Wiki Skill

This repository is the source of truth for the local `obsidian-wiki` Agent Skill.

The skill persists codebase knowledge into an Obsidian vault as per-repository wiki documents. The same skill package can be installed for Codex, Claude Code, and ForgeCode.

Existing wiki documents can be updated by appending content, replacing a named heading section, or rewriting the full article body with `update --mode rewrite`.
Created documents keep one generated top-level title heading; duplicate matching H1 headings in supplied content are removed automatically.
Search is backed by a lightweight JSON index at `{vault_path}/{wiki_dir}/.obsidian-wiki-index.json` when present, so agents can find likely matching notes from titles, tags, filenames, headings, ticket IDs, and short excerpts without reading every note body. Old notes can be archived reversibly under `{vault_path}/{wiki_dir}/_archive/{project}/`.

## Layout

- `SKILL.md`: agent-agnostic skill manifest and operating instructions.
- `commands/`: slash-command wrappers that invoke the skill from supported agents.
- `scripts/obsidian_wiki.py`: deterministic scan/read/create/update/index/archive/doctor tool for wiki documents.
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

They also install the `document` command into each agent's command location:

```text
~/.codex/prompts/document.md
~/.claude/commands/document.md
~/.agents/commands/document.md
```

Use it as `/document ...` in Codex and Claude Code. In ForgeCode, use the native command form `:document ...`.

Restart the target agent after installing or changing the skill so the skill manifest is reloaded.

## Codex Permissions

For fast documentation runs in Codex, approve this command prefix when prompted:

```text
python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py
```

Codex approvals are command-prefix based, not skill-name based. There is no separate "allow this whole skill" switch in `SKILL.md`; permission belongs in Codex's sandbox, approval policy, and rules configuration.

To make the permission durable, add a Codex rule in `~/.codex/rules/default.rules` and restart Codex:

```starlark
prefix_rule(
    pattern = ["python", "/Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py"],
    decision = "allow",
    justification = "Allow the vetted Obsidian wiki skill helper without repeated prompts",
    match = [
        "python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py scan",
        "python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py index status",
        "python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py doctor",
    ],
    not_match = [
        "python /Users/christian/.codex/skills/other-skill/scripts/obsidian_wiki.py scan",
        "python /Users/christian/.codex/skills/obsidian-wiki/scripts/other.py",
    ],
)
```

This trusts invocations of that helper script through the matching prefix; it is not a fine-grained audit of every file write or subprocess inside Python. Keep the helper small, deterministic, and path-constrained.

The skill instructions prefer inline `--content` for create and update operations, which avoids a separate temporary-file creation step. Use `--content-file` only for notes that are too large or awkward to quote inline.

## Search Index

Build or refresh the wiki search index with:

```bash
python dist/obsidian-wiki/scripts/obsidian_wiki.py index rebuild
```

Check index freshness and resolved paths with:

```bash
python dist/obsidian-wiki/scripts/obsidian_wiki.py index status
python dist/obsidian-wiki/scripts/obsidian_wiki.py doctor
```

`scan --query` uses the index when it exists and falls back to direct Markdown scanning when it does not. Successful `create` and `update` operations refresh their affected index entry automatically if an index already exists.

## Archive

List old-note candidates without changing files:

```bash
python dist/obsidian-wiki/scripts/obsidian_wiki.py archive candidates --older-than-days 90
```

Scan all active project wiki folders instead of only the detected project:

```bash
python dist/obsidian-wiki/scripts/obsidian_wiki.py archive candidates --older-than-days 90 --global
```

Durable notes such as project overviews, architecture notes, runbooks, and glossary entries are excluded from normal candidates. Include them only for explicit force requests:

```bash
python dist/obsidian-wiki/scripts/obsidian_wiki.py archive candidates --older-than-days 90 --force
```

Archive and restore explicit paths:

```bash
python dist/obsidian-wiki/scripts/obsidian_wiki.py archive apply \
  --path "Wiki/my-project/old-ticket.md" \
  --reason "superseded by current runbook"

python dist/obsidian-wiki/scripts/obsidian_wiki.py archive restore \
  --path "Wiki/_archive/my-project/old-ticket.md"
```

Archived notes move to `Wiki/_archive/{project}/`, keep their content, and get archive metadata in frontmatter. Normal `scan` excludes archived notes; use `scan --include-archived` to find them explicitly.

## Verify

Run:

```bash
task verify
```

This builds the package, checks the script entrypoint, and runs the unit tests.

After installing, verify agent-specific installs with:

```bash
task verify:codex
task verify:claude
task verify:forge
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
