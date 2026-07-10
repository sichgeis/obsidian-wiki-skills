# Fundus Target Picture

Status: stable target for the remediation and second release
Date: 2026-07-10
Supersedes: target picture dated 2026-07-09 where statements conflict

## Document role

This document defines the desired product behavior, domain model, corpus contract, and target architecture for Fundus.

Use:

- `docs/agent-implementation-tracker.md` for ordered execution and phase status.
- `docs/implementation.md` for current implementation facts and target technical contracts.
- `docs/architecture-invariants.md` for normative safety and consistency rules.
- `docs/testing-and-validation.md` for verification strategy.
- `docs/decision-record.md` for defaults selected during the review.

Change this file only when a durable product or architecture decision changes.

## Executive target

Fundus is Christian's personal-first, portable Codex workbench for durable work knowledge.

It persists project, ticket, domain, epic, decision, interview, architecture, runbook, and cross-repository knowledge as Markdown in an Obsidian vault. It should feel native inside Codex while preserving these boundaries:

1. Fundus is evidence, not authority.
2. Source code and current primary evidence win.
3. Human direct edits in Obsidian remain supported.
4. Agent writes go only through Fundus operations.
5. Read-only context retrieval may happen opportunistically.
6. Mutations are explicit, conflict-aware, and recoverable.
7. The corpus remains understandable without Codex or the plugin.
8. Administrative operations do not dominate the normal workbench surface.

## Current corpus state

The canonical local corpus is:

```text
/Users/christian/vault/Hypatos/Fundus
```

The legacy `Wiki/` corpus was migrated on 2026-07-09, verified, backed up, and retired. `Fundus/` is the single live work-knowledge root.

The personal path above describes the current owner's environment. It MUST NOT be embedded as a default in a distributable plugin package.

## Product audience and distribution

The near-term product optimizes for one user and one local corpus. It is nevertheless designed so another user can install it by configuring a vault path.

In scope:

- personal local use,
- multiple repositories,
- cross-repository areas,
- ordinary direct Obsidian editing by the human,
- one or more local Codex processes,
- hundreds to low thousands of notes,
- recovery from backups and archives.

Out of scope for the next release:

- real-time team collaboration,
- remote hosted synchronization,
- access-control systems,
- complex graph visualization,
- semantic vector infrastructure,
- a web user interface,
- autonomous bulk rewriting of the corpus.

## Source hierarchy

When evidence conflicts, use this order:

1. Source code for implemented behavior.
2. Current primary work sources such as Jira, GitHub, Confluence, Slack, interviews, or the user's direct statement.
3. Fundus as durable context, discussion history, and prior decisions.
4. Archived Fundus content as explicitly historical evidence.

Fundus must not silently override fresher evidence. A stale note should produce a concise correction proposal or a verification-state update.

## Core interaction model

### Read-only implicit context

Codex may invoke Fundus implicitly during ticket, research, architecture, or implementation work when prior context is likely to help.

Implicit use is read-only from the user's perspective:

```text
search
read best match
read a bounded number of additional candidates when necessary
```

If an opportunistic lookup finds nothing useful, Codex may remain silent. If the user explicitly requested a Fundus search, it reports the result even when empty.

### Explicit search

Representative intent:

```text
Search Fundus for BACKEND-2291.
Find prior decisions about prompt authoring.
Show archived context for the old extraction design.
```

The result is compact and includes enough metadata to decide what to read:

```json
{
  "path": "Fundus/demo/prompt-boundary.md",
  "title": "Prompt Boundary",
  "scope": "project",
  "scope_path": "demo",
  "score": 98,
  "confidence": "high",
  "reason": ["ticket", "alias"],
  "updated": "2026-07-09T12:00:00+02:00",
  "last_verified": "2026-07-09",
  "revision": "sha256:..."
}
```

### Save

Representative intent:

```text
Save this finding in Fundus.
Document this decision.
Remember this durable implementation constraint.
```

The backend performs duplicate detection before creating a note. If a likely match exists, it returns update candidates rather than creating a duplicate automatically.

### Update

The normal safe sequence is:

```text
search
read with revision
build proposal
show or internally validate diff
apply with expected revision
refresh derived index
confirm briefly
```

Explicit broad write intent may allow proposal and apply within the same user turn, but the backend still enforces revision safety.

### Stale-note correction

A stale-note proposal includes:

```text
target path
base revision
reason for staleness
primary evidence
proposed mode
proposed content or diff
metadata changes
```

Ordinary research does not silently rewrite stale Fundus content.

### Move, archive, and restore

Move changes location without changing stable note identity.

Archive:

- is explicit,
- preserves the note,
- mirrors the active path under `_archive`,
- records original path and reason,
- removes the note from normal evidence retrieval.

Restore validates the archived original path and fails safely if the destination conflicts.

## Scope model

### Project scope

Project scope is the default for implementation-local knowledge:

```text
Fundus/{project}/...
```

Examples:

- code behavior,
- repository architecture,
- tests,
- deployment notes,
- project-specific runbooks,
- ticket research tied to one implementation.

A project name is one safe path segment.

### Area scope

Area scope is explicit for cross-repository or domain knowledge:

```text
Fundus/Epics/{name}/...
Fundus/Domains/{name}/...
Fundus/Decisions/{name}/...
Fundus/Interviews/{name}/...
Fundus/References/{name}/...
Fundus/Operations/{name}/...
```

Examples:

- domain models,
- cross-repository capabilities,
- discovery and interviews,
- story maps,
- strategic decisions,
- epics spanning several services.

### Logical scope versus physical folder

`scope_path` identifies the logical scope root:

```yaml
scope: area
scope_path: Epics/AI Agent Templates
```

A note may physically live in:

```text
Fundus/Epics/AI Agent Templates/references/source-notes.md
```

The physical folder remains available through `path`; it does not change the logical scope.

### Canonical classifier

One scope classifier is shared by:

```text
create
move
normalize
migrate
index
archive
restore
doctor
```

No operation infers scope independently from string-prefix heuristics.

## Corpus and document model

### Canonical storage

Markdown is canonical. Generated indexes and reports are caches or diagnostics.

Target layout:

```text
Fundus/
├── project-name/
│   ├── index.md
│   ├── overview.md
│   ├── research/
│   └── decisions/
├── Epics/
│   └── AI Agent Templates/
│       ├── index.md
│       ├── log.md
│       ├── overview.md
│       ├── decisions/
│       ├── open-questions/
│       ├── stories/
│       ├── interviews/
│       ├── domain-model/
│       ├── implementation-map/
│       └── references/
├── Domains/
├── Decisions/
├── Operations/
└── _archive/
```

### Concept notes

A new active non-reserved note uses the local OKF-compatible profile:

```yaml
---
type: Research
title: Prompt Authoring Boundary
description: Current boundary between prompt authoring and prompt execution.
id: project/prompting-service/prompt-authoring-boundary
scope: project
scope_path: prompting-service
created: 2026-07-10T10:00:00+02:00
updated: 2026-07-10T10:00:00+02:00
timestamp: 2026-07-10T10:00:00+02:00
project: prompting-service
tags:
  - fundus
  - project/prompting-service
aliases:
  - BACKEND-2291
resource: https://jira.example/browse/BACKEND-2291
status: active
last_verified: 2026-07-10
---
```

Recommended provenance fields may include:

```yaml
verified_against:
  - github:org/repo@commit
  - jira:BACKEND-2291
source_fingerprint: github:org/repo:path@sha256
verification_status: current
```

Unknown supported frontmatter fields must survive round trips.

### Reserved files

Active `index.md` and `log.md` are reserved files:

- no concept frontmatter,
- navigation or chronological content only,
- not ranked as ordinary evidence,
- may be indexed as explicitly reserved records.

`overview.md` holds the scope's concept metadata.

### Redirects

When a move leaves a stub, the stub is a first-class redirect:

```yaml
type: Redirect
redirect_to: Fundus/Epics/AI Agent Templates/prompt-boundary.md
```

Redirects are excluded from normal evidence search and resolved on read.

### Complete read delivery

Agent-facing reads use a bounded, lossless continuation contract rather than assuming that a host will display an arbitrarily large tool result.

The first read returns either the complete note or the first exact segment. Every result reports:

```text
requested path
resolved path
redirect state
content revision
current offset
next offset
total character count
completion state
opaque next cursor when incomplete
```

The server controls the maximum page size, currently 2,000 decoded characters. A caller follows the cursor until completion and concatenates only pages with the same revision. Cursors are bound to the requested path, resolved target, revision, and next offset. If direct editing changes any bound state between pages, Fundus returns a stale-cursor error and the caller restarts from the first page.

Short notes still complete in one call. Long notes must never rely on silent host truncation, an arbitrary increased output limit, or an agent guessing that the visible text is complete.

### Stable revision

Every read operation returns a revision derived from the canonical bytes, normally SHA-256.

Mutations that can overwrite content accept `expected_revision`. A mismatch returns a conflict and writes nothing.

## Search and index target

The index remains a lightweight JSON cache at:

```text
{vault_path}/{fundus_dir}/.fundus-index.json
```

Each record stores bounded retrieval data:

```text
path
stable id
scope
scope path
title
description
aliases
resource
status
owner
last verified
tags
headings
bounded excerpt
ticket ids
normalized tokens
archive state
content revision
mtime
```

Requirements:

1. Search semantics are the same with and without an index.
2. A search detects changed, new, and removed files in its relevant scope.
3. Stale entries are refreshed or bypassed before results are returned.
4. Archived notes remain excluded unless requested.
5. Corrupt indexes fall back safely and produce a diagnostic.
6. Full rebuild remains deterministic.
7. Search output stays compact by default.
8. Benchmarks are recorded for 2,000 representative notes.

The initial performance target is a warm local p95 search at or below 100 ms for 2,000 notes on the primary development machine. If the baseline cannot meet that target, record the measurements and optimize before changing storage technology.

## Write safety and concurrency

### Atomicity

Single-file replacements use a temporary file in the destination directory, flush data as appropriate, and atomically replace the destination.

### Optimistic concurrency

Read returns a revision. Apply requires the expected revision for overwrite-like operations.

### Locking

A corpus lock serializes note-plus-index mutations. The lock implementation:

- has bounded acquisition time,
- reports lock ownership diagnostics,
- recovers from stale locks safely,
- is testable in temporary vaults,
- does not leave persistent state after read-only calls.

### Multi-step operations

Move, archive, restore, backup restore, and migration promotion use atomic rename where possible and a journal or rollback plan where not.

A failed operation must not silently leave:

- duplicate active and archived copies,
- a removed source without a valid destination,
- an index that claims a different corpus state,
- an unrecoverable partially promoted migration.

## Target implementation architecture

```text
User or Codex
    |
    +-- Skill policy
    |     +-- implicit read-only context
    |     +-- explicit curation
    |
    +-- MCP transport --------+
    |                         |
    +-- CLI transport --------+--> Application operations
                                      |
                                      +-- scope and path values
                                      +-- note repository
                                      +-- frontmatter codec
                                      +-- revision and locking
                                      +-- search/index
                                      +-- backup/archive
                                      +-- proposals/provenance
```

Target source layout:

```text
fundus/
├── config.py
├── models.py
├── paths.py
├── frontmatter.py
├── repository.py
├── search.py
├── revisions.py
├── locking.py
├── operations.py
├── errors.py
├── cli.py
├── mcp_server.py
└── admin/
    ├── backup.py
    ├── migration.py
    ├── normalization.py
    └── verification.py
```

The exact module names may change, but the boundaries are required.

## MCP target

### Transport

The stdio server uses one UTF-8 JSON-RPC message per line. It writes no non-MCP text to stdout.

### Lifecycle

The server:

- accepts `initialize` as the first interaction,
- negotiates from an explicit supported-version list,
- advertises only implemented capabilities,
- waits for `notifications/initialized` before normal server-originated interaction,
- rejects malformed requests with protocol errors,
- returns unknown-tool errors without terminating,
- shuts down cleanly when stdin closes.

### Tool contracts

Tools expose input schemas, output schemas where practical, structured content, and behavior annotations.

Representative annotations:

| Operation | Read only | Destructive | Idempotent | Open world |
| --- | --- | --- | --- | --- |
| search | yes, unless persistent repair occurs | no | yes | no |
| read | yes | no | yes | no |
| propose update | yes | no | yes | no |
| apply create | no | no | no | no |
| apply update | no | yes | conditional | no |
| move | no | yes | no | no |
| archive | no | yes | no | no |
| index rebuild | no | no | yes | no |

The implementation must not advertise a read-only hint for a tool that persistently repairs an index.

### Tool surface

Normal server:

```text
search_fundus
read_note
propose_create
apply_create
propose_update
apply_update
move_note
archive_note
restore_note
doctor
```

Administrative operations may remain CLI-only or move to a separately enabled server:

```text
backup
migration
global normalization
index repair
cleanup
corpus verification
```

Compatibility wrappers may remain temporarily but should be deprecated explicitly.

## Configuration target

Precedence:

1. explicit CLI/MCP argument where supported,
2. `OBSIDIAN_VAULT_PATH` for compatibility,
3. `FUNDUS_CONFIG_PATH`,
4. project `.codex/fundus.json`,
5. user configuration such as `~/.config/fundus/config.json`,
6. non-personal built-in defaults.

The package contains an example configuration, not a personal absolute path.

`doctor` reports:

```text
resolved project root
project name
scope
vault path
Fundus root
configuration source for each value
Python executable
plugin root
index state
lock state
corpus verification summary
```

## Plugin packaging target

The plugin root contains:

```text
.codex-plugin/plugin.json
.mcp.json
skills/fundus/
```

The companion `.mcp.json` uses a Codex-supported direct server map or `mcp_servers` wrapper.

The exact packaged command is exercised by integration tests.

Plugin manifest, MCP server info, marketplace metadata, and release notes share one version source.

The repository contains the license declared by the manifest.

## Skill behavior target

The skill remains compact. It communicates:

- when Fundus should and should not be used,
- evidence hierarchy,
- implicit read-only behavior,
- scope inference,
- scan before create,
- propose/apply behavior,
- no raw Markdown fallback,
- archive quietness,
- blocked-write reporting.

Exact commands and admin workflows stay in reference documents.

## Release criteria

The next release is ready only when:

1. Packaged MCP integration completes initialize, tools/list, and a real tool call through a conforming client.
2. Path traversal and scope-boundary tests pass.
3. `area init` produces a corpus that immediately passes verification.
4. Indexed and unindexed search pass the same retrieval fixtures.
5. External Obsidian edits are visible on the next search.
6. Revision conflicts prevent lost updates.
7. Concurrent mutations do not corrupt the index.
8. Frontmatter round trips pass the supported-value corpus.
9. Move tests cover every project/area direction.
10. The default tool surface excludes one-time migration operations.
11. The built artifact contains no personal vault path.
12. CI runs focused, package, protocol, and unit tests.
13. Documentation describes actual behavior.
14. A clean temporary-vault end-to-end scenario passes.
15. `task verify` passes.

## External references

- Codex plugin packaging: https://learn.chatgpt.com/docs/build-plugins
- MCP transport: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- MCP lifecycle: https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
- MCP tools: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- MCP schema: https://modelcontextprotocol.io/specification/2025-11-25/schema
