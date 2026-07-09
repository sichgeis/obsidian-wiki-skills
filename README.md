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
- `scripts/obsidian_wiki_mcp.py`: stdio MCP server exposing the same wiki operations as typed tools.
- `config.json`: local default configuration used by the installed skill.
- `config.example.json`: portable configuration template.
- `requirements.txt`: Python runtime dependency list for the MCP server.
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

## MCP Server

The package also includes a local stdio MCP server. MCP clients such as Codex launch this command as a child process and keep it alive while the client session is using the server:

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki_mcp.py
```

Install the Python MCP SDK in the environment that will run the server:

```bash
pip install -r /path/to/obsidian-wiki/requirements.txt
```

Example Codex MCP configuration:

```json
{
  "mcpServers": {
    "obsidian-wiki": {
      "command": "python",
      "args": [
        "/Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki_mcp.py"
      ]
    }
  }
}
```

The MCP server exposes typed tools for scanning, reading, creating, updating, indexing, archiving, restoring, cleaning up, and diagnosing wiki notes. It uses the same configuration precedence, path confinement, redaction, atomic writes, index refresh behavior, and archive behavior as `scripts/obsidian_wiki.py`.

## Codex Permissions

For fast documentation runs in Codex, approve the installed helper prefix that matches the Python command Codex will actually run:

```text
python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py
```

Use `python3` instead of `python` only when that is the command available in the agent environment.

Codex has two separate gates:

- Command approval: whether the proposed command is trusted.
- Filesystem sandboxing: whether the command may write outside the active workspace.

Codex approvals are command-prefix based, not skill-name based. The interpreter token is part of that prefix: a rule for `python .../obsidian_wiki.py` does not match `python3 .../obsidian_wiki.py`. There is no separate "allow this whole skill" switch in `SKILL.md`; permission belongs in Codex's sandbox, approval policy, and rules configuration. Because the default vault is `/Users/christian/vault/Hypatos`, normal wiki writes usually happen outside repository workspaces. In `workspace-write` sessions, agents should run write-like helper commands as the exact installed Python command with escalated sandbox permissions.

Once the helper prefix is already allowlisted, routine wiki writes should not propose a fresh `prefix_rule`. If the Codex tool API still requires a `justification` for `sandbox_permissions=require_escalated`, keep that wording terse and operational rather than presenting it as another durable approval request. Only suggest the durable rule when the prefix is missing, the command is denied, or the command shape does not match the existing rule.

To make the permission durable, add a Codex rule in `~/.codex/rules/default.rules` and restart Codex:

You can also ask the coding agent to add or update this allow rule for you. The agent can edit the rules file and run the required setup commands, subject to the normal approval prompts for changing Codex configuration.

```starlark
prefix_rule(
    pattern=["python", "/Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py"],
    decision="allow",
    justification="Allow the vetted Obsidian wiki helper without repeated prompts",
)
```

Use the same shape with `pattern=["python3", "/Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py"]` if `python3` is the command the agent will actually run.

This trusts invocations of that helper script through the matching prefix; it is not a fine-grained audit of every file write or subprocess inside Python. Keep the helper small, deterministic, and path-constrained.

This rule covers the installed wiki helper only. It does not cover repository maintenance commands such as `task install`, `task install:codex`, or direct edits under `~/.codex`; those are separate filesystem writes outside the active workspace and may still require their own approval or durable rule. Do not run install tasks during normal wiki documentation. Install only after changing the skill source and when the installed agent copy actually needs to be refreshed.

For Codex, keep the helper invocation itself simple so the prefix rule can match it. Read-only helper calls such as `scan`, `read`, `doctor`, `index status`, and `archive candidates` do not need escalated sandbox permissions. Use inline `--content` only for short, simple, single-line content. For multiline or quote-heavy Markdown, write the body to a temporary file in a sandbox-writable location such as `/private/tmp`, then call the helper with `--content-file`:

```bash
python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py update \
  --path "Wiki/my-project/authentication-flow.md" \
  --mode replace \
  --section "Session Handling" \
  --content-file /private/tmp/wiki-update.md
```

Avoid wrapping wiki writes in shell-heavy commands such as here-docs, `$'...'` strings, command substitutions, redirections, or long `/bin/zsh -lc ...` payloads. Those forms can fall outside Codex's conservative command-prefix matching even though the underlying Python script is allowlisted. If Codex is launched with `--add-dir /Users/christian/vault/Hypatos`, the vault is part of the writable sandbox and write commands may not need escalation; otherwise the exact allowlisted helper command should be escalated for writes.

Good allowlisted write shape:

```text
sandbox_permissions=require_escalated + exact installed helper command + --content-file /private/tmp/wiki-update.md + no prefix_rule
```

Avoid for already-allowlisted helpers:

```text
sandbox_permissions=require_escalated + shell wrapper or inline multiline content + repeated prefix_rule request
```

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

Remove leftover empty folders for the detected project, or across all wiki project folders:

```bash
python dist/obsidian-wiki/scripts/obsidian_wiki.py archive cleanup
python dist/obsidian-wiki/scripts/obsidian_wiki.py archive cleanup --global
```

Archived notes move to `Wiki/_archive/{project}/`, keep their content, and get archive metadata in frontmatter. Empty active project folders are removed after archive, and restore recreates the original folder while cleaning up empty archive project folders. `archive cleanup` removes leftover empty active and archived project folders without moving notes. Normal `scan` excludes archived notes; use `scan --include-archived` to find them explicitly.

## Verify

Run:

```bash
task verify
```

This builds the package, checks the CLI and MCP script entrypoints, and runs the unit tests.

After installing, verify agent-specific installs with:

```bash
task verify:codex
task verify:claude
task verify:forge
```

You can also run the built or installed script directly:

```bash
python dist/obsidian-wiki/scripts/obsidian_wiki.py --help
python dist/obsidian-wiki/scripts/obsidian_wiki_mcp.py --help
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
