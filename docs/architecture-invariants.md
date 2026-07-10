# Fundus Architecture Invariants

Status: normative target contract
Date: 2026-07-10

## Document role

These invariants define behavior that must remain true across the CLI, MCP server, indexing, migration, archive, and future refactors. Tests should refer to invariant identifiers where practical.

The terms **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative.

## Authority and evidence

### FND-001 — Primary evidence wins

Source code is authoritative for implemented behavior. Current primary work sources and the user's direct statements outrank Fundus. Fundus provides durable context, prior decisions, and discussion history.

### FND-002 — Stale evidence is visible

Fundus MUST NOT silently override fresher evidence. When a note appears stale, the normal workflow produces a correction proposal or records a verification state.

### FND-003 — Agent writes use Fundus operations

Agents MUST write through the Fundus operation layer exposed by MCP or the CLI. They MUST NOT use raw Markdown editing, shell redirection, generic Obsidian write tools, or an editor API as a fallback.

Human direct edits in Obsidian remain supported.

## Corpus boundaries

### FND-004 — Ordinary note operations stay inside Fundus

Search, read, create, update, move, archive, restore, normalize, and note-level diagnostics MUST constrain note paths to:

```text
{vault_path}/{fundus_dir}
```

Being inside the wider vault is not sufficient.

### FND-005 — Operation-specific path types

The implementation MUST distinguish:

```text
FundusRoot
ActiveNotePath
ArchivedNotePath
ReservedFilePath
BackupPath
MigrationSourcePath
```

A value valid for one category MUST NOT be accepted automatically by another.

### FND-006 — Project names are safe single segments

A project name MUST be one non-empty path segment. It MUST reject separators, absolute paths, `.`, `..`, reserved roots, and traversal after resolution.

### FND-007 — Area roots are explicit

An area path MUST be relative to the Fundus root and begin with an allowed area root or an explicitly configured equivalent. Reserved roots such as `_archive` MUST NOT be used as active areas.

### FND-008 — Symlink escapes are rejected

Resolved paths MUST remain inside the appropriate root after following existing symlinks. Tests MUST cover symlinked parents and targets where the platform permits.

## Scope and metadata

### FND-009 — One scope classifier

Create, move, normalize, migrate, index, archive, and restore MUST use one canonical scope classifier.

### FND-010 — Logical scope is stable

`scope_path` represents the logical project or area root. A nested physical folder does not create a new scope.

### FND-011 — Stable identity is independent of filename

A note's stable `id` SHOULD survive safe filename or folder moves. Moving a note MUST NOT silently generate a new identity.

### FND-012 — Reserved files are not concept notes

Active `index.md` and `log.md` MUST contain no concept frontmatter. Metadata belongs in `overview.md` or another normal note.

Reserved files MAY be indexed for navigation, but they MUST be explicitly typed as reserved index records and MUST NOT be presented as ordinary evidence.

## Persistence and concurrency

### FND-013 — Markdown is canonical

Markdown files are the source of truth. The JSON search index and other generated files are derived state and MUST be rebuildable.

### FND-014 — Writes are atomic and conflict-aware

A note mutation MUST use an atomic filesystem replacement and MUST support an expected revision for operations that can overwrite content.

A revision mismatch MUST fail without writing.

### FND-015 — Corpus mutations are serialized

Operations that update notes and the index MUST use a corpus-level or appropriately scoped lock. Index read-modify-write sequences MUST NOT lose concurrent changes.

### FND-016 — Multi-step moves are recoverable

Move, archive, restore, migration promotion, and backup restore MUST either complete their logical mutation or leave enough journal/rollback information to recover safely.

### FND-017 — Restore metadata is untrusted input

An archived note's `original_path` MUST be validated as an active Fundus path before restore. It MUST NOT target arbitrary vault content.

### FND-018 — Backups are verifiable

Backups MUST include manifests and checksums. A restore or recovery workflow MUST verify the selected snapshot before promotion.

## Search and index

### FND-019 — Search semantics do not depend on cache presence

A query MUST produce materially equivalent matches and ranking whether the index is absent, current, or rebuilt immediately before the query.

### FND-020 — Stale index entries are repaired or bypassed

Before using an index entry, Fundus MUST detect changed, added, and removed files for the relevant search scope. It MAY incrementally refresh or fall back to direct parsing.

It MUST NOT knowingly return stale tokens or excerpts as current results.

### FND-021 — Archived notes remain quiet

Normal search excludes archived notes. Archive results require an explicit archive or historical intent and are marked clearly as archived evidence.

### FND-022 — Redirects are not evidence

A move stub or redirect note MUST be represented as a redirect, excluded from normal evidence ranking, and resolved automatically when read.

## MCP and CLI

### FND-023 — One application layer

CLI and MCP transports call the same operations. Neither transport implements independent scope, path, validation, or write rules.

### FND-024 — MCP is protocol-conformant

The stdio transport uses newline-delimited UTF-8 JSON-RPC messages. The server negotiates supported protocol versions, enforces lifecycle state, validates input, and distinguishes protocol errors from tool execution errors.

### FND-025 — Tool contracts are explicit

Every MCP tool has:

```text
name
title
description
input schema
output schema where practical
behavior annotations
operation handler
```

Structured results conform to the advertised output schema.

### FND-026 — Read-only means read-only

A tool marked read-only MUST NOT modify notes, index files, timestamps, lock files that outlive the request, or other persistent state.

A search that repairs a stale index is therefore a write-capable operation unless repair is performed in memory or through a separately modeled maintenance path. The implementation must choose and document the policy rather than mislabeling it.

## Configuration and packaging

### FND-027 — Distributable artifacts contain no personal path

A built plugin MUST NOT embed Christian's vault path as a runtime default.

### FND-028 — Configuration provenance is observable

`doctor` MUST report the resolved configuration values and the source of each relevant value without exposing secrets.

### FND-029 — Packaged command is tested exactly

Verification MUST launch the MCP command as packaged in `.mcp.json`, not an equivalent developer-only command.

### FND-030 — Version information has one source

Plugin manifest, MCP `serverInfo`, marketplace output, and release metadata MUST derive from one version source or be checked for equality.

## Safety and privacy

### FND-031 — Redaction is defense in depth

Redaction SHOULD reduce accidental secret persistence, but MUST NOT be presented as a complete secret scanner. It SHOULD return warnings when content was changed by redaction.

### FND-032 — Errors do not leak secret content

Errors and diagnostics MUST avoid echoing full note bodies, environment values, credentials, or unredacted input.

### FND-033 — Live-corpus maintenance is explicit

Migration, global normalization, backup restore, and bulk curation MUST be explicit admin actions with dry-run support and backup requirements where applicable.

### FND-034 — Agent-facing reads are provably complete

An agent-facing read MUST either return the complete note with an explicit completion marker or return a bounded, lossless segment with an opaque continuation cursor.

Every segment in one read sequence MUST be bound to the same requested path, resolved target, and content revision. If the note or redirect target changes during the sequence, continuation MUST fail and the caller MUST restart rather than combine revisions.

Silent truncation, an unmarked partial result, or a continuation sequence with gaps or duplicated content is not permitted.

The current release bound is 2,000 decoded characters per agent-facing page. A complete page has no continuation cursor; an incomplete page always has one.

### FND-035 — Area layout follows content

New area initialization MUST create only `overview.md` unless optional reserved files are explicitly requested. It MUST NOT pre-create empty category directories. Typed concept notes SHOULD remain at the logical area root; `sources/` MAY group multiple raw evidence notes.

### FND-036 — Layout planning is deterministic and read-only

An area-layout plan MUST NOT mutate the vault. Identical selected state MUST produce the same proposal ID, exact moves, revisions, stable IDs, link rewrites, collisions, and warnings.

### FND-037 — Layout apply is exact and recoverable

Layout apply MUST accept only the exact fresh proposal, serialize globally, reject collisions and changed revisions before writes, create and verify a current backup, journal all touched files, rebuild the index, verify the corpus, and roll back the logical mutation on failure.

### FND-038 — Layout moves preserve navigation and identity

A layout migration MUST preserve stable IDs and exact bytes for pure moves. When a moved path changes Markdown navigation, Fundus MUST rebase links inside moved documents and rewrite active backlinks while preserving labels, anchors, and titles. It MUST NOT introduce a broken local link that resolved before the migration.
