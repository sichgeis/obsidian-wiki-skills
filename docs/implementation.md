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
- `update`: append content, replace a named heading section, or rewrite the full article body.
- `index rebuild`: build a lightweight search index for all project wiki Markdown documents.
- `index status`: report whether the index exists and has the expected document count.
- `archive candidates`: list old active notes that may be safe to archive.
- `archive apply`: move one explicit active note into the archive.
- `archive restore`: move one archived note back to its original path.
- `archive status`: report active and archived note counts for the current project.
- `doctor`: print resolved project, configuration, vault, wiki, and index diagnostics.

All writes go through `scripts/obsidian_wiki.py`; agents should not edit wiki documents directly.
Create removes a duplicate leading H1 from supplied content when it matches the generated document title, so notes keep a single top-level title heading.
Use `update --mode rewrite` when a note is outdated enough that append or section replacement would preserve misleading stale content.

## Search Index

The optional search index is stored at:

```text
{vault_path}/{wiki_dir}/.obsidian-wiki-index.json
```

Each entry stores compact metadata: vault-relative path, project, title, tags, updated timestamp, headings, a short excerpt, normalized lexical tokens, and ticket IDs such as `BACKEND-2242`. `scan --query` uses the index when present and falls back to direct project-folder Markdown scanning when absent.

Successful `create` and `update` operations refresh only the affected index entry when an index already exists. They do not create the index implicitly; use `index rebuild` to opt into indexed search.

## Archive

Archived notes are stored under:

```text
{vault_path}/{wiki_dir}/_archive/{project-name}/
```

`archive apply` moves the file, preserves its body, and adds frontmatter fields: `archived`, `archived_at`, `archived_reason`, and `original_path`. `archive restore` uses `original_path` and fails if the destination already exists.

Normal `scan` excludes archived notes. `scan --include-archived` returns archived entries with archive metadata. The index includes active and archived notes so archive and restore keep search state fresh without requiring a full rebuild.

`archive candidates` is intentionally read-only. It scans the detected project by default; passing `--global` scans every active project folder under the wiki root and includes the project name in each candidate. It uses the note `updated` timestamp and excludes durable tags such as `project-overview`, `architecture`, `runbook`, and `glossary` by default. Passing `--force` includes those durable notes and marks them as `old_durable_note`, so explicit force requests can still surface every age-matching note before `archive apply` moves selected paths.

## Agent Package

The repository builds one agent-agnostic skill package. The same `SKILL.md`, `config.json`, and `scripts/obsidian_wiki.py` are copied to each supported agent location:

- Codex: `~/.codex/skills/obsidian-wiki`
- Claude Code: `~/.claude/skills/obsidian-wiki`
- ForgeCode: `~/.forge/skills/obsidian-wiki`

The skill instructions avoid agent-specific paths. Agents should resolve the script relative to the loaded skill directory.

## Document Command

The repository also installs a `document` command wrapper for each supported agent. The wrapper asks the active agent to inspect the current project, use the `obsidian-wiki` skill, and write or update a wiki page for the supplied topic.

- Codex: `~/.codex/prompts/document.md`, invoked as `/document ...`.
- Claude Code: `~/.claude/commands/document.md`, invoked as `/document ...`.
- ForgeCode: `~/.agents/commands/document.md`, invoked as `:document ...`.

The command files are thin wrappers. The actual wiki behavior remains governed by `SKILL.md` and `scripts/obsidian_wiki.py`.

## Codex Approvals

Codex should run the installed script directly with this reusable command prefix:

```text
python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py
```

Codex approvals are command-prefix based, not skill-name based. This repository cannot declare a semantic "allow all obsidian-wiki skill calls" rule by itself. For durable allowlisting, configure Codex Rules outside the skill, for example in `~/.codex/rules/default.rules`:

```starlark
prefix_rule(
    pattern = ["python", "/Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py"],
    decision = "allow",
    justification = "Allow the vetted Obsidian wiki skill helper without repeated prompts",
    match = [
        "python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py scan",
        "python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py index status",
    ],
    not_match = [
        "python /Users/christian/.codex/skills/obsidian-wiki/scripts/other.py",
    ],
)
```

This allowlist trusts commands that start with the matching script prefix. It does not inspect every file write, network call, or subprocess inside the Python process, so the helper should remain small, deterministic, and constrained to the configured vault.

`SKILL.md` tells Codex to prefer inline `--content` for create and update operations. That keeps the workflow to a single Python command and avoids an extra approval for creating a temporary Markdown file. `--content-file` remains available for very large notes or content that is impractical to pass as one shell argument.

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
- `commands/document.md`
- `commands/forge-document.md`

It also copies the relevant command wrapper into the target agent command directory. Repository docs, examples, and development files are intentionally not installed as part of the skill runtime.
