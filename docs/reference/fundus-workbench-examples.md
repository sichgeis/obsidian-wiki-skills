# Fundus Workbench Examples

Use these examples to calibrate agent behavior. They are not a replacement for current source evidence.

## Search

User: "Search Fundus for BACKEND-2291."

Agent behavior:

- Scan active Fundus notes for `BACKEND-2291`.
- Read the strongest match if the scan result is directly relevant.
- Return a compact answer.
- Mention the note title/path briefly.
- If nothing relevant exists, say that no relevant Fundus note was found.

Example response shape:

```text
Fundus has related context in `Prompt Authoring Boundary`. It frames BACKEND-2291 as an authoring-surface boundary; current code still needs to be checked before treating that as implemented behavior.
```

## Opportunistic Research

User: "Research this ticket and summarize what matters."

Agent behavior:

- Check primary sources such as Jira, GitHub, and source code as needed.
- Optionally scan Fundus when prior context is likely useful.
- If Fundus is relevant, cite it briefly.
- If opportunistic Fundus search finds nothing useful, silence is fine unless the user explicitly asked for Fundus.

## Save

User: "Remember this domain rule: suppliers can have multiple remittance accounts, but only one default per currency."

Agent behavior:

- Infer scope from the conversation.
- If the conversation is domain or cross-repository work, prefer an area such as `Domains/...`.
- Search the inferred scope first.
- Use `propose_update` for a matching note or `propose_create` only when no good match exists.
- Apply the current proposal because the user's explicit save request supplies write intent; review every duplicate candidate before any override.
- Confirm with the title or path.

Example response shape:

```text
Saved in `Supplier Payment Rules`.
```

## Update

User: "We learned that BACKEND-2291 is actually about prompt-template lineage. Update everything relevant."

Agent behavior:

- Treat this as broad update intent.
- Use `propose_update`, then `apply_update` when the proposal remains current.
- Also update Jira or other requested systems when the user asks for them.
- Summarize what changed afterward.

Example response shape:

```text
Updated Fundus note `Prompt Template Lineage` and linked BACKEND-2291 as an alias.
```

## Stale Note Proposal

User: "Research whether this behavior is still true."

Agent behavior:

- Source code and current primary work sources win over Fundus.
- If Fundus disagrees, do not silently mutate Fundus during ordinary research.
- Use `mark_stale` only when write intent covers recording the contradiction; otherwise tell the user the note appears stale and present a concise proposed replacement without applying it.

Example response shape:

```text
Fundus note `LLM OCR Retry Budget` appears stale: the code now applies the retry budget per page, not per document. Proposed Fundus update: replace the old retry paragraph with "Retry budget is page-scoped as of the current implementation."
```

## Scope Inference

Use project scope for:

- repository-specific architecture
- local implementation details
- tests
- module behavior
- deployment details for one repo

Use area scope for:

- epics
- domains
- capabilities
- interviews
- business rules
- story maps
- cross-repository decisions

When uncertain, infer the best scope and report where the note was saved. The user can move it later.
