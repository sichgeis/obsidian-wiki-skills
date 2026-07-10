# Fundus Testing and Validation Strategy

Status: target release strategy
Date: 2026-07-10

## Goals

Tests must establish:

1. protocol interoperability,
2. path and corpus safety,
3. search correctness,
4. conflict-safe persistence,
5. reversible maintenance behavior,
6. package portability,
7. agent workflow quality,
8. provably complete note delivery.

A test owned entirely by the same implementation is not sufficient evidence for an interoperability boundary.

## Test layers

### Unit tests

Use unit tests for:

- value-object validation,
- scope classification,
- frontmatter parsing and rendering,
- scoring,
- diff/proposal generation,
- error mapping,
- path confinement,
- revision calculation,
- lossless read segmentation and cursor validation.

### Operation tests

Use temporary vaults to test complete application operations through the shared operation layer.

Examples:

```text
create -> search -> read
long read -> follow every cursor -> exact reconstruction
read -> external edit -> revision conflict
read page -> external edit -> stale cursor -> restart
move project -> area
archive -> search exclusion -> restore
area init -> corpus verify
```

### Transport tests

Test CLI and MCP as thin adapters over the same operations.

### Package integration tests

Build the plugin and launch the exact packaged `.mcp.json` command.

### Host smoke tests

Exercise the installed local plugin in Codex after package integration passes. Host smoke tests may be manual initially but must have a written checklist and captured output.

### Agent evaluations

Use repeatable prompts and fixtures to test selection and workflow behavior.

## Test-environment rule

Automated tests MUST use temporary vaults.

They MUST NOT write to:

```text
/Users/christian/vault/Hypatos/Fundus
```

A test should fail early if its resolved vault equals the known live path unless an explicit destructive-test environment variable is present. No normal CI job sets that variable.

## P11 protocol and package tests

### Stdio framing

Test input:

```text
{"jsonrpc":"2.0","id":1,"method":"ping"}\n
```

Expected output is exactly one JSON object followed by a newline. No `Content-Length` header and no logging on stdout.

Test:

- multiple sequential messages,
- blank lines according to chosen tolerance,
- malformed JSON,
- EOF after a complete message,
- EOF during invalid content,
- Unicode content,
- embedded escaped `\n` inside JSON strings.

### Lifecycle

Test:

- operation before initialize,
- supported latest version,
- compatibility version,
- unsupported version,
- initialize response capabilities,
- initialized notification,
- repeated initialize,
- ping before and after initialization,
- shutdown on stdin close.

### Error handling

Test:

- unknown method,
- unknown tool,
- non-object params,
- non-string tool name,
- non-object arguments,
- missing required input,
- business error returned as tool error,
- server continues after every recoverable error.

### Real client

At least one integration test uses an official or independently implemented MCP client. The test must not reuse Fundus framing and lifecycle code.

### Packaged command

The test reads built `.mcp.json`, resolves the command from the plugin root, launches it, initializes, lists tools, and calls a temporary-vault operation.

### Codex shape validation

Test both the selected `.mcp.json` shape and the plugin manifest pointer against current Codex plugin documentation or an available official validator.

## P12 path and corpus safety tests

Test every operation with:

```text
../Other
../../outside
/absolute/path
Fundus/../Other
Fundus/_archive as active scope
project name with slash
project name with backslash
empty project
.
..
```

Test ordinary note operations against:

- another note inside the vault but outside Fundus,
- a backup path,
- a migration staging path,
- a directory instead of Markdown,
- a non-`.md` file.

Where supported, test:

- symlink inside Fundus pointing outside Fundus,
- symlinked destination parent,
- archive `original_path` through symlink.

### Reserved files

After `area init`:

- `index.md` has no frontmatter,
- `log.md` has no frontmatter,
- `overview.md` has concept frontmatter,
- corpus verification passes,
- index records reserved files according to the selected policy.

### Project enumeration

Verify that global project enumeration excludes:

```text
_archive
Epics
Domains
Decisions
Interviews
References
Logs
Operations
```

Area traversal uses an area-aware path rather than mislabeling those roots as projects.

## P13 search and index tests

Create one fixture corpus and run every query:

1. with no index,
2. after full rebuild,
3. after incremental refresh,
4. after an external edit,
5. after an external add,
6. after an external delete,
7. after index corruption.

Compare result identities and ordering within documented tolerances.

Fixture cases:

- exact title,
- alias,
- resource URL,
- description,
- tag,
- filename,
- heading,
- body phrase,
- ticket ID,
- Unicode,
- archived note,
- redirect,
- ambiguous candidates,
- stop-word-heavy phrase.

### Freshness

A search after a direct Obsidian edit must return current title, tokens, excerpt, and revision.

### Performance

Generate deterministic corpora at:

```text
200 notes
2,000 notes
10,000 notes for observation only
```

Record:

- full rebuild time,
- warm search p50/p95,
- one-file incremental refresh,
- memory use if practical,
- index size.

Initial release gate:

```text
2,000-note warm search p95 <= 100 ms on the primary development machine
```

If hardware or Python startup dominates, document measurement method and adjust the target through a recorded decision rather than silently ignoring it.

### P13 measured baseline — 2026-07-10

Command:

```text
task benchmark:search
```

Environment and method:

- macOS 26.5.2 arm64, Python 3.14.6;
- 2,000 deterministic project notes in a temporary vault;
- one full index rebuild;
- 25 warm searches, each validating relevant file fingerprints and scoring the shared record shape;
- one external file edit followed by an in-memory incremental search repair.

Results:

```text
generation:                    2632.599 ms
full rebuild:                  1733.529 ms
warm search p50:                 49.180 ms
warm search p95:                 50.927 ms
warm search max:                 61.574 ms
one-file in-memory refresh:      47.622 ms
index size:                    4092517 bytes
max RSS (macOS raw bytes):     53968896
```

The measured p95 passes the initial `<= 100 ms` release gate. The benchmark uses only temporary data and asserts the threshold when run through the Taskfile target.

## P14 concurrency and recovery tests

### Revision conflicts

1. Read revision A.
2. Modify the note externally to revision B.
3. Apply update with expected A.
4. Assert no write and a `REVISION_CONFLICT`.

### Concurrent index updates

Run two processes that update different notes from the same starting index. Assert that both final entries exist and index status is fresh.

### Lock behavior

Test:

- acquisition,
- timeout,
- release on success,
- release on exception,
- stale-lock recovery,
- diagnostics without secret leakage.

### Failure injection

Inject failure after each step of:

```text
move
archive
restore
backup restore
migration promotion
```

Assert either rollback or a documented recoverable journal state.

### Backup verification

Corrupt a copied backup file and confirm checksum verification fails before restore.

## P15 frontmatter tests

Build a fixture suite with:

- simple scalars,
- scalar tags where a list is required,
- inline lists,
- block lists,
- quoted colons,
- hashes in values,
- apostrophes and quotes,
- Unicode,
- multiline descriptions,
- booleans,
- null,
- dates,
- unknown keys,
- nested unsupported values,
- BOM,
- LF and CRLF,
- empty frontmatter,
- missing closing delimiter.

For supported values:

```text
parse -> render -> parse
```

must preserve semantic values.

For unsupported values, fail with `FRONTMATTER_INVALID`; do not silently drop or reinterpret them.

Body bytes must remain unchanged during metadata-only normalization except where newline normalization is explicitly documented and tested.

## P16 scope and move tests

Cover:

```text
project -> same project folder
project -> other project
project -> area
area -> same area folder
area -> other area
area -> project
```

Assert:

- stable ID behavior,
- logical `scope_path`,
- project field presence or absence,
- scope tag replacement,
- non-scope tag preservation,
- path and link correctness,
- source cleanup,
- index correctness,
- redirect behavior if requested.

A redirect:

- is classified as redirect,
- is absent from ordinary search,
- resolves on read,
- cannot loop indefinitely.

## P17 MCP contract tests

For each tool:

- input schema matches runtime validation,
- required parameters are required,
- optional types are represented correctly,
- output matches output schema,
- `structuredContent` is present where advertised,
- text fallback is valid JSON where retained,
- annotations match actual behavior.

Maintain a table in tests or source that prevents a read-only annotation on a persistent writer.

## P18 workflow and agent evaluations

### Duplicate prevention

Attempt create by:

- same normalized title,
- same stable ID,
- same ticket alias,
- same canonical resource,
- high-confidence lexical match.

Verify candidate response and explicit override behavior.

### Proposal and apply

Verify:

- proposal does not write,
- proposal includes base revision,
- diff is deterministic,
- apply succeeds against base revision,
- apply conflicts after external change,
- evidence metadata is preserved.

### Staleness

Fixtures cover:

- note current and source unchanged,
- note old but still correct,
- note contradicted by source,
- source unavailable,
- archived historical context.

### Agent prompt set

Evaluate representative prompts:

```text
Search Fundus for BACKEND-2291.
What did we previously decide about prompt authoring?
Save this durable finding in Fundus.
Remember that I prefer tea.                 # must not write work knowledge
The Fundus note contradicts the current code.
Update everything relevant, including Fundus.
Show archived context for the retired design.
```

Record expected tool sequence and acceptable variants.

## P19 portability tests

Build artifacts and scan them for:

```text
/Users/christian
Hypatos/Fundus
other known personal paths
```

Test configuration from:

- environment,
- explicit config path,
- project config,
- user config,
- missing config.

Test on environments where:

```text
python exists
python3 exists
only one exists
```

The packaged launcher must use the tested path.

Verify that `doctor` reports configuration provenance without exposing environment secrets.

Verify the repository contains the declared license.

## P20 CI and release validation

Recommended CI matrix:

```text
Python 3.11
Python 3.12
Python 3.13
Linux
macOS where available
```

Windows may be included once path and lock behavior are intentionally supported.

CI jobs:

1. formatting and static checks,
2. unit and operation tests,
3. package build,
4. packaged MCP integration,
5. artifact personal-path scan,
6. token/output budget,
7. documentation link and consistency checks.

Release checklist:

```text
[ ] version synchronized
[ ] license present
[ ] changelog/release notes written
[ ] task verify passes
[ ] packaged MCP client test passes
[ ] temporary-vault end-to-end passes
[ ] Codex local install smoke test passes
[ ] tracker phase evidence recorded
[ ] implementation docs reflect current behavior
[ ] no live corpus changes were made during testing
```

## P21 complete-read tests

### Shared operation

Use deterministic temporary-vault fixtures for:

```text
empty note
short note
exact page boundary
one character over the boundary
one line longer than a page
three-or-more-page Markdown note
UTF-8 multibyte content
leading BOM
LF and CRLF
redirected note
```

For every multi-page fixture:

1. read without a cursor,
2. follow each opaque cursor until `complete: true`,
3. assert offsets are contiguous and monotonic,
4. assert requested path, resolved path, redirect state, total length, and revision are stable,
5. concatenate page content,
6. compare with the exact decoded source text.

No test may treat the presence of visible content as proof of completion.

### Cursor safety

Test malformed encoding, unsupported cursor versions, modified fields, a cursor reused with another requested path, a changed redirect target, zero/negative/out-of-range offsets, and a cursor presented after an external edit.

Expected stable outcomes:

```text
READ_CURSOR_INVALID
READ_CURSOR_STALE
```

Errors must not echo note content or cursor internals beyond actionable diagnostics.

### MCP contract and output budget

Validate:

- optional cursor input and all required completion fields in the output schema,
- `complete: false` always has a non-empty next cursor,
- `complete: true` has no continuation cursor,
- read remains read-only and idempotent,
- the chosen server page bound accounts for both text JSON and `structuredContent`,
- serialized ordinary-Markdown and multibyte pages remain below the recorded release budget,
- deprecated read aliases cannot bypass the bound.

The independent source and packaged MCP clients must reconstruct a note spanning at least three pages and verify distinct start, middle, and end sentinels.

### Direct-edit race

Read the first page, modify the temporary-vault note directly, then continue with the old cursor. The continuation must fail as stale. A fresh sequence must reconstruct only the new revision.

### Skill and agent behavior

Contract tests and agent fixtures require:

```text
read -> next_cursor -> ... -> complete true -> summarize or act
```

An agent must discard collected pages and restart after `READ_CURSOR_STALE`. A sequence that stops before completion, combines revisions, or relies on a truncated tool display fails.

## P22 Fundus 0.2.2 release validation

Run the normal P20 release checklist plus:

```text
[ ] P21 focused suite passes
[ ] maximum serialized page size is recorded
[ ] source MCP reconstructs the complete long fixture
[ ] exact packaged MCP reconstructs the complete long fixture
[ ] built SKILL.md requires continuation through complete true
[ ] installed version is 0.2.2 in a fresh Codex task
[ ] host smoke reads start, middle, and end sentinels
[ ] host smoke reports one revision and final complete true
[ ] stale-cursor host smoke restarts cleanly
[ ] no live corpus note or index was mutated
```

The host smoke uses a synthetic note and temporary configuration. It must be large enough for at least three server pages; a one-call short-note check is insufficient evidence.

## Required evidence format

A phase cannot be marked done with “tests pass” alone. Record:

```text
commands run
test counts
important output
built artifact path
manual checks
known residual risks
files changed
```
