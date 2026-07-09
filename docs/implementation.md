# Implementation Notes

## Document Role

This document describes the current implementation. Use `docs/agent-implementation-tracker.md` for pass-by-pass planning, phase status, backlog tracking, and acceptance criteria. Use `docs/fundus-target-picture.md` for stable product decisions, corpus findings, OKF profile, and target architecture.

## Current Corpus State

The current local knowledge corpus lives under `/Users/christian/vault/Hypatos/Fundus`.

The old `Wiki/` corpus was migrated on 2026-07-09 through `migrate wiki-to-fundus`, verified, backed up, and retired as `/Users/christian/vault/Hypatos/Wiki.migrated-20260709T182817+0200-wiki-to-fundus-resume`. The migration preserved archived notes under `Fundus/_archive/`, removed frontmatter from active reserved `index.md` and `log.md` files, rebuilt the index, and verified structure plus retrieval smoke checks.

`Fundus/` is now the single canonical personal work knowledge base. Recovery should rely on `.fundus-backups/`, the retired `Wiki.migrated-*` tree, and archive storage, not on a parallel live `Wiki/` source.

## Behavior

The skill writes long-lived repository knowledge and cross-repository area knowledge into an Obsidian vault under:

```text
{vault_path}/{fundus_dir}/{project-name}/
{vault_path}/{fundus_dir}/{area-path}/
```

The script supports:

- `scan`: list Markdown documents for the active project or selected area, optionally filtered by query terms.
- `read`: print a vault-relative or absolute document path.
- `create`: create a new Markdown document with OKF-compatible frontmatter, title heading, tags, and redacted content.
- `update`: append content, replace a named heading section, or rewrite the full article body.
- `move`: move one active Fundus document for later curation workflows.
- `backup create/list/inspect`: create and inspect snapshots of the configured Fundus before curation.
- `migrate wiki-to-fundus --dry-run/--apply/--verify`: migrate the legacy `Wiki/` corpus into canonical `Fundus/`.
- `area init`: create an explicit area skeleton without overwriting existing files.
- `index rebuild`: build a lightweight search index for all project and area Fundus Markdown documents.
- `index status`: report whether the index exists and has the expected document count.
- `archive candidates`: list old active notes that may be safe to archive.
- `archive apply`: move one explicit active note into the archive.
- `archive restore`: move one archived note back to its original path.
- `archive status`: report active and archived note counts for the current project.
- `doctor`: print resolved project, configuration, vault, Fundus, and index diagnostics.

All writes go through `scripts/fundus.py`; Codex should not edit Fundus documents directly.
Create removes a duplicate leading H1 from supplied content when it matches the generated document title, so notes keep a single top-level title heading. New notes include local OKF-compatible fields such as `type`, `description`, `id`, `scope`, `scope_path`, and `timestamp`; optional fields such as `aliases`, `resource`, `status`, `owner`, and `last_verified` can be stored for better retrieval. Old project notes remain supported.
Use `update --mode rewrite` when a note is outdated enough that append or section replacement would preserve misleading stale content.

Fundus is evidence, not authority. Source code is the source of truth for implemented behavior. If Fundus content appears stale during research, Codex should normally propose a concise update rather than changing Fundus silently; automatic updates are appropriate when the user explicitly asks to document or propagate new learning.

## Scopes

Project scope is the default and targets `Fundus/{project-name}/`. Area scope is explicit and targets paths such as `Fundus/Epics/AI Agent Templates/` or `Fundus/Domains/Invoicing/`.

`--project` and `--area` are mutually exclusive. Area paths are relative to the Fundus root, may contain nested directories and spaces, and cannot use reserved directories or escape the Fundus root.

## Search Index

The optional search index is stored at:

```text
{vault_path}/{fundus_dir}/.fundus-index.json
```

Each entry stores compact metadata: vault-relative path, project, scope, scope path, title, description, aliases, resource, owner/status verification metadata, tags, updated timestamp, headings, a short excerpt, normalized lexical tokens, and ticket IDs such as `BACKEND-2242`. `scan --query` uses the index when present and falls back to direct scope-folder Markdown scanning when absent. Indexed scan results include compact scores, confidence, and match reasons.

Successful `create` and `update` operations refresh only the affected index entry when an index already exists. They do not create the index implicitly; use `index rebuild` to opt into indexed search.

## Archive

Archived notes are stored under:

```text
{vault_path}/{fundus_dir}/_archive/...
```

`archive apply` mirrors the active path under `_archive`, preserves the body, and adds frontmatter fields: `archived`, `archived_at`, `archived_reason`, and `original_path`. Project notes still archive to `_archive/{project-name}/`; area notes preserve their nested area path. `archive restore` uses `original_path`, recreates the original directory as needed, fails if the destination already exists, and removes the archive directory when it becomes empty.

Normal `scan` excludes archived notes. `scan --include-archived` returns archived entries with archive metadata. The index includes active and archived notes so archive and restore keep search state fresh without requiring a full rebuild.

`archive candidates` is intentionally read-only. It scans the detected project by default or an explicit `--area`; passing `--global` scans every active project folder under the Fundus root and includes the project name in each candidate. It uses the note `updated` timestamp and excludes durable tags such as `project-overview`, `architecture`, `runbook`, and `glossary` by default. Passing `--force` includes those durable notes and marks them as `old_durable_note`, so explicit force requests can still surface every age-matching note before `archive apply` moves selected paths.

## Backup

Backups are stored outside the indexed Fundus tree:

```text
{vault_path}/.fundus-backups/{backup-id}/
```

`backup create --label ...` copies the configured `Fundus/` directory into the backup folder and writes `manifest.json` with timestamp, file count, byte count, and SHA-256 checksums. Migration uses the same backup machinery against the legacy `Wiki/` source before mutating or retiring it. `backup list` returns compact manifest summaries. `backup inspect --id ...` returns the full manifest.

## Migration

`migrate wiki-to-fundus --dry-run` reports source/destination paths, active/archive/reserved/concept counts, reserved files that will lose frontmatter, path mappings, and conflicts without writing.

`migrate wiki-to-fundus --apply` requires a conflict-free plan, creates a source backup, writes transformed files into `.fundus-migration-staging/`, verifies the staged corpus, promotes it to `Fundus/`, rebuilds `.fundus-index.json`, verifies the final corpus, and renames `Wiki/` to a timestamped `Wiki.migrated-*` path by default. Use `--retire-source keep` only when the caller explicitly wants to keep the legacy source in place after migration.

`migrate wiki-to-fundus --verify` checks the configured destination corpus for active/archive/reserved/concept counts, missing concept frontmatter, missing concept `type`, reserved files with frontmatter, index state, and bounded smoke-search results.

## OKF Corpus Rules

Active non-reserved notes should follow the local OKF-compatible profile: `type`, `title`, `description`, `id`, `scope`, `scope_path`, `created`, `updated`, `timestamp`, `tags`, and `project` for project-scoped notes.

Active `index.md` and `log.md` files are OKF reserved files. During the canonical migration they should lose frontmatter and keep only their navigation or chronological body content. Area or project metadata should live in regular concept notes such as `overview.md`.

Archived notes are preserved but quiet. They should live under `Fundus/_archive/`, remain excluded from normal scans, and be included only when archive lookup is explicit. Archive metadata should be preserved where present, but archived legacy notes do not need expensive normalization for the first plugin release.

## Codex Skill Package

The repository builds one direct Codex skill package at `dist/fundus`. Runtime installation copies that package to:

```text
~/.codex/skills/fundus
```

`SKILL.md` contains the workflow instructions, while `agents/openai.yaml` provides Codex app metadata and the invocation policy. Codex should resolve helper scripts relative to the loaded skill directory.

The plugin target is a thin distribution wrapper around the same workflow: compact Fundus skill, local stdio MCP server, plugin metadata, and local marketplace entry. `task build:plugin` generates `dist/fundus-plugin`; `task plugin:refresh` generates `dist/fundus-marketplace` with a local marketplace entry for testing. The plugin does not replace the deterministic helper or bypass Codex permissions.

## MCP Server

`scripts/fundus_mcp.py` is a dependency-free stdio MCP server with a small built-in JSON-RPC adapter. It is an additional runtime surface over the same domain functions as `scripts/fundus.py`; it does not implement a separate write path.

The server exposes typed tools for scan, read, create, update, add-frontmatter, move, backup create/list/inspect, migrate wiki-to-fundus, area init, index status/rebuild, archive candidates/apply/restore/cleanup/status, and doctor diagnostics. Each tool resolves the active project root, configuration, project name, and optional area scope before calling the existing helper functions. Optional `project_root`, `project`, and `area` arguments let Codex override those values when the server process cwd is not the repository being documented.

Codex normally launches the server command as a child process:

```text
python /Users/christian/.codex/skills/fundus/scripts/fundus_mcp.py
```

The process stays alive while the MCP client uses it and exits when the client disconnects. The Python environment that launches the server only needs the standard library and the bundled Fundus files; `fundus_mcp.py --check` verifies construction.

## Codex Approvals

Codex should run the installed script directly with a reusable command prefix matching the Python command available in the Codex environment:

```text
python /Users/christian/.codex/skills/fundus/scripts/fundus.py
```

Use `python3` instead when that is the command Codex will actually run:

```text
python3 /Users/christian/.codex/skills/fundus/scripts/fundus.py
```

Codex approvals are command-prefix based, not skill-name based. This repository cannot declare a semantic "allow all fundus skill calls" rule by itself. The interpreter token is part of the matched prefix, so `python .../fundus.py` and `python3 .../fundus.py` need separate rules. The command allowlist is also separate from filesystem sandboxing: the helper can be an approved command and still need escalated sandbox permissions when it writes to an Obsidian vault outside the active workspace.

The operational distinction matters:

- Read-only helper calls such as `scan`, `read`, `doctor`, `index status`, and `archive candidates` should run without escalated sandbox permissions.
- Write-like helper calls such as `create`, `update`, `add-frontmatter`, `index rebuild`, `archive apply`, `archive restore`, and `archive cleanup` need escalated sandbox permissions when the vault is outside the writable workspace.
- If the helper prefix is already allowlisted, Codex should not pass another `prefix_rule` for routine Fundus commands. When the tool API requires a `justification` for escalation, the wording should be terse and operational instead of asking the user for another durable approval.
- Codex should suggest a durable prefix rule only when the helper prefix is missing, the command was denied, or the command shape does not match the existing rule.

For durable allowlisting, configure Codex Rules outside the skill, for example in `~/.codex/rules/default.rules`:

```starlark
prefix_rule(
    pattern=["python", "/Users/christian/.codex/skills/fundus/scripts/fundus.py"],
    decision="allow",
    justification="Allow the vetted Fundus helper without repeated prompts",
)
```

For `python3` environments, use the same rule with `pattern=["python3", "/Users/christian/.codex/skills/fundus/scripts/fundus.py"]`.

This allowlist trusts commands that start with the matching script prefix. It does not inspect every file write, network call, or subprocess inside the Python process, so the helper should remain small, deterministic, and constrained to the configured vault.

`SKILL.md` tells Codex to keep the allowlisted helper invocation simple. Inline `--content` is appropriate for short, simple, single-line content. Multiline or quote-heavy Markdown should be passed with `--content-file` from a sandbox-writable temporary path such as `/private/tmp`. This avoids shell-heavy command shapes, including here-docs, `$'...'` strings, command substitutions, redirections, and long `/bin/zsh -lc ...` payloads. Those forms can fail Codex's conservative command-prefix matching even when the underlying Python helper prefix is allowlisted.

Good allowlisted write shape:

```text
sandbox_permissions=require_escalated + exact installed helper command + --content-file /private/tmp/fundus-update.md + no prefix_rule
```

Avoid for already-allowlisted helpers:

```text
sandbox_permissions=require_escalated + shell wrapper or inline multiline content + repeated prefix_rule request
```

In a normal `workspace-write` session, the repository is writable but `/Users/christian/vault/Hypatos` is not necessarily part of the sandbox. For commands that create, update, archive, restore, clean up, or rebuild the index, Codex should therefore invoke the exact installed helper command with escalated sandbox permissions. If the prefix rule above is loaded, the escalation should be covered by the existing approval and should not produce a new prompt. An alternative is launching Codex with `--add-dir /Users/christian/vault/Hypatos`, which makes the vault an explicit writable root for the session.

The helper allowlist is separate from repository maintenance. Installing the source package with `task install` or `task install:codex` writes outside the active workspace into the Codex configuration directory. Those commands need their own approval/rules and should only be run when the installed skill copy must be refreshed, not during routine Fundus note writes.

## Configuration

Config precedence:

1. `OBSIDIAN_VAULT_PATH` overrides only `vault_path`.
2. `.codex/fundus.json` overrides skill defaults for the active project.
3. `config.json` in the installed skill directory provides local defaults.

The script rejects writes outside the configured vault root.

## Installation

`Taskfile.yml` first builds `dist/fundus`, then copies only runtime files into the Codex skill directory:

- `SKILL.md`
- `config.json`
- `requirements.txt` (currently a no-dependency marker)
- `agents/openai.yaml`
- `docs/reference/fundus-cli-reference.md`
- `scripts/fundus.py`
- `scripts/fundus_mcp.py`

Repository docs, examples, and development files are intentionally not installed as part of the skill runtime.

`Taskfile.yml` also builds plugin artifacts:

- `dist/fundus-plugin`: plugin root with `.codex-plugin/plugin.json`, `.mcp.json`, and `skills/fundus/`.
- `dist/fundus-marketplace`: local test marketplace with `.agents/plugins/marketplace.json` and `plugins/fundus/`.
