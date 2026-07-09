# Agent Implementation Tracker

Status: active work tracker
Date: 2026-07-09

This is the primary file for multi-pass implementation. A coding agent should read this first, then use `docs/fundus-target-picture.md` for product decisions and `docs/implementation.md` for current runtime behavior.

## Agent Read Order

1. `README.md`: repository orientation, build/install commands, and document map.
2. `docs/agent-implementation-tracker.md`: current implementation state, phase status, pass protocol, and active backlog.
3. `docs/fundus-target-picture.md`: stable desired behavior, OKF profile, corpus findings, and architecture.
4. `docs/implementation.md`: existing helper, MCP, packaging, permissions, and runtime notes.
5. Source and tests: `scripts/fundus.py`, `scripts/fundus_mcp.py`, `tests/`, `Taskfile.yml`, `SKILL.md`.

## Tracker Rules

- Keep this file current after every meaningful implementation pass.
- Mark phase status honestly: `planned`, `in_progress`, `partial`, `blocked`, or `done`.
- A phase is `done` only when its acceptance criteria pass and the docs describe the resulting behavior.
- Update `docs/implementation.md` when actual helper, MCP, packaging, permission, or runtime behavior changes.
- Update `README.md` when user-facing setup, commands, install flow, or document layout changes.
- Update `docs/fundus-target-picture.md` only when the desired product behavior or durable decisions change.
- Do not delete target-picture knowledge when moving details between docs.
- Run `task verify` after code changes unless the pass is documentation-only.
- For documentation-only passes, at minimum run `git diff --check`.

## Current Implementation Inventory

### Implemented And Keep

- Codex skill package build and install via `Taskfile.yml`.
- Runtime package in `dist/fundus` with `SKILL.md`, `config.json`, `requirements.txt`, `agents/openai.yaml`, `scripts/fundus.py`, and `scripts/fundus_mcp.py`.
- Local default config points to `/Users/christian/vault/Hypatos/Fundus`.
- Project and area scopes exist; `--project` and `--area` are mutually exclusive.
- Area paths are constrained below the configured Fundus root.
- Helper-mediated writes are the rule; Codex should not edit Fundus notes directly.
- CLI helper supports scan, read, create, update, add-frontmatter, normalize-frontmatter, move, backup, area init, index, archive, restore, cleanup, status, and doctor workflows.
- Create writes OKF-compatible frontmatter and removes duplicate matching H1 content.
- Update supports append, section replace, and full rewrite.
- Backup support exists for the configured Fundus directory under `{vault_path}/.fundus-backups/`.
- Index support exists with compact metadata, ticket IDs, headings, excerpts, and index status.
- Normal scan excludes archived notes; explicit `--include-archived` includes them.
- Archive mirrors nested area paths under `Fundus/_archive/...` and restore uses `original_path`.
- MCP server exists and wraps the helper domain functions through typed tools.
- `fundus_mcp.py --check` validates server construction.
- Tests cover many helper and MCP flows.

### Partial Or Needs Care

- The configured target is `Fundus/`, but the live corpus is still under `Wiki/`; migration is not implemented.
- The index already supports compact retrieval, but the target calls for stronger alias/resource signals, compact confidence/reason metadata, and output auditing.
- Optional metadata fields such as `aliases`, `resource`, `status`, `owner`, and `last_verified` are part of the target profile, but creation and retrieval behavior still need a deliberate implementation pass.
- MCP exists, but its tool descriptions, instruction footprint, and write outputs have not been optimized for token conservation.
- Permission docs exist for helper fallback; plugin/MCP approval guidance still needs final treatment when plugin packaging lands.
- `SKILL.md` is functional, but not yet the compact future workbench contract.

### Not Yet Implemented

- One-time `Wiki/` to `Fundus/` migration dry-run/apply/verify workflow.
- Staged migration promotion and old `Wiki/` retirement.
- Strict reserved-file cleanup for migrated active `index.md` and `log.md`.
- Migration verification report and retrieval smoke tests.
- Codex plugin manifest and plugin package layout.
- Local marketplace refresh task.
- Plugin verification task.
- Split reference docs for long command catalogs and maintenance guidance.
- Token and output footprint audit.
- First-release examples/tests for natural save intent, scope inference, tiered retrieval, and stale-note proposals.

## Phase Status Board

| Phase | Status | Current Meaning |
| --- | --- | --- |
| P0 - Migration Design And Safety | planned | Backup exists, but migration command/workflow does not. |
| P1 - Migration Transformation Rules | planned | Normalization exists; migration transforms still need implementation. |
| P2 - Migration Verification | planned | Index/doctor exist; migration-specific verification is missing. |
| P3 - Core Helper And Index Behavior | partial | Active scans, archive exclusion, and index exist; confidence/alias/resource/output audit still missing. |
| P4 - Compact Skill For Progressive Disclosure | planned | Current `SKILL.md` is functional but too long for the target. |
| P5 - MCP Happy Path | partial | MCP exists; tool metadata/output compactness and workflow bias need work. |
| P6 - Plugin Package Skeleton | planned | Direct skill package exists; plugin package does not. |
| P7 - Snappy Install And Dev Loop | partial | Direct skill build/verify exists; plugin and migration tasks missing. |
| P8 - Permission And Vault Friction | partial | Helper fallback permissions documented; plugin/MCP approval guidance pending. |
| P9 - Token Budget And Output Audit | planned | No measured audit yet. |
| P10 - First-Release Workbench Polish | planned | Target UX is specified; examples/tests still missing. |

## Pass Protocol

At the start of a pass:

1. Check `git status --short --branch`.
2. Read this tracker plus the target and implementation docs.
3. Pick the first phase that is not done unless the user explicitly names another phase.
4. Inspect source and tests before editing.
5. Keep edits scoped to the selected phase unless an earlier dependency is missing.

During a pass:

1. Update tests with the implementation.
2. Prefer existing helper/domain functions over new parallel paths.
3. Keep output compact by default.
4. Preserve backward compatibility for direct skill install until plugin install is proven.
5. Keep write paths path-constrained and helper-mediated.

At the end of a pass:

1. Run focused tests and `task verify` when code changed.
2. Update this tracker status and checklist items.
3. Update `docs/implementation.md` for changed behavior.
4. Update `README.md` only for changed user-facing setup or commands.
5. Leave `docs/fundus-target-picture.md` alone unless product decisions changed.

## Implementation Phases

### P0 - Migration Design And Safety

Status: planned

Goal:

- Add a one-time Wiki to Fundus migration workflow outside normal plugin usage.

Spec:

- Source: `/Users/christian/vault/Hypatos/Wiki`.
- Destination: `/Users/christian/vault/Hypatos/Fundus`.
- Create a backup before mutating or removing any source files.
- Stage migration into a temporary destination before promotion.
- Preserve active notes and archived notes.
- Exclude archived notes from normal retrieval after migration.
- Remove or retire old `Wiki/` as a live source after successful verification, keeping backup recovery.
- Prefer a command shape close to `fundus.py migrate wiki-to-fundus --dry-run`, `--apply`, and `--verify`, unless implementation shows a separate script is cleaner.
- Dry-run should report planned counts, target paths, reserved-file cleanup counts, archive counts, and conflicts without writing.
- Apply should require an existing or newly created backup and should write into a staged destination before promotion.
- Promotion should not leave `Wiki/` and `Fundus/` as parallel live sources.

Acceptance criteria:

- Backup exists and can be inspected.
- Migration can run without hand-reviewing every note.
- Dry-run reports active, archive, reserved, conflict, and target counts.
- Apply uses a staged destination before final promotion.
- `Fundus/` becomes canonical after verification.
- Old `Wiki/` no longer remains as a parallel live source.

### P1 - Migration Transformation Rules

Status: planned

Spec:

- Copy all active non-archive notes into equivalent `Fundus/` paths.
- Copy archived notes under `Fundus/_archive/`.
- For active non-reserved notes, ensure the local OKF-compatible profile:
  - `type`
  - `title`
  - `description`
  - `id`
  - `scope`
  - `scope_path`
  - `created`
  - `updated`
  - `timestamp`
  - `tags`
  - `project` for project scope only
- For active reserved files named `index.md` or `log.md`, remove frontmatter and preserve body.
- Preserve unknown fields on concept notes.
- Convert `wiki` default tags to `fundus` where appropriate.
- Preserve existing Markdown links.
- Do not over-normalize archived legacy notes unless cheap.
- If archived legacy notes missing `type` can cheaply receive `type: Note` without risk, choose that during implementation; otherwise preserve them as-is and document the choice.

Acceptance criteria:

- Active concept files parse cleanly and have non-empty `type`.
- Active reserved `index.md` and `log.md` have no frontmatter.
- Archive files are present under `Fundus/_archive/`.
- Archive metadata remains enough to identify archived status.
- Unknown concept-note frontmatter fields survive migration.

### P2 - Migration Verification

Status: planned

Spec:

- Add structural verification:
  - file counts by active/archive/reserved/concept
  - parseable frontmatter for active concept notes
  - no active concept note missing `type`
  - no active reserved file with frontmatter
  - no path escapes
- Add retrieval smoke tests:
  - project lookup, for example `prompting-service`
  - ticket lookup, for example `BACKEND-2291`
  - epic lookup, for example `AI Agent Templates`
  - domain lookup, for example `Prompt Authoring`
  - archive lookup with explicit archive flag
- Build or rebuild the search index after migration.
- Verification output should be compact JSON plus a human-readable summary.

Acceptance criteria:

- Structural verification passes.
- Smoke searches return expected active notes.
- Archive lookup works only when explicitly requested.
- `doctor` reports the canonical `Fundus/` root and a valid index.

### P3 - Core Helper And Index Behavior

Status: partial

Spec:

- Make `Fundus/` the canonical configured directory.
- Ensure `scan` defaults to active notes only.
- Keep `--include-archived` explicit.
- Index headings, title, description, tags, ticket IDs, aliases, resource, path, scope, scope path, and a short body excerpt.
- Add or improve confidence/reason metadata so Codex can decide whether to read one or a few candidates.
- Keep scan outputs compact by default.
- Make snippets opt-in or tightly bounded.

Acceptance criteria:

- Common scans return compact JSON.
- Relevant active notes rank above archive or weak matches.
- Ticket IDs and aliases are strong retrieval signals.
- Scan output supports brief Fundus citation without reading many files.

### P4 - Compact Skill For Progressive Disclosure

Status: planned

Spec:

- Rewrite `SKILL.md` as a compact workbench contract.
- Keep only trigger rules, source hierarchy, scope inference, retrieval behavior, write behavior, stale-note behavior, and fallback behavior in the main skill.
- Move command catalogs and maintenance instructions to references.
- Include the four core intents:
  - search Fundus
  - save into Fundus
  - update relevant Fundus note
  - propose correction for stale Fundus note
- Make the first 20 lines enough for Codex to choose correctly.

Acceptance criteria:

- `SKILL.md` is materially shorter.
- Natural durable save intent triggers Fundus when appropriate.
- The skill says source code wins over Fundus.
- The skill says stale notes are proposed, not silently rewritten, unless broad update intent is explicit.

### P5 - MCP Happy Path

Status: partial

Spec:

- Add concise MCP server instructions.
- Keep the first 512 characters self-contained:
  - scan first
  - prefer update over duplicate create
  - write only through Fundus tools
  - respect project/area scoping
  - source code wins over Fundus
- Review MCP tool names and descriptions for compactness.
- Return compact write results: title, path, scope, changed mode, updated timestamp, and warnings.
- Keep maintenance tools available, but make normal workflows prefer search/read/create/update/doctor.

Acceptance criteria:

- Normal search/save/update flows complete through MCP without shell commands.
- MCP output is compact enough for repeated use.
- Tests cover representative read/write wrappers and server construction.

### P6 - Plugin Package Skeleton

Status: planned

Spec:

- Add `.codex-plugin/plugin.json`.
- Generate plugin runtime layout in `dist/fundus-plugin`.
- Package the Fundus skill under `skills/fundus/`.
- Bundle the local stdio MCP server in the plugin manifest.
- Add local marketplace metadata for testing.
- Keep direct skill install available until plugin install is proven.

Acceptance criteria:

- Codex can see Fundus as a local plugin.
- Installing the plugin exposes the Fundus skill.
- Plugin-provided MCP config launches `fundus_mcp.py` without manual global MCP config.
- Direct skill install still works during transition.

### P7 - Snappy Install And Dev Loop

Status: partial

Spec:

- Add build tasks for:
  - skill package
  - plugin package
  - local marketplace refresh
  - migration dry-run
  - migration apply
  - verification
- Add a tiny MCP smoke check using `fundus_mcp.py --check`.
- Add dependency diagnostics for missing Python MCP SDK.
- Update README with the direct skill path, migration path, and plugin install path.

Acceptance criteria:

- `task verify` checks helper, MCP, tests, and plugin package shape.
- A local plugin refresh is one command.
- README explains what requires restart or approval.

### P8 - Permission And Vault Friction

Status: partial

Spec:

- Document command approval, filesystem sandboxing, MCP tool approval, and plugin install as separate concerns.
- Recommend a personal setup:
  - either add the vault as a writable Codex root, or
  - keep explicit write escalation for write-like operations.
- Provide Codex Rules examples for helper fallback.
- Provide MCP tool approval guidance for read-only and write-like tools.
- Keep permission prompts stable by avoiding shell wrappers and inline multiline content.

Acceptance criteria:

- Routine Fundus writes do not surprise the user with repeated differently shaped approval prompts.
- Read-only search does not need write escalation.
- Write-like fallback commands use the exact installed helper shape.

### P9 - Token Budget And Output Audit

Status: planned

Spec:

- Measure loaded `SKILL.md` size.
- Measure MCP instructions and tool metadata footprint.
- Measure representative scan/read/update outputs.
- Reduce noisy fields in scan output.
- Keep final answers compact:
  - brief Fundus citation when used
  - brief write confirmation after saves
  - brief stale-note suggestion when needed

Acceptance criteria:

- Common save/update flows read no more than one to three candidate notes.
- Common research flows cite Fundus briefly when relevant.
- No-result opportunistic checks can remain silent.

### P10 - First-Release Workbench Polish

Status: planned

Spec:

- Make the four core intents feel excellent:
  - search
  - save
  - update
  - stale-note proposal
- Add examples/tests for natural save intent.
- Add examples/tests for scope inference.
- Add examples/tests for tiered retrieval.
- Add examples/tests for stale-note proposal behavior.

Acceptance criteria:

- "Search Fundus for BACKEND-2291" returns concise relevant context.
- "Remember this domain rule" saves or updates the inferred area note in work contexts.
- "Update the relevant Fundus note with what we learned" updates and summarizes briefly.
- A stale note found during code research produces a concise proposal, not an automatic mutation.

## Backlog Checklist

### Migration

- [ ] Add Wiki to Fundus migration dry-run.
- [ ] Add pre-migration backup.
- [ ] Add staged migration apply.
- [ ] Copy active notes to `Fundus/`.
- [ ] Copy archived notes to `Fundus/_archive/`.
- [ ] Remove frontmatter from active `index.md` and `log.md`.
- [ ] Normalize active concept frontmatter to the Fundus local OKF-compatible profile.
- [ ] Preserve unknown concept-note frontmatter fields.
- [ ] Convert default `wiki` tags to `fundus` tags where appropriate.
- [ ] Build the Fundus index after migration.
- [ ] Verify structure and retrieval smoke tests.
- [ ] Retire old `Wiki/` as a live source after successful migration.

### Retrieval And Evidence

- [ ] Ensure normal scans exclude archives.
- [ ] Keep archive lookup explicit.
- [ ] Add compact match reasons and confidence signals.
- [ ] Index aliases, resources, ticket IDs, headings, links, and short excerpts.
- [ ] Add brief Fundus citation guidance to the skill.
- [ ] Add stale-note proposal guidance to the skill.

### Writes

- [ ] Make create/update output compact.
- [ ] Support natural durable save intent in skill instructions.
- [ ] Encode source hierarchy in skill instructions.
- [ ] Keep direct note editing forbidden.
- [ ] Add optional `aliases`, `resource`, `status`, `owner`, and `last_verified` support where useful.

### Plugin

- [ ] Add plugin manifest.
- [ ] Generate plugin runtime layout in `dist/fundus-plugin`.
- [ ] Bundle skill and MCP server.
- [ ] Add local marketplace metadata.
- [ ] Add plugin verification task.
- [ ] Keep direct skill install until plugin path is proven.

### Documentation

- [ ] Keep README current as migration and plugin packaging land.
- [ ] Keep implementation docs current as helper, MCP, migration, and plugin architecture land.
- [ ] Split long skill reference material into `docs/reference/`.
- [ ] Document permission model clearly.
- [ ] Document first-release out-of-scope items: team sharing and complex graph visualization.

## Open Implementation Choices

These are implementation choices, not product/domain blockers:

1. Whether migration is a `fundus.py migrate wiki-to-fundus` subcommand or a separate one-time script.
   Recommended default: start with a subcommand unless the implementation becomes awkward.
2. The exact old `Wiki/` retirement shape after successful migration.
   Recommended default: choose the simplest safe option after backup and verification; do not spend effort on elaborate archive curation.
3. Whether archived legacy notes missing `type` get a cheap `type: Note` during migration or remain as-is.
   Recommended default: add `type: Note` only if it is automatic and clearly safe.
4. Whether `last_verified` should be automatically set only after source-code inspection, or also after Jira/GitHub/Confluence verification.
   Recommended default: be conservative; set it when the agent knows what source verified the note.
5. Whether plugin packaging should include all maintenance MCP tools enabled by default or rely on guidance to keep normal workflows focused.
   Recommended default: include maintenance tools but bias descriptions and skill instructions toward normal search/read/create/update/doctor flows.

## Suggested Execution Order

1. Implement migration dry-run, backup, apply, and verification.
2. Run migration from `Wiki/` to `Fundus/` and verify.
3. Rebuild the index and make `Fundus/` canonical.
4. Compact `SKILL.md` and move long references out.
5. Make MCP the happy path and compact tool outputs.
6. Add plugin packaging and local marketplace metadata.
7. Update README and implementation docs.
8. Run token/output audit.
9. Polish the four first-release workbench intents.

## Progress Log

- 2026-07-09: Documentation split into target picture, active implementation tracker, and current implementation notes for multi-pass agent work.
