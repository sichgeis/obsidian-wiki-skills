# Fundus release notes

## 0.2.1 — 2026-07-10

Fundus 0.2.1 is the local-production vault compatibility patch for the 0.2 release line.

- Adds a dry-run-first `repair-frontmatter` maintenance command for narrowly recognized legacy `title` and `archived_reason` plain scalars containing unquoted colons.
- Repairs are atomic and journaled, preserve bodies byte-for-byte, retain BOM/newline style, and refuse structured, tagged, commented, or otherwise ambiguous YAML.
- Corpus verification now reports every malformed frontmatter path instead of stopping at the first parse failure.
- Bulk frontmatter normalization skips reserved `index.md` and `log.md` files while explicit reserved-file operations remain rejected.
- No physical corpus restructure or Wiki migration is required.

## 0.2.0 — 2026-07-10

Fundus 0.2.0 is the second-release hardening milestone. It turns the local skill into a portable, contract-driven plugin while preserving the existing Markdown corpus and compatibility entrypoints.

### Highlights

- Confines all note, archive, backup, migration, and redirect paths through explicit path types with traversal and symlink escape protection.
- Preserves supported YAML comments, formatting, unknown fields, BOM/newline style, and body bytes with vendored `ruamel.yaml`.
- Makes logical project/area scope path-derived and stable across the complete move matrix.
- Treats the search index as a freshness-checked cache with identical indexed and uncached scoring.
- Adds SHA-256 revisions, cross-process locking, rollback journals, atomic moves, and verified backup restore.
- Publishes explicit MCP input/output contracts, stable errors, behavior annotations, and a compact default tool surface.
- Adds proposal/apply create and update, duplicate review, provenance, source fingerprints, and current/stale/unverified evidence state.
- Removes personal paths from artifacts, adds XDG/user/project/custom/environment configuration provenance, and launches through either `python3` or `python`.
- Adds MIT and dependency-license artifacts, a supported Python 3.11–3.13 CI matrix, package integration, fixtures, clean-vault smoke validation, documentation checks, and performance reporting.
- Moves the runtime and MCP implementation behind thin `scripts/fundus.py` and `scripts/fundus_mcp.py` compatibility facades.

### Upgrade notes

- A vault is no longer embedded in packaged `config.json`. Configure `~/.config/fundus/config.json`, project `.codex/fundus.json`, `FUNDUS_CONFIG_PATH`, `OBSIDIAN_VAULT_PATH`, or explicit CLI arguments.
- Normal MCP discovery lists the proposal-oriented workbench. Immediate create/update and previous MCP names remain callable as unlisted compatibility aliases for this release.
- The index format is version 4 and can be rebuilt from Markdown with `fundus.py index rebuild`.
- The local plugin should be reinstalled with `task install`; start a fresh Codex task afterward so version 0.2.0 is loaded.

### Deferred, non-blocking work

Vector search, remote synchronization, team access control, a web UI, networked MCP transport, filesystem watchers, and autonomous global curation remain intentionally out of scope.
