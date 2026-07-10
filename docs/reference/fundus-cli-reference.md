# Fundus CLI Reference

This reference is installed with the skill for progressive disclosure. Load it only when exact command syntax or maintenance details are needed.

## MCP Surface

The installed plugin lists `search`, `read`, `propose_create`, `apply_create`, `propose_update`, `apply_update`, `move`, `archive`, `restore`, `mark_stale`, `verify_note`, and `doctor`. Administrative operations in this document stay available through the CLI; a deliberately launched standalone server may expose them with `fundus_mcp.py --admin`. Immediate create/update and previous normal MCP names remain unlisted compatibility aliases.

MCP successes return both text JSON and schema-validated `structuredContent`. Tool failures return `isError: true` plus structured `error` and stable `code` fields.

## Configuration and doctor

Fundus resolves configuration from highest to lowest precedence: explicit global CLI `--vault-path` / `--fundus-dir`, compatibility `OBSIDIAN_VAULT_PATH`, `FUNDUS_CONFIG_PATH`, project `.codex/fundus.json`, `${XDG_CONFIG_HOME:-~/.config}/fundus/config.json`, then portable defaults. A vault path is required; package defaults never select a personal vault.

```bash
python /path/to/fundus/scripts/fundus.py \
  --vault-path /path/to/vault \
  --fundus-dir Fundus \
  doctor
```

`doctor` is read-only and reports configuration provenance for every value in `config_provenance`, plus the resolved roots, Python executable, plugin/runtime root, path policy, index state, and lock state. `FUNDUS_CONFIG_PATH` must name a JSON file with the same shape as `config.example.json`.

## Common Search And Read

```bash
python /path/to/fundus/scripts/fundus.py scan --query "authentication flow"
python /path/to/fundus/scripts/fundus.py scan --query "BACKEND-2242 retry budget" --limit 5 --include-snippet
python /path/to/fundus/scripts/fundus.py scan --area "Epics/AI Agent Templates" --query "story map"
python /path/to/fundus/scripts/fundus.py scan --include-archived --query "old decision"
python /path/to/fundus/scripts/fundus.py read --path "Fundus/my-project/authentication-flow.md"
```

## Create And Update

Prefer proposal/apply. `propose-create` and `propose-update` write nothing and print a JSON proposal with deterministic diff, revision, and duplicate candidates. Save that JSON through a safe caller-managed file, then apply it:

```bash
python /path/to/fundus/scripts/fundus.py propose-create \
  --title "Authentication Flow" \
  --content-file /private/tmp/fundus-note.md

python /path/to/fundus/scripts/fundus.py apply-create \
  --proposal-file /private/tmp/fundus-create-proposal.json

python /path/to/fundus/scripts/fundus.py propose-update \
  --path "Fundus/my-project/authentication-flow.md" \
  --mode append \
  --content-file /private/tmp/fundus-update.md

python /path/to/fundus/scripts/fundus.py apply-update \
  --proposal-file /private/tmp/fundus-update-proposal.json
```

Duplicate candidates block create/update apply. Override only after reviewing all candidates, using `--duplicate-override` plus one `--reviewed-duplicate PATH` for every returned path.

Record evidence lifecycle explicitly:

```bash
python /path/to/fundus/scripts/fundus.py mark-stale --path "Fundus/my-project/note.md" --reason "Source changed" --expected-revision "sha256:..."
python /path/to/fundus/scripts/fundus.py verify-note --path "Fundus/my-project/note.md" --verified-against "github:org/repo@abc" --source-fingerprint "github:org/repo:path@sha256:def" --expected-revision "sha256:..."
```

The immediate commands below remain compatibility routes.

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

Inspect legacy plain-scalar YAML errors before normalization:

```bash
python /path/to/fundus/scripts/fundus.py repair-frontmatter
python /path/to/fundus/scripts/fundus.py repair-frontmatter --apply
```

The repair is deliberately narrow: it quotes only unambiguous legacy `title` and `archived_reason` text containing `: `. Dry-run is the default. Ambiguous YAML is reported but never rewritten, and note bodies remain unchanged.

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
