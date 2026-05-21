---
name: obsidian-wiki
description: Persist codebase knowledge and documented findings into an Obsidian per-repository wiki. Use when the user asks to document findings, save research, build a long-lived project wiki, create a new wiki note for a topic, or update an existing repository knowledge page in Obsidian.
---

# Obsidian Wiki

Use this skill when a user wants persistent repository knowledge written into the Obsidian wiki. Do not use it when the user says "without wiki logging" or otherwise opts out.

## Required behavior

- Never write wiki notes directly. Use `scripts/obsidian_wiki.py` for scan, read, create, and update operations.
- Resolve `scripts/obsidian_wiki.py` relative to this skill directory when the current working directory is not the installed skill directory.
- Run the script from the project you want to document, or pass `--project` when you need to override the detected project name.
- Keep wiki pages organized under `{vault_path}/{wiki_dir}/{project-name}/`.
- Detect the project name automatically unless the repository needs an explicit `--project` override.
- Before creating a note, always scan the project wiki folder for possible matches.
- If a likely match exists, read it before deciding whether to update or create.
- Update existing notes automatically when they already cover the topic. Create a new note only when no good match exists.
- Prefer indexed scan results when available. Rebuild the index with `index rebuild` when `index status` or `doctor` reports it as missing or stale.
- Preserve concise, useful Markdown. The body is free-form, so choose headings and structure that fit the topic.
- Created notes get a generated `# Title` heading. If create content already starts with the same H1, the tool removes that duplicate heading automatically.
- Expect secret redaction to run automatically before content is written.

## Configuration

Configuration resolves in this order:

1. `OBSIDIAN_VAULT_PATH` environment variable for `vault_path`
2. `.agents/obsidian-wiki.json` in the active project
3. `.codex/obsidian-wiki.json` in the active project for backward compatibility
4. `.claude/obsidian-wiki.json` in the active project for backward compatibility
5. `config.json` in this skill directory

Defaults installed with this skill:

- `vault_path`: `/Users/christian/vault/Hypatos`
- `wiki_dir`: `Wiki`
- `default_tags`: `wiki`

## Workflow

1. Scan the current project's wiki pages.
2. Match by title, tags, filename, headings, ticket IDs, and indexed excerpts.
3. Read the best existing match when one exists.
4. Decide whether to update or create.
5. Write the final note content.

Use full-document rewrite only when the existing note is stale enough that appending or replacing one section would leave misleading old content behind.

## Codex Permission Behavior

When running under Codex, minimize approval prompts:

- Use the installed script path: `/Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py`.
- Prefer `--content` for create and update operations so Codex can run one approved Python command without creating a temporary content file first.
- Use `--content-file` only when inline shell quoting or command length makes `--content` impractical.
- If Codex asks for command approval, allow the prefix `python /Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py` for future runs.
- Codex approvals are command-prefix based, not skill-name based. There is no separate skill-level whitelist in this repository; durable allowlisting belongs in Codex Rules, for example `~/.codex/rules/default.rules`.
- A suitable Codex Rule is `prefix_rule(pattern = ["python", "/Users/christian/.codex/skills/obsidian-wiki/scripts/obsidian_wiki.py"], decision = "allow", ...)`. Restart Codex after adding or changing rules.
- Treat such a rule as trust in this script invocation, not as fine-grained inspection of every internal Python file write or subprocess.

## Slash command workflow

The optional `document` slash command is a convenience wrapper around this skill. When invoked, treat the command arguments as the wiki topic to document for the current repository.

- Use the argument text as the note topic, for example `all unit tests of the project`.
- Inspect the project enough to document the topic accurately before writing.
- For unit-test documentation, identify test directories, frameworks, major test groups, fixtures, helpers, and relevant test commands. Summarize behavior by area instead of listing every assertion unless the project is small.
- Use the standard scan/read/create/update workflow above. Do not create a duplicate note when an existing page already covers the topic.
- In the final response, include the vault-relative wiki note path that was created or updated.

## Commands

Run the installed script from the project you want to document. Replace `/path/to/obsidian-wiki` with this skill directory when needed:

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki.py scan [--query "authentication flow"]
```

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki.py scan \
  --query "BACKEND-2242 retry budget" \
  --limit 5 \
  --include-snippet
```

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki.py read --path "Wiki/my-project/authentication-flow.md"
```

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki.py create \
  --title "Authentication Flow" \
  --content "## Overview

Document the relevant behavior here." \
  --tag auth
```

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki.py update \
  --path "Wiki/my-project/authentication-flow.md" \
  --mode append \
  --content "## New Findings

Document the update here."
```

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki.py update \
  --path "Wiki/my-project/authentication-flow.md" \
  --mode replace \
  --section "Session Handling" \
  --content "Session handling details go here."
```

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki.py update \
  --path "Wiki/my-project/authentication-flow.md" \
  --mode rewrite \
  --content "## Overview

Replace the full article body here."
```

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki.py index rebuild
```

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki.py index status
```

```bash
python /path/to/obsidian-wiki/scripts/obsidian_wiki.py doctor
```

## Notes

- `scan` returns compact JSON with titles, tags, vault-relative paths, updated timestamps, and indexed match scores/reasons when an index exists.
- `scan` uses `{vault_path}/{wiki_dir}/.obsidian-wiki-index.json` when present and falls back to direct project Markdown scanning when absent.
- `index rebuild` refreshes the lightweight search index from all project wiki Markdown documents.
- `index status` and `doctor` help diagnose missing or stale indexes and resolved configuration.
- The script detects the active project from the current working directory and its git root, unless `--project` is provided.
- `read` returns the full Markdown document.
- `create` fails if the slug already exists.
- `create` and `update` refresh their affected index entry automatically when an index already exists.
- `create` preserves one generated title H1 and removes a duplicate matching leading H1 from supplied content.
- `update --mode replace` replaces the named heading section or creates it if missing.
- `update --mode rewrite` replaces the full article body while preserving frontmatter.
- All resolved paths are constrained to the configured vault root.
- Writes are atomic to avoid partial documents.

After creating or updating this skill, restart the coding agent so it can load the updated skill manifest.
