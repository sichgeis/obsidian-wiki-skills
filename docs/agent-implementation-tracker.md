# Fundus Agent Implementation Tracker

Status: Fundus 0.2.3 live migration and release active
Date: 2026-07-10
Current iteration: P23-P24
First active phase: P24

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

The historical implementation remains useful. P11-P20 hardened and evolved it rather than discarding it. P21-P22 completed the lossless-read patch. P23-P24 deliver the approved lean-area model, migrate the live Fundus vault, and release 0.2.3.

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

### 0.2.1 smoke-test follow-up

The 2026-07-10 Fundus 0.2.1 smoke test passed search, read, proposal/apply, direct Obsidian editing, revision detection, configuration, indexing, locking, and interoperability checks without a functional regression.

One correctness gap remains release-blocking for the next patch:

- A large `read` result was truncated in the Codex tool display. The core operation reads the complete file, but the current MCP response places the complete note in both serialized text JSON and `structuredContent` and provides no bounded continuation contract. A caller therefore cannot prove that all note content reached the model.

Decisions for the next iteration:

- Deliver lossless, revision-bound, cursor-based read pages and require agents to continue until the result explicitly reports completion.
- Keep direct Obsidian edit interoperability unchanged. Manually stale `updated` and `timestamp` frontmatter is accepted because the content revision detects the edit correctly.
- Do not tune ambiguous search ranking from this smoke test; equal top scores remain acceptable.
- Do not add proposal-by-ID storage in this patch. Passing the proposal object is mechanical overhead, not a correctness failure, and server-side proposal persistence would broaden the patch materially.

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
| P18 — Proposal/apply, duplicates, and provenance | done | high | P14, P17 |
| P19 — Configuration, portability, and packaging | done | high | P11 |
| P20 — Modularization, CI, and release readiness | done | medium | P13-P19 |
| P21 — Lossless complete-note reads | done | critical | P17, P20 |
| P22 — Fundus 0.2.2 release validation | done | high | P21 |
| P23 — Lean content-driven areas and safe layout migration | done | critical | P14, P16, P18 |
| P24 — Live vault migration and Fundus 0.2.3 release | in_progress | critical | P23 |

P23 and P24 are deliberately sequential. Complete and verify the migration engine on disposable vaults before creating a current live-vault backup or applying P24.

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

Status: done

### Goal

Turn safe curation behavior from prompt guidance into backend-supported workflows.

### Required implementation

- [x] Add propose-create.
- [x] Add apply-create.
- [x] Add propose-update.
- [x] Add apply-update with expected revision.
- [x] Represent section replace, append, rewrite, and metadata changes in proposals.
- [x] Produce deterministic diffs or structured before/after summaries.
- [x] Add duplicate checks for title, ID, alias, ticket, resource, and high-confidence similarity.
- [x] Require explicit override for reviewed duplicate creation.
- [x] Add provenance fields and source fingerprints.
- [x] Add verification status.
- [x] Add mark-stale, verify-note, or equivalent operations.
- [x] Update SKILL behavior for implicit read-only versus explicit mutation.
- [x] Add agent-evaluation fixtures.
- [x] Keep human-facing confirmations compact.

### Acceptance criteria

- [x] Proposal operations never write.
- [x] Apply operations reject stale proposals.
- [x] Duplicate candidates prevent accidental duplicate creation.
- [x] Explicit broad write intent can complete safely in one turn.
- [x] Ordinary research produces a stale-note proposal rather than a silent rewrite.
- [x] Provenance can indicate current, stale, and unverified states.
- [x] Agent evaluation set meets documented expectations.
- [x] `task verify` passes.

### Completion evidence — 2026-07-10

Files changed:

- `scripts/fundus.py`
- `scripts/fundus_mcp.py`
- `tests/test_fundus.py`
- `tests/test_fundus_mcp.py`
- `tests/test_fundus_mcp_integration.py`
- `tests/test_skill_contract.py`
- `tests/fixtures/agent_evaluations.json`
- `SKILL.md`
- `README.md`
- `docs/reference/fundus-cli-reference.md`
- `docs/implementation.md`
- `docs/agent-implementation-tracker.md`

Commands and results:

```text
python -m unittest tests.test_fundus.ProposalWorkflowTest
# 5 tests passed

python -m unittest tests.test_fundus_mcp tests.test_fundus_mcp_integration
# 26 tests passed; one expected package-only skip

python -m unittest discover -s tests
# 122 tests passed; one expected package-only skip

task verify
# packaged MCP integration 2/2 passed
# full suite 122 tests passed; one expected package-only skip

git diff --check
# passed
```

Implemented evidence:

- Create/update proposals are deterministic, redaction-aware, bounded, and read-only. Repeating the same create intent produces the same proposal ID and diff without creating a lock, index, or note.
- Apply validates proposal integrity under the corpus lock, rechecks duplicate state, and binds updates to the proposal's expected revision; external edits return `REVISION_CONFLICT` unchanged.
- Append, section replace, full rewrite, and allowed retrieval/provenance metadata changes are represented in proposals with unified body diffs and structured metadata summaries.
- Duplicate candidates cover exact title, stable ID, alias, ticket ID, resource, and high-confidence similarity. Apply requires both an explicit override and every currently returned reviewed candidate path.
- New notes default to `verification_status: unverified`; proposals and metadata operations support `verified_against`, `source_fingerprint`, current/stale/unverified state, last verification, and stale reason.
- `mark_stale` records contradicted evidence; `verify_note` requires a source reference or fingerprint and transitions the note to current. Index version 4 exposes verification state and source fingerprint in retrieval.
- The default MCP surface now prefers proposal/apply and keeps immediate create/update as unlisted deprecated compatibility aliases. CLI equivalents and proposal-file apply routes use the same core functions.
- Agent-evaluation fixtures cover explicit save, reviewed duplicate override, broad update intent, stale evidence without write intent, and read-only research. SKILL instructions prohibit silent apply or raw writes.
- Proposal diffs are capped at 12,000 characters for compact human review.
- All tests used temporary vaults; no live corpus operation was run.

Residual risks:

- Similarity duplicate detection is deliberately conservative and local; P20 release monitoring should watch false-positive rates before tuning thresholds.
- P19 owns portable configuration defaults and artifact scans; P20 owns removal timing for immediate compatibility aliases.

Next phase:

- P19 — Configuration, portability, and packaging is ready.

---

## P19 — Configuration, portability, and packaging

Status: done

### Goal

Remove machine-specific assumptions and make a built plugin reproducible on another supported machine.

### Required implementation

- [x] Remove personal vault path from distributable config.
- [x] Add user-level configuration.
- [x] Add `FUNDUS_CONFIG_PATH`.
- [x] Report configuration provenance in doctor.
- [x] Preserve `OBSIDIAN_VAULT_PATH` compatibility.
- [x] Resolve the `python` versus `python3` launcher mismatch.
- [x] Test environments with only one interpreter command.
- [x] Add an artifact scan for personal paths.
- [x] Establish one version source.
- [x] Synchronize manifest, MCP server info, and marketplace metadata.
- [x] Add the license file declared by the manifest.
- [x] Review dependency licenses.
- [x] Add first-install/setup documentation.
- [x] Clarify personal-first versus public distribution in README.
- [x] Update privacy and terms links only if publication intent requires owner-specific documents; no owner-specific publication documents were added because this remains a local, unpublished plugin.

### Acceptance criteria

- [x] Built plugin contains no known personal path.
- [x] New-machine temporary setup can resolve config and run doctor.
- [x] Packaged launcher works on supported interpreter layouts.
- [x] Versions agree.
- [x] Declared license exists.
- [x] `task verify` passes.

### Completion evidence — 2026-07-10

Files changed:

- `config.json`, `.mcp.json`
- `scripts/fundus.py`, `scripts/fundus_mcp.py`, `scripts/fundus_mcp_launcher.sh`
- `scripts/build_plugin_marketplace.py`, `scripts/validate_plugin_package.py`, `scripts/verify_release_consistency.py`
- `Taskfile.yml`, `LICENSE`, `THIRD_PARTY_LICENSES.md`
- configuration, launcher, package-validator, and packaged-integration tests
- `README.md`, `SKILL.md`, and installed reference/implementation documentation

Commands and results:

```text
python3 -m unittest tests.test_fundus.ConfigurationResolutionTest tests.test_plugin_package_validator tests.test_fundus_mcp_integration.PortableLauncherTest -v
# 9 tests passed

python3 -m unittest discover -s tests
# 128 tests passed; one expected package-only skip

task verify
# package validator and personal-path scan passed
# version consistency passed at 0.1.0 for source, build, marketplace metadata, and marketplace copy
# exact packaged launcher integration and both one-interpreter layouts passed
# full suite 128 tests passed; one expected package-only skip

git diff --check
# passed
```

Implemented evidence:

- Configuration precedence is explicit operation arguments, `OBSIDIAN_VAULT_PATH`, `FUNDUS_CONFIG_PATH`, project config, XDG-aware user config, then non-personal package/built-in defaults. A missing vault fails with `CONFIG_MISSING`.
- `doctor` reports provenance per resolved configuration value along with Python and runtime/plugin roots. A fresh temporary machine setup resolves through user config and runs doctor without a corpus write.
- The packaged POSIX launcher prefers `python3`, falls back to `python`, and was exercised with each name as the only command on `PATH`.
- The plugin validator rejects known personal path markers, a missing/non-executable launcher, missing declared/dependency licenses, and invalid package configuration.
- `.codex-plugin/plugin.json` is the version source. Packaged MCP discovers it at runtime and marketplace generation copies it into metadata; a release consistency gate checks all copies.
- Root MIT licensing and the vendored `ruamel.yaml` 0.19.1 MIT license inventory are included in both direct-skill and plugin artifacts.
- First-install documentation distinguishes the personal-first current use from portable, not-yet-public distribution. No public privacy/terms ownership claim was introduced.
- All tests used temporary vaults; no live corpus operation was run.

Next phase:

- P20 — Modularization, CI, and release readiness is ready.

---

## P20 — Modularization, CI, and release readiness

Status: done

### Goal

Reduce maintenance risk, enforce the new contracts continuously, and prepare the next release.

### Required implementation

- [x] Extract modules incrementally behind compatibility entrypoints.
- [x] Keep CLI and MCP thin.
- [x] Add CI for supported Python versions.
- [x] Add package integration job.
- [x] Add personal-path artifact scan.
- [x] Add frontmatter and path-security fixtures.
- [x] Add concurrency tests appropriate for CI.
- [x] Add performance reporting.
- [x] Add documentation consistency checks.
- [x] Update README, SKILL, reference docs, and examples.
- [x] Archive or condense completed migration instructions from normal onboarding.
- [x] Write release notes.
- [x] Select and apply the next version.
- [x] Reinstall the local plugin and execute the host smoke checklist.
- [x] Update this tracker to reflect remaining deferred work.

### Acceptance criteria

- [x] Target module boundaries exist or equivalent boundaries are documented.
- [x] CI passes on the supported matrix.
- [x] Clean temporary-vault end-to-end passes.
- [x] Local Codex plugin smoke test passes.
- [x] All P11-P19 release-blocking criteria are done.
- [x] Documentation describes actual behavior.
- [x] Release artifact is versioned and reproducible.
- [x] `task verify` passes.

### Completion evidence — 2026-07-10

Files changed:

- thin `scripts/fundus.py` and `scripts/fundus_mcp.py` compatibility entrypoints,
- `scripts/fundus_core/runtime.py`, `scripts/fundus_core/mcp_server.py`, and package-boundary documentation,
- `.github/workflows/ci.yml`, `Taskfile.yml`, package validation, documentation checks, release smoke, and benchmark reporting,
- fixture-driven frontmatter/path-security cases and architecture tests; existing cross-process tests are explicit CI coverage,
- `.codex-plugin/plugin.json`, `RELEASE_NOTES.md`, `README.md`, `SKILL.md`, and implementation/testing/reference/example docs.

Commands and results:

```text
python3 -m unittest tests.test_architecture_contract tests.test_fundus.FrontmatterCodecTest tests.test_fundus.PathSafetyTest -v
# 16 focused architecture/fixture tests passed

python3.11 -m unittest discover -s tests
# 130 tests passed; one expected package-only skip

docker run ... python:3.12-slim python -m unittest discover -s tests
docker run ... python:3.13-slim python -m unittest discover -s tests
# 130 tests passed on each Linux interpreter; one expected package-only skip

task verify
# exact plugin package, version 0.2.0, license, personal-path, docs, clean-vault, MCP, and 130-test gates passed

python3 scripts/benchmark_search.py --notes 2000 --iterations 25 --assert-p95-ms 100 --output /private/tmp/fundus-performance-0.2.0.json
# 49.180 ms p50; 50.927 ms p95; 1,733.529 ms rebuild; p95 gate passed

task install
# installed fundus@fundus-local 0.2.0+codex.20260710102735

codex plugin list
codex mcp list
# plugin enabled; launcher resolved from the installed 0.2.0 cache root

codex exec --ephemeral --sandbox read-only -C /Users/christian/projects/fundus-skill "...doctor exactly once..."
# {"succeeded":true,"scope":"project","fundus_root_exists":true,"config_provenance_keys":["default_tags","fundus_dir","redaction","vault_path"]}
```

Built artifacts:

- `dist/fundus`
- `dist/fundus-plugin`
- `dist/fundus-marketplace`
- installed cache `/Users/christian/.codex/plugins/cache/fundus-local/fundus/0.2.0+codex.20260710102735`

Implemented evidence:

- The stable scripts are enforced at 50 lines or fewer and delegate to a packaged core. Runtime/application and MCP contract/transport boundaries now exist; documented internal seams permit later low-risk extraction without changing public imports.
- CI declares Python 3.11, 3.12, and 3.13 on Linux plus Python 3.13 on macOS. Equivalent 3.11/3.12/3.13 suites passed locally (native plus isolated official Python containers); the package job runs `task verify` and uploads benchmark JSON.
- External fixture files now drive supported/unsupported frontmatter and adversarial path cases. Cross-process success/conflict, lock recovery, rollback checkpoints, and backup recovery run in normal CI discovery.
- `task verify` includes documentation/release consistency and a subprocess CLI flow covering doctor, proposal/apply create/update, search/read, move, archive/restore, index rebuild, and corpus verification in one temporary vault.
- Release 0.2.0 is synchronized across source/build/marketplace metadata and runtime MCP info, with release notes and licenses packaged at both skill and plugin roots.
- The first host attempt correctly surfaced `CONFIG_MISSING` after removal of the embedded vault. The documented user config was installed at `~/.config/fundus/config.json`; a second fresh Codex 0.144.1 read-only host completed exactly one `fundus/doctor` call.
- The host smoke and direct doctor were read-only. They observed the live index as incompatible/stale and deliberately did not rebuild it. No live corpus note, index, archive, backup, or journal was mutated.

Residual risks and deferred boundaries:

- `runtime.py` remains consolidated for the compatibility release. Further config/path/frontmatter/search/locking/operation/admin extraction is deferred behind the stable facade and complete contract suite.
- Immediate create/update and previous MCP names remain unlisted compatibility aliases. Removal requires a later explicit deprecation decision.
- The installed live index should be rebuilt in a separately authorized maintenance operation; correctness is preserved because search repairs/falls back in memory.
- The GitHub workflow is committed and its declared interpreter suites passed equivalently locally; the first hosted workflow run will occur when the branch is pushed.

---

## P21 — Lossless complete-note reads

Status: done

### Goal

Make every agent-facing note read provably complete even when a note is larger than a host's single tool-result display budget.

### Confirmed starting point

- `read_note_text()` and `read_document_result()` currently load the complete UTF-8 file.
- The MCP adapter returns that full result twice: serialized in a text content block and again in `structuredContent`.
- The `read` tool has no page boundary, completion marker, continuation cursor, or protection against mixing pages from different revisions.
- The 0.2.1 smoke test observed truncation at the host display boundary, so increasing one output limit is not a sufficient fix.

### Protocol decision

Keep `read` as a tool and add application-level pagination to its input/output contract. MCP's standard pagination contract applies to list operations rather than `tools/call`, but its opaque-cursor rules are the appropriate model: server-controlled page size, stable opaque cursor, explicit continuation, and a clean invalid-cursor error.

Current sources checked on 2026-07-10:

- [MCP 2025-11-25 tool results and structured content](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP cursor pagination guidance](https://modelcontextprotocol.io/specification/draft/server/utilities/pagination)

### Required implementation

- [x] Add one shared, read-only `read_document_page` operation behind the CLI and MCP adapters.
- [x] Use a conservative server-controlled page bound. Select and document the exact bound from serialized-size tests; callers must not be able to request an unbounded page.
- [x] Preserve the existing single-result experience for short notes: first call returns all content with `complete: true`.
- [x] For long notes, return exact content segments with `offset`, `next_offset`, `total_characters`, `complete`, and `next_cursor` when more content remains.
- [x] Keep `path`, `resolved_path`, `redirected`, and the SHA-256 `revision` on every page.
- [x] Make the cursor opaque, versioned, path-bound, resolved-target-bound, revision-bound, and offset-bound.
- [x] Reject malformed, cross-note, wrong-target, and out-of-range cursors with `READ_CURSOR_INVALID`.
- [x] Reject continuation after the note or redirect target changes with `READ_CURSOR_STALE`; the agent must discard collected pages and restart from the first page.
- [x] Slice without losing, duplicating, normalizing, or reordering content. Concatenating pages from one revision must reproduce the exact decoded file text, including frontmatter, Unicode, BOM, and newline style.
- [x] Make the default MCP `read` and its deprecated alias use the bounded contract. Do not retain a hidden unbounded MCP route.
- [x] Preserve the existing full CLI `read` behavior for compatibility, but add an explicit paged CLI mode and cursor argument for the skill's fallback workflow. Both modes must use the shared operation layer.
- [x] Update the MCP input/output schemas and tool description so continuation is unambiguous.
- [x] Retain schema-validated `structuredContent` and compatible text JSON. Account for both copies when choosing and testing the page bound.
- [x] Update `SKILL.md` so an agent must follow `next_cursor` until `complete: true` before summarizing or acting on a note.
- [x] Instruct the agent to restart a read after `READ_CURSOR_STALE`, never combine revisions, and never infer completeness from a visually truncated display.
- [x] Update the README, CLI reference, workbench examples, implementation notes, architecture contract, and release smoke coverage when the behavior exists.

### Focused tests

- [x] Short note returns one exact page with `complete: true` and no continuation cursor.
- [x] A deterministic long Markdown fixture requires at least three pages and reconstructs byte-for-byte after UTF-8 decoding.
- [x] Boundary fixtures cover multibyte Unicode, BOM, LF, CRLF, an empty note, an exact-boundary note, and one line longer than a page.
- [x] Every page reports the same requested path, resolved path, redirect state, total length, and revision.
- [x] A redirect continuation remains bound to the original path and resolved target.
- [x] Invalid, tampered, cross-note, and out-of-range cursors return `READ_CURSOR_INVALID` without leaking note content.
- [x] A direct external edit between pages returns `READ_CURSOR_STALE`; a fresh read reconstructs only the new revision.
- [x] MCP unit tests validate the new signature, output schema, annotations, error codes, and bounded serialized response size.
- [x] The independent source and exact-package MCP clients follow every cursor and recover start, middle, and end sentinels from a temporary-vault note.
- [x] Skill contract/evaluation coverage fails if retrieval instructions permit stopping before `complete: true`.

### Acceptance criteria

- [x] No successful MCP `read` page can silently omit remaining content.
- [x] A caller can distinguish complete, incomplete, invalid, and stale reads mechanically.
- [x] Concatenating a successful page sequence yields the complete note at exactly one SHA-256 revision.
- [x] Normal short-note reads remain one call and preserve existing core fields.
- [x] CLI compatibility remains intact and the documented agent fallback is bounded.
- [x] All automated tests use temporary vaults.
- [x] Focused tests and `task verify` pass.

### Expected implementation surface

```text
scripts/fundus_core/runtime.py
scripts/fundus_core/mcp_server.py
scripts/release_smoke_test.py
tests/test_fundus.py
tests/test_fundus_mcp.py
tests/test_fundus_mcp_integration.py
tests/test_skill_contract.py
SKILL.md
README.md
docs/reference/fundus-cli-reference.md
docs/reference/fundus-workbench-examples.md
docs/implementation.md
docs/architecture-invariants.md
docs/testing-and-validation.md
```

### Exit evidence

Completed 2026-07-10:

- Server bound: 2,000 decoded characters; incomplete pages always include `next_cursor`, complete pages never do.
- Cursor v1 fields: requested path, resolved target, SHA-256 revision, and next character offset in an integrity-checked base64url envelope.
- Errors: `READ_CURSOR_INVALID` for malformed, tampered, unsupported-version, cross-note, and out-of-range input; `READ_CURSOR_STALE` for changed content or redirect resolution.
- Focused command: `python3 -m unittest tests.test_fundus.ReadPaginationTest tests.test_fundus_mcp.McpWrapperTest tests.test_fundus_mcp.McpProtocolTest tests.test_fundus_mcp_integration.SourceMcpIntegrationTest tests.test_skill_contract` — 33 tests passed.
- Measured full JSON-RPC page maxima, including text JSON and `structuredContent`: 6,130 bytes ordinary Markdown and 13,184 bytes multibyte/emoji, below the 32 KiB release budget.
- Source and exact-package independent clients reconstructed three-plus-page temporary notes with stable revisions and all sentinels.
- `task verify` passed from a clean ignored-artifact build with 141 tests passing and one intentional skip.
- Residual risk: host display budgets are not standardized, but the conservative bounded page and explicit completion contract were verified in a fresh Codex host task.

Next phase:

- P22 — Fundus 0.2.2 release validation.

---

## P22 — Fundus 0.2.2 release validation

Status: done

### Goal

Package, install, and smoke-test the complete-read contract as Fundus 0.2.2 after P21 is fully accepted.

### Required implementation

- [x] Confirm every P21 acceptance criterion and record its completion evidence.
- [x] Change the manifest version from 0.2.1 to 0.2.2 only after the complete-read implementation passes focused tests.
- [x] Add 0.2.2 release notes centered on lossless long-note reads, cursor/revision safety, and agent continuation behavior.
- [x] Update current-behavior documentation and remove any wording that implies one unbounded MCP result is always complete.
- [x] Run package build, validators, documentation checks, release smoke, independent source/package MCP integration, the full test suite, and `task verify`.
- [x] Inspect the built skill and plugin to confirm the updated `SKILL.md`, schemas, version, release notes, and runtime are packaged.
- [x] Reinstall the local plugin with the established cache-buster workflow and start a fresh Codex task.
- [x] Run a temporary-vault host smoke with a synthetic note large enough for at least three pages and unique start, middle, and end sentinels.
- [x] Require the host smoke agent to report the final `complete: true`, one stable revision across all pages, and all sentinels. A summary based on only the visible first page fails the smoke test.
- [x] Exercise one stale-cursor case after a direct temporary-vault edit and verify that the agent restarts rather than combining revisions.
- [x] Confirm search ranking, direct-edit frontmatter timestamps, and proposal payload transport are unchanged.
- [x] Record the installed cache path, exact plugin version, commands, test counts, manual evidence, and residual risks in this tracker.

### Acceptance criteria

- [x] Version 0.2.2 is consistent across source manifest, built manifest, MCP `serverInfo`, marketplace metadata, installed plugin, README, and release notes.
- [x] `task verify` passes from a clean build.
- [x] Exact packaged MCP reconstruction proves the complete synthetic note was delivered.
- [x] Fresh Codex host smoke proves the agent automatically follows continuation to completion.
- [x] No automated or host-smoke operation writes to the live Hypatos Fundus corpus.
- [x] P22 completion evidence is recorded and no release-blocking risk remains.

### Completion evidence

- `task verify`: source/build/marketplace version `0.2.2`; package validator, documentation check, release smoke, four independent MCP integration tests, and 141-test discovery passed with one intentional skip. The optional external validator was skipped because its PyYAML dependency is absent; the repository package validator passed.
- Release smoke: temporary vault only, nine pages, one revision, final `complete: true`, all sentinels, and `READ_CURSOR_STALE` after a direct temporary file edit.
- Final install: `task install` produced and enabled `fundus@fundus-local` version `0.2.2+codex.20260710163814` at `/Users/christian/.codex/plugins/cache/fundus-local/fundus/0.2.2+codex.20260710163814`.
- Installed-package inspection confirmed the manifest, updated `SKILL.md`, and paged runtime in the cache root.
- Fresh ephemeral Codex host smoke used only the installed MCP `read` tool from cache-bust `0.2.2+codex.20260710163251`. It received `READ_CURSOR_STALE`, discarded the cursor, restarted, followed 30 pages at revision `sha256:5534ed8be06f98c47e2b63c774e7cc053819c89304570b1485187f76a70293d3`, ended with `complete: true`, and found the start, middle, and end sentinels. The final cache-bust changed only malformed-checksum/revision validation and passed the complete release gate before reinstall.
- Search ranking, proposal transport, and direct-edit timestamp behavior were not changed; the full regression suite remained green.
- All release and host fixtures used temporary vaults under the system temporary directory. The live Hypatos Fundus corpus and its index were not read or written.
- Residual risk: future hosts may choose different display budgets. The server-controlled bound, explicit continuation state, and version-bound restart behavior prevent silent completion assumptions; no release-blocking risk remains.

---

## P23 — Lean content-driven areas and safe layout migration

Status: done

### Goal

Replace eager universal area scaffolding with a content-driven layout and add a deterministic, proposal-first migration that safely rebases Markdown links when existing areas are simplified.

### Product decisions

- New areas contain their root and `overview.md` by default.
- `index.md` and `log.md` are explicit opt-ins; existing curated files remain valid.
- Typed concept notes live at the area root. Frontmatter type and tags carry classification.
- Raw evidence uses `sources/` only when it improves navigation; the default threshold is three source documents.
- The old seven-folder layout is a Fundus convention, not an Open Knowledge Format requirement. OKF permits producer-defined directories and optional index/log files.
- Search ranking, direct-edit timestamps, and proposal-by-ID storage are outside this patch.

### Required implementation

- [x] Make `area init` create only `overview.md` by default and add explicit `--with-index` and `--with-log` options.
- [x] Add deterministic `area layout plan` output with proposal ID, source/destination paths, source revisions, stable IDs, link rewrites, collisions, warnings, and policy metadata.
- [x] Add exact-proposal `area layout apply` with global locking, staleness/collision rejection, a verified current backup, mutation journaling, rollback, index rebuild, and corpus/link verification.
- [x] Rebase relative links inside moved documents and rewrite backlinks across all active Markdown while preserving labels, anchors, titles, and root-relative semantics.
- [x] Preserve stable IDs and body bytes for pure moves; preserve and rewrite curated area `index.md` and `log.md` files.
- [x] Remove only emptied legacy category directories after successful apply.
- [x] Cover deterministic plans, collisions, stale revisions, link variants, redirects, rollback checkpoints, index freshness, and idempotent re-planning with temporary-vault tests.
- [x] Update architecture, decision, target-picture, implementation, testing, CLI, workbench, README, and skill documentation.
- [x] Run focused tests and `task verify`; review the patch before marking P23 done.

### Acceptance criteria

- [x] A new area is lean by default and optional reserved files remain available.
- [x] Planning never mutates the vault and identical state produces an identical proposal ID.
- [x] Apply accepts only the exact fresh proposal, creates a recoverable backup, and leaves no partial state on injected failure.
- [x] Successful migration introduces no new broken local Markdown links and preserves all active documents and stable IDs.
- [x] The full automated suite uses disposable vaults and passes.

### Expected implementation surface

```text
scripts/fundus_core/runtime.py
scripts/fundus_core/mcp_server.py
scripts/fundus.py
tests/
SKILL.md
README.md
docs/
```

### Completion evidence — 2026-07-10

- Focused suite: `python3 -m unittest tests.test_fundus.AreaLayoutMigrationTest tests.test_fundus.ScopeAndAreaTest tests.test_fundus_mcp.McpWrapperTest.test_area_init_wrapper_creates_skeleton` passed 16 tests.
- Full operation/MCP unit suite passed 133 tests.
- `task verify` built and validated the source skill, plugin, and marketplace; release smoke and four independent MCP integration tests passed; full discovery passed 146 tests with one intentional skip.
- Fixture coverage includes relative, rooted, encoded, angle-wrapped, anchored, titled, image, reference-definition, wikilink, and quoted redirect rewrites.
- An injected failure after backlink writes restored all sources, destinations, curated index bytes, and the mutation journal to the pre-apply state. A checksum-verified backup was retained.
- Review found no personal path, generated artifact, or unrelated change in the tracked diff. The live vault was not mutated in P23.
- Next phase: rehearse the exact live proposal and semantic curation manifest in P24.

---

## P24 — Live vault migration and Fundus 0.2.3 release

Status: in_progress

### Goal

Use the verified proposal-first workflow to simplify the authorized live Fundus vault, curate the two complex epic areas, and ship the exact tested implementation as Fundus 0.2.3.

### Required implementation

- [x] Record the final live inventory and deterministic proposal without mutating the vault.
- [x] Create and verify a new current backup immediately before apply.
- [x] Rehearse the exact structural policy and semantic consolidation rules against a disposable vault copy.
- [x] Apply the approved area matrix from `docs/area-layout-migration.md` through Fundus operations, never direct Markdown writes.
- [x] Consolidate the AI Agent Templates and Configuration Promotion epics without losing unique facts, provenance, stable links, or source material.
- [x] Verify active/archive counts, stable IDs, corpus invariants, search, index freshness, all rewritten links, and no newly broken local links.
- [x] Create or update the durable Fundus production note through proposal/apply and record backup, proposal, verification, and rollback evidence.
- [x] Update version and release notes to 0.2.3 only after the live migration succeeds.
- [ ] Run `task verify`, build and inspect the package, install through the cache-buster workflow, and run a fresh-host smoke against a disposable vault.
- [ ] Commit and push every stage, create and push annotated tag `v0.2.3`, and leave the dedicated branch clean and reviewable without merging it into `main`.

### Acceptance criteria

- [x] The live vault matches the approved lean target matrix and retains all intended knowledge.
- [x] A verified pre-apply backup and an actionable rollback point exist.
- [x] Live corpus, index, search, and link checks pass after migration.
- [ ] Source, build, marketplace, installed cache, MCP server info, README, and release notes all report 0.2.3.
- [ ] The installed plugin passes the disposable-vault host smoke and the release branch/tag are pushed.

### Rehearsal evidence — 2026-07-10

- Final curated proposal: `sha256:4579f48579e46ebb2f69a19eeb8b9a93d3d5044926bc5d3e3f41c035bbbcf1ee`.
- Plan: 26 moves, four explicit absorptions, 25 rewritten documents, 103 link rewrites, zero collisions, zero warnings, and zero newly broken links.
- Structural rehearsal created and checksum-verified a 220-file backup, preserved 18 pure moves byte-for-byte, kept all 219 Markdown documents, rebuilt a fresh index, and passed all corpus smoke searches.
- Semantic rehearsal appended the complete, link-rebased bodies of the four absorbed notes through revision-bound Fundus update proposals, reviewed duplicate candidates explicitly, verified each target before archiving its source, and archived all four originals through Fundus.
- Final rehearsal counts were 156 active, 63 archived, 32 reserved, and 124 active concepts. Corpus verification passed with no issues and the 219-document index was current.
- AI Agent Templates ended with four canonical concept files (`overview.md`, `domain.md`, `implementation.md`, `sources.md`) plus its existing curated `index.md` and `log.md`. Configuration Promotion ended with three root concepts, five files under `sources/`, and its existing curated reserved files.
- Active-link searches found no surviving link to an absorbed or superseded structural path. Provenance strings and stable IDs deliberately retain historical path vocabulary.

### Live migration evidence — 2026-07-10

- The final live proposal was byte-identical to the rehearsal proposal immediately before apply.
- Explicit rollback backup `20260710T234428162020+0200-pre-fundus-0-2-3-lean-areas` and apply backup `20260710T234443354327+0200-pre-area-layout-4579f48579e4` both contain 220 files / 3,925,588 bytes and pass checksum verification.
- Live structural apply matched rehearsal: 26 moves, four absorptions, 18 pure byte-identical moves, 25 rewritten documents, 103 link rewrites, zero broken links, and a current index.
- The four semantic merges were applied through revision-bound Fundus update proposals; all duplicate candidates were reviewed, target inclusion was verified, and original notes were archived through Fundus.
- Post-curation corpus verification passed at 219 documents (156 active, 63 archived). The durable production record was then created through proposal/apply, producing the final 220-document corpus (157 active, 63 archived, 32 reserved, 125 active concepts) with a current index and no issues.
- Durable record: `Fundus/Operations/Fundus Production/fundus-0-2-3-lean-area-migration.md` at creation revision `sha256:41b214e82d04c823df3b26d372fccea43d10f1826f0c81c0a86600bb060063e2`.
- A follow-up global layout plan is idempotent: zero moves, absorptions, rewrites, collisions, warnings, or new broken links.

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
- real-time filesystem watchers instead of on-demand freshness checks,
- further extraction of the consolidated runtime behind the stable facade,
- removal of unlisted immediate-write and legacy-name compatibility aliases after an explicit deprecation window.

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
