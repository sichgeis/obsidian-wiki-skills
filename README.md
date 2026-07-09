# Fundus Skill

This repository is the source of truth for the local Codex `fundus` skill.

The skill persists codebase knowledge into an Obsidian vault as per-repository Fundus documents and explicit cross-repository areas. It is packaged for Codex, with an optional local MCP server for typed Fundus tools.

Existing Fundus documents can be updated by appending content, replacing a named heading section, or rewriting the full article body with `update --mode rewrite`.
Created documents keep one generated top-level title heading; duplicate matching H1 headings in supplied content are removed automatically.
Search is backed by a lightweight JSON index at `{vault_path}/{fundus_dir}/.fundus-index.json` when present, so Codex can find likely matching notes from titles, tags, filenames, headings, ticket IDs, and short excerpts without reading every note body. Old notes can be archived reversibly under `{vault_path}/{fundus_dir}/_archive/...`, with nested area paths mirrored under the archive root.

## Current Direction

Fundus is being refined into Christian's personal Codex workbench for durable work knowledge. The workbench should stay explicit: use it to search, save, retrieve, update, and curate Fundus knowledge. During ticket or research work, Codex may also do a read-only Fundus lookup when prior context is likely useful.

Fundus is evidence, not authority. Source code remains the source of truth for implemented behavior; Fundus helps discover business ideas, technical concepts, prior decisions, and discussion history. When Fundus appears stale, Codex should propose a concise correction instead of silently rewriting it, unless the user explicitly asks to propagate new learning into Fundus.

The live legacy corpus currently exists under `/Users/christian/vault/Hypatos/Wiki`. The target canonical corpus is `/Users/christian/vault/Hypatos/Fundus`. The next major setup work is a verified one-time migration from `Wiki/` to `Fundus/`, including active notes, quiet archived-note preservation, strict reserved-file cleanup for `index.md` and `log.md`, and an index rebuild. Start implementation work from `docs/agent-implementation-tracker.md`.

## Layout

- `SKILL.md`: Codex skill manifest and operating instructions.
- `agents/openai.yaml`: Codex app metadata and invocation policy.
- `scripts/fundus.py`: deterministic scan/read/create/update/index/archive/doctor tool for Fundus documents.
- `scripts/fundus_mcp.py`: stdio MCP server exposing the same Fundus operations as typed tools.
- `config.json`: local default configuration used by the installed skill.
- `config.example.json`: portable configuration template.
- `requirements.txt`: Python runtime dependency list for the MCP server.
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

The build task creates:

```text
dist/fundus
```

Only runtime files are copied into the package.

## Install

Install for Codex:

```bash
task install
```

The explicit Codex target is equivalent:

```bash
task install:codex
```

The install target copies the built package into:

```text
~/.codex/skills/fundus
```

It also removes stale pre-Fundus and retired prompt-wrapper installs from the Codex home. Restart Codex after installing or changing the skill so the skill manifest is reloaded.

## MCP Server

The package also includes a local stdio MCP server. Codex launches this command as a child process and keeps it alive while the session is using the server:

```bash
python /path/to/fundus/scripts/fundus_mcp.py
```

Install the Python MCP SDK in the environment that will run the server:

```bash
pip install -r /path/to/fundus/requirements.txt
```

Example `~/.codex/config.toml` entry:

```toml
[mcp_servers.fundus]
command = "python"
args = ["/Users/christian/.codex/skills/fundus/scripts/fundus_mcp.py"]
```

The same server can be registered through the Codex CLI:

```bash
codex mcp add fundus -- python /Users/christian/.codex/skills/fundus/scripts/fundus_mcp.py
```

The MCP server exposes typed tools for scanning, reading, creating, updating, moving, backing up, area initialization, indexing, archiving, restoring, cleaning up, and diagnosing Fundus notes. It uses the same configuration precedence, path confinement, redaction, atomic writes, index refresh behavior, and archive behavior as `scripts/fundus.py`.

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

## Codex Permissions

For fast documentation runs in Codex, approve the installed helper prefix that matches the Python command Codex will actually run:

```text
python /Users/christian/.codex/skills/fundus/scripts/fundus.py
```

Use `python3` instead of `python` only when that is the command available in the Codex environment.

Codex has two separate gates:

- Command approval: whether the proposed command is trusted.
- Filesystem sandboxing: whether the command may write outside the active workspace.

Codex approvals are command-prefix based, not skill-name based. The interpreter token is part of that prefix: a rule for `python .../fundus.py` does not match `python3 .../fundus.py`. There is no separate "allow this whole skill" switch in `SKILL.md`; permission belongs in Codex's sandbox, approval policy, and rules configuration. Because the default vault is `/Users/christian/vault/Hypatos`, normal Fundus writes usually happen outside repository workspaces. In `workspace-write` sessions, Codex should run write-like helper commands as the exact installed Python command with escalated sandbox permissions.

Once the helper prefix is already allowlisted, routine Fundus writes should not propose a fresh `prefix_rule`. If the Codex tool API still requires a `justification` for `sandbox_permissions=require_escalated`, keep that wording terse and operational rather than presenting it as another durable approval request. Only suggest the durable rule when the prefix is missing, the command is denied, or the command shape does not match the existing rule.

To make the permission durable, add a Codex rule in `~/.codex/rules/default.rules` and restart Codex:

You can also ask Codex to add or update this allow rule for you. Codex can edit the rules file and run the required setup commands, subject to the normal approval prompts for changing Codex configuration.

```starlark
prefix_rule(
    pattern=["python", "/Users/christian/.codex/skills/fundus/scripts/fundus.py"],
    decision="allow",
    justification="Allow the vetted Fundus helper without repeated prompts",
)
```

Use the same shape with `pattern=["python3", "/Users/christian/.codex/skills/fundus/scripts/fundus.py"]` if `python3` is the command Codex will actually run.

This trusts invocations of that helper script through the matching prefix; it is not a fine-grained audit of every file write or subprocess inside Python. Keep the helper small, deterministic, and path-constrained.

This rule covers the installed Fundus helper only. It does not cover repository maintenance commands such as `task install`, `task install:codex`, or direct edits under `~/.codex`; those are separate filesystem writes outside the active workspace and may still require their own approval or durable rule. Do not run install tasks during normal Fundus documentation. Install only after changing the skill source and when the installed skill copy actually needs to be refreshed.

For Codex, keep the helper invocation itself simple so the prefix rule can match it. Read-only helper calls such as `scan`, `read`, `doctor`, `index status`, and `archive candidates` do not need escalated sandbox permissions. Use inline `--content` only for short, simple, single-line content. For multiline or quote-heavy Markdown, write the body to a temporary file in a sandbox-writable location such as `/private/tmp`, then call the helper with `--content-file`:

```bash
python /Users/christian/.codex/skills/fundus/scripts/fundus.py update \
  --path "Fundus/my-project/authentication-flow.md" \
  --mode replace \
  --section "Session Handling" \
  --content-file /private/tmp/fundus-update.md
```

Avoid wrapping Fundus writes in shell-heavy commands such as here-docs, `$'...'` strings, command substitutions, redirections, or long `/bin/zsh -lc ...` payloads. Those forms can fall outside Codex's conservative command-prefix matching even though the underlying Python script is allowlisted. If Codex is launched with `--add-dir /Users/christian/vault/Hypatos`, the vault is part of the writable sandbox and write commands may not need escalation; otherwise the exact allowlisted helper command should be escalated for writes.

Good allowlisted write shape:

```text
sandbox_permissions=require_escalated + exact installed helper command + --content-file /private/tmp/fundus-update.md + no prefix_rule
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

This builds the package, checks the CLI and MCP script entrypoints, and runs the unit tests.

After installing, verify the Codex install with:

```bash
task verify:codex
```

You can also run the built or installed script directly:

```bash
python dist/fundus/scripts/fundus.py --help
python dist/fundus/scripts/fundus_mcp.py --help
```

## Configuration

Configuration resolves in this order:

1. `OBSIDIAN_VAULT_PATH`
2. project-local `.codex/fundus.json`
3. installed skill-local `config.json`

Default configuration targets:

```text
/Users/christian/vault/Hypatos/Fundus
```

Current local note history is still under `/Users/christian/vault/Hypatos/Wiki` until the planned migration runs. Do not treat both trees as live canonical sources after migration; `Fundus/` should become the single work knowledge root.

## Update Workflow

1. Edit the source files in this repository.
2. Run `task verify`.
3. Run `task install`.
4. Start a new Codex session.

The installed skill is a copied directory, so repository changes are not reflected globally until the install task runs again.
