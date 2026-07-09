---
name: fundus
description: Persist codebase, epic, domain, and cross-repository work knowledge into Fundus. Use when the user asks to document findings, save research, build a long-lived project or area knowledge base, create a new Fundus note for a topic, or update an existing Fundus page.
---

# Fundus

Use this skill when a user wants persistent repository, epic, domain, or other durable work knowledge written into Fundus. Do not use it when the user says "without Fundus logging" or otherwise opts out.

## Required behavior

- Never write Fundus notes directly. Use `scripts/fundus.py` for scan, read, create, update, archive, and restore operations.
- When a `fundus` MCP server is available, prefer its typed tools over shell commands; the MCP server wraps the same deterministic helper behavior.
- Resolve `scripts/fundus.py` relative to this skill directory when the current working directory is not the installed skill directory.
- Run the script from the project you want to document, or pass `--project` when you need to override the detected project name.
- Keep project-local pages organized under `{vault_path}/{fundus_dir}/{project-name}/`.
- Use `--area "Epics/..."`, `--area "Domains/..."`, or another explicit area path for cross-repository epics, business domains, capabilities, interviews, story maps, and decisions.
- Do not pass `--project` and `--area` together.
- Detect the project name automatically unless the repository needs an explicit `--project` override.
- Before creating a note, always scan the selected project or area scope for possible matches.
- If a likely match exists, read it before deciding whether to update or create.
- Update existing notes automatically when they already cover the topic. Create a new note only when no good match exists.
- Prefer indexed scan results when available. Rebuild the index with `index rebuild` when `index status` or `doctor` reports it as missing or stale.
- Archive stale notes only through explicit `archive apply --path ...`; use `archive candidates` for review, and do not bulk-archive without selected paths.
- Create backups with `backup create --label ...` before migration, curation, or bulk path changes.
- Normalize legacy frontmatter with `normalize-frontmatter`; run it as a dry-run first and add `--apply` only after reviewing the planned metadata changes.
- Do not initialize new areas or migrate existing notes unless the user explicitly asks for that step.
- Preserve concise, useful Markdown. The body is free-form, so choose headings and structure that fit the topic.
- Created notes get OKF-compatible frontmatter and a generated `# Title` heading. If create content already starts with the same H1, the tool removes that duplicate heading automatically.
- Expect secret redaction to run automatically before content is written.

## Configuration

Configuration resolves in this order:

1. `OBSIDIAN_VAULT_PATH` environment variable for `vault_path`
2. `.codex/fundus.json` in the active project
3. `config.json` in this skill directory

Defaults installed with this skill:

- `vault_path`: `/Users/christian/vault/Hypatos`
- `fundus_dir`: `Fundus`
- `default_tags`: `fundus`

## Workflow

1. Decide the scope: default project scope, or explicit `--area` for cross-repo knowledge.
2. Scan the selected Fundus scope.
3. Match by title, tags, filename, headings, ticket IDs, and indexed excerpts.
4. Read the best existing match when one exists.
5. Decide whether to update or create.
6. Write the final note content.

Use full-document rewrite only when the existing note is stale enough that appending or replacing one section would leave misleading old content behind.

Use project scope for repository-local implementation knowledge. Use area scope for durable knowledge spanning repositories, stories, business processes, product decisions, interviews, or domain language.

## Archive workflow

Use archive when old notes are superseded but still worth preserving.

1. Run `archive candidates --older-than-days 90` to list old notes for the active project, or include `--area "..."` for an explicit area.
2. If the user asks to archive globally, across all projects, or all Fundus notes, run candidates with `--global`.
3. Durable notes tagged as project overviews, architecture, runbooks, or glossary entries are excluded from normal candidates. If the user explicitly says to force archiving, run candidates with `--force`.
4. Review candidate titles, tags, paths, and reasons with the user when archiving is not explicitly requested for a path.
5. Archive only explicit selected paths with `archive apply --path "Fundus/project/note.md" --reason "..."`.
6. Restore with `archive restore --path "Fundus/_archive/project/note.md"` when needed.
7. Remove leftover empty active/archive folders with `archive cleanup`; pass `--global` only when explicitly cleaning all Fundus project folders.

Archived project notes move to `Fundus/_archive/{project}/`. Archived area notes mirror their active path under `Fundus/_archive/...`. Archived notes keep their content and are excluded from normal scan results. Empty active folders are removed after archive, and restore recreates the original path while cleaning up empty archive folders. Use `scan --include-archived` for explicit archived lookup.

## Codex Permission Behavior

When running under Codex, minimize approval prompts:

- Run the installed script directly: `/Users/christian/.codex/skills/fundus/scripts/fundus.py`.
- Pick the Python command Codex can actually run (`python` or `python3`) and keep it stable. Codex prefix rules include the interpreter token, so `python .../fundus.py` and `python3 .../fundus.py` are different command prefixes.
- If the matching helper prefix is not already allowlisted, ask once for the narrow rule matching the actual command, for example `prefix_rule(pattern=["python", "/Users/christian/.codex/skills/fundus/scripts/fundus.py"], decision="allow", justification="Allow the vetted Fundus helper without repeated prompts")`.
- Use `--content` only for short, simple, single-line content that does not need shell interpolation, command substitution, here-docs, or ANSI-C `$'...'` quoting.
- Use `--content-file` for multiline, quote-heavy, or generated Markdown. Put the temporary file under a sandbox-writable location such as `/private/tmp`, then run a clean helper command like `python /Users/christian/.codex/skills/fundus/scripts/fundus.py update --path ... --mode ... --content-file /private/tmp/note.md`.
- Treat read-only helper calls (`scan`, `read`, `doctor`, `index status`, and `archive candidates`) as normal commands; do not request escalated sandbox permissions for them.
- In Codex `workspace-write` sessions, the configured Obsidian vault is usually outside the writable workspace. For any helper command that creates, updates, archives, restores, cleans up, or rebuilds the index, run the exact installed helper command with `sandbox_permissions=require_escalated` instead of first trying an un-escalated write.
- When the helper prefix is already allowlisted, do not pass a new `prefix_rule` for routine Fundus commands. If the tool API requires a `justification` with `sandbox_permissions=require_escalated`, keep it terse and operational, and do not phrase it as a request for another durable rule.
- Only suggest the durable prefix rule when the helper prefix is missing, the command was denied, or the command shape does not match the existing rule.
- Keep escalated helper commands simple: no `/bin/zsh -lc`, no shell redirection, no heredocs, no command substitution, and no inline ANSI-C quoted multiline content. Those wrappers change the approved command prefix and can make Codex ask again.
- Codex approvals are command-prefix based, not skill-name based. There is no separate skill-level whitelist in this repository; durable allowlisting belongs in Codex Rules, for example `~/.codex/rules/default.rules`. Restart Codex after adding or changing rules.
- This helper rule does not cover maintenance commands such as `task install:codex` or direct writes to `~/.codex`; those require separate approval/rules and should not be part of normal Fundus note creation or updates.
- Treat such a rule as trust in this script invocation, not as fine-grained inspection of every internal Python file write or subprocess.

Good allowlisted write shape:

```text
sandbox_permissions=require_escalated + exact installed helper command + --content-file /private/tmp/note.md + no prefix_rule
```

Avoid for already-allowlisted helpers:

```text
sandbox_permissions=require_escalated + shell wrapper or inline multiline content + repeated prefix_rule request
```

## Commands

Run the installed script from the project you want to document. Replace `/path/to/fundus` with this skill directory when needed:

```bash
python /path/to/fundus/scripts/fundus.py scan [--query "authentication flow"]
```

```bash
python /path/to/fundus/scripts/fundus.py scan \
  --query "BACKEND-2242 retry budget" \
  --limit 5 \
  --include-snippet
```

```bash
python /path/to/fundus/scripts/fundus.py scan \
  --area "Epics/AI Agent Templates" \
  --query "story map"
```

```bash
python /path/to/fundus/scripts/fundus.py read --path "Fundus/my-project/authentication-flow.md"
```

```bash
python /path/to/fundus/scripts/fundus.py create \
  --title "Authentication Flow" \
  --content "## Overview

Document the relevant behavior here." \
  --tag auth
```

```bash
python /path/to/fundus/scripts/fundus.py create \
  --area "Epics/AI Agent Templates" \
  --title "Story Map" \
  --type Epic \
  --description "Cross-repository story map for the epic." \
  --content-file /private/tmp/story-map.md
```

```bash
python /path/to/fundus/scripts/fundus.py update \
  --path "Fundus/my-project/authentication-flow.md" \
  --mode append \
  --content "## New Findings

Document the update here."
```

```bash
python /path/to/fundus/scripts/fundus.py update \
  --path "Fundus/my-project/authentication-flow.md" \
  --mode replace \
  --section "Session Handling" \
  --content "Session handling details go here."
```

```bash
python /path/to/fundus/scripts/fundus.py update \
  --path "Fundus/my-project/authentication-flow.md" \
  --mode rewrite \
  --content "## Overview

Replace the full article body here."
```

```bash
python /path/to/fundus/scripts/fundus.py index rebuild
```

```bash
python /path/to/fundus/scripts/fundus.py index status
```

```bash
python /path/to/fundus/scripts/fundus.py normalize-frontmatter \
  --path "Fundus/my-project/legacy-note.md"
```

```bash
python /path/to/fundus/scripts/fundus.py normalize-frontmatter \
  --path "Fundus/my-project/legacy-note.md" \
  --apply
```

```bash
python /path/to/fundus/scripts/fundus.py normalize-frontmatter --global --limit 20
```

```bash
python /path/to/fundus/scripts/fundus.py normalize-frontmatter --global --apply
```

```bash
python /path/to/fundus/scripts/fundus.py backup create --label pre-curation
```

```bash
python /path/to/fundus/scripts/fundus.py backup list
```

```bash
python /path/to/fundus/scripts/fundus.py backup inspect --id 20260709T103010+0200-pre-okf-option-b
```

```bash
python /path/to/fundus/scripts/fundus.py area init \
  --area "Epics/AI Agent Templates" \
  --type Epic \
  --title "AI Agent Templates"
```

```bash
python /path/to/fundus/scripts/fundus.py archive candidates --older-than-days 90
```

```bash
python /path/to/fundus/scripts/fundus.py archive candidates --older-than-days 90 --global
```

```bash
python /path/to/fundus/scripts/fundus.py archive candidates --older-than-days 90 --force
```

```bash
python /path/to/fundus/scripts/fundus.py archive apply \
  --path "Fundus/my-project/old-ticket.md" \
  --reason "superseded by current runbook"
```

```bash
python /path/to/fundus/scripts/fundus.py archive restore \
  --path "Fundus/_archive/my-project/old-ticket.md"
```

```bash
python /path/to/fundus/scripts/fundus.py archive cleanup
```

```bash
python /path/to/fundus/scripts/fundus.py archive cleanup --global
```

```bash
python /path/to/fundus/scripts/fundus.py doctor
```

## Notes

- `scan` returns compact JSON with titles, tags, vault-relative paths, updated timestamps, and indexed match scores/reasons when an index exists.
- `scan` uses `{vault_path}/{fundus_dir}/.fundus-index.json` when present and falls back to direct Markdown scanning when absent. It excludes archived notes unless `--include-archived` is passed.
- `index rebuild` refreshes the lightweight search index from all project and area Markdown documents.
- `normalize-frontmatter` upgrades existing notes to OKF-compatible metadata without changing note bodies. It is a dry-run unless `--apply` is passed, infers scope from the note path rather than the current working directory, refreshes the index for changed notes, and reports body hashes plus `body_unchanged`.
- `normalize-frontmatter --global` scans all active Fundus notes; add `--include-archived` only when archived notes should be normalized too.
- `normalize-frontmatter --add-missing` adds generated frontmatter to plain Markdown notes; otherwise missing-frontmatter notes are reported and skipped.
- `backup create` snapshots the configured Fundus under `{vault_path}/.fundus-backups/`; use it before migration or curation.
- `area init` creates an explicit area skeleton but should only be run after the user asks to create that area.
- `archive candidates` is read-only and suggests old notes by `updated` timestamp and tags. It scans the active project or selected area by default; pass `--global` to scan all active project Fundus folders. Durable notes are excluded unless `--force` is passed.
- `archive apply` moves an active note under `Fundus/_archive/...`, writes archive frontmatter, and removes the active folder when it becomes empty.
- `archive restore` moves an archived note back to its recorded `original_path`, recreating the original folder as needed and removing the archive project folder when it becomes empty.
- `archive cleanup` removes empty active and archived project folders without moving notes. By default it checks only the detected project; `--global` checks every Fundus project folder.
- `index status` and `doctor` help diagnose missing or stale indexes and resolved configuration.
- The script detects the active project from the current working directory and its git root, unless `--project` is provided.
- `read` returns the full Markdown document.
- `create` fails if the slug already exists.
- `create` and `update` refresh their affected index entry automatically when an index already exists.
- `create` preserves one generated title H1 and removes a duplicate matching leading H1 from supplied content.
- `update --mode replace` replaces the named heading section or creates it if missing.
- `update --mode rewrite` replaces the full article body while preserving frontmatter.
- All resolved paths are constrained to the configured vault root.
- Writes are atomic to avoid partial documents.

After creating or updating this skill, restart Codex so it can load the updated skill manifest.
