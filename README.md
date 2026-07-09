# Fundus Codex Plugin

This repository is the source of truth for the local Codex `fundus` plugin.

The plugin packages the `fundus` skill, a dependency-free local MCP server, and a deterministic CLI helper for typed Fundus tools. Fundus persists codebase knowledge into an Obsidian vault as per-repository documents and explicit cross-repository areas.

Existing Fundus documents can be updated by appending content, replacing a named heading section, or rewriting the full article body with `update --mode rewrite`.
Created documents keep one generated top-level title heading; duplicate matching H1 headings in supplied content are removed automatically.
Search is backed by a lightweight JSON index at `{vault_path}/{fundus_dir}/.fundus-index.json` when present, so Codex can find likely matching notes from titles, tags, filenames, headings, ticket IDs, and short excerpts without reading every note body. Old notes can be archived reversibly under `{vault_path}/{fundus_dir}/_archive/...`, with nested area paths mirrored under the archive root.

## Current Direction

Fundus is being refined into Christian's personal Codex workbench for durable work knowledge. The workbench should stay explicit: use it to search, save, retrieve, update, and curate Fundus knowledge. During ticket or research work, Codex may also do a read-only Fundus lookup when prior context is likely useful.

Fundus is evidence, not authority. Source code remains the source of truth for implemented behavior; Fundus helps discover business ideas, technical concepts, prior decisions, and discussion history. When Fundus appears stale, Codex should propose a concise correction instead of silently rewriting it, unless the user explicitly asks to propagate new learning into Fundus.

The canonical live corpus is `/Users/christian/vault/Hypatos/Fundus`. The old `Wiki/` source was migrated on 2026-07-09, verified, backed up, and retired as `/Users/christian/vault/Hypatos/Wiki.migrated-20260709T182817+0200-wiki-to-fundus-resume`.

## Layout

- `.codex-plugin/plugin.json`: Codex plugin manifest.
- `.mcp.json`: plugin MCP server registration.
- `SKILL.md`: packaged Codex skill manifest and operating instructions.
- `agents/openai.yaml`: Codex app metadata and invocation policy.
- `scripts/fundus.py`: deterministic scan/read/create/update/index/archive/doctor tool for Fundus documents.
- `scripts/fundus_mcp.py`: stdio MCP server exposing the same Fundus operations as typed tools.
- `config.json`: local default configuration packaged with the skill runtime.
- `config.example.json`: portable configuration template.
- `requirements.txt`: dependency-free runtime marker kept for packaging symmetry.
- `docs/`: project documentation for maintainers.
- `Taskfile.yml`: local development tasks.

## Agent Documentation

- `docs/agent-implementation-tracker.md`: active multi-pass work tracker, phase status board, implementation inventory, backlog, and pass protocol. Start here when implementing the target solution.
- `docs/fundus-target-picture.md`: stable target picture, DDD decisions, corpus findings, OKF-compatible profile, source hierarchy, and plugin architecture.
- `docs/implementation.md`: current helper, MCP, packaging, permissions, and runtime notes. Update this when code behavior changes.

## Build

Run:

```bash
task build
```

The build task creates the direct skill package:

```text
dist/fundus
```

That package is the runtime payload used by the plugin. Use `task build:plugin` for `dist/fundus-plugin` and `task plugin:refresh` for the generated local marketplace at `dist/fundus-marketplace`.

## Install

Install or refresh the local Codex plugin:

```bash
task install
```

`task install` rebuilds the local plugin marketplace, applies a Codex cachebuster to the generated plugin package, and reinstalls `fundus@fundus-local`.

For the first install on a machine, configure the generated marketplace once before running `task install`:

```bash
task plugin:refresh
codex plugin marketplace add "$(pwd)/dist/fundus-marketplace"
task install
```

Start a new Codex thread, or restart Codex, after reinstalling so the refreshed skill and MCP tools are loaded.

This repository still keeps a legacy direct-skill target for recovery and compatibility:

```bash
task install:codex
```

Do not use `task install:codex` alongside the plugin. It copies the skill into `~/.codex/skills/fundus`, which makes Codex see a second `fundus` skill in addition to the plugin-provided one.

## MCP Server

The plugin includes a local stdio MCP server. Codex reads `.mcp.json` from the installed plugin package and launches the server relative to the plugin root:

```json
{
  "command": "python",
  "args": ["./skills/fundus/scripts/fundus_mcp.py"],
  "cwd": "."
}
```

The server is self-contained and uses only the Python standard library plus the bundled Fundus helper. Check the built server with:

```bash
python dist/fundus/scripts/fundus_mcp.py --check
```

The MCP server exposes typed tools for scanning, reading, creating, updating, moving, backing up, area initialization, indexing, archiving, restoring, cleaning up, and diagnosing Fundus notes. It uses the same configuration precedence, path confinement, redaction, atomic writes, index refresh behavior, and archive behavior as `scripts/fundus.py`.

## Plugin Package

Build the plugin package and local marketplace:

```bash
task build:plugin
task plugin:refresh
```

The generated plugin root is:

```text
dist/fundus-plugin
```

The generated test marketplace is:

```text
dist/fundus-marketplace/.agents/plugins/marketplace.json
```

Install that explicit local marketplace once when setting up this local plugin source:

```bash
codex plugin marketplace add "$(pwd)/dist/fundus-marketplace"
codex plugin add fundus@fundus-local
```

This local plugin is installed in this Codex environment as `fundus@fundus-local`.

## Project And Area Scopes

The default scope is still the detected project:

```bash
python dist/fundus/scripts/fundus.py scan --query "authentication"
python dist/fundus/scripts/fundus.py create --title "Authentication Flow" --content-file /tmp/note.md
```

Use `--area` for cross-repository knowledge such as epics, domains, capabilities, interviews, decisions, and story maps:

```bash
python dist/fundus/scripts/fundus.py scan --area "Epics/AI Agent Templates" --query "lineage"
python dist/fundus/scripts/fundus.py create --area "Epics/AI Agent Templates" --title "Story Map" --type Epic --content-file /tmp/story-map.md
```

`--project` and `--area` are mutually exclusive. Area paths are always relative to `{vault_path}/{fundus_dir}` and cannot target reserved directories or escape the Fundus root.

New notes get OKF-compatible frontmatter (`type`, `title`, `description`, `id`, `scope`, `scope_path`, `timestamp`, `created`, `updated`, and `tags`) while legacy project notes remain readable and updateable.

Use optional metadata when it improves retrieval:

```bash
python dist/fundus/scripts/fundus.py create \
  --title "Prompt Authoring Boundary" \
  --alias BACKEND-2291 \
  --resource "https://jira.example/browse/BACKEND-2291" \
  --last-verified 2026-07-09 \
  --content-file /tmp/note.md
```

Initialize an area skeleton only when explicitly starting a new area:

```bash
python dist/fundus/scripts/fundus.py area init --area "Epics/AI Agent Templates" --type Epic --title "AI Agent Templates"
```

This creates `index.md`, `log.md`, `overview.md`, and standard subfolders without overwriting existing files.

The refined target profile treats active non-reserved notes as OKF-compatible concept notes. Reserved `index.md` and `log.md` files should become pure OKF reserved files without frontmatter during the canonical `Fundus/` migration. Concept metadata belongs in regular notes such as `overview.md`.

## Frontmatter Normalization

Normalize legacy note metadata without changing note bodies:

```bash
python dist/fundus/scripts/fundus.py normalize-frontmatter --path "Fundus/my-project/old-note.md"
```

The command is a dry-run by default. It reports planned changes, body hashes, and whether the body would remain unchanged. Add `--apply` to write:

```bash
python dist/fundus/scripts/fundus.py normalize-frontmatter \
  --path "Fundus/my-project/old-note.md" \
  --apply
```

For curation batches, normalize a selected scope or all active Fundus notes:

```bash
python dist/fundus/scripts/fundus.py --area "Epics/AI Agent Templates" normalize-frontmatter
python dist/fundus/scripts/fundus.py normalize-frontmatter --global --limit 20
python dist/fundus/scripts/fundus.py normalize-frontmatter --global --apply
```

Use `--include-archived` only when archived notes should be normalized too. Use `--add-missing` only when plain Markdown notes should receive generated OKF frontmatter; otherwise missing-frontmatter files are reported and skipped.

Normalization infers project and area scope from the note path, not from the current working directory. This avoids accidental `scope_path` drift when running from a vault or operations folder.

## Backup

Create a restorable snapshot before migration or bulk curation:

```bash
python dist/fundus/scripts/fundus.py backup create --label pre-okf-curation
python dist/fundus/scripts/fundus.py backup list
python dist/fundus/scripts/fundus.py backup inspect --id 20260709T103010+0200-pre-okf-option-b
```

Backups are stored under `{vault_path}/.fundus-backups/`, outside the indexed `Fundus/` tree. Each backup includes a manifest with file counts, byte counts, and SHA-256 checksums.

## Wiki To Fundus Migration

Inspect the migration plan without writing:

```bash
python dist/fundus/scripts/fundus.py migrate wiki-to-fundus --dry-run
```

Apply the migration through a backup and staged destination:

```bash
python dist/fundus/scripts/fundus.py migrate wiki-to-fundus --apply
```

Verify the canonical `Fundus/` corpus:

```bash
python dist/fundus/scripts/fundus.py migrate wiki-to-fundus --verify
```

By default, apply renames the old `Wiki/` tree to a timestamped `Wiki.migrated-*` path after successful verification so `Wiki/` and `Fundus/` do not remain parallel live sources. Use `--retire-source keep` only for an explicit temporary transition.

## Codex Permissions

In normal Codex use, prefer the plugin-provided `fundus` MCP tools. The plugin owns the MCP server registration, so no manual `~/.codex/config.toml` MCP entry is needed.

Fundus does not depend on a separate Obsidian MCP. If the `fundus` MCP tools are not visible in a Codex thread, use the Fundus CLI helper as the fallback. Do not use generic Obsidian tools or direct Markdown edits for Fundus writes.

Codex has two separate gates:

- Command approval: whether the proposed command is trusted.
- Filesystem sandboxing: whether the command may write outside the active workspace.

Because the default vault is `/Users/christian/vault/Hypatos`, normal Fundus writes usually happen outside repository workspaces. In `workspace-write` sessions, write-like MCP calls or CLI helper commands need escalated sandbox permissions unless the vault was added as a writable root.

If MCP tools are unavailable and Codex must use the CLI helper, run the helper from the repository build or from the installed plugin cache path shown by `codex plugin add` / `codex plugin list`. Plugin cache paths include the installed version, for example:

```text
~/.codex/plugins/cache/fundus-local/fundus/<version>/skills/fundus/scripts/fundus.py
```

Do not use the old direct-skill path `~/.codex/skills/fundus/scripts/fundus.py` unless you intentionally installed the legacy direct skill with `task install:codex`.

If neither the `fundus` MCP tools nor the Fundus CLI helper are available, stop and report that Fundus writes are blocked. Do not create, update, or rewrite vault Markdown directly as a fallback.

Codex approvals are command-prefix based, not skill-name based. The interpreter token is part of that prefix: a rule for `python .../fundus.py` does not match `python3 .../fundus.py`. If you choose to allowlist direct CLI usage, allowlist the exact helper path and interpreter that Codex will run. After a plugin cache-bust reinstall, the versioned installed path may change, so the MCP tools are the steadier day-to-day interface.

For CLI fallback, keep the helper invocation itself simple so any prefix rule can match it. Read-only helper calls such as `scan`, `read`, `doctor`, `index status`, and `archive candidates` do not need escalated sandbox permissions. Use inline `--content` only for short, simple, single-line content. For multiline or quote-heavy Markdown, write the body to a temporary file in a sandbox-writable location such as `/private/tmp`, then call the helper with `--content-file`:

```bash
python dist/fundus/scripts/fundus.py update \
  --path "Fundus/my-project/authentication-flow.md" \
  --mode replace \
  --section "Session Handling" \
  --content-file /private/tmp/fundus-update.md
```

Avoid wrapping Fundus writes in shell-heavy commands such as here-docs, `$'...'` strings, command substitutions, redirections, or long `/bin/zsh -lc ...` payloads. Those forms can fall outside Codex's conservative command-prefix matching even though the underlying Python script is allowlisted. If Codex is launched with `--add-dir /Users/christian/vault/Hypatos`, the vault is part of the writable sandbox and write commands may not need escalation.

Good allowlisted write shape:

```text
sandbox_permissions=require_escalated + exact helper command + --content-file /private/tmp/fundus-update.md + no repeated prefix_rule
```

Avoid for already-allowlisted helpers:

```text
sandbox_permissions=require_escalated + shell wrapper or inline multiline content + repeated prefix_rule request
```

## Search Index

Build or refresh the Fundus search index with:

```bash
python dist/fundus/scripts/fundus.py index rebuild
```

Check index freshness and resolved paths with:

```bash
python dist/fundus/scripts/fundus.py index status
python dist/fundus/scripts/fundus.py doctor
```

`scan --query` uses the index when it exists and falls back to direct Markdown scanning when it does not. Successful `create` and `update` operations refresh their affected index entry automatically if an index already exists.

## Archive

List old-note candidates without changing files:

```bash
python dist/fundus/scripts/fundus.py archive candidates --older-than-days 90
```

Scan all active project Fundus folders instead of only the detected project:

```bash
python dist/fundus/scripts/fundus.py archive candidates --older-than-days 90 --global
```

Durable notes such as project overviews, architecture notes, runbooks, and glossary entries are excluded from normal candidates. Include them only for explicit force requests:

```bash
python dist/fundus/scripts/fundus.py archive candidates --older-than-days 90 --force
```

Archive and restore explicit paths:

```bash
python dist/fundus/scripts/fundus.py archive apply \
  --path "Fundus/my-project/old-ticket.md" \
  --reason "superseded by current runbook"

python dist/fundus/scripts/fundus.py archive restore \
  --path "Fundus/_archive/my-project/old-ticket.md"
```

Remove leftover empty folders for the detected project, or across all Fundus project folders:

```bash
python dist/fundus/scripts/fundus.py archive cleanup
python dist/fundus/scripts/fundus.py archive cleanup --global
```

Archived notes move under `Fundus/_archive/...`, keep their content, and get archive metadata in frontmatter. Project notes still archive under `Fundus/_archive/{project}/`; area notes mirror their active nested path, for example `Fundus/Epics/AI Agent Templates/story-map.md` archives to `Fundus/_archive/Epics/AI Agent Templates/story-map.md`. `archive cleanup` removes leftover empty active and archived folders without moving notes. Normal `scan` excludes archived notes; use `scan --include-archived` to find them explicitly.

## Verify

Run:

```bash
task verify
```

This builds the direct skill package, plugin package, and local marketplace; checks the CLI and MCP entrypoints; validates the plugin manifest when the local validator is available; and runs the unit tests.

After installing, verify the plugin is visible to Codex with:

```bash
codex plugin list
```

You can also run the built scripts directly:

```bash
python dist/fundus/scripts/fundus.py --help
python dist/fundus/scripts/fundus_mcp.py --help
```

## Configuration

Configuration resolves in this order:

1. `OBSIDIAN_VAULT_PATH`
2. project-local `.codex/fundus.json`
3. packaged skill-local `config.json` inside the installed plugin

Default configuration targets:

```text
/Users/christian/vault/Hypatos/Fundus
```

The old `Wiki/` tree has been migrated and retired. Treat `Fundus/` as the single live work knowledge root.

## Update Workflow

1. Edit the source files in this repository.
2. Run `task verify`.
3. Run `task install`.
4. Start a new Codex thread or restart Codex.

The installed plugin is a copied, cached package. Repository changes are not reflected globally until the plugin marketplace is rebuilt, cache-busted, and reinstalled.
