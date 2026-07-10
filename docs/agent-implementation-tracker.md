# Fundus Agent Implementation Tracker

Status: active remediation and second-release tracker
Date: 2026-07-10
First active phase: P11

## Agent read order

1. `README.md`
2. `docs/agent-implementation-tracker.md`
3. `docs/fundus-target-picture.md`
4. `docs/decision-record.md`
5. `docs/architecture-invariants.md`
6. `docs/implementation.md`
7. `docs/testing-and-validation.md`
8. source and tests

## Tracker rules

Status values:

```text
done
in_progress
ready
planned
blocked
deferred
superseded
```

Rules:

1. Work on the first `ready` phase unless the user names another.
2. Do not mark a phase done until all acceptance criteria pass.
3. Record commands, test results, and important manual evidence.
4. Add or update tests with every behavior change.
5. Update `docs/implementation.md` when current behavior changes.
6. Update `README.md`, `SKILL.md`, examples, and manifests only when user-facing behavior changes.
7. Change the target picture only for a durable decision change.
8. Never run implementation tests against the live Hypatos Fundus corpus.
9. Preserve CLI and MCP compatibility where practical, but do not preserve an unsafe or non-conformant behavior merely because it exists.
10. Keep each implementation pass scoped to one phase or a tightly coupled dependency.
11. Run focused tests during work and `task verify` before phase completion.
12. If official host or protocol documentation has changed, update the source references and record the resulting decision.

## Review correction

The previous tracker stated that no known first-release gaps remained. The 2026-07-10 review identified protocol, packaging, path, corpus, search, and concurrency gaps. That earlier statement is superseded by this tracker.

## Baseline retained from P0-P10

The existing project already delivered substantial capabilities:

| Historical phase | Status | Retained outcome |
| --- | --- | --- |
| P0 | done | staged Wiki-to-Fundus migration with backup and retirement |
| P1 | done | migration transformation and OKF-compatible concept metadata |
| P2 | done | corpus verification and smoke checks |
| P3 | done | lightweight index and compact ranked search |
| P4 | done | compact skill with progressive disclosure |
| P5 | done | dependency-free MCP wrapper over shared helper functions |
| P6 | done | plugin package and local marketplace skeleton |
| P7 | done | build, install, validation, and verification tasks |
| P8 | done | permission and vault-friction documentation |
| P9 | done | token/output footprint audit |
| P10 | done | first-release workbench examples and polish |

The historical implementation remains useful. P11-P20 harden and evolve it rather than discarding it.

## Current findings inventory

### Critical compatibility and correctness

- Ordinary path resolution is bounded by the vault rather than the Fundus root.
- Project overrides are not safe single-segment values.
- `area init` violates reserved-file rules.
- Search can trust stale index content.
- Indexed and unindexed search semantics differ.
- Writes have no optimistic concurrency check.
- Index read-modify-write is not locked.

### Important product and maintainability

- Move scope classification is heuristic and incomplete.
- Redirect stubs are not first-class search-excluded objects.
- Frontmatter parser is not a robust YAML implementation.
- Tool outputs lack output schemas and structured content.
- Tool annotations are absent.
- Normal and administrative operations share one large MCP surface.
- Package config embeds a personal path.
- Runtime interpreter selection differs between build and `.mcp.json`.
- Duplicate prevention exists mainly as skill guidance.
- Stale-note proposals are not first-class backend operations.
- Provenance is metadata, not yet an operational verification workflow.
- Core helper is a large module with several responsibilities.
- Manifest declares MIT but the reviewed repository did not expose a matching license file.

The P11 transport, lifecycle, package-shape, error-recovery, and independent-client findings are resolved. See the P11 completion evidence below.

## Phase board

| Phase | Status | Priority | Depends on |
| --- | --- | --- | --- |
| P11 — MCP and Codex package conformance | done | critical | none |
| P12 — Fundus path safety and corpus invariants | done | critical | none |
| P13 — Search consistency and index freshness | done | critical | P12 |
| P14 — Revisions, locking, and recoverable mutations | done | critical | P12 |
| P15 — Frontmatter correctness | done | high | none |
| P16 — Canonical scope and move semantics | done | high | P12, P15 |
| P17 — Explicit operation and MCP tool contracts | done | high | P11 |
| P18 — Proposal/apply, duplicates, and provenance | ready | high | P14, P17 |
| P19 — Configuration, portability, and packaging | planned | high | P11 |
| P20 — Modularization, CI, and release readiness | planned | medium | P13-P19 |

Parallel work is allowed only when branches do not change the same contracts. P11, P12, P15, and part of P19 are conceptually parallel, but a single agent should complete P11 first.

---

## P11 — MCP and Codex package conformance

Status: done

### Goal

Make the built plugin launch a protocol-conformant MCP server through the documented Codex plugin configuration.

### Required implementation

- [x] Replace stdio output framing with compact newline-delimited UTF-8 JSON.
- [x] Simplify stdio input to one message per line, with deliberate handling of blank and malformed lines.
- [x] Ensure stdout contains MCP messages only.
- [x] Change `.mcp.json` to a documented direct server map or `mcp_servers` wrapper.
- [x] Update `scripts/validate_plugin_package.py` for the documented shape.
- [x] Maintain an explicit supported protocol-version list.
- [x] Negotiate versions according to MCP lifecycle rules.
- [x] Track initialization state.
- [x] Return protocol errors for unknown tools and malformed requests.
- [x] Ensure recoverable request errors do not terminate the server.
- [x] Validate basic JSON-RPC envelope types.
- [x] Keep server capabilities limited to implemented features.
- [x] Add one independent MCP-client integration test.
- [x] Add one built-package test that launches the exact `.mcp.json` command.
- [x] Confirm compatibility with the current Codex host and record the negotiated version.
- [x] Synchronize `serverInfo.version` with the plugin version or record the temporary follow-up.

### Focused tests

See P11 in `docs/testing-and-validation.md`.

Minimum commands:

```text
python -m unittest tests.test_fundus_mcp
task build:plugin
python scripts/validate_plugin_package.py dist/fundus-plugin
```

Add an integration command that uses an independent client.

### Acceptance criteria

- [x] Newline-delimited stdio passes an independent client.
- [x] `initialize -> notifications/initialized -> tools/list -> tools/call` succeeds.
- [x] Unsupported protocol versions are negotiated or rejected correctly.
- [x] Unknown tools return an error and the next ping succeeds.
- [x] Built `.mcp.json` launches from the plugin root.
- [x] The custom validator accepts only a documented shape.
- [x] `task verify` passes.
- [x] Codex local-plugin smoke test succeeds or a reproducible host blocker is recorded.

### Exit evidence

Record:

```text
negotiated protocol version
client used
packaged command
commands and test counts
sample initialize response
sample unknown-tool response
Codex smoke-test result
```

### Completion evidence — 2026-07-10

Commit:

- Base commit `c3f3580`; P11 changes are present in the working tree.

Files changed:

- `.mcp.json`
- `scripts/fundus_mcp.py`
- `scripts/validate_plugin_package.py`
- `tests/test_fundus_mcp.py`
- `tests/test_fundus_mcp_integration.py`
- `tests/test_plugin_package_validator.py`
- `Taskfile.yml`
- `README.md`
- remediation and implementation documents under `docs/`

Commands:

```text
python -m unittest tests.test_fundus_mcp tests.test_fundus_mcp_integration tests.test_plugin_package_validator
task build:plugin
python scripts/validate_plugin_package.py dist/fundus-plugin
FUNDUS_PLUGIN_ROOT=dist/fundus-plugin python -m unittest tests.test_fundus_mcp_integration
task verify
task install
codex plugin list
codex mcp list
codex exec --ephemeral --sandbox read-only -C /Users/christian/projects/fundus-skill "...call the Fundus doctor MCP tool exactly once..."
```

Results:

- Negotiated protocol version: `2025-11-25`; compatibility coverage: `2025-06-18`.
- Independent client: repository-owned test client that shares no Fundus transport or lifecycle code.
- Packaged command: `python ./skills/fundus/scripts/fundus_mcp.py`, `cwd: .`, read directly from `dist/fundus-plugin/.mcp.json`.
- Focused suite: 27 tests passed with one package-only skip when `FUNDUS_PLUGIN_ROOT` was absent; the explicit package run executed both integrations with no skips.
- `task verify`: packaged integration 2/2 passed; full suite 84 tests passed with one expected package-only skip during the later environment-free discovery run.
- Custom package validator accepted the direct server map and rejects the old camel-case wrapper.
- The optional external plugin validator was unavailable because PyYAML was not installed for Task's selected interpreter; the current Codex host accepted and loaded the package.

Sample initialize result:

```json
{"protocolVersion":"2025-11-25","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"fundus","version":"0.1.0"}}
```

Sample unknown-tool response:

```json
{"jsonrpc":"2.0","id":4,"error":{"code":-32602,"message":"Unknown tool: does_not_exist"}}
```

Manual verification:

- Installed `fundus@fundus-local` as `0.1.0+codex.20260710083041`.
- `codex mcp list` reported `fundus` enabled and resolved the installed cache command and working directory.
- A fresh ephemeral Codex 0.144.1 host completed one read-only `fundus/doctor` MCP call and returned scope `project`.
- No live corpus mutation or maintenance command was run.

Residual risks:

- P17 still owns output schemas, structured content, annotations, the operation registry, and normal/admin tool separation.
- P19 still owns interpreter portability and a single build-time version source; P11 synchronizes runtime `serverInfo.version` by reading the nearest packaged manifest.

Next phase:

- P12 — Fundus path safety and corpus invariants is ready.

---

## P12 — Fundus path safety and corpus invariants

Status: done

### Goal

Ensure normal Fundus operations can affect only correctly classified paths inside the Fundus root and that newly generated corpora satisfy their own verifier.

### Required implementation

- [x] Introduce operation-specific path constructors or value objects.
- [x] Validate project names as safe single segments.
- [x] Constrain ordinary note read/write paths to the Fundus root.
- [x] Constrain archive operations to active or archive roots as appropriate.
- [x] Validate restore `original_path` as an active Fundus path.
- [x] Require Markdown suffix for note operations unless explicitly justified.
- [x] Reject directories and reserved paths where notes are expected.
- [x] Add symlink escape protections and tests.
- [x] Make allowed area roots explicit or configurable.
- [x] Ensure global project enumeration excludes area roots.
- [x] Generate `index.md` and `log.md` without frontmatter in `area init`.
- [x] Make `area init` followed by corpus verification pass.
- [x] Return stable path-related error codes.
- [x] Update doctor output for resolved roots and classifications.

### Acceptance criteria

- [x] Traversal and vault-outside-Fundus fixtures fail without writes.
- [x] Another Obsidian note inside the vault but outside Fundus cannot be read or mutated through note tools.
- [x] Archive metadata cannot redirect restore outside active Fundus.
- [x] `area init` produces valid reserved and concept files.
- [x] Project and area enumeration are not conflated.
- [x] Existing valid project and area workflows remain compatible.
- [x] `task verify` passes.

### Completion evidence — 2026-07-10

Commit:

- Base commit `4e54f32`; phase checkpoint committed immediately after this evidence update.

Files changed:

- `scripts/fundus.py`
- `tests/test_fundus.py`
- `docs/agent-implementation-tracker.md`
- `docs/implementation.md`

Commands and results:

```text
python -m unittest tests.test_fundus tests.test_fundus_mcp
# 86 tests passed

task verify
# packaged MCP integration 2/2 passed
# full suite 92 tests passed; one expected package-only skip

git diff --check
# passed
```

Implemented evidence:

- Active, archived, reserved, backup, and migration path value objects constrain operation-specific paths.
- Project names are safe non-reserved segments; areas require an explicit allowlisted root and logical name.
- Vault paths outside Fundus, traversal, non-Markdown paths, directories, reserved note paths, and symlink escapes fail before writes.
- Restore treats `original_path` as untrusted and revalidates it as an active Fundus note.
- `area init` writes frontmatter-free `index.md` and `log.md`; the resulting corpus passes verification.
- Doctor reports resolved roots, scope classification, allowlisted area roots, reserved files, and symlink policy.
- All tests used temporary vaults; no live corpus operation was run.

Residual risks:

- P16 owns canonical logical-scope classification across every move and redirect behavior.
- P17 will consolidate coded errors into the operation registry and MCP structured results.

Next phase:

- P15 — Frontmatter correctness is ready.

---

## P13 — Search consistency and index freshness

Status: done

### Goal

Make the JSON index a safe acceleration cache whose presence never changes search semantics or causes stale results.

### Required implementation

- [x] Extract one common document-to-search-record path.
- [x] Use one scorer for indexed and direct search.
- [x] Store content revision and sufficient fast-fingerprint metadata.
- [x] Detect changed, added, and removed paths for the relevant scope before search.
- [x] Refresh or bypass stale records before returning results.
- [x] Define whether search persists repair or performs it in memory.
- [x] Align MCP read-only annotations with the chosen repair policy.
- [x] Handle corrupt and incompatible indexes safely.
- [x] Exclude redirect records from ordinary results.
- [x] Preserve explicit archive search.
- [x] Version the new index shape.
- [x] Add deterministic search fixtures and equivalence tests.
- [x] Add performance benchmark output to verification or a dedicated task.

### Acceptance criteria

- [x] No-index and current-index fixtures produce equivalent result identities and ordering.
- [x] External edit, add, and delete are visible on the next search.
- [x] Corrupt index does not produce incorrect results.
- [x] Archived and redirect policies hold.
- [x] 2,000-note benchmark is measured and documented.
- [x] Initial p95 target is met or a decision-record adjustment is approved.
- [x] `task verify` passes.

### Completion evidence — 2026-07-10

Files changed:

- `scripts/fundus.py`
- `scripts/fundus_mcp.py`
- `scripts/benchmark_search.py`
- `tests/test_fundus.py`
- `tests/test_fundus_mcp.py`
- `Taskfile.yml`
- `README.md`
- `docs/reference/fundus-cli-reference.md`
- `docs/implementation.md`
- `docs/testing-and-validation.md`
- `docs/agent-implementation-tracker.md`

Commands and results:

```text
python -m unittest tests.test_fundus.IndexSearchTest
# 12 tests passed

python -m unittest tests.test_fundus_mcp tests.test_fundus
# 100 tests passed

task benchmark:search
# 2,000 notes; warm search p95 74.543 ms <= 100 ms

task verify
# packaged MCP integration 2/2 passed
# full suite 106 tests passed; one expected package-only skip

git diff --check
# passed
```

Implemented evidence:

- Index version 3 stores one canonical search-record shape with content revision plus mtime, ctime, and size fingerprints.
- Current-index and uncached paths use the same Unicode-aware tokenization, record builder, scorer, filters, presentation, and deterministic score/title/path ordering.
- Each search enumerates the relevant physical scope, reuses fresh records, rebuilds changed and added records in memory, and omits deleted paths without writing the index.
- Corrupt, incompatible, and missing indexes fall back to current Markdown and remain untouched; index status reports their state and diagnostics.
- Redirects and reserved files are excluded from ordinary evidence, while archived notes remain available only when explicitly requested.
- Scan advertises read-only MCP annotations consistent with the in-memory repair policy.
- Search results include stable ID and SHA-256 revision.
- The deterministic temporary-vault benchmark measured 53.218 ms p50, 74.543 ms p95, 1,895.374 ms full rebuild, 46.130 ms one-file refresh, and a 3,778,517-byte index on arm64 macOS/Python 3.14.6.
- All tests and benchmarks used temporary vaults; no live corpus operation was run.

Residual risks:

- P14 owns lock-protected persisted index updates and optimistic revision conflicts.
- Benchmark results are machine-specific; the dedicated task keeps the threshold reproducible on the primary development host.

Next phase:

- P14 — Revisions, locking, and recoverable mutations is ready.

---

## P14 — Revisions, locking, and recoverable mutations

Status: done

### Goal

Prevent lost updates and index corruption and make multi-step file operations recoverable.

### Required implementation

- [x] Return SHA-256 revision from read and relevant search results.
- [x] Add `expected_revision` to overwrite-like operations.
- [x] Return `REVISION_CONFLICT` without writing on mismatch.
- [x] Add a corpus mutation lock abstraction.
- [x] Lock note-plus-index mutations as one logical operation.
- [x] Add bounded lock timeouts and diagnostics.
- [x] Ensure locks release on exceptions.
- [x] Define stale-lock recovery.
- [x] Update archive, restore, and move for recoverable sequencing.
- [x] Prefer atomic rename over copy/unlink when safe.
- [x] Add rollback or a mutation journal for multi-step failures.
- [x] Add backup verification.
- [x] Add an explicit backup restore workflow or document why it is deferred.
- [x] Add multi-process tests.

### Acceptance criteria

- [x] Human edit between read and update cannot be overwritten silently.
- [x] Concurrent updates to different notes preserve both index entries.
- [x] Concurrent updates to the same note result in one success and one conflict.
- [x] Failure injection leaves either original state or a documented recoverable journal.
- [x] Backup corruption is detected before restore.
- [x] `task verify` passes.

### Completion evidence — 2026-07-10

Files changed:

- `scripts/fundus.py`
- `scripts/fundus_mcp.py`
- `tests/test_fundus.py`
- `tests/test_fundus_mcp.py`
- `SKILL.md`
- `README.md`
- `docs/reference/fundus-cli-reference.md`
- `docs/implementation.md`
- `docs/agent-implementation-tracker.md`

Commands and results:

```text
python -m unittest tests.test_fundus.MutationSafetyTest
# 7 tests passed, including spawned multi-process writers

python -m unittest tests.test_fundus.MutationSafetyTest tests.test_fundus.MigrationTest
# 13 tests passed

python -m unittest tests.test_fundus tests.test_fundus_mcp
# 107 tests passed

task verify
# packaged MCP integration 2/2 passed
# full suite 114 tests passed; one expected package-only skip

git diff --check
# passed
```

Implemented evidence:

- Read and search operation results expose SHA-256 revisions; overwrite-like CLI/MCP operations accept `expected_revision` and return `REVISION_CONFLICT` before any write on mismatch.
- Fsync-backed atomic file replacement and a cross-process `O_EXCL` lock serialize note-plus-index read-modify-write sequences.
- The lock has bounded timeout, owner diagnostics, same-host dead-process stale recovery, same-thread reentrancy, and exception-safe release; doctor reports current lock and journal state.
- Spawned writers updating different notes preserve both fresh index entries; two writers using the same note revision produce exactly one success and one conflict.
- Move, archive, and restore use atomic rename plus snapshot journals. Failure injection at every rename, metadata, redirect, and index checkpoint restores original files and index.
- Prepared journals survive a simulated process crash and recover automatically on the next mutation lock.
- Migration remains stage-and-verify before promotion; an injected post-promotion failure leaves a verified destination that the tested resume path completes safely.
- Backup verify checks manifest totals, sizes, and SHA-256 for every file. Restore is dry-run by default and, on apply, verifies first, creates a safety backup, journals the full change, rebuilds the index, and verifies the corpus.
- Injected backup-restore failure rolls back; corrupted backup content fails with `BACKUP_CORRUPT` before current corpus writes.
- All tests used temporary vaults; no live corpus operation was run.

Residual risks:

- P17 will expose revision conflicts and other stable codes in structured MCP error results and consolidate operation annotations.
- Locking assumes the local single-host vault model; cross-host shared-filesystem locking is intentionally outside the current product boundary.

Next phase:

- P17 — Explicit operation and MCP tool contracts is ready.

---

## P15 — Frontmatter correctness

Status: done

### Goal

Make frontmatter parsing and rendering explicit, safe, and lossless for the supported corpus.

### Decision gate

First perform a short packaging spike:

- official or common YAML library,
- round-trip requirements,
- plugin dependency provisioning,
- artifact size,
- licensing.

Default direction: use a real, pinned YAML implementation. A strict custom subset is allowed only when the spike proves dependency provisioning unsuitable and the subset is validated rigorously.

### Required implementation

- [x] Document the supported frontmatter model.
- [x] Parse booleans, lists, strings, dates, nulls, and unknown fields deliberately.
- [x] Normalize known fields through typed helpers.
- [x] Reject unsupported constructs explicitly.
- [x] Serialize values with correct quoting.
- [x] Preserve unknown supported keys.
- [x] Preserve note body bytes during metadata-only changes.
- [x] Support LF/CRLF and BOM according to a documented policy.
- [x] Fix scalar/list ambiguity such as `tags: ticket`.
- [x] Add corpus fixtures and property-style round-trip tests.
- [x] Update package dependencies and build tasks if required.
- [x] Update migration and normalization tests.

### Acceptance criteria

- [x] Supported fixture values round trip semantically.
- [x] Unsupported YAML does not silently lose data.
- [x] Body preservation tests pass.
- [x] Existing live-corpus shapes are covered by sanitized fixtures.
- [x] Package installation includes required dependencies reliably.
- [x] `task verify` passes.

### Completion evidence — 2026-07-10

Dependency decision:

- Selected `ruamel.yaml==0.19.1`, a common round-trip YAML implementation distributed under the MIT license.
- Vendored the pure-Python wheel payload and upstream license so the exact built skill and plugin require no network or package-install step.
- Added about 1.4 MiB to the runtime artifact; source and built-package execution both load the vendored codec.

Files changed:

- `scripts/fundus.py`
- `tests/test_fundus.py`
- `requirements.txt`
- `vendor/`
- `Taskfile.yml`
- `README.md`
- `.codex-plugin/plugin.json`
- `docs/frontmatter-profile.md`
- `docs/implementation.md`
- `docs/agent-implementation-tracker.md`

Commands and results:

```text
python -m unittest tests.test_fundus
# 70 tests passed

task build
python dist/fundus/scripts/fundus.py --help
python dist/fundus/scripts/fundus_mcp.py --check
# exact built package loaded successfully

task verify
# packaged MCP integration 2/2 passed
# full suite 98 tests passed; one expected package-only skip

git diff --check
# passed
```

Implemented evidence:

- The round-trip YAML codec handles quoted and multiline strings, scalar and block lists, booleans, nulls, numbers, dates, Unicode, comments, and unknown supported fields.
- Known list fields deliberately normalize scalar values such as `tags: ticket` to one-item lists; known temporal fields normalize parsed dates to ISO metadata strings.
- Nested collections, custom tags, duplicate keys, malformed delimiters, non-mapping roots, non-string keys, and invalid UTF-8 fail with `FRONTMATTER_INVALID`.
- Metadata-only normalization preserves decoded body bytes, LF/CRLF convention, BOM, comments, trailing whitespace, and blank lines; output is reparsed before a write is accepted.
- Archive, restore, move, migration, and normalization paths preserve round-trip metadata and exact existing bodies where the body is not intentionally changed.
- All tests used temporary vaults; no live corpus operation was run.

Residual risks:

- P16 owns one canonical scope classifier and first-class redirect semantics across all move directions.
- P14 will add revision checks, locks, and recoverable multi-file mutation boundaries around these writes.

Next phase:

- P16 — Canonical scope and move semantics is ready.

---

## P16 — Canonical scope and move semantics

Status: done

### Goal

Use one logical scope model for all operations and make every move direction correct.

### Required implementation

- [x] Implement a canonical scope classifier.
- [x] Make `scope_path` the logical root.
- [x] Keep physical parent information in path-derived fields.
- [x] Update create, normalize, migration, index, archive, and move to use the classifier.
- [x] Preserve stable note ID during move.
- [x] Correct project-to-project moves.
- [x] Correct project-to-area moves.
- [x] Correct area-to-project moves.
- [x] Correct area-to-area moves.
- [x] Preserve neutral tags and replace old scope tags.
- [x] Introduce first-class redirect metadata.
- [x] Generate a correct relative or validated canonical redirect target.
- [x] Exclude redirects from ordinary search and resolve them on read.
- [x] Detect redirect loops.
- [x] Add a dry-run normalization plan for existing subfolder-valued `scope_path` notes.

### Acceptance criteria

- [x] Full move matrix passes.
- [x] Stable IDs behave according to the target.
- [x] Redirects are safe and quiet.
- [x] Normalization dry-run identifies affected existing notes without writing.
- [x] Corpus verification passes after every move fixture.
- [x] `task verify` passes.

### Completion evidence — 2026-07-10

Files changed:

- `scripts/fundus.py`
- `tests/test_fundus.py`
- `SKILL.md`
- `README.md`
- `docs/reference/fundus-cli-reference.md`
- `docs/implementation.md`
- `docs/agent-implementation-tracker.md`

Commands and results:

```text
python -m unittest tests.test_fundus
# 74 tests passed

python -m unittest discover -s tests
# 102 tests passed; one expected package-only skip

task verify
# packaged MCP integration 2/2 passed
# full suite 102 tests passed; one expected package-only skip

git diff --check
# passed
```

Implemented evidence:

- A single path-derived classifier treats project scope as one root segment and area scope as exactly `AreaRoot/LogicalName`; nested folders remain physical placement.
- Index version 2 records stable ID, kind, canonical scope, physical parent, scope-relative path, and redirect target independently of stale metadata.
- Create, update, add-frontmatter, normalization/migration, index, archive/restore, and move use canonical path classification.
- The project-to-same-project-folder, project-to-project, project-to-area, area-to-same-area-folder, area-to-area, and area-to-project matrix preserves the note ID and neutral tags while replacing old scope fields and tags.
- Redirect stubs receive a distinct redirect ID and canonical validated target plus a relative Markdown link. Direct and indexed search suppress redirects; read follows them and rejects loops, invalid targets, and excessive chains with stable codes.
- Normalization dry-runs identify subfolder-overloaded `scope_path` values without writing and report the canonical logical root plus physical path fields.
- Corpus verification checks canonical active scope metadata and validates redirect chains; it passes after every move fixture.
- All tests used temporary vaults; no live corpus operation was run.

Residual risks:

- P13 owns stale-index detection and identical indexed/direct search semantics.
- P14 owns transactional safety when a move updates two notes and the index.

Next phase:

- P13 — Search consistency and index freshness is ready.

---

## P17 — Explicit operation and MCP tool contracts

Status: done

### Goal

Make operation metadata, validation, output schemas, and MCP behavior derive from one registry.

### Required implementation

- [x] Introduce an operation registry or equivalent single source.
- [x] Store handler, schemas, descriptions, and behavior metadata together.
- [x] Validate tool arguments server-side.
- [x] Add output schemas where practical.
- [x] Return `structuredContent` conforming to output schemas.
- [x] Retain text JSON for backward compatibility where useful.
- [x] Add `title` and tool behavior annotations.
- [x] Audit read-only, destructive, idempotent, and open-world hints.
- [x] Add stable error-code mapping.
- [x] Shorten and improve tool descriptions.
- [x] Define deprecation wrappers for existing tool names.
- [x] Separate normal workbench tools from admin operations.
- [x] Keep CLI and MCP over one application layer.

### Acceptance criteria

- [x] Runtime validation matches advertised schemas.
- [x] Structured outputs validate.
- [x] An annotation-consistency test passes.
- [x] Default tool list is compact and workbench-oriented.
- [x] Admin operations remain available through an explicit path.
- [x] Existing normal workflows retain a documented compatibility route.
- [x] `task verify` passes.

### Completion evidence — 2026-07-10

Files changed:

- `scripts/fundus_mcp.py`
- `tests/test_fundus_mcp.py`
- `tests/test_fundus_mcp_integration.py`
- `README.md`
- `docs/reference/fundus-cli-reference.md`
- `docs/implementation.md`
- `docs/agent-implementation-tracker.md`

Commands and results:

```text
python -m unittest tests.test_fundus_mcp tests.test_fundus_mcp_integration
# 25 tests passed; one expected package-only skip

python -m unittest discover -s tests
# 115 tests passed; one expected package-only skip

task verify
# packaged MCP integration 2/2 passed
# full suite 115 tests passed; one expected package-only skip

git diff --check
# passed
```

Implemented evidence:

- One `OperationSpec` registry stores name, title, concise description, handler, generated input schema, output schema, all four behavior annotations, category, visibility, and deprecation state.
- The default listed workbench is exactly `search`, `read`, `create`, `update`, `move`, `archive`, `restore`, and `doctor`.
- Administrative tools remain in the CLI and become discoverable only through explicit MCP `--admin` mode.
- Previous normal names such as `scan_fundus`, `read_note`, and `create_note` remain callable as unlisted deprecated compatibility aliases; the independent client proves the route against source and exact package commands.
- Successful calls return backward-compatible text JSON plus schema-validated `structuredContent`; a deliberately invalid handler result is rejected as `OUTPUT_SCHEMA_MISMATCH`.
- Input validation and core failures return `isError` with structured stable codes such as `INVALID_ARGUMENT`, `NOTE_NOT_FOUND`, and `REVISION_CONFLICT`.
- Every visible operation publishes non-empty title, bounded description, input/output schema, and audited read-only/destructive/idempotent/open-world annotations. Consistency tests ensure read-only tools are not destructive and all local operations are closed-world.
- CLI and MCP handlers continue to call the same core functions; no transport-specific domain implementation was introduced.
- All tests used temporary vaults; no live corpus operation was run.

Residual risks:

- P18 will replace immediate create/update as the preferred workflow with proposal/apply tools while retaining their compatibility path.
- P20 owns the eventual compatibility-removal policy and release notes.

Next phase:

- P18 — Proposal/apply, duplicate prevention, and provenance is ready.

---

## P18 — Proposal/apply, duplicate prevention, and provenance

Status: ready

### Goal

Turn safe curation behavior from prompt guidance into backend-supported workflows.

### Required implementation

- [ ] Add propose-create.
- [ ] Add apply-create.
- [ ] Add propose-update.
- [ ] Add apply-update with expected revision.
- [ ] Represent section replace, append, rewrite, and metadata changes in proposals.
- [ ] Produce deterministic diffs or structured before/after summaries.
- [ ] Add duplicate checks for title, ID, alias, ticket, resource, and high-confidence similarity.
- [ ] Require explicit override for reviewed duplicate creation.
- [ ] Add provenance fields and source fingerprints.
- [ ] Add verification status.
- [ ] Add mark-stale, verify-note, or equivalent operations.
- [ ] Update SKILL behavior for implicit read-only versus explicit mutation.
- [ ] Add agent-evaluation fixtures.
- [ ] Keep human-facing confirmations compact.

### Acceptance criteria

- [ ] Proposal operations never write.
- [ ] Apply operations reject stale proposals.
- [ ] Duplicate candidates prevent accidental duplicate creation.
- [ ] Explicit broad write intent can complete safely in one turn.
- [ ] Ordinary research produces a stale-note proposal rather than a silent rewrite.
- [ ] Provenance can indicate current, stale, and unverified states.
- [ ] Agent evaluation set meets documented expectations.
- [ ] `task verify` passes.

---

## P19 — Configuration, portability, and packaging

Status: planned

### Goal

Remove machine-specific assumptions and make a built plugin reproducible on another supported machine.

### Required implementation

- [ ] Remove personal vault path from distributable config.
- [ ] Add user-level configuration.
- [ ] Add `FUNDUS_CONFIG_PATH`.
- [ ] Report configuration provenance in doctor.
- [ ] Preserve `OBSIDIAN_VAULT_PATH` compatibility.
- [ ] Resolve the `python` versus `python3` launcher mismatch.
- [ ] Test environments with only one interpreter command.
- [ ] Add an artifact scan for personal paths.
- [ ] Establish one version source.
- [ ] Synchronize manifest, MCP server info, and marketplace metadata.
- [ ] Add the license file declared by the manifest.
- [ ] Review dependency licenses.
- [ ] Add first-install/setup documentation.
- [ ] Clarify personal-first versus public distribution in README.
- [ ] Update privacy and terms links only if publication intent requires owner-specific documents.

### Acceptance criteria

- [ ] Built plugin contains no known personal path.
- [ ] New-machine temporary setup can resolve config and run doctor.
- [ ] Packaged launcher works on supported interpreter layouts.
- [ ] Versions agree.
- [ ] Declared license exists.
- [ ] `task verify` passes.

---

## P20 — Modularization, CI, and release readiness

Status: planned

### Goal

Reduce maintenance risk, enforce the new contracts continuously, and prepare the next release.

### Required implementation

- [ ] Extract modules incrementally behind compatibility entrypoints.
- [ ] Keep CLI and MCP thin.
- [ ] Add CI for supported Python versions.
- [ ] Add package integration job.
- [ ] Add personal-path artifact scan.
- [ ] Add frontmatter and path-security fixtures.
- [ ] Add concurrency tests appropriate for CI.
- [ ] Add performance reporting.
- [ ] Add documentation consistency checks.
- [ ] Update README, SKILL, reference docs, and examples.
- [ ] Archive or condense completed migration instructions from normal onboarding.
- [ ] Write release notes.
- [ ] Select and apply the next version.
- [ ] Reinstall the local plugin and execute the host smoke checklist.
- [ ] Update this tracker to reflect remaining deferred work.

### Acceptance criteria

- [ ] Target module boundaries exist or equivalent boundaries are documented.
- [ ] CI passes on the supported matrix.
- [ ] Clean temporary-vault end-to-end passes.
- [ ] Local Codex plugin smoke test passes.
- [ ] All P11-P19 release-blocking criteria are done.
- [ ] Documentation describes actual behavior.
- [ ] Release artifact is versioned and reproducible.
- [ ] `task verify` passes.

---

## Deferred backlog

These are intentionally not release blockers unless new evidence changes priority:

- vector or embedding search,
- remote sync,
- team sharing and access control,
- graph visualization,
- web UI,
- networked MCP transport,
- autonomous global curation,
- complex task-augmented MCP execution,
- real-time filesystem watchers instead of on-demand freshness checks.

## Pass protocol

### Start

1. Check `git status --short --branch`.
2. Record the current commit.
3. Read the required documents.
4. Reproduce the phase's primary finding before editing.
5. Inspect official documentation for unstable protocol or host behavior.
6. Select focused tests.

### During

1. Add failing tests for confirmed behavior gaps.
2. Implement through shared operations.
3. Keep compatibility wrappers small.
4. Avoid live-corpus writes.
5. Update docs with code when behavior changes.
6. Share partial findings early.

### End

1. Run focused tests.
2. Run package integration where applicable.
3. Run `task verify`.
4. Review the diff for unrelated changes.
5. Record evidence in the phase.
6. Update phase status honestly.
7. Summarize residual risks and the next ready phase.

## Evidence log template

Add beneath the completed phase:

```markdown
### Completion evidence — YYYY-MM-DD

Commit:

Files changed:

Commands:

Results:

Manual verification:

Residual risks:

Next phase:
```
