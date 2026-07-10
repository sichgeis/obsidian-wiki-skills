# Fundus CLI Reference

This reference is installed with the skill for progressive disclosure. Load it only when exact command syntax or maintenance details are needed.

## MCP Surface

The installed plugin lists the compact workbench tools `search`, `read`, `create`, `update`, `move`, `archive`, `restore`, and `doctor`. Administrative operations in this document stay available through the CLI; a deliberately launched standalone server may expose them with `fundus_mcp.py --admin`. Previous normal MCP names remain unlisted compatibility aliases.

MCP successes return both text JSON and schema-validated `structuredContent`. Tool failures return `isError: true` plus structured `error` and stable `code` fields.

## Common Search And Read

```bash
python /path/to/fundus/scripts/fundus.py scan --query "authentication flow"
python /path/to/fundus/scripts/fundus.py scan --query "BACKEND-2242 retry budget" --limit 5 --include-snippet
python /path/to/fundus/scripts/fundus.py scan --area "Epics/AI Agent Templates" --query "story map"
python /path/to/fundus/scripts/fundus.py scan --include-archived --query "old decision"
python /path/to/fundus/scripts/fundus.py read --path "Fundus/my-project/authentication-flow.md"
```

## Create And Update

```bash
python /path/to/fundus/scripts/fundus.py create \
  --title "Authentication Flow" \
  --description "How authentication works in this project." \
  --alias BACKEND-2242 \
  --resource "https://jira.example/browse/BACKEND-2242" \
  --content-file /private/tmp/fundus-note.md
```

```bash
python /path/to/fundus/scripts/fundus.py create \
  --area "Epics/AI Agent Templates" \
  --title "Story Map" \
  --type Epic \
  --description "Cross-repository story map for the epic." \
  --content-file /private/tmp/story-map.md
```

```bash
python /path/to/fundus/scripts/fundus.py update \
  --path "Fundus/my-project/authentication-flow.md" \
  --mode append \
  --content-file /private/tmp/fundus-update.md
```

```bash
python /path/to/fundus/scripts/fundus.py update \
  --path "Fundus/my-project/authentication-flow.md" \
  --mode replace \
  --section "Session Handling" \
  --content-file /private/tmp/fundus-section.md
```

```bash
python /path/to/fundus/scripts/fundus.py update \
  --path "Fundus/my-project/authentication-flow.md" \
  --mode rewrite \
  --content-file /private/tmp/fundus-rewrite.md
```

Use `--content` only for short single-line content. Use `--content-file` for generated Markdown, quotes, or multiline bodies.

## Migration

```bash
python /path/to/fundus/scripts/fundus.py migrate wiki-to-fundus --dry-run
python /path/to/fundus/scripts/fundus.py migrate wiki-to-fundus --apply
python /path/to/fundus/scripts/fundus.py migrate wiki-to-fundus --verify
```

Useful options:

```bash
python /path/to/fundus/scripts/fundus.py migrate wiki-to-fundus \
  --source-dir Wiki \
  --destination-dir Fundus \
  --backup-label pre-wiki-to-fundus \
  --retire-source rename \
  --apply
```

`--retire-source rename` is the default for apply. Use `--retire-source keep` only when the user explicitly wants `Wiki/` left in place after migration.

## Frontmatter

```bash
python /path/to/fundus/scripts/fundus.py normalize-frontmatter --path "Fundus/my-project/legacy-note.md"
python /path/to/fundus/scripts/fundus.py normalize-frontmatter --path "Fundus/my-project/legacy-note.md" --apply
python /path/to/fundus/scripts/fundus.py normalize-frontmatter --global --limit 20
python /path/to/fundus/scripts/fundus.py normalize-frontmatter --global --apply
```

Add `--include-archived` only when archived notes should be normalized too. Add `--add-missing` only when plain Markdown notes should receive generated OKF frontmatter.

## Revisions And Conflicts

`read` returns JSON containing `content`, `resolved_path`, and a `sha256:` revision. Scan results include the same revision. Pass it back to update, move, archive, restore, or add-frontmatter:

```bash
python /path/to/fundus/scripts/fundus.py update \
  --path "Fundus/my-project/note.md" \
  --mode append \
  --content "New evidence" \
  --expected-revision "sha256:..."
```

If the note changed after the read, Fundus returns `REVISION_CONFLICT` and writes nothing. Mutations serialize through a bounded cross-process corpus lock; move/archive/restore use recovery journals and atomic renames.

## Move

```bash
python /path/to/fundus/scripts/fundus.py move \
  --from "Fundus/my-project/research/prompt-boundary.md" \
  --to "Fundus/Epics/AI Agent Templates/references/prompt-boundary.md"
```

Project and area scope are classified from the destination path. The stable note ID and neutral tags remain unchanged; the old scope tag is replaced. Add `--leave-stub` to retain a first-class redirect at the source. Redirect metadata stores a validated canonical `Fundus/...` target, its Markdown link is relative to the source, ordinary scan omits it, and read follows it with loop detection.

## Backup

```bash
python /path/to/fundus/scripts/fundus.py backup create --label pre-curation
python /path/to/fundus/scripts/fundus.py backup list
python /path/to/fundus/scripts/fundus.py backup inspect --id 20260709T103010+0200-pre-curation
python /path/to/fundus/scripts/fundus.py backup verify --id BACKUP_ID
python /path/to/fundus/scripts/fundus.py backup restore --id BACKUP_ID
python /path/to/fundus/scripts/fundus.py backup restore --id BACKUP_ID --apply
```

Backups are stored under `{vault_path}/.fundus-backups/` and are excluded from normal Fundus indexing. Restore is a dry-run unless `--apply` is present; apply verifies checksums, creates a current-state safety backup, uses the mutation journal, rebuilds the index, and verifies the restored corpus.

## Area Setup

```bash
python /path/to/fundus/scripts/fundus.py area init \
  --area "Epics/AI Agent Templates" \
  --type Epic \
  --title "AI Agent Templates"
```

Area init creates `index.md`, `log.md`, `overview.md`, and standard subfolders without overwriting existing files.

## Index

```bash
python /path/to/fundus/scripts/fundus.py index status
python /path/to/fundus/scripts/fundus.py index rebuild
python /path/to/fundus/scripts/fundus.py doctor
```

`scan --query` validates cached fingerprints for the relevant scope and repairs stale or missing records in memory. Indexed and uncached records use the same scorer and ordering. Search never writes the cache; run `index rebuild` to persist repairs. Corrupt or incompatible indexes fall back safely and are reported by `index status`.

## Archive

```bash
python /path/to/fundus/scripts/fundus.py archive candidates --older-than-days 90
python /path/to/fundus/scripts/fundus.py archive candidates --older-than-days 90 --global
python /path/to/fundus/scripts/fundus.py archive candidates --older-than-days 90 --force
```

```bash
python /path/to/fundus/scripts/fundus.py archive apply \
  --path "Fundus/my-project/old-ticket.md" \
  --reason "superseded by current runbook"

python /path/to/fundus/scripts/fundus.py archive restore \
  --path "Fundus/_archive/my-project/old-ticket.md"
```

```bash
python /path/to/fundus/scripts/fundus.py archive cleanup
python /path/to/fundus/scripts/fundus.py archive cleanup --global
```

Normal scan excludes archived notes. Use `scan --include-archived` for explicit archived lookup.

## Plugin Development

Build the direct skill package:

```bash
task build
```

Build the plugin package:

```bash
task build:plugin
```

Build a local marketplace folder for testing:

```bash
task plugin:refresh
```

The generated marketplace lives at:

```text
dist/fundus-marketplace/.agents/plugins/marketplace.json
```

Install that explicit local marketplace only when needed:

```bash
codex plugin marketplace add /absolute/path/to/dist/fundus-marketplace
codex plugin add fundus@fundus-local
```

Run full verification:

```bash
task verify
```
