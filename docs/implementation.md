# Fundus Implementation Notes

Status: current baseline plus target implementation contract
Reviewed: 2026-07-10

## Document role

This document has two deliberately separate purposes:

1. Describe confirmed current repository behavior as observed during review.
2. Define the technical contract that planned phases will implement.

A planned item is not current behavior until its phase is completed and this document is updated.

Use:

- `docs/fundus-target-picture.md` for product and architecture decisions.
- `docs/agent-implementation-tracker.md` for phase order and progress.
- `docs/architecture-invariants.md` for normative rules.
- `docs/testing-and-validation.md` for release evidence.

## Current implementation baseline

### Repository surfaces

The current repository contains:

```text
.codex-plugin/plugin.json
.mcp.json
SKILL.md
agents/openai.yaml
config.json
config.example.json
requirements.txt
vendor/
scripts/fundus.py
scripts/fundus_mcp.py
scripts/build_plugin_marketplace.py
scripts/validate_plugin_package.py
scripts/audit_token_budget.py
Taskfile.yml
tests/
docs/
```

The direct skill package is built under:

```text
dist/fundus
```

The plugin package and local marketplace are built under:

```text
dist/fundus-plugin
dist/fundus-marketplace
```

### Current domain behavior

`scripts/fundus.py` currently implements a large shared domain/helper module covering:

- config resolution,
- project and area scopes,
- frontmatter parsing and formatting,
- secret redaction,
- atomic file writes,
- create, read, update, and move,
- index rebuild and entry refresh,
- archive candidates, archive, restore, and cleanup,
- backup creation and manifest inspection,
- Wiki-to-Fundus migration,
- frontmatter normalization,
- corpus verification,
- CLI parsing and output.

`scripts/fundus_mcp.py` wraps the same functions in a custom stdio JSON-RPC/MCP adapter.

This shared-domain direction is correct and should be preserved during refactoring.

### Current corpus state

The current personal corpus is under:

```text
/Users/christian/vault/Hypatos/Fundus
```

The legacy `Wiki/` source was migrated and retired on 2026-07-09. Migration and backup functionality remain useful for recovery, but migration is no longer an everyday workbench action.

### Current configuration

Current precedence is:

1. explicit CLI operation arguments where supported,
2. `OBSIDIAN_VAULT_PATH` compatibility,
3. `FUNDUS_CONFIG_PATH`,
4. project `.codex/fundus.json`,
5. `${XDG_CONFIG_HOME:-~/.config}/fundus/config.json`,
6. portable packaged and built-in defaults.

The packaged `config.json` contains no vault path. A caller must select a vault through one of the higher-precedence sources. `doctor` reports provenance per resolved value plus the Python executable and runtime/plugin root.

Legacy corpus preparation uses `repair-frontmatter` before normalization. The repair recognizes only unambiguous plain-text `title` and `archived_reason` values whose unquoted colon made old YAML invalid; it is dry-run-first, atomic, journaled, and body preserving. Verification records malformed paths individually, and bulk normalization excludes reserved `index.md` and `log.md` files.

### Current search

The index is:

```text
{vault_path}/{fundus_dir}/.fundus-index.json
```

Index version 4 stores canonical search records with metadata, bounded excerpts, tokens, ticket IDs, archive/redirect kind, provenance and verification state, content revision, and a fast `mtime_ns`/`ctime_ns`/size fingerprint.

Current behavior:

- index rebuild scans active and archived Markdown,
- create and update refresh an existing index entry,
- archive and restore refresh source and destination entries,
- every scan enumerates the relevant physical scope and validates cached fingerprints,
- changed and added files are converted to current records in memory and deleted files disappear immediately,
- indexed and uncached records use the same record builder, scorer, filters, and deterministic ordering,
- read-only search never persists repairs; `index rebuild` is the explicit persistence boundary,
- corrupt, incompatible, and missing indexes fall back to current Markdown without being overwritten,
- index status reports `current`, `missing`, `incompatible`, or `corrupt` plus stale paths,
- redirects and reserved files are never ordinary evidence, while archives remain opt-in.

This in-memory repair policy keeps scan and its MCP wrapper read-only. The final 0.2.0 benchmark on the primary arm64 macOS/Python 3.14.6 machine measured 2,000-note warm search at 49.180 ms p50 and 50.927 ms p95, below the 100 ms release target. Full rebuild was 1,733.529 ms, one-file in-memory refresh was 47.622 ms, and the index was 4,092,517 bytes. Re-run with `task benchmark:search`.

### Current write behavior

`atomic_write()` flushes and fsyncs a temporary file in the destination directory before atomically replacing the destination. Read and search results include a `sha256:` revision. Overwrite-like operations accept `expected_revision`, check it while holding the mutation lock, and fail with `REVISION_CONFLICT` before writing when it differs.

A tested lock file under the vault's `.fundus-locks/` directory serializes note-plus-index mutations across processes. Acquisition has a bounded timeout, live-owner diagnostics, same-host dead-process stale recovery, same-thread reentrancy, and exception-safe release. Pure reads and dry-runs do not acquire it.

Move, archive, restore, and backup restore snapshot every affected file plus the index in `.fundus-journal/`. They use atomic rename where a path changes, roll back injected failures immediately, and recover any prepared journal on the next mutation lock acquisition. Migration promotes only a fully verified staging tree; a failure after promotion leaves the supported resumable destination state.

Backup manifests can be verified file-by-file by size and SHA-256. Restore is a dry-run by default; apply verifies first, creates a safety backup, restores under the lock and journal, rebuilds the index, and requires corpus verification before commit.

### Current proposal, duplicate, and provenance behavior

Create and update use deterministic, read-only proposal operations before apply. Proposals contain an integrity ID, target path and revision where applicable, redaction warnings, deterministic unified body diff, metadata changes, and current duplicate candidates. Apply recomputes proposal integrity, freshness, and duplicates while holding the mutation lock.

Create duplicate detection covers exact title, stable ID, alias, ticket, resource, and high-confidence title/metadata similarity. Any candidate blocks apply unless the caller explicitly enables the override and passes every reviewed candidate path. Update proposals use the same check while excluding the note being updated.

Operational provenance fields are `verified_against`, `source_fingerprint`, `verification_status`, `last_verified`, and optional `stale_reason`. `mark_stale` records contradicted evidence; `verify_note` requires a source reference or fingerprint and transitions the note to current. Search records expose verification status and source fingerprint.

### Current frontmatter behavior

Fundus uses a pinned, vendored `ruamel.yaml==0.19.1` round-trip codec. It deliberately supports scalar values and lists of scalar values, preserves unknown supported keys and comments, quotes serialized values safely, and normalizes known list and timestamp fields through typed helpers.

Metadata-only changes preserve the decoded UTF-8 body exactly. LF, CRLF, and a leading BOM are retained. Unsupported nested values, custom tags, duplicate keys, non-string keys, malformed delimiters, and invalid UTF-8 fail with `FRONTMATTER_INVALID` instead of being reinterpreted. The full supported profile is documented in `docs/frontmatter-profile.md`.

### Current MCP behavior

The server currently:

- derives name, title, concise description, handler, input schema, output schema, category, compatibility state, and behavior annotations from one operation registry,
- lists a compact proposal-oriented workbench: `search`, `read`, `propose_create`, `apply_create`, `propose_update`, `apply_update`, `move`, `archive`, `restore`, `mark_stale`, `verify_note`, and `doctor`,
- exposes maintenance operations only through explicit `--admin` MCP mode or the CLI,
- accepts the previous normal tool names as unlisted deprecated compatibility aliases,
- returns successful object results as both backward-compatible text JSON and schema-validated `structuredContent`,
- returns tool failures with `isError`, text JSON, and structured `error`/stable `code`,
- uses compact newline-delimited UTF-8 JSON-RPC messages on stdio,
- accepts `initialize`, `notifications/initialized`, `ping`, `tools/list`, and `tools/call`,
- supports and negotiates the explicit protocol versions `2025-11-25` and `2025-06-18`,
- gates normal operations until the initialization lifecycle completes,
- validates basic JSON-RPC envelopes and `tools/call` request types,
- validates required, unexpected, typed, and enumerated tool arguments against the generated input schemas,
- returns unknown tools and malformed calls as protocol errors,
- validates output objects against advertised schemas and turns contract violations into `OUTPUT_SCHEMA_MISMATCH`,
- continues serving after recoverable parse, protocol, and tool errors,
- derives `serverInfo.version` from the nearest plugin manifest when packaged.

An independent subprocess client exercises the source server and exact packaged command through initialize, initialized notification, tools/list, a real temporary-vault tool call, unknown-tool recovery, and a final ping.

The CLI and every MCP handler call the same core application functions. Immediate create/update names remain unlisted compatibility aliases; proposal/apply is the preferred workbench contract.

### Current plugin configuration

The plugin manifest points to `.mcp.json` through its `mcpServers` field.

The current `.mcp.json` uses the documented direct server-map shape:

```json
{
  "fundus": {
    "command": "./skills/fundus/scripts/fundus_mcp_launcher.sh",
    "args": [],
    "cwd": "."
  }
}
```

The POSIX launcher prefers `python3` and falls back to `python`; integration tests exercise environments where each command is the only interpreter name. Current Codex plugin documentation accepts a direct server map or a wrapped `mcp_servers` object. The repository validator accepts those documented shapes, checks launcher executability, licenses, and personal-path absence, and rejects the old camel-case wrapper.

### Current path behavior

Ordinary note operations use explicit active, archived, reserved, backup, and migration path value objects. Active and archive note operations are constrained to their respective roots under Fundus after symlink resolution. Note paths require `.md`, reject directories and reserved `index.md`/`log.md`, and preserve the existing vault-relative `Fundus/...` interface.

Project names are safe, non-reserved single segments. Area paths require an allowlisted root such as `Epics`, `Domains`, or `Operations` plus a logical area name. Global project enumeration excludes archive and area roots.

Archived `original_path` metadata is treated as untrusted input and must resolve as an active Fundus note before restore. Path-related failures carry stable codes such as `PATH_OUTSIDE_FUNDUS`, `PROJECT_NAME_INVALID`, `AREA_PATH_INVALID`, and `NOTE_PATH_INVALID`.

### Current reserved-file behavior

The documented corpus contract says active `index.md` and `log.md` have no frontmatter.

Migration and verification enforce that rule.

`area_init()` writes concept frontmatter only to `overview.md`; `index.md` and `log.md` are frontmatter-free reserved files. A newly initialized area passes corpus verification.

### Current scope move behavior

One path-derived classifier now defines logical scope for create, update, normalization, migration, indexing, archive/restore, and move operations. A project scope is the first path segment. An area scope is exactly an allowlisted area root plus one logical name, such as `Epics/AI Agent Templates`; deeper folders such as `references/` remain physical placement and never become part of `scope_path`.

Index version 2 records the canonical scope, stable ID, kind, physical parent, and scope-relative path. Normalization dry-runs explicitly report legacy `scope_path` values that overloaded a physical subfolder.

Move supports the full project/area direction matrix. It retains the destination note's stable ID and neutral tags, replaces the old scope tag, maintains the `project` field only for project scope, and refreshes both index paths. `--leave-stub` writes a distinct `Redirect` record with validated canonical `redirect_to` metadata and a relative Markdown link. Redirects are absent from ordinary search, reads follow them with a bounded hop count, and loops or invalid targets fail with stable redirect codes.

### Current tests

The test suite covers unit and operation contracts, fixture-driven frontmatter/path adversarial cases, cross-process concurrency and rollback, proposal/apply and stale evidence workflows, MCP schema/lifecycle/error contracts, an independent source and packaged stdio client, configuration and launcher portability, a clean temporary-vault CLI end-to-end, documentation consistency, artifact privacy, and a measured 2,000-note search gate.

## Current source architecture and extraction seams

The stable entrypoints are now thin facades:

```text
scripts/fundus.py              compatibility import and CLI facade
scripts/fundus_mcp.py          compatibility MCP entrypoint
scripts/fundus_core/runtime.py application runtime and CLI dispatch
scripts/fundus_core/mcp_server.py MCP contracts, validation, and JSON-RPC transport
```

This is an incremental boundary, not a big-bang rewrite. `runtime.py` remains consolidated for the 0.2.0 compatibility release; `scripts/fundus_core/README.md` records the protected seams for later extraction. The intended decomposition remains:

```text
fundus/
├── config.py
├── models.py
├── errors.py
├── paths.py
├── frontmatter.py
├── repository.py
├── revisions.py
├── locking.py
├── search.py
├── operations.py
├── cli.py
├── mcp_server.py
└── admin/
    ├── backup.py
    ├── migration.py
    ├── normalization.py
    └── verification.py
```

Compatibility entrypoints remain:

```text
scripts/fundus.py
scripts/fundus_mcp.py
```

They are thin and are enforced at 50 lines or fewer by the documentation/architecture checks. New transport behavior belongs in `mcp_server.py`; future runtime extraction must keep the facade API stable and pass the complete suite after every move.

## Target value objects

### Scope

```python
@dataclass(frozen=True)
class Scope:
    kind: Literal["project", "area"]
    path: str
    display_name: str
```

Scope construction validates its own invariants.

### NotePath

Use explicit constructors:

```python
NotePath.active(config, value)
NotePath.archived(config, value)
NotePath.any_fundus(config, value)
```

Do not expose one generic vault-relative resolver to ordinary note operations.

### Revision

```python
@dataclass(frozen=True)
class Revision:
    algorithm: Literal["sha256"]
    value: str
```

Revision is computed from canonical file bytes.

### Operation result

Operation results are structured dictionaries or typed data that can be serialized consistently by CLI and MCP. They include stable error codes and avoid full note content unless requested.

## Target operation contracts

### Search

Input:

```text
query
scope
limit
include archived
include snippet
```

Behavior:

1. Resolve and validate scope.
2. Load index metadata.
3. detect changed, new, and removed files in the relevant scope,
4. refresh in memory or persist under the correct mutation policy,
5. run the common scorer,
6. exclude redirects and archives unless requested,
7. return compact results with revisions.

### Read

Input:

```text
active or explicitly archived Fundus path
optional opaque continuation cursor
```

Output:

```json
{
  "path": "...",
  "resolved_path": "...",
  "content": "...",
  "revision": "sha256:...",
  "redirected": false,
  "offset": 0,
  "next_offset": 2000,
  "total_characters": 6000,
  "complete": false,
  "next_cursor": "opaque"
}
```

Read follows a validated redirect with a bounded hop count. Agent-facing MCP reads are server-bounded and lossless: callers continue with `next_cursor` until `complete` is true. All pages are bound to one requested path, resolved target, and revision. A malformed cursor fails with `READ_CURSOR_INVALID`; a direct edit or redirect change between pages fails with `READ_CURSOR_STALE` so the caller can discard partial pages and restart.

The server-controlled bound is 2,000 decoded Python characters. It was selected against the full JSON-RPC representation, including both text JSON and `structuredContent`, with a 32 KiB per-response release budget. Content is sliced only after one byte snapshot is decoded and hashed, preserving BOM, Unicode, LF/CRLF, and long lines exactly.

The opaque version-1 cursor carries requested path, resolved target, SHA-256 revision, and next character offset inside an integrity-checked base64url envelope. Malformed, tampered, cross-note, unsupported-version, and out-of-range cursors fail with `READ_CURSOR_INVALID`. Changed content or redirect resolution fails with `READ_CURSOR_STALE`. Short notes remain single-call reads. The full-result CLI compatibility route internally follows the same page operation; the documented agent fallback uses `read --paged` and passes each cursor back with `--cursor`.

### Propose create

Behavior:

1. Validate desired scope and metadata.
2. search for normalized title, ID, aliases, ticket keys, and canonical resource,
3. return duplicate candidates or a create proposal,
4. do not write.

### Apply create

Input includes a proposal or equivalent validated fields. It fails on path or stable-ID conflict.

### Propose update

Input:

```text
path
base revision
mode
section if applicable
new content
evidence and metadata changes
```

It returns a diff-like structured proposal and does not write.

### Apply update

Requires `expected_revision`. It:

1. acquires the mutation lock,
2. re-reads and verifies revision,
3. applies redaction with warnings,
4. writes atomically,
5. updates the index under the same lock,
6. returns the new revision.

### Move

Move uses the canonical scope classifier for the destination. It preserves stable ID, updates scope metadata, and optionally creates a first-class redirect.

### Archive and restore

Archive and restore validate active/archive path types. `original_path` is untrusted metadata and must be revalidated.

## Target error model

Use stable machine-readable codes:

```text
CONFIG_INVALID
PATH_OUTSIDE_FUNDUS
PROJECT_NAME_INVALID
AREA_PATH_INVALID
NOTE_NOT_FOUND
NOTE_ALREADY_EXISTS
DUPLICATE_CANDIDATE
REVISION_CONFLICT
LOCK_TIMEOUT
FRONTMATTER_INVALID
INDEX_INVALID
MCP_PROTOCOL_VERSION_UNSUPPORTED
MCP_REQUEST_INVALID
MCP_TOOL_UNKNOWN
MUTATION_INCOMPLETE
BACKUP_INVALID
```

CLI output may include a human-readable message. MCP distinguishes:

- JSON-RPC protocol errors,
- tool execution errors with `isError: true`.

Unknown tools and malformed protocol messages are protocol errors.

## Target frontmatter implementation

P15 must make and document one choice:

### Preferred path

Use a pinned YAML implementation that can safely parse the supported corpus and preserve unknown keys. Prefer round-trip behavior when package provisioning is reliable.

### Allowed fallback

Retain a zero-dependency subset only when:

- the subset is documented,
- unsupported constructs fail explicitly,
- serializer quoting is correct,
- supported values round trip,
- type normalization is deliberate,
- property and fixture tests are comprehensive.

Silent pseudo-YAML is not an acceptable target.

## Target index implementation

Index version increases when its shape changes.

Recommended record:

```json
{
  "path": "Fundus/demo/note.md",
  "id": "project/demo/note",
  "scope": "project",
  "scope_path": "demo",
  "kind": "concept",
  "title": "Note",
  "description": "...",
  "aliases": [],
  "resource": null,
  "tags": [],
  "headings": [],
  "excerpt": "...",
  "tokens": [],
  "ticket_ids": [],
  "archived": false,
  "redirect_to": null,
  "revision": "sha256:...",
  "mtime_ns": 0,
  "size": 0
}
```

Freshness compares path, revision or a safe fast fingerprint, mtime, and size. Correctness must not depend solely on mtime.

All index updates occur under the corpus mutation lock.

## Target locking and transactions

Provide one lock abstraction. The implementation may use a small dependency or a tested lock-file strategy.

Requirements:

- bounded timeout,
- diagnostic owner metadata,
- stale-lock handling,
- process-safe behavior,
- no lock acquisition for pure read-only parsing,
- mutation lock covers note and index changes.

Multi-step operations use:

- atomic rename where possible,
- staged destination,
- explicit rollback,
- or a small journal.

Tests inject failures after each logical step.

## Target MCP implementation

The project may keep a custom adapter or adopt the official Python MCP SDK. The decision is based on packaging reliability and testability.

Regardless of implementation:

- stdio is newline-delimited JSON,
- stdout contains only MCP messages,
- supported versions are explicit,
- initialization state is tracked,
- advertised capabilities are accurate,
- tool arguments are validated,
- output schemas are honored,
- structured content is returned,
- behavior annotations are provided,
- the packaged command is integration-tested.

Supported protocol versions confirmed during P11:

```text
2025-11-25
2025-06-18
```

Codex host verification negotiated `2025-11-25`; integration coverage also retains `2025-06-18` compatibility.

## Target `.mcp.json`

Use a documented Codex shape, preferably a direct server map:

```json
{
  "fundus": {
    "command": "python3",
    "args": [
      "./skills/fundus/scripts/fundus_mcp.py"
    ],
    "cwd": "."
  }
}
```

The packaged launcher selects `python3` and falls back to `python`, and is tested with each command as the only interpreter name.

The custom package validator validates the documented direct and `mcp_servers` shapes and rejects the old repository-specific camel-case wrapper.

## Configuration contract

Configuration source precedence:

```text
explicit operation argument
OBSIDIAN_VAULT_PATH
FUNDUS_CONFIG_PATH
project .codex/fundus.json
user ~/.config/fundus/config.json
non-personal built-in defaults
```

`config.example.json` remains portable, while package-local `config.json` provides only non-personal defaults.

Package validation fails if a known personal path appears in distributable files. The plugin manifest is the release-version source; the MCP server discovers that manifest at runtime and the marketplace builder copies its value into marketplace metadata.

## Tool-surface migration

During compatibility:

- keep existing MCP tool names as wrappers where practical,
- add new proposal/apply operations,
- mark old immediate mutation names deprecated in descriptions,
- remove one-time migration tools from the default surface only after CLI/admin access and docs are verified.

## Documentation rules during implementation

After a phase:

- current behavior moves from “target” to “current” only when tests pass,
- README changes describe only shipped behavior,
- SKILL instructions remain compact,
- examples use current tool names,
- external spec links use the tested protocol revision,
- tracker records evidence and remaining risks.

## External references

- https://learn.chatgpt.com/docs/build-plugins
- https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- https://modelcontextprotocol.io/specification/2025-11-25/schema
