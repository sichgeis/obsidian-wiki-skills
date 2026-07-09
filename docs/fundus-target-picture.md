# Fundus Target Picture

Status: stable decision reference after DDD interview
Date: 2026-07-09

Use this document as the durable product and domain picture for implementation. It should change only when the desired behavior, OKF profile, corpus strategy, or plugin architecture changes. Use `docs/agent-implementation-tracker.md` for pass-by-pass execution status.

## Target Picture

Fundus should become Christian's personal Codex workbench for durable work knowledge. It should feel native in Codex, but it should remain explicit: the user invokes it to search, save, retrieve, update, or curate knowledge. During ticket and research work, Codex may also perform a read-only Fundus lookup when prior context is likely useful.

Fundus is evidence, not authority. Source code is the primary source of truth for implemented behavior. Jira, GitHub, source code, interviews, and user-provided context can all update Fundus, but Fundus should never silently override fresher primary evidence.

The first satisfying release should include:

- A canonical `Fundus/` corpus migrated from the existing `Wiki/` corpus.
- Strict enough OKF compatibility for active concept notes.
- Strict OKF reserved-file cleanup for `index.md` and `log.md`.
- Quiet preservation of archived notes under `Fundus/_archive/`.
- A compact, MCP-first Codex skill packaged as a local plugin.
- Snappy core workbench flows for search, save, update, and stale-note proposals.

Team sharing and complex graph visualization are explicitly out of scope for the first release.

## Current Corpus Findings

The live personal work knowledge base currently lives at:

```text
/Users/christian/vault/Hypatos/Wiki
```

The current Fundus config points to:

```text
/Users/christian/vault/Hypatos/Fundus
```

That `Fundus/` directory does not exist yet. The migration from `Wiki/` to `Fundus/` is therefore not optional; it is part of the setup path before the plugin can feel coherent.

Read-only inspection on 2026-07-09 found:

- 217 Markdown files under `Wiki/`.
- 158 active notes and 59 archived notes.
- No files missing frontmatter entirely.
- All active notes have `type`, `title`, `tags`, `scope`, `scope_path`, and timestamps.
- 49 archived legacy notes are missing `type`.
- Active project, domain, epic, decision, and operations areas already use useful folder structure.
- Existing `index.md` and `log.md` files have frontmatter today, but strict OKF treats them as reserved files rather than ordinary concept documents.
- No notes currently use `aliases`, `resource`, or `last_verified`.
- A few notes use "Sources used"; none use OKF's conventional `# Citations` heading.

Conclusion: the corpus is already agent-traversable, but it needs a canonical `Fundus/` location, an index, strict reserved-file cleanup, and a few metadata improvements for future retrieval.

## Product Decisions

### Workbench Role

Fundus is primarily an explicit workbench tool.

Core first-release intents:

- "Search Fundus for X."
- "Save this into Fundus."
- "Update the relevant Fundus note with what we learned."
- "This Fundus note seems stale; propose a correction."

Natural save intent should also work. Phrases such as "remember this", "document this", "save this", or "put this into Fundus" may create or update Fundus notes when the current context is clearly durable work knowledge.

If the save intent is casual, personal, or not clearly work-related, Codex should ask instead of writing to Fundus.

### Evidence Behavior

When Fundus is used in research:

- Treat Fundus as evidence when the note is current and directly relevant.
- Mention Fundus briefly when it materially influenced the answer.
- Prefer a short citation, for example: "Fundus has related context in `Prompt Authoring`; it frames this as an authoring-surface boundary."
- Do not include a large evidence block unless asked.
- If Fundus was checked opportunistically and nothing useful was found, silence is fine.
- If the user explicitly asks to search Fundus, report the result even when no relevant note exists.

### Source Hierarchy

Use this source hierarchy when Fundus and current work disagree:

1. Source code for implemented behavior.
2. Current primary work sources such as Jira, GitHub, Confluence, Slack, interviews, or the user's direct statement.
3. Fundus as contextual evidence and discussion history.

If Fundus appears stale or contradicted by code, Codex should propose a concise natural-language update. It should not patch Fundus by default during ordinary research.

Codex may update Fundus automatically when the user explicitly grants broad update intent, for example: "we learned X, update everything relevant", "update Jira and Fundus", or "document this in Fundus". In that case, Codex should summarize the Fundus changes afterward.

### Scope Inference

Low friction matters. When scope is not explicit, Codex should infer the likely Fundus placement from the whole conversation, then report where it saved.

Signals:

- Conversation intent is the strongest signal.
- Current repository is a strong signal for implementation-local knowledge.
- Ticket IDs, epic names, domain terms, and area names are supporting signals.
- Discovery, interview, strategy, domain, or cross-repository work should usually go to an area.
- Code behavior, repo architecture, tests, and implementation details should usually go to the current project.

The user can correct placement later through a move workflow.

### Retrieval Behavior

Start with tiered retrieval:

- Use the best active Fundus match when confidence is good.
- If confidence is uncertain and the task matters, inspect a bounded number of additional plausible matches automatically.
- Do not interrupt the user to ask whether to search wider.
- Keep the final answer compact.
- Mention additional candidates only briefly when relevant.

Archived notes are preserved but quiet:

- Migrate archives to `Fundus/_archive/`.
- Exclude archives from normal search.
- Include archived notes only when the user explicitly asks for archived, stale, historical, or recovery context.
- Archived notes should not be treated as normal evidence.

### Write Completion

The human-facing confirmation after a write should be short, often just the title or path.

The note itself must be good enough for agents:

- OKF-compatible frontmatter on active concept notes.
- Strong title and useful description.
- Scope and tags that make later lookup easy.
- Ordinary Markdown links for relationships.
- Citations or source sections when the note body relies on important source material.

## OKF And Local Profile

The public OKF v0.1 shape is intentionally small: Markdown files, YAML frontmatter, a required non-empty `type` field for concept documents, optional recommended metadata, ordinary Markdown links, optional `index.md`, and optional `log.md`.

Fundus should be OKF-compatible, but stricter for active concept notes because agents traverse the corpus.

Required for new active non-reserved notes:

```yaml
---
type: Research
title: Example Title
description: Short useful retrieval summary.
id: project/example-repo/example-title
scope: project
scope_path: example-repo
created: 2026-07-09T00:00:00+02:00
updated: 2026-07-09T00:00:00+02:00
timestamp: 2026-07-09T00:00:00+02:00
project: example-repo
tags:
  - fundus
  - project/example-repo
---
```

Area notes omit `project` and use area scope:

```yaml
---
type: Domain
title: Prompt Authoring
description: Stable domain context for prompt authoring concepts and boundaries.
id: area/domains/prompt-authoring/overview
scope: area
scope_path: Domains/Prompt Authoring
created: 2026-07-09T00:00:00+02:00
updated: 2026-07-09T00:00:00+02:00
timestamp: 2026-07-09T00:00:00+02:00
tags:
  - fundus
  - area/domains/prompt-authoring
  - prompt-authoring
---
```

Recommended optional fields:

```yaml
aliases:
  - BACKEND-2291
resource: https://jira.example/browse/BACKEND-2291
status: active
owner: Christian
last_verified: 2026-07-09
projects:
  - prompting-service
repos:
  - prompting-service
```

Rules:

- Preserve unknown frontmatter keys.
- Do not force strict normalization on archived legacy notes unless it is cheap and automatic.
- Active `index.md` and `log.md` are reserved files and should not have frontmatter after cleanup.
- Concept metadata belongs in regular notes such as `overview.md`, not in reserved files.
- Use normal Markdown links for graph relationships.
- Prefer `# Citations` when a note needs source provenance.

## Target Architecture

```text
Fundus corpus
├── project-name/
│   ├── index.md              # reserved, no frontmatter
│   ├── overview.md           # concept note with frontmatter
│   └── research-note.md      # concept note with frontmatter
├── Domains/
│   └── Prompt Authoring/
│       ├── index.md          # reserved, no frontmatter
│       ├── log.md            # reserved, no frontmatter
│       ├── overview.md       # concept note with frontmatter
│       └── domain-model/
└── _archive/
    └── ...
```

Plugin package:

```text
fundus plugin
├── .codex-plugin/plugin.json
├── .mcp.json
├── skills/fundus/SKILL.md
├── skills/fundus/agents/openai.yaml
├── skills/fundus/scripts/fundus.py
├── skills/fundus/scripts/fundus_mcp.py
├── skills/fundus/requirements.txt  # no-dependency marker
└── skills/fundus/docs/reference/*.md
```

Runtime flow:

```text
user asks to save or consult durable knowledge
  -> Codex selects Fundus skill
  -> Fundus skill prefers MCP
  -> MCP scans indexed active Fundus metadata
  -> Codex reads only likely matches
  -> MCP create/update writes through Fundus domain functions
  -> affected index entry refreshes
  -> Codex confirms briefly
```

Fallback flow:

```text
MCP unavailable
  -> skill uses installed helper directly
  -> read-only commands run normally
  -> write-like commands use explicit sandbox escalation when vault is outside workspace
  -> if the helper is unavailable too, Codex reports Fundus writes as blocked instead of editing Markdown directly
```

## Source References

- Google Cloud OKF announcement: https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing
- OKF specification: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
- OKF repository: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf
- Data Commons data model, used only as contrast for heavier graph modeling: https://docs.datacommons.org/data_model.html
