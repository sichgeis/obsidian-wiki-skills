# Fundus Decision Record

Status: adopted defaults for the remediation program
Date: 2026-07-10

## Document role

This file resolves the questions that would otherwise cause an implementation agent to stop repeatedly for clarification. These are target defaults, not claims about current behavior.

A decision may be revised by the product owner. When revised, record the date, rationale, affected phases, and required migration.

## D1 — Product audience

**Decision:** Fundus remains personal-first but portable.

The primary user is Christian, and the first production corpus remains the local Hypatos vault. The plugin must nevertheless avoid hard-coded personal filesystem paths in distributable artifacts and should be installable by another user through explicit configuration.

**Consequences:**

- Personal workflow optimization is valid.
- Package-local configuration must not contain `/Users/christian/...`.
- Setup and diagnostics must be understandable on a new machine.
- Team synchronization, permissions, and collaborative editing remain out of scope.

## D2 — Direct Obsidian edits

**Decision:** Direct human edits in Obsidian are supported.

Fundus tools remain the required path for agent-authored writes, but the human may edit Markdown directly. Therefore the search index is derived state and must detect or repair external changes before returning results.

**Consequences:**

- An existing index cannot be trusted solely because it parses.
- Indexed and unindexed search must have the same retrieval semantics.
- Revision checks are required before applying agent-authored updates.
- The corpus remains usable without the plugin.

## D3 — Write interaction model

**Decision:** The default safe workflow is propose then apply.

A direct write is allowed when the user gives explicit and sufficiently broad write intent, such as “save this in Fundus” or “update Fundus with what we learned.” When a write could overwrite current content, change scope, or reconcile conflicting evidence, the agent should produce a proposal or diff first.

**Consequences:**

- Read operations return a revision.
- Mutation operations accept an expected revision.
- Proposals are first-class structured data.
- Stale-note correction is not merely a prompt convention.

## D4 — Search technology

**Decision:** Keep the lightweight JSON index for the current scale.

The expected near-term scale is hundreds to low thousands of notes. The index remains a cache and can be rebuilt from Markdown. A database or external search service is not introduced unless measured performance or concurrency requirements justify it.

**Consequences:**

- Search correctness is a stronger requirement than index speed.
- Incremental refresh and locking are required.
- Performance must be measured before changing storage technology.

## D5 — Scope semantics

**Decision:** `scope_path` identifies the logical scope root, not the physical subfolder.

Examples:

```text
Fundus/demo/research/auth.md
  scope: project
  scope_path: demo

Fundus/Epics/AI Agent Templates/references/source.md
  scope: area
  scope_path: Epics/AI Agent Templates
```

The physical folder is represented by the document path. It must not be overloaded into `scope_path`.

**Consequences:**

- One canonical scope classifier is required.
- Move, normalize, migration, indexing, and archive logic must use the same classifier.
- Existing notes whose `scope_path` contains a subfolder may require a dry-run normalization migration.

## D6 — Default tool surface

**Decision:** Normal Codex use exposes a compact workbench; administrative operations are separate.

Normal operations:

```text
search
read
propose create
apply create
propose update
apply update
move
archive
restore
doctor
```

Migration, bulk normalization, backup repair, and other maintenance actions remain available through an explicit admin surface, preferably the CLI or a separately enabled MCP server.

**Consequences:**

- Implicit invocation is read-only.
- Administrative tools do not compete with normal tools during model selection.
- Existing commands remain available for recovery until a compatibility policy says otherwise.

## D7 — Runtime dependencies

**Decision:** Zero dependencies is a preference, not a correctness constraint.

Protocol compliance, safe YAML handling, and data integrity take precedence. A dependency may be introduced when it is pinned, packaged reliably, licensed appropriately, and materially reduces implementation risk.

**Consequences:**

- Prefer a real YAML parser capable of preserving the supported metadata model.
- Prefer an official MCP SDK if it can be packaged reliably and does not complicate the local plugin substantially.
- A custom implementation is acceptable only with protocol conformance tests.

## D8 — MCP protocol support

**Decision:** Target the latest published MCP specification supported by the Codex host, with explicit compatibility for the currently used `2025-06-18` version when practical.

As of this handoff, the latest published MCP specification is `2025-11-25`. The server must advertise a finite supported-version list and negotiate rather than echoing arbitrary input.

**Consequences:**

- Test against a real MCP client.
- Test the exact packaged command.
- Do not assume that a self-owned writer/reader round trip proves interoperability.

## D9 — Frontmatter preservation

**Decision:** Fundus must not silently reinterpret valid frontmatter.

The implementation must either use a proper YAML implementation or enforce a clearly documented strict subset. Unknown keys and supported values must survive a read/write round trip.

**Consequences:**

- Scalar-vs-list ambiguity is an error or an explicit normalization, never an accidental character list.
- Quoting, Unicode, colons, hashes, CRLF, and multiline values require tests.
- Reserved files remain frontmatter-free.

## D10 — Live corpus safety

**Decision:** Automated tests and implementation passes never mutate the live Hypatos corpus.

Use temporary vaults for all tests. Any live migration, normalization, index repair, or bulk update requires an explicit owner instruction and a verified backup.

## D11 — Release identity

**Decision:** The remediation program culminates in a new minor release rather than silently retaining `0.1.0`.

The exact number may be chosen during P20, but protocol, configuration, and write-contract changes must share one version source and have release notes.

## D12 — Licensing

**Decision:** The repository must contain the license file declared by the plugin manifest.

If the manifest says MIT, add a valid MIT `LICENSE` file and confirm that any new dependencies are license-compatible.

## D13 — Content-driven area layouts

**Decision:** Fundus areas start lean and grow folders only from actual content needs.

`overview.md` is the only default area file. `index.md` and `log.md` are optional reserved files. Typed concept notes normally live at the logical area root; several raw evidence documents may be grouped under `sources/`.

The former seven-folder scaffold is a Fundus convention, not an Open Knowledge Format requirement. OKF permits producer-defined directories and optional index/log files. Physical placement remains independent of stable identity and logical `scope_path`.

Existing areas are simplified only through a deterministic proposal-first migration that is revision-bound, collision-aware, link-safe, backed up, journaled, verified, and recoverable. Curated reserved files are preserved rather than deleted mechanically.

**Consequences:**

- Agents need fewer directory reads to understand a small epic or domain.
- Classification remains explicit in frontmatter type and tags.
- Areas with substantial raw evidence can still use `sources/` without forcing that cost on every area.
- Bulk layout changes require review of the exact proposal and a verified current backup.
