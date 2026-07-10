# Fundus 0.2.3 Area Layout Migration

Status: complete
Date: 2026-07-10
Branch: `codex/fundus-0-2-3-lean-areas`
Baseline: `75090fe` (`v0.2.2`)

## Purpose

This document is the execution contract for simplifying Fundus areas without losing knowledge or breaking navigation. It separates the reusable migration mechanism from the authorized live-vault curation and gives an autonomous agent explicit gates, evidence requirements, and rollback rules.

## Accepted scope

- Make area layout content-driven instead of pre-creating seven category folders.
- Default a new area to `overview.md`; make `index.md` and `log.md` optional.
- Flatten typed concepts to the area root.
- Use `sources/` when an area has at least three raw evidence documents or the live manifest explicitly requires it.
- Add a deterministic proposal-first, link-safe migration with exact apply, backup, journaling, rollback, index rebuild, and verification.
- Migrate and curate the authorized live Fundus vault.
- Release and install Fundus 0.2.3 from the exact verified branch.

## Non-goals

- Search ranking changes.
- Automatic updates to manually stale `updated` or `timestamp` frontmatter.
- Server-side proposal storage or proposal-by-ID apply.
- Enforcing one physical directory scheme as an OKF requirement.
- Merging the release branch into `main`.

## Why this is compatible with OKF

Google's Open Knowledge Format leaves directory organization to the producer and treats `index.md` and `log.md` as optional. The seven Fundus category folders originated as a local convention. Fundus scope metadata already treats the area root as the logical scope, independently of physical subfolders, so flattening changes navigation rather than knowledge identity.

Primary references:

- <https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md>
- <https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/>

## Live baseline inventory

The pre-implementation read-only inventory found:

- 9 logical areas.
- 219 Markdown files: 160 active and 59 archived.
- 128 active concept notes and 32 reserved files.
- 30 deterministic structural moves under the lean policy with no destination collision.
- At least 73 affected local links across 23 documents.
- Corpus verification passed with no issues.
- The index was structurally valid but stale for one Fundus Production note.

Do not publish or commit the user's absolute vault path. Resolve it through Fundus configuration at execution time.

## Target layout policy

1. Keep `overview.md` at every area root.
2. Keep existing curated `index.md` and `log.md`; rewrite their links when necessary.
3. Flatten `decisions/`, `open-questions/`, `stories/`, `domain-model/`, and `implementation-map/` notes to the area root.
4. Combine `interviews/` and `references/` under `sources/` when their total is at least three; otherwise flatten them to the root.
5. Preserve explicit document type, stable ID, provenance, and revision checks.
6. Remove only empty legacy category directories after all writes and verification succeed.

## Approved live area matrix

| Area | Target |
| --- | --- |
| Epics / AI Agent Templates | Four canonical root notes: `overview.md`, `domain.md`, `implementation.md`, `sources.md`; archive three absorbed notes after equivalence review |
| Epics / BACKEND-1426 Configuration Promotion | Root `overview.md`, `implementation.md`, and `impact-map.md`; five raw documents under `sources/`; archive the absorbed small open-question note |
| Domains / Document Processing and OCR | Four root concepts plus `sources/` containing three raw documents |
| Domains / Enrichment Context | Three flat root concepts |
| Domains / Prompt Authoring | Three flat root concepts |
| Domains / Similarity Retrieval | Root overview plus `sources/` containing five documents |
| Decisions / DR-2026-002 Similarity Service and OCR | Three flat root concepts |
| Operations / Fundus Production | Already lean; retain layout and update its durable release record through proposal/apply |
| Operations / Wiki Vault Curation | Already lean; retain layout |

### AI Agent Templates consolidation

- `overview.md` absorbs the story map and current open decisions.
- The OOTB lineage becomes `domain.md`.
- Repository touchpoints and API contract become `implementation.md`.
- Source authority and superseded assumptions become `sources.md`.
- Archive the original story-map, product-domain-questions, and API-contract notes only after unique-fact and inbound-link equivalence checks pass.

### Configuration Promotion consolidation

- `overview.md` absorbs the small configuration-promotion-versus-IaC question.
- The configuration CI/CD overview becomes `implementation.md`.
- The impacted-projects estimate becomes `impact-map.md`.
- Transcripts, Slack capture, source guide, and visual evidence move under `sources/`.
- Archive the absorbed open-question note only after equivalence and link checks pass.

## Migration proposal contract

The plan must contain:

- deterministic proposal ID and policy version;
- exact source and destination paths;
- source revisions and stable IDs;
- all internal link rebases and global backlink rewrites;
- collisions, warnings, reserved-file treatment, and expected counts;
- enough data to reject any stale or altered apply.

The live curation manifest may additionally declare explicit canonical moves and absorption mappings. An absorption rewrites links to the canonical target but leaves its source present until semantic equivalence is reviewed, the target is updated through a Fundus proposal, and the source is archived through Fundus.

Apply must:

- acquire the global mutation lock;
- reject stale revisions, changed destinations, collisions, or a non-identical proposal;
- create and verify a current backup before writes;
- journal every touched file and roll back the complete operation on failure;
- preserve labels, anchors, titles, stable IDs, and pure-move body bytes;
- rebuild the search index and verify the corpus and local links before success.

## Execution stages

| Stage | Status | Exit evidence |
| --- | --- | --- |
| Steering contract | completed | Tracker and this specification committed and pushed in `f64d775` |
| Runtime and tests | completed | 16 focused tests and 146-test full verification pass; P23 review complete |
| Disposable-vault rehearsal | completed | Proposal `sha256:4579…cf1ee`; 26 moves, 4 absorptions, 103 links; final corpus/index checks pass |
| Live backup and apply | completed | Two verified backups; live 26-move/4-absorption apply and 103 link rewrites verified |
| Release and install | completed | 0.2.3 package, tag, cache-busted install, verifier, and fresh-host smoke pass |

Exactly one stage may be `in_progress`. Update this table and the implementation tracker at every stage boundary.

## Stop and rollback conditions

Stop before live apply if the proposal differs from the reviewed matrix, a collision exists, an affected file revision changed, backup verification fails, or a semantic consolidation cannot prove unique-fact preservation.

Rollback immediately if apply reports a journal failure, active documents or stable IDs disappear unexpectedly, the corpus fails verification, the index cannot be rebuilt, or the migration introduces a broken local link. Verify the restored corpus against the pre-apply inventory before continuing.

## Current next action

No implementation action remains. Integrate the dedicated branch into `main` only when explicitly requested.
