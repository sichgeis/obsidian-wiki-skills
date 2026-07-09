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

`archive apply` moves the file, preserves its body, and adds frontmatter fields: `archived`, `archived_at`, `archived_reason`, and `original_path`. If the active project directory becomes empty after the move, it is removed. `archive restore` uses `original_path`, recreates the original project directory as needed, fails if the destination already exists, and removes the archive project directory when it becomes empty.

Normal `scan` excludes archived notes. `scan --include-archived` returns archived entries with archive metadata. The index includes active and archived notes so archive and restore keep search state fresh without requiring a full rebuild.

`archive candidates` is intentionally read-only. It scans the detected project by default; passing `--global` scans every active project folder under the wiki root and includes the project name in each candidate. It uses the note `updated` timestamp and excludes durable tags such as `project-overview`, `architecture`, `runbook`, and `glossary` by default. Passing `--force` includes those durable notes and marks them as `old_durable_note`, so explicit force requests can still surface every age-matching note before `archive apply` moves selected paths.

## Agent Package

The repository builds one agent-agnostic skill package. The same `SKILL.md`, `config.json`, CLI helper, MCP server, and dependency declaration are copied to each supported agent location:

- Codex: `~/.codex/skills/obsidian-wiki`
- Claude Code: `~/.claude/skills/obsidian-wiki`
- ForgeCode: `~/.forge/skills/obsidian-wiki`

The skill instructions avoid agent-specific paths. Agents should resolve the script relative to the loaded skill directory.

## MCP Server

`scripts/obsidian_wiki_mcp.py` is a stdio MCP server built with the Python MCP SDK. It is an additional runtime surface over the same domain functions as `scripts/obsidian_wiki.py`; it does not implement a separate write path.

The server exposes typed tools for scan, read, create, update, add-frontmatter, index status/rebuild, archive candidates/apply/restore/cleanup/status, and doctor diagnostics. Each tool resolves the active project root, configuration, and project name before calling the existing helper functions. Optional `project_root` and `project` arguments let MCP clients override those values when their server process cwd is not the repository being documented.

Codex and other MCP clients normally launch the server command as a child process:

```text
python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki_mcp.py
```

The process stays alive while the MCP client uses it and exits when the client disconnects. The Python environment that launches the server must have `requirements.txt` installed.

## Document Command

The repository also installs a `document` command wrapper for each supported agent. The wrapper asks the active agent to inspect the current project, use the `obsidian-wiki` skill, and write or update a wiki page for the supplied topic.

- Codex: `~/.codex/prompts/document.md`, invoked as `/document ...`.
- Claude Code: `~/.claude/commands/document.md`, invoked as `/document ...`.
- ForgeCode: `~/.agents/commands/document.md`, invoked as `:document ...`.

The command files are thin wrappers. The actual wiki behavior remains governed by `SKILL.md` and `scripts/obsidian_wiki.py`.

## Codex Approvals

Codex should run the installed script directly with a reusable command prefix matching the Python command available in the agent environment:

```text
python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py
```

Use `python3` instead when that is the command the agent will actually run:

```text
python3 /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py
```

Codex approvals are command-prefix based, not skill-name based. This repository cannot declare a semantic "allow all obsidian-wiki skill calls" rule by itself. The interpreter token is part of the matched prefix, so `python .../obsidian_wiki.py` and `python3 .../obsidian_wiki.py` need separate rules. The command allowlist is also separate from filesystem sandboxing: the helper can be an approved command and still need escalated sandbox permissions when it writes to an Obsidian vault outside the active workspace.

The operational distinction matters:

- Read-only helper calls such as `scan`, `read`, `doctor`, `index status`, and `archive candidates` should run without escalated sandbox permissions.
- Write-like helper calls such as `create`, `update`, `add-frontmatter`, `index rebuild`, `archive apply`, `archive restore`, and `archive cleanup` need escalated sandbox permissions when the vault is outside the writable workspace.
- If the helper prefix is already allowlisted, agents should not pass another `prefix_rule` for routine wiki commands. When the tool API requires a `justification` for escalation, the wording should be terse and operational instead of asking the user for another durable approval.
- Agents should suggest a durable prefix rule only when the helper prefix is missing, the command was denied, or the command shape does not match the existing rule.

For durable allowlisting, configure Codex Rules outside the skill, for example in `~/.codex/rules/default.rules`:

```starlark
prefix_rule(
    pattern=["python", "/Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py"],
    decision="allow",
    justification="Allow the vetted Obsidian wiki helper without repeated prompts",
)
```

For `python3` environments, use the same rule with `pattern=["python3", "/Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py"]`.

This allowlist trusts commands that start with the matching script prefix. It does not inspect every file write, network call, or subprocess inside the Python process, so the helper should remain small, deterministic, and constrained to the configured vault.

`SKILL.md` tells Codex to keep the allowlisted helper invocation simple. Inline `--content` is appropriate for short, simple, single-line content. Multiline or quote-heavy Markdown should be passed with `--content-file` from a sandbox-writable temporary path such as `/private/tmp`. This avoids shell-heavy command shapes, including here-docs, `$'...'` strings, command substitutions, redirections, and long `/bin/zsh -lc ...` payloads. Those forms can fail Codex's conservative command-prefix matching even when the underlying Python helper prefix is allowlisted.

Good allowlisted write shape:

```text
sandbox_permissions=require_escalated + exact installed helper command + --content-file /private/tmp/wiki-update.md + no prefix_rule
```

Avoid for already-allowlisted helpers:

```text
sandbox_permissions=require_escalated + shell wrapper or inline multiline content + repeated prefix_rule request
```

In a normal `workspace-write` session, the repository is writable but `/Users/christian/vault/Hypatos` is not necessarily part of the sandbox. For commands that create, update, archive, restore, clean up, or rebuild the index, Codex should therefore invoke the exact installed helper command with escalated sandbox permissions. If the prefix rule above is loaded, the escalation should be covered by the existing approval and should not produce a new prompt. An alternative is launching Codex with `--add-dir /Users/christian/vault/Hypatos`, which makes the vault an explicit writable root for the session.

The helper allowlist is separate from repository maintenance. Installing the source package with `task install`, `task install:codex`, `task install:claude`, or `task install:forge` writes outside the active workspace into agent configuration directories. Those commands need their own approval/rules and should only be run when the installed skill copy must be refreshed, not during routine wiki note writes.

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
- `requirements.txt`
- `scripts/obsidian_wiki.py`
- `scripts/obsidian_wiki_mcp.py`
- `commands/document.md`
- `commands/forge-document.md`

It also copies the relevant command wrapper into the target agent command directory. Repository docs, examples, and development files are intentionally not installed as part of the skill runtime.
