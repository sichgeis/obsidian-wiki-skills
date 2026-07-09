---
name: fundus
description: Search, save, update, migrate, and curate Christian's durable project, epic, domain, ticket, and cross-repository work knowledge in Fundus.
---

# Fundus

Use Fundus when the user explicitly asks to search, save, remember, document, update, migrate, archive, or curate durable work knowledge. Also use it opportunistically during ticket or research work when prior Fundus context is likely useful.

Do not use Fundus when the user opts out, when the content is casual/non-work knowledge, or when current source evidence is enough and Fundus is unlikely to help.

## Core Contract

- Fundus is evidence, not authority. Source code wins for implemented behavior.
- Mention Fundus briefly when it materially influences an answer, for example: "Fundus has related context in `Prompt Authoring`."
- If Fundus was checked opportunistically and nothing useful was found, silence is fine.
- If the user explicitly asks to search Fundus, report the result even when nothing relevant exists.
- If Fundus appears stale or contradicted by code/current Jira/GitHub/interview/user context, propose a concise Fundus update instead of silently changing it.
- Update Fundus automatically only when the user gives broad update intent, such as "update everything relevant", "document this in Fundus", or "update Jira and Fundus".
- Keep user-facing write confirmations short, usually just the note title or path.

## Scope Inference

- Infer placement from the whole conversation instead of asking by default.
- Conversation intent is the strongest signal.
- Current repository points to project scope for code behavior, architecture, tests, and implementation details.
- Ticket IDs, epic names, domain terms, and area names are supporting signals.
- Discovery, interview, strategy, domain, capability, decision, story-map, and cross-repository knowledge usually belongs in an area.
- Use `--area "Epics/..."`, `--area "Domains/..."`, or another explicit area path for non-project knowledge.
- Do not pass `--project` and `--area` together.

## Retrieval

- Prefer the `fundus` MCP server when available; otherwise use `scripts/fundus.py`.
- Fundus does not depend on a separate Obsidian MCP. Do not describe missing Fundus tools as "the Obsidian MCP was not configured."
- Start with `scan`; read only the best active match when confidence is good.
- If confidence is uncertain and the task matters, inspect a bounded number of additional plausible matches automatically.
- Normal retrieval excludes archived notes. Include archives only when the user asks for archived, stale, historical, or recovery context.
- Prefer indexed results. Run `index status` or `doctor` when retrieval looks stale; rebuild the index only when appropriate.

## Writes

- Never edit Fundus notes directly. Write only through Fundus MCP tools or `scripts/fundus.py`.
- Do not use generic Obsidian tools, `apply_patch`, shell redirection, editor writes, or raw Markdown file edits for Fundus note writes.
- If both Fundus MCP tools and `scripts/fundus.py` are unavailable, stop and tell the user Fundus writes are blocked. Do not create, update, or rewrite Markdown directly as a fallback.
- Scan before creating. If a likely match exists, read it and update instead of creating a duplicate.
- Use append or section replace for incremental additions.
- Use rewrite only when old body content would remain misleading.
- New active concept notes should have OKF-compatible frontmatter with strong title, useful description, scope, tags, aliases/resources when relevant, and citations when source material matters.
- Active `index.md` and `log.md` are reserved files; concept metadata belongs in notes such as `overview.md`.

## Migration And Maintenance

- Canonical Fundus is `/Users/christian/vault/Hypatos/Fundus`.
- The legacy `Wiki/` corpus was migrated on 2026-07-09 and retired as `/Users/christian/vault/Hypatos/Wiki.migrated-20260709T182817+0200-wiki-to-fundus-resume`.
- Use `migrate wiki-to-fundus --dry-run`, then `--apply`, then `--verify` only for recovery or deliberate re-run workflows.
- Migration must back up the source, stage the transformed destination, clean reserved `index.md` and `log.md` frontmatter, preserve archives under `Fundus/_archive/`, rebuild the index, verify, and retire old `Wiki/` as a live source unless explicitly kept.
- Create backups before migration, curation, or bulk path changes.
- Archive only explicit selected paths; use archive candidates for review.

## Codex Permission Behavior

- Prefer the plugin-provided `fundus` MCP tools for normal Fundus reads and writes.
- Read-only helper calls such as `scan`, `read`, `doctor`, `index status`, `archive candidates`, and migration `--dry-run` should not request write escalation.
- Write-like calls such as `create`, `update`, `index rebuild`, `archive apply`, `archive restore`, `archive cleanup`, and migration `--apply` need escalated sandbox permissions when the vault is outside the writable workspace.
- If MCP tools are unavailable and you must use the CLI helper, run `scripts/fundus.py` from the loaded skill package or from the repository build. Do not assume the legacy direct-skill path `~/.codex/skills/fundus`; plugin installs live under the versioned Codex plugin cache.
- If you cannot locate the helper path, ask for help or report the blocked write. Never fall back to editing vault Markdown directly.
- If the exact helper prefix is already allowlisted, do not pass a new `prefix_rule`; keep required escalation justifications terse.
- For multiline Markdown, write a temporary file under `/private/tmp` and pass `--content-file`. Avoid shell wrappers, heredocs, redirection, command substitution, and inline multiline shell quoting.

## References

Load `docs/reference/fundus-cli-reference.md` only when you need exact CLI commands, plugin packaging notes, or maintenance details.

Load `docs/reference/fundus-workbench-examples.md` only when you need examples for search, save, update, scope inference, opportunistic research, or stale-note proposal behavior.
