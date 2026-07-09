#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parent.parent
SKILL_CONFIG_PATH = SKILL_DIR / "config.json"
PROJECT_CONFIG_RELATIVE_PATHS = [
    Path(".codex") / "fundus.json",
]
DEFAULT_CONFIG = {
    "fundus_dir": "Fundus",
    "default_tags": ["fundus"],
    "redaction": {
        "enabled": True,
        "patterns": ["API_KEY", "SECRET", "TOKEN", "PASSWORD"],
    },
}
INDEX_FILENAME = ".fundus-index.json"
INDEX_VERSION = 1
MAX_INDEX_EXCERPT_CHARS = 600
MAX_SCAN_RESULTS = 20
ARCHIVE_DIRNAME = "_archive"
BACKUP_DIRNAME = ".fundus-backups"
BACKUP_MANIFEST_FILENAME = "manifest.json"
MIGRATION_STAGING_DIRNAME = ".fundus-migration-staging"
DEFAULT_LEGACY_SOURCE_DIR = "Wiki"
RESERVED_FILENAMES = {"index.md", "log.md"}
RESERVED_FUNDUS_DIRNAMES = {ARCHIVE_DIRNAME, BACKUP_DIRNAME}
ARCHIVE_DURABLE_TAGS = {"project-overview", "architecture", "runbook", "glossary"}
ARCHIVE_BOOST_TAGS = {"ticket", "review", "investigation", "refinement"}
AREA_SUBDIRECTORIES = [
    "decisions",
    "open-questions",
    "stories",
    "interviews",
    "domain-model",
    "implementation-map",
    "references",
]
AREA_ROOT_DIRNAMES = {"Epics", "Domains", "Decisions", "Interviews", "References", "Logs", "Operations"}


class FundusError(Exception):
    pass


@dataclass
class Config:
    vault_path: Path
    fundus_dir: str
    default_tags: list[str]
    redaction_enabled: bool
    redaction_patterns: list[str]


@dataclass(frozen=True)
class Scope:
    kind: str
    path: str
    display_name: str


@dataclass
class Document:
    path: Path
    relative_path: str
    title: str
    project: str
    tags: list[str]
    created: str | None
    updated: str | None
    body: str
    frontmatter: dict[str, Any]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise FundusError(f"Invalid JSON config at {path}: {exc}") from exc


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def discover_project_root(start: Path | None = None) -> Path:
    candidate = (start or Path.cwd()).expanduser().resolve()

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=candidate,
            check=True,
            capture_output=True,
            text=True,
        )
        git_root = result.stdout.strip()
        if git_root:
            return Path(git_root).expanduser().resolve()
    except Exception:
        pass

    for path in [candidate, *candidate.parents]:
        has_project_config = any((path / config_path).exists() for config_path in PROJECT_CONFIG_RELATIVE_PATHS)
        if has_project_config or (path / ".git").exists():
            return path

    return candidate


def project_config_paths(project_root: Path) -> list[Path]:
    return [project_root / config_path for config_path in PROJECT_CONFIG_RELATIVE_PATHS]


def resolve_config(project_root: Path) -> Config:
    merged: dict[str, Any] = deep_merge(DEFAULT_CONFIG, load_json(SKILL_CONFIG_PATH))
    for config_path in reversed(project_config_paths(project_root)):
        merged = deep_merge(merged, load_json(config_path))

    env_vault = os.getenv("OBSIDIAN_VAULT_PATH")
    if env_vault:
        merged["vault_path"] = env_vault

    vault_path = merged.get("vault_path")
    if not vault_path:
        raise FundusError(
            "Missing vault_path. Set OBSIDIAN_VAULT_PATH, add it to "
            ".codex/fundus.json, or add it to the skill config."
        )

    fundus_dir = merged.get("fundus_dir") or DEFAULT_CONFIG["fundus_dir"]
    default_tags = merged.get("default_tags") or list(DEFAULT_CONFIG["default_tags"])
    redaction = merged.get("redaction") or {}

    return Config(
        vault_path=Path(vault_path).expanduser().resolve(),
        fundus_dir=str(fundus_dir).strip("/") or DEFAULT_CONFIG["fundus_dir"],
        default_tags=list(default_tags),
        redaction_enabled=bool(redaction.get("enabled", True)),
        redaction_patterns=list(redaction.get("patterns") or DEFAULT_CONFIG["redaction"]["patterns"]),
    )


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise FundusError("Title must contain at least one alphanumeric character.")
    return slug


def slugify_path(value: str) -> str:
    return "/".join(slugify(part) for part in value.split("/") if part.strip())


def detect_project_name(project_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
        remote = result.stdout.strip()
        if remote:
            remote = remote.rstrip("/")
            name = remote.rsplit("/", 1)[-1]
            if ":" in name:
                name = name.rsplit(":", 1)[-1]
            if name.endswith(".git"):
                name = name[:-4]
            name = name.strip()
            if name:
                return name
    except Exception:
        pass
    return project_root.name


def ensure_within(root: Path, target: Path) -> Path:
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise FundusError(f"Resolved path escapes the vault root: {target}") from exc
    return target_resolved


def fundus_project_dir(config: Config, project_name: str) -> Path:
    project_dir = config.vault_path / config.fundus_dir / project_name
    return ensure_within(config.vault_path, project_dir)


def normalize_area_path(area: str) -> str:
    original = area.strip()
    if Path(original).is_absolute():
        raise FundusError("--area must be relative to the Fundus root.")
    raw = original.strip("/")
    if not raw:
        raise FundusError("--area must not be empty.")
    path = Path(raw)
    parts = [part for part in raw.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise FundusError("--area must not contain '.' or '..' path segments.")
    if parts[0] in RESERVED_FUNDUS_DIRNAMES:
        raise FundusError(f"--area must not target reserved Fundus directory: {parts[0]}")
    return "/".join(parts)


def project_scope(project_name: str) -> Scope:
    return Scope(kind="project", path=project_name, display_name=project_name)


def area_scope(area: str) -> Scope:
    normalized = normalize_area_path(area)
    return Scope(kind="area", path=normalized, display_name=normalized)


def resolve_scope(project_name: str, area: str | None = None) -> Scope:
    if area:
        return area_scope(area)
    return project_scope(project_name)


def fundus_scope_dir(config: Config, scope: Scope) -> Path:
    return ensure_within(config.vault_path, fundus_root_dir(config) / scope.path)


def fundus_archive_dir(config: Config) -> Path:
    return ensure_within(config.vault_path, fundus_root_dir(config) / ARCHIVE_DIRNAME)


def fundus_archive_project_dir(config: Config, project_name: str) -> Path:
    return ensure_within(config.vault_path, fundus_archive_dir(config) / project_name)


def fundus_archive_scope_dir(config: Config, scope: Scope) -> Path:
    return ensure_within(config.vault_path, fundus_archive_dir(config) / scope.path)


def fundus_root_dir(config: Config) -> Path:
    return ensure_within(config.vault_path, config.vault_path / config.fundus_dir)


def fundus_relative_path(config: Config, path: Path) -> str:
    return str(ensure_within(config.vault_path, path).relative_to(fundus_root_dir(config)))


def fundus_project_names(config: Config) -> list[str]:
    root = fundus_root_dir(config)
    if not root.exists():
        return []
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and path.name != ARCHIVE_DIRNAME
    )


def index_path(config: Config) -> Path:
    return ensure_within(config.vault_path, fundus_root_dir(config) / INDEX_FILENAME)


def backup_root_dir(config: Config) -> Path:
    return ensure_within(config.vault_path, config.vault_path / BACKUP_DIRNAME)


def migration_staging_root_dir(config: Config) -> Path:
    return ensure_within(config.vault_path, config.vault_path / MIGRATION_STAGING_DIRNAME)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text

    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text

    raw_frontmatter = parts[0][4:]
    body = parts[1]
    data: dict[str, Any] = {}
    current_list_key: str | None = None

    for raw_line in raw_frontmatter.splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith("  - ") and current_list_key:
            data.setdefault(current_list_key, []).append(raw_line[4:].strip())
            continue
        if ":" not in raw_line:
            current_list_key = None
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = []
            current_list_key = key
        else:
            data[key] = value
            current_list_key = None

    return data, body


def format_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    ordered_keys = [
        "type",
        "title",
        "description",
        "id",
        "resource",
        "scope",
        "scope_path",
        "created",
        "updated",
        "timestamp",
        "project",
        "projects",
        "repos",
        "aliases",
        "status",
        "owner",
        "last_verified",
        "archived",
        "archived_at",
        "archived_reason",
        "original_path",
        "moved_from",
        "moved_to",
        "supersedes",
        "tags",
    ]
    seen: set[str] = set()

    def append_value(key: str, value: Any) -> None:
        seen.add(key)
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
            return
        if isinstance(value, bool):
            value = str(value).lower()
        if value is not None:
            lines.append(f"{key}: {value}")

    for key in ordered_keys:
        value = data.get(key)
        if value is not None:
            append_value(key, value)
    for key, value in data.items():
        if key not in seen and value is not None:
            append_value(key, value)
    lines.append("---")
    return "\n".join(lines)


def read_content_arg(content: str | None, content_file: str | None) -> str:
    if bool(content) == bool(content_file):
        raise FundusError("Provide exactly one of --content or --content-file.")
    if content_file:
        path = Path(content_file).expanduser()
        return path.read_text()
    return content or ""


def normalize_tags(config: Config, project_name: str, extra_tags: list[str] | None) -> list[str]:
    tags: list[str] = []
    for tag in config.default_tags + [f"project/{project_name}"] + (extra_tags or []):
        normalized = tag.strip()
        if normalized and normalized not in tags:
            tags.append(normalized)
    return tags


def normalize_scope_tags(config: Config, project_name: str, scope: Scope, extra_tags: list[str] | None) -> list[str]:
    if scope.kind == "project":
        return normalize_tags(config, project_name, extra_tags)
    tags: list[str] = []
    area_tag = f"area/{slugify_path(scope.path)}"
    for tag in config.default_tags + [area_tag] + (extra_tags or []):
        normalized = tag.strip()
        if normalized and normalized not in tags:
            tags.append(normalized)
    return tags


def redact_secrets(text: str, config: Config) -> str:
    if not config.redaction_enabled:
        return text

    redacted = text

    for key in config.redaction_patterns:
        escaped = re.escape(key)
        redacted = re.sub(
            rf"(?im)\b({escaped})\s*=\s*([^\s\n]+)",
            rf"\1=[REDACTED]",
            redacted,
        )

    redacted = re.sub(r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]{12,}", r"\1 [REDACTED]", redacted)
    redacted = re.sub(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\b\s*[:=]\s*([^\s\n]+)", r"\1: [REDACTED]", redacted)
    redacted = re.sub(r"\b[a-f0-9]{32,}\b", "[REDACTED_HEX]", redacted)
    redacted = re.sub(r"\b[A-Za-z0-9+/]{40,}={0,2}\b", "[REDACTED_TOKEN]", redacted)

    return redacted


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_id_for(label: str | None, timestamp: datetime | None = None) -> str:
    created = timestamp or datetime.now().astimezone()
    suffix = slugify(label or "backup")
    return f"{created.strftime('%Y%m%dT%H%M%S%z')}-{suffix}"


def iter_backup_source_files(config: Config, root: Path | None = None) -> list[Path]:
    root = ensure_within(config.vault_path, root or fundus_root_dir(config))
    if not root.exists():
        raise FundusError(f"Fundus root does not exist: {root}")
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part == BACKUP_DIRNAME for part in relative_parts):
            continue
        files.append(path)
    return sorted(files)


def create_backup_for_root(config: Config, source_root: Path, source_dir_name: str, label: str | None = None) -> dict[str, Any]:
    created_at = datetime.now().astimezone()
    backup_id = backup_id_for(label, created_at)
    root = ensure_within(config.vault_path, source_root)
    backup_root = backup_root_dir(config)
    destination_root = ensure_within(config.vault_path, backup_root / backup_id)
    if destination_root.exists():
        raise FundusError(f"Backup already exists: {backup_id}")

    files = iter_backup_source_files(config, root)
    copied_files: list[dict[str, Any]] = []
    total_bytes = 0

    for source_path in files:
        relative_path = source_path.relative_to(root)
        destination_path = ensure_within(config.vault_path, destination_root / source_dir_name / relative_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        size = source_path.stat().st_size
        total_bytes += size
        copied_files.append(
            {
                "path": str((Path(source_dir_name) / relative_path).as_posix()),
                "source_path": str((Path(source_dir_name) / relative_path).as_posix()),
                "size": size,
                "sha256": file_sha256(source_path),
            }
        )

    manifest = {
        "id": backup_id,
        "label": label or "backup",
        "created": created_at.isoformat(),
        "source_vault_path": str(config.vault_path),
        "source_fundus_dir": source_dir_name,
        "source_fundus_path": str(root),
        "backup_path": str(destination_root),
        "file_count": len(copied_files),
        "byte_count": total_bytes,
        "files": copied_files,
    }
    atomic_write(destination_root / BACKUP_MANIFEST_FILENAME, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def create_backup(config: Config, label: str | None = None) -> dict[str, Any]:
    return create_backup_for_root(config, fundus_root_dir(config), config.fundus_dir, label)


def list_backups(config: Config) -> list[dict[str, Any]]:
    root = backup_root_dir(config)
    if not root.exists():
        return []
    backups: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob(f"*/{BACKUP_MANIFEST_FILENAME}")):
        manifest = load_json(manifest_path)
        backups.append(
            {
                "id": manifest.get("id") or manifest_path.parent.name,
                "label": manifest.get("label"),
                "created": manifest.get("created"),
                "file_count": manifest.get("file_count"),
                "byte_count": manifest.get("byte_count"),
                "backup_path": manifest.get("backup_path") or str(manifest_path.parent),
            }
        )
    backups.sort(key=lambda item: str(item.get("created") or ""), reverse=True)
    return backups


def inspect_backup(config: Config, backup_id: str) -> dict[str, Any]:
    if not backup_id or "/" in backup_id or "\\" in backup_id or backup_id in {".", ".."}:
        raise FundusError("Backup id must be a single backup directory name.")
    manifest_path = ensure_within(config.vault_path, backup_root_dir(config) / backup_id / BACKUP_MANIFEST_FILENAME)
    if not manifest_path.exists():
        raise FundusError(f"Backup does not exist: {backup_id}")
    manifest = load_json(manifest_path)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def load_document(path: Path, vault_root: Path) -> Document:
    safe_path = ensure_within(vault_root, path)
    text = safe_path.read_text()
    frontmatter, body = parse_frontmatter(text)
    try:
        relative_path = str(safe_path.relative_to(vault_root))
    except ValueError:
        relative_path = str(safe_path)
    return Document(
        path=safe_path,
        relative_path=relative_path,
        title=str(frontmatter.get("title") or safe_path.stem.replace("-", " ").title()),
        project=str(frontmatter.get("project") or ""),
        tags=list(frontmatter.get("tags") or []),
        created=frontmatter.get("created"),
        updated=frontmatter.get("updated"),
        body=body,
        frontmatter=frontmatter,
    )


def frontmatter_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.casefold() in {"true", "yes", "1"}
    return False


def tokenize(value: str) -> list[str]:
    return [term.casefold() for term in re.findall(r"[A-Za-z0-9]+", value)]


def extract_ticket_ids(value: str) -> list[str]:
    ids: list[str] = []
    for ticket_id in re.findall(r"\b[A-Z][A-Z0-9]+-\d+\b", value.upper()):
        if ticket_id not in ids:
            ids.append(ticket_id)
    return ids


def extract_headings(body: str) -> list[str]:
    headings: list[str] = []
    for line in body.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            headings.append(match.group(1).strip())
    return headings


def make_excerpt(body: str) -> str:
    text = re.sub(r"\s+", " ", body).strip()
    return text[:MAX_INDEX_EXCERPT_CHARS]


def fundus_relative_parts_from_vault_path(config: Config, path: Path) -> tuple[str, ...]:
    try:
        return tuple(ensure_within(config.vault_path, path).relative_to(fundus_root_dir(config)).parts)
    except ValueError:
        return ()


def active_fundus_relative_path_for_document(config: Config, doc: Document) -> str:
    original_path = str(doc.frontmatter.get("original_path") or "")
    if original_path:
        try:
            original = resolve_doc_path(config, original_path)
            return fundus_relative_path(config, original)
        except (FundusError, ValueError):
            pass
    parts = list(fundus_relative_parts_from_vault_path(config, doc.path))
    if parts and parts[0] == ARCHIVE_DIRNAME:
        return "/".join(parts[1:])
    return "/".join(parts)


def scope_metadata_for_document(config: Config, doc: Document) -> dict[str, Any]:
    explicit_scope = str(doc.frontmatter.get("scope") or "")
    explicit_scope_path = str(doc.frontmatter.get("scope_path") or "")
    active_relative = active_fundus_relative_path_for_document(config, doc)
    parent_path = str(Path(active_relative).parent).replace(".", "")

    if explicit_scope == "area":
        scope_path = explicit_scope_path or parent_path
        return {"scope": "area", "scope_path": scope_path, "area": scope_path}
    if explicit_scope == "project":
        scope_path = explicit_scope_path or doc.project or parent_path
        return {"scope": "project", "scope_path": scope_path, "area": None}
    if explicit_scope_path:
        return {"scope": "area", "scope_path": explicit_scope_path, "area": explicit_scope_path}
    if doc.project:
        return {"scope": "project", "scope_path": doc.project, "area": None}
    if parent_path:
        return {"scope": "area", "scope_path": parent_path, "area": parent_path}
    return {"scope": "area", "scope_path": "", "area": ""}


def frontmatter_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def confidence_for_score(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def index_entry_for_document(config: Config, doc: Document) -> dict[str, Any]:
    aliases = frontmatter_list(doc.frontmatter.get("aliases"))
    resource = str(doc.frontmatter.get("resource") or "").strip()
    optional_metadata_text = " ".join(
        [
            *aliases,
            resource,
            str(doc.frontmatter.get("status") or ""),
            str(doc.frontmatter.get("owner") or ""),
            str(doc.frontmatter.get("last_verified") or ""),
            " ".join(frontmatter_list(doc.frontmatter.get("projects"))),
            " ".join(frontmatter_list(doc.frontmatter.get("repos"))),
        ]
    )
    source_text = " ".join(
        [
            doc.relative_path,
            doc.title,
            *doc.tags,
            *extract_headings(doc.body),
            optional_metadata_text,
            doc.body,
        ]
    )
    archived = frontmatter_bool(doc.frontmatter.get("archived")) or f"/{ARCHIVE_DIRNAME}/" in f"/{doc.relative_path}"
    scope_metadata = scope_metadata_for_document(config, doc)
    return {
        "path": doc.relative_path,
        "project": doc.project,
        **scope_metadata,
        "title": doc.title,
        "tags": doc.tags,
        "description": doc.frontmatter.get("description"),
        "aliases": aliases,
        "resource": resource or None,
        "status": doc.frontmatter.get("status"),
        "owner": doc.frontmatter.get("owner"),
        "last_verified": doc.frontmatter.get("last_verified"),
        "projects": frontmatter_list(doc.frontmatter.get("projects")),
        "repos": frontmatter_list(doc.frontmatter.get("repos")),
        "updated": doc.updated,
        "headings": extract_headings(doc.body)[:20],
        "excerpt": make_excerpt(doc.body),
        "tokens": sorted(set(tokenize(source_text))),
        "ticket_ids": extract_ticket_ids(source_text),
        "mtime_ns": doc.path.stat().st_mtime_ns,
        "archived": archived,
        "original_path": doc.frontmatter.get("original_path"),
        "archived_at": doc.frontmatter.get("archived_at"),
        "archived_reason": doc.frontmatter.get("archived_reason"),
    }


def iter_fundus_markdown_paths(config: Config) -> list[Path]:
    root = fundus_root_dir(config)
    if not root.exists():
        return []
    active_paths = [
        path
        for path in root.rglob("*.md")
        if ARCHIVE_DIRNAME not in path.relative_to(root).parts
        and BACKUP_DIRNAME not in path.relative_to(root).parts
    ]
    archive_paths = list(fundus_archive_dir(config).rglob("*.md")) if fundus_archive_dir(config).exists() else []
    return sorted([*active_paths, *archive_paths])


def load_index(config: Config) -> dict[str, Any] | None:
    path = index_path(config)
    if not path.exists():
        return None
    data = load_json(path)
    if data.get("version") != INDEX_VERSION or not isinstance(data.get("documents"), list):
        return None
    return data


def write_index(config: Config, documents: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "version": INDEX_VERSION,
        "generated": now_iso(),
        "fundus_dir": config.fundus_dir,
        "documents": sorted(documents, key=lambda doc: str(doc.get("path", ""))),
    }
    atomic_write(index_path(config), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def rebuild_index(config: Config) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    for path in iter_fundus_markdown_paths(config):
        doc = load_document(path, config.vault_path)
        documents.append(index_entry_for_document(config, doc))
    return write_index(config, documents)


def refresh_index_entry(config: Config, path: Path) -> None:
    existing_index = load_index(config)
    if existing_index is None:
        return

    safe_path = ensure_within(config.vault_path, path)
    relative_path = str(safe_path.relative_to(config.vault_path))
    documents = [doc for doc in existing_index["documents"] if doc.get("path") != relative_path]
    if safe_path.exists():
        documents.append(index_entry_for_document(config, load_document(safe_path, config.vault_path)))
    write_index(config, documents)


def score_index_entry(entry: dict[str, Any], query: str | None) -> tuple[int, str]:
    query_terms = tokenize(query or "")
    query_ticket_ids = extract_ticket_ids(query or "")
    if not query_terms and not query_ticket_ids:
        return 1, "listed"

    score = 0
    reasons: list[str] = []
    title_tokens = set(tokenize(str(entry.get("title", ""))))
    alias_tokens = set(tokenize(" ".join(entry.get("aliases") or [])))
    resource_tokens = set(tokenize(str(entry.get("resource") or "")))
    description_tokens = set(tokenize(str(entry.get("description") or "")))
    tag_tokens = set(tokenize(" ".join(entry.get("tags") or [])))
    filename_tokens = set(tokenize(str(entry.get("path", "")).rsplit("/", 1)[-1]))
    heading_tokens = set(tokenize(" ".join(entry.get("headings") or [])))
    body_tokens = set(entry.get("tokens") or [])
    entry_ticket_ids = set(entry.get("ticket_ids") or [])

    for ticket_id in query_ticket_ids:
        if ticket_id in entry_ticket_ids:
            score += 80
            reasons.append(f"ticket:{ticket_id}")

    for term in query_terms:
        if term in title_tokens:
            score += 20
            reasons.append("title")
        elif term in alias_tokens:
            score += 18
            reasons.append("alias")
        elif term in resource_tokens:
            score += 16
            reasons.append("resource")
        elif term in description_tokens:
            score += 15
            reasons.append("description")
        elif term in tag_tokens:
            score += 14
            reasons.append("tag")
        elif term in filename_tokens:
            score += 12
            reasons.append("filename")
        elif term in heading_tokens:
            score += 8
            reasons.append("heading")
        elif term in body_tokens:
            score += 3
            reasons.append("body")

    matched_terms = sum(1 for term in query_terms if term in body_tokens)
    if query_terms and matched_terms == 0 and not query_ticket_ids:
        return 0, ""
    if len(query_terms) > 1 and matched_terms < max(1, len(query_terms) // 2) and not query_ticket_ids:
        return 0, ""

    reason = ",".join(dict.fromkeys(reasons)) or "match"
    return score, reason


def present_index_entry(entry: dict[str, Any], score: int | None = None, reason: str | None = None, include_snippet: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": entry.get("path"),
        "title": entry.get("title"),
        "tags": entry.get("tags") or [],
        "updated": entry.get("updated"),
    }
    if entry.get("project"):
        payload["project"] = entry.get("project")
    if entry.get("scope"):
        payload["scope"] = entry.get("scope")
        payload["scope_path"] = entry.get("scope_path")
    if entry.get("area"):
        payload["area"] = entry.get("area")
    if entry.get("aliases"):
        payload["aliases"] = entry.get("aliases")
    if entry.get("resource"):
        payload["resource"] = entry.get("resource")
    if entry.get("last_verified"):
        payload["last_verified"] = entry.get("last_verified")
    if entry.get("archived"):
        payload["archived"] = True
        payload["original_path"] = entry.get("original_path")
        payload["archived_at"] = entry.get("archived_at")
    if score is not None:
        payload["score"] = score
        payload["confidence"] = confidence_for_score(score)
    if reason:
        payload["reason"] = reason
    if include_snippet:
        payload["snippet"] = entry.get("excerpt") or ""
    return payload


def resolve_doc_path(config: Config, path_arg: str) -> Path:
    raw_path = Path(path_arg).expanduser()
    if raw_path.is_absolute():
        return ensure_within(config.vault_path, raw_path)
    return ensure_within(config.vault_path, config.vault_path / raw_path)


def entry_matches_scope(config: Config, entry: dict[str, Any], scope: Scope) -> bool:
    path = str(entry.get("path") or "")
    prefix = f"{config.fundus_dir}/{scope.path}/"
    archive_prefix = f"{config.fundus_dir}/{ARCHIVE_DIRNAME}/{scope.path}/"
    if scope.kind == "project":
        return (
            entry.get("scope") == "project"
            and entry.get("scope_path") == scope.path
        ) or entry.get("project") == scope.path
    return path.startswith(prefix) or path.startswith(archive_prefix) or entry.get("scope_path") == scope.path


def markdown_paths_for_scope(config: Config, scope: Scope, include_archived: bool = False) -> list[Path]:
    active_dir = fundus_scope_dir(config, scope)
    paths = sorted(active_dir.rglob("*.md")) if active_dir.exists() else []
    if include_archived:
        archive_dir = fundus_archive_scope_dir(config, scope)
        if archive_dir.exists():
            paths.extend(sorted(archive_dir.rglob("*.md")))
    return paths


def scan_documents(
    config: Config,
    project_name: str,
    query: str | None,
    limit: int = MAX_SCAN_RESULTS,
    include_snippet: bool = False,
    include_archived: bool = False,
    scope: Scope | None = None,
) -> list[dict[str, Any]]:
    active_scope = scope or project_scope(project_name)
    existing_index = load_index(config)
    if existing_index is not None:
        matches: list[tuple[int, str, dict[str, Any]]] = []
        for entry in existing_index["documents"]:
            if not entry_matches_scope(config, entry, active_scope):
                continue
            if entry.get("archived") and not include_archived:
                continue
            score, reason = score_index_entry(entry, query)
            if score <= 0:
                continue
            matches.append((score, reason, entry))

        matches.sort(key=lambda item: (-item[0], str(item[2].get("title", ""))))
        return [present_index_entry(entry, score, reason, include_snippet) for score, reason, entry in matches[:limit]]

    scope_dir = fundus_scope_dir(config, active_scope)
    archive_scope_dir = fundus_archive_scope_dir(config, active_scope)
    if not scope_dir.exists() and not (include_archived and archive_scope_dir.exists()):
        return []

    query_terms = tokenize(query or "")
    documents: list[dict[str, Any]] = []
    scan_paths = markdown_paths_for_scope(config, active_scope, include_archived)

    for path in scan_paths:
        doc = load_document(path, config.vault_path)
        haystack = " ".join([doc.title, *doc.tags, path.name]).lower()
        if query_terms and not all(term in haystack for term in query_terms):
            continue
        documents.append(present_index_entry(index_entry_for_document(config, doc)))

    return documents[:limit]


def remove_duplicate_title_heading(body: str, title: str) -> str:
    lines = body.strip().splitlines()
    if not lines:
        return ""

    match = re.match(r"^#\s+(.+?)\s*$", lines[0])
    if not match or match.group(1).strip().casefold() != title.strip().casefold():
        return body.strip()

    remaining_lines = lines[1:]
    while remaining_lines and not remaining_lines[0].strip():
        remaining_lines = remaining_lines[1:]
    return "\n".join(remaining_lines).strip()


def render_document(frontmatter: dict[str, Any], body: str) -> str:
    cleaned_body = remove_duplicate_title_heading(body, str(frontmatter["title"]))
    return f"{format_frontmatter(frontmatter)}\n\n# {frontmatter['title']}\n\n{cleaned_body}\n"


def default_document_id(scope: Scope, title: str) -> str:
    return f"{scope.kind}/{slugify_path(scope.path)}/{slugify(title)}"


def frontmatter_for_new_document(
    config: Config,
    project_name: str,
    scope: Scope,
    title: str,
    extra_tags: list[str] | None,
    doc_type: str | None = None,
    description: str | None = None,
    document_id: str | None = None,
    aliases: list[str] | None = None,
    resource: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    last_verified: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    frontmatter: dict[str, Any] = {
        "type": (doc_type or "Note").strip() or "Note",
        "title": title.strip(),
        "description": (description or title).strip(),
        "id": (document_id or default_document_id(scope, title)).strip(),
        "scope": scope.kind,
        "scope_path": scope.path,
        "created": timestamp,
        "updated": timestamp,
        "timestamp": timestamp,
        "tags": normalize_scope_tags(config, project_name, scope, extra_tags),
    }
    if scope.kind == "project":
        frontmatter["project"] = project_name
    clean_aliases = [alias.strip() for alias in aliases or [] if alias.strip()]
    if clean_aliases:
        frontmatter["aliases"] = clean_aliases
    if resource and resource.strip():
        frontmatter["resource"] = resource.strip()
    if status and status.strip():
        frontmatter["status"] = status.strip()
    if owner and owner.strip():
        frontmatter["owner"] = owner.strip()
    if last_verified and last_verified.strip():
        frontmatter["last_verified"] = last_verified.strip()
    return frontmatter


def create_document(
    config: Config,
    project_name: str,
    title: str,
    body: str,
    extra_tags: list[str] | None,
    scope: Scope | None = None,
    doc_type: str | None = None,
    description: str | None = None,
    document_id: str | None = None,
    aliases: list[str] | None = None,
    resource: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    last_verified: str | None = None,
) -> dict[str, Any]:
    active_scope = scope or project_scope(project_name)
    project_dir = fundus_scope_dir(config, active_scope)
    slug = slugify(title)
    path = ensure_within(config.vault_path, project_dir / f"{slug}.md")
    if path.exists():
        raise FundusError(f"Document already exists: {path.relative_to(config.vault_path)}")

    frontmatter = frontmatter_for_new_document(
        config,
        project_name,
        active_scope,
        title,
        extra_tags,
        doc_type,
        description,
        document_id,
        aliases,
        resource,
        status,
        owner,
        last_verified,
    )
    content = render_document(frontmatter, redact_secrets(body, config))
    atomic_write(path, content)
    refresh_index_entry(config, path)
    return {
        "path": str(path.relative_to(config.vault_path)),
        "title": title.strip(),
        "created": frontmatter["created"],
        "updated": frontmatter["updated"],
        "scope": active_scope.kind,
        "scope_path": active_scope.path,
        "warnings": [],
    }


def append_body(existing_body: str, new_content: str) -> str:
    current = existing_body.rstrip()
    addition = new_content.strip()
    if not current:
        return addition
    return f"{current}\n\n{addition}"


def replace_section(existing_body: str, section: str, new_content: str) -> str:
    lines = existing_body.splitlines()
    heading_pattern = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
    target_index = None
    target_level = None

    for index, line in enumerate(lines):
        match = heading_pattern.match(line)
        if match and match.group(2).strip() == section:
            target_index = index
            target_level = len(match.group(1))
            break

    replacement_block = [f"## {section}", "", *new_content.strip().splitlines()]

    if target_index is None:
        base = existing_body.rstrip()
        addition = "\n".join(replacement_block).strip()
        if not base:
            return addition
        return f"{base}\n\n{addition}"

    end_index = len(lines)
    for index in range(target_index + 1, len(lines)):
        match = heading_pattern.match(lines[index])
        if match and len(match.group(1)) <= (target_level or 2):
            end_index = index
            break

    updated_lines = lines[:target_index] + replacement_block + lines[end_index:]
    return "\n".join(updated_lines).strip()


def update_document(
    config: Config,
    project_name: str,
    path_arg: str,
    mode: str,
    new_content: str,
    section: str | None,
    scope: Scope | None = None,
) -> dict[str, Any]:
    path = resolve_doc_path(config, path_arg)
    if not path.exists():
        raise FundusError(f"Document does not exist: {path_arg}")

    text = path.read_text()
    frontmatter, body = parse_frontmatter(text)
    if not frontmatter:
        raise FundusError(f"Document is missing expected frontmatter: {path}")

    redacted_content = redact_secrets(new_content, config)
    if mode == "append":
        updated_body = append_body(body, redacted_content)
    elif mode == "replace":
        if not section:
            raise FundusError("--section is required when mode is replace.")
        updated_body = replace_section(body, section, redacted_content)
    elif mode == "rewrite":
        updated_body = redacted_content.strip()
    else:
        raise FundusError(f"Unknown update mode: {mode}")

    frontmatter["updated"] = now_iso()
    frontmatter["timestamp"] = frontmatter["updated"]
    doc = Document(
        path=path,
        relative_path=str(path.relative_to(config.vault_path)),
        title=str(frontmatter.get("title") or path.stem.replace("-", " ").title()),
        project=str(frontmatter.get("project") or ""),
        tags=list(frontmatter.get("tags") or []),
        created=frontmatter.get("created"),
        updated=frontmatter.get("updated"),
        body=body,
        frontmatter=frontmatter,
    )
    if scope is None:
        if frontmatter.get("scope") == "area" or frontmatter.get("scope_path"):
            metadata_scope = scope_metadata_for_document(config, doc)
            active_scope = Scope(
                kind=str(metadata_scope.get("scope") or "project"),
                path=str(metadata_scope.get("scope_path") or project_name),
                display_name=str(metadata_scope.get("scope_path") or project_name),
            )
        else:
            active_scope = project_scope(project_name)
    else:
        active_scope = scope
    if not frontmatter.get("scope"):
        frontmatter["scope"] = active_scope.kind
    if not frontmatter.get("scope_path"):
        frontmatter["scope_path"] = active_scope.path
    if active_scope.kind == "project" and not frontmatter.get("project"):
        frontmatter["project"] = project_name
    if not frontmatter.get("tags"):
        frontmatter["tags"] = normalize_scope_tags(config, project_name, active_scope, [])

    rendered = f"{format_frontmatter(frontmatter)}\n\n{updated_body.strip()}\n"
    atomic_write(path, rendered)
    refresh_index_entry(config, path)
    return {
        "path": str(path.relative_to(config.vault_path)),
        "title": frontmatter.get("title"),
        "updated": frontmatter.get("updated"),
        "mode": mode,
        "section": section,
    }


def read_document(config: Config, path_arg: str) -> str:
    path = resolve_doc_path(config, path_arg)
    if not path.exists():
        raise FundusError(f"Document does not exist: {path_arg}")
    return path.read_text()


def filesystem_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()


def add_frontmatter_to_document(
    config: Config,
    project_name: str,
    path_arg: str,
    title: str | None,
    extra_tags: list[str] | None,
    scope: Scope | None = None,
    doc_type: str | None = None,
    description: str | None = None,
    document_id: str | None = None,
    aliases: list[str] | None = None,
    resource: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    last_verified: str | None = None,
) -> dict[str, Any]:
    path = resolve_doc_path(config, path_arg)
    if not path.exists():
        raise FundusError(f"Document does not exist: {path_arg}")

    text = path.read_text()
    existing_frontmatter, body = parse_frontmatter(text)
    if existing_frontmatter:
        raise FundusError(f"Document already has frontmatter: {path.relative_to(config.vault_path)}")

    timestamp = filesystem_timestamp(path)
    active_scope = scope or project_scope(project_name)
    note_title = (title or path.stem.replace("-", " ").title()).strip()
    frontmatter = frontmatter_for_new_document(
        config,
        project_name,
        active_scope,
        note_title,
        extra_tags,
        doc_type,
        description,
        document_id,
        aliases,
        resource,
        status,
        owner,
        last_verified,
    )
    frontmatter["created"] = timestamp
    frontmatter["updated"] = timestamp
    frontmatter["timestamp"] = timestamp

    atomic_write(path, render_existing_document(frontmatter, body))
    refresh_index_entry(config, path)
    return {
        "path": str(path.relative_to(config.vault_path)),
        "title": frontmatter["title"],
        "created": frontmatter["created"],
        "updated": frontmatter["updated"],
        "tags": frontmatter["tags"],
    }


def fundus_relative_parts_for_active_document(config: Config, path: Path, frontmatter: dict[str, Any]) -> tuple[str, ...]:
    original_path = str(frontmatter.get("original_path") or "")
    if original_path:
        parts = Path(original_path).parts
        if parts and parts[0] == config.fundus_dir:
            return tuple(parts[1:])
        return tuple(parts)

    parts = fundus_relative_parts_from_vault_path(config, path)
    if parts and parts[0] == ARCHIVE_DIRNAME:
        return tuple(parts[1:])
    return parts


def infer_scope_from_document_path(config: Config, path: Path, frontmatter: dict[str, Any]) -> tuple[Scope, str | None]:
    parts = fundus_relative_parts_for_active_document(config, path, frontmatter)
    if not parts:
        raise FundusError(f"Document path is not inside the Fundus root: {path}")
    if parts[0] in RESERVED_FUNDUS_DIRNAMES:
        raise FundusError(f"Cannot normalize reserved Fundus path: {path.relative_to(config.vault_path)}")

    if parts[0] in AREA_ROOT_DIRNAMES:
        area_parts = parts[:-1]
        if not area_parts:
            raise FundusError(f"Cannot infer area scope for path: {path.relative_to(config.vault_path)}")
        area_path = "/".join(area_parts)
        return area_scope(area_path), None

    project_name = parts[0]
    return project_scope(project_name), project_name


def infer_doc_type_from_path(config: Config, path: Path, frontmatter: dict[str, Any], scope: Scope) -> str:
    existing_type = str(frontmatter.get("type") or "").strip()
    if existing_type:
        return existing_type

    parts = [part.casefold() for part in fundus_relative_parts_for_active_document(config, path, frontmatter)]
    filename = parts[-1] if parts else path.name.casefold()
    raw_tags = frontmatter.get("tags") or []
    existing_tags = raw_tags if isinstance(raw_tags, list) else [str(raw_tags)]
    tags = {str(tag).casefold() for tag in existing_tags}

    if filename == "index.md":
        return "Index"
    if filename == "log.md":
        return "Log"
    if "interviews" in parts:
        return "Interview"
    if "implementation-map" in parts:
        return "ImplementationMap"
    if "domain-model" in parts:
        return "DomainModel"
    if "open-questions" in parts:
        return "OpenQuestions"
    if "references" in parts:
        return "Reference"
    if "decisions" in parts or scope.path.startswith("Decisions/"):
        return "Decision"
    if "runbook" in filename or "runbook" in tags:
        return "Runbook"
    if "architecture" in filename or "architecture" in tags:
        return "Architecture"
    if "functional-overview" in filename or "functional" in tags:
        return "FunctionalOverview"
    if "technical-implementation-notes" in filename or "implementation" in tags:
        return "ImplementationNotes"
    if "overview" in filename or "project-overview" in tags:
        return "Overview"
    if "ticket" in tags or extract_ticket_ids(f"{path.name} {frontmatter.get('title') or ''}"):
        return "Research"
    return "Note"


def scope_neutral_tags(tags: list[str]) -> list[str]:
    neutral: list[str] = []
    for tag in tags:
        normalized = str(tag).strip()
        if not normalized:
            continue
        if normalized in {"fundus", "wiki"} or normalized.startswith("project/") or normalized.startswith("area/"):
            continue
        if normalized not in neutral:
            neutral.append(normalized)
    return neutral


def frontmatter_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes.append({"key": key, "before": before.get(key), "after": after.get(key)})
    return changes


def render_existing_document_preserving_body(frontmatter: dict[str, Any], body: str) -> str:
    return f"{format_frontmatter(frontmatter)}\n{body}"


def normalize_frontmatter_for_path(
    config: Config,
    path: Path,
    apply: bool = False,
    add_missing: bool = False,
) -> dict[str, Any]:
    safe_path = resolve_doc_path(config, str(path))
    if safe_path.suffix != ".md":
        raise FundusError(f"Can only normalize Markdown documents: {safe_path.relative_to(config.vault_path)}")
    ensure_within(fundus_root_dir(config), safe_path)
    if not safe_path.exists():
        raise FundusError(f"Document does not exist: {path}")

    text = safe_path.read_text()
    frontmatter, body = parse_frontmatter(text)
    if not frontmatter and not add_missing:
        return {
            "path": str(safe_path.relative_to(config.vault_path)),
            "changed": False,
            "applied": False,
            "skipped": True,
            "reason": "missing_frontmatter",
        }

    before_frontmatter = dict(frontmatter)
    active_scope, inferred_project = infer_scope_from_document_path(config, safe_path, before_frontmatter)
    title = str(frontmatter.get("title") or safe_path.stem.replace("-", " ").title()).strip()
    timestamp = str(frontmatter.get("updated") or frontmatter.get("created") or filesystem_timestamp(safe_path))
    created = str(frontmatter.get("created") or timestamp)
    updated = str(frontmatter.get("updated") or timestamp)
    raw_tags = frontmatter.get("tags") or []
    existing_tags = raw_tags if isinstance(raw_tags, list) else [str(raw_tags)]
    project_for_tags = inferred_project or ""

    normalized = dict(frontmatter)
    normalized["type"] = infer_doc_type_from_path(config, safe_path, frontmatter, active_scope)
    normalized["title"] = title
    normalized["description"] = str(normalized.get("description") or title).strip()
    normalized["id"] = str(normalized.get("id") or default_document_id(active_scope, title)).strip()
    normalized["scope"] = active_scope.kind
    normalized["scope_path"] = active_scope.path
    normalized["created"] = created
    normalized["updated"] = updated
    normalized["timestamp"] = str(normalized.get("timestamp") or updated)
    if active_scope.kind == "project":
        normalized["project"] = inferred_project
    else:
        normalized.pop("project", None)
    normalized["tags"] = normalize_scope_tags(
        config,
        project_for_tags,
        active_scope,
        scope_neutral_tags(existing_tags),
    )

    changes = frontmatter_changes(before_frontmatter, normalized)
    rendered = render_existing_document_preserving_body(normalized, body)
    _, rendered_body = parse_frontmatter(rendered)
    body_sha256 = hashlib.sha256(body.encode()).hexdigest()
    body_unchanged = rendered_body == body
    if not body_unchanged:
        raise FundusError(f"Refusing to normalize because body would change: {safe_path.relative_to(config.vault_path)}")

    if apply and changes:
        atomic_write(safe_path, rendered)
        refresh_index_entry(config, safe_path)

    return {
        "path": str(safe_path.relative_to(config.vault_path)),
        "title": title,
        "changed": bool(changes),
        "applied": bool(apply and changes),
        "skipped": False,
        "scope": active_scope.kind,
        "scope_path": active_scope.path,
        "body_sha256": body_sha256,
        "body_unchanged": body_unchanged,
        "changes": changes,
    }


def normalize_frontmatter_paths(
    config: Config,
    project_name: str,
    scope: Scope,
    path_arg: str | None = None,
    global_scope: bool = False,
    include_archived: bool = False,
    apply: bool = False,
    add_missing: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    if path_arg and global_scope:
        raise FundusError("--path and --global cannot be used together.")
    if path_arg and limit is not None:
        raise FundusError("--limit cannot be used with --path.")

    if path_arg:
        paths = [resolve_doc_path(config, path_arg)]
        scope_name = "path"
        scope_path = path_arg
    elif global_scope:
        root = fundus_root_dir(config)
        paths = [
            path
            for path in sorted(root.rglob("*.md"))
            if BACKUP_DIRNAME not in path.relative_to(root).parts
            and (include_archived or ARCHIVE_DIRNAME not in path.relative_to(root).parts)
        ]
        scope_name = "global"
        scope_path = None
    else:
        paths = markdown_paths_for_scope(config, scope, include_archived)
        scope_name = scope.kind
        scope_path = scope.path

    if limit is not None:
        paths = paths[:limit]

    documents = [
        normalize_frontmatter_for_path(config, path, apply=apply, add_missing=add_missing)
        for path in paths
    ]
    changed_count = sum(1 for doc in documents if doc.get("changed"))
    applied_count = sum(1 for doc in documents if doc.get("applied"))
    skipped_count = sum(1 for doc in documents if doc.get("skipped"))
    return {
        "scope": scope_name,
        "scope_path": scope_path,
        "project": project_name if scope_name == "project" else None,
        "apply": apply,
        "include_archived": include_archived,
        "add_missing": add_missing,
        "documents": documents,
        "document_count": len(documents),
        "changed_count": changed_count,
        "applied_count": applied_count,
        "skipped_count": skipped_count,
    }


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def age_days(value: str | None) -> int | None:
    parsed = parse_iso_datetime(value)
    if not parsed:
        return None
    return max(0, (datetime.now().astimezone() - parsed).days)


def archive_destination_for(config: Config, doc: Document) -> Path:
    relative_path = Path(active_fundus_relative_path_for_document(config, doc))
    return ensure_within(config.vault_path, fundus_archive_dir(config) / relative_path)


def archive_candidates(
    config: Config,
    project_name: str,
    older_than_days: int,
    limit: int,
    force: bool = False,
    scope: Scope | None = None,
) -> list[dict[str, Any]]:
    cutoff = datetime.now().astimezone() - timedelta(days=older_than_days)
    candidates: list[dict[str, Any]] = []
    active_scope = scope or project_scope(project_name)
    scope_dir = fundus_scope_dir(config, active_scope)
    if not scope_dir.exists():
        return []

    for path in sorted(scope_dir.rglob("*.md")):
        doc = load_document(path, config.vault_path)
        if not doc.frontmatter:
            candidates.append(
                {
                    "path": doc.relative_path,
                    "title": doc.title,
                    "reason": "needs_review",
                    "detail": "missing frontmatter",
                }
            )
            continue
        if frontmatter_bool(doc.frontmatter.get("archived")):
            continue
        has_durable_tag = bool(ARCHIVE_DURABLE_TAGS.intersection(set(doc.tags)))
        if has_durable_tag and not force:
            continue
        updated = parse_iso_datetime(doc.updated or doc.created)
        if not updated or updated > cutoff:
            continue
        recommendation = "old_note"
        if ARCHIVE_BOOST_TAGS.intersection(set(doc.tags)) or extract_ticket_ids(f"{doc.title} {doc.path.name}"):
            recommendation = "old_ticket_or_investigation"
        if has_durable_tag:
            recommendation = "old_durable_note"
        candidates.append(
            {
                "path": doc.relative_path,
                "title": doc.title,
                "tags": doc.tags,
                "updated": doc.updated,
                "age_days": age_days(doc.updated or doc.created),
                "reason": recommendation,
                "scope": active_scope.kind,
                "scope_path": active_scope.path,
            }
        )

    candidates.sort(key=lambda item: (item.get("updated") or "", item.get("title") or ""))
    return candidates[:limit]


def archive_candidates_global(
    config: Config,
    older_than_days: int,
    limit: int,
    force: bool = False,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for project_name in fundus_project_names(config):
        for candidate in archive_candidates(config, project_name, older_than_days, limit, force):
            candidates.append({"project": project_name, **candidate})

    candidates.sort(key=lambda item: (item.get("updated") or "", item.get("project") or "", item.get("title") or ""))
    return candidates[:limit]


def render_existing_document(frontmatter: dict[str, Any], body: str) -> str:
    return f"{format_frontmatter(frontmatter)}\n\n{body.strip()}\n"


def remove_empty_directory(directory: Path, protected_directories: set[Path]) -> bool:
    resolved_directory = directory.resolve()
    resolved_protected = {path.resolve() for path in protected_directories}
    if resolved_directory in resolved_protected:
        return False
    try:
        resolved_directory.rmdir()
    except OSError:
        return False
    return True


def cleanup_empty_directories(
    config: Config,
    project_name: str,
    global_scope: bool = False,
    scope: Scope | None = None,
) -> dict[str, Any]:
    root = fundus_root_dir(config)
    archive_root = fundus_archive_dir(config)
    protected_directories = {root, archive_root}
    active_scope = scope or project_scope(project_name)
    candidate_roots = [root] if global_scope else [fundus_scope_dir(config, active_scope), fundus_archive_scope_dir(config, active_scope)]
    candidates: list[Path] = []

    for candidate_root in candidate_roots:
        if not candidate_root.exists() or not candidate_root.is_dir():
            continue
        candidates.extend(path for path in candidate_root.rglob("*") if path.is_dir())
        candidates.append(candidate_root)

    unique_candidates = sorted({path.resolve() for path in candidates}, key=lambda path: len(path.parts), reverse=True)
    removed_paths: list[str] = []
    for candidate in unique_candidates:
        if remove_empty_directory(candidate, protected_directories):
            removed_paths.append(str(candidate.relative_to(config.vault_path)))

    return {
        "scope": "global" if global_scope else active_scope.kind,
        "scope_path": None if global_scope else active_scope.path,
        "project": None if global_scope or active_scope.kind != "project" else project_name,
        "removed_directories": sorted(removed_paths),
        "removed_count": len(removed_paths),
    }


def archive_document(config: Config, path_arg: str, reason: str | None) -> dict[str, Any]:
    source_path = resolve_doc_path(config, path_arg)
    if not source_path.exists():
        raise FundusError(f"Document does not exist: {path_arg}")

    doc = load_document(source_path, config.vault_path)
    if not doc.frontmatter:
        raise FundusError(f"Document is missing expected frontmatter: {source_path}")
    if frontmatter_bool(doc.frontmatter.get("archived")):
        raise FundusError(f"Document is already archived: {doc.relative_path}")

    destination_path = archive_destination_for(config, doc)
    if destination_path.exists():
        raise FundusError(f"Archive destination already exists: {destination_path.relative_to(config.vault_path)}")

    timestamp = now_iso()
    frontmatter = dict(doc.frontmatter)
    frontmatter["updated"] = timestamp
    frontmatter["archived"] = True
    frontmatter["archived_at"] = timestamp
    frontmatter["archived_reason"] = reason or "archived"
    frontmatter["original_path"] = doc.relative_path

    atomic_write(destination_path, render_existing_document(frontmatter, doc.body))
    source_path.unlink()
    active_directory_removed = remove_empty_directory(source_path.parent, {fundus_root_dir(config), fundus_archive_dir(config)})
    refresh_index_entry(config, source_path)
    refresh_index_entry(config, destination_path)
    return {
        "path": str(destination_path.relative_to(config.vault_path)),
        "original_path": doc.relative_path,
        "title": doc.title,
        "archived_at": timestamp,
        "reason": frontmatter["archived_reason"],
        "active_directory_removed": active_directory_removed,
    }


def restore_document(config: Config, path_arg: str) -> dict[str, Any]:
    archive_path = resolve_doc_path(config, path_arg)
    if not archive_path.exists():
        raise FundusError(f"Document does not exist: {path_arg}")

    doc = load_document(archive_path, config.vault_path)
    if not doc.frontmatter:
        raise FundusError(f"Document is missing expected frontmatter: {archive_path}")
    if not frontmatter_bool(doc.frontmatter.get("archived")):
        raise FundusError(f"Document is not archived: {doc.relative_path}")

    original_path = str(doc.frontmatter.get("original_path") or "")
    if not original_path:
        raise FundusError(f"Archived document is missing original_path: {doc.relative_path}")
    destination_path = resolve_doc_path(config, original_path)
    if destination_path.exists():
        raise FundusError(f"Restore destination already exists: {original_path}")

    frontmatter = dict(doc.frontmatter)
    timestamp = now_iso()
    frontmatter["updated"] = timestamp
    for key in ["archived", "archived_at", "archived_reason", "original_path"]:
        frontmatter.pop(key, None)

    atomic_write(destination_path, render_existing_document(frontmatter, doc.body))
    archive_path.unlink()
    archive_directory_removed = remove_empty_directory(archive_path.parent, {fundus_archive_dir(config), fundus_root_dir(config)})
    refresh_index_entry(config, archive_path)
    refresh_index_entry(config, destination_path)
    return {
        "path": str(destination_path.relative_to(config.vault_path)),
        "archived_path": doc.relative_path,
        "title": doc.title,
        "restored_at": timestamp,
        "archive_directory_removed": archive_directory_removed,
    }


def area_init(config: Config, project_name: str, area: str, area_type: str, title: str) -> dict[str, Any]:
    scope = area_scope(area)
    root = fundus_scope_dir(config, scope)
    created_paths: list[str] = []
    skipped_paths: list[str] = []

    for directory in AREA_SUBDIRECTORIES:
        path = ensure_within(config.vault_path, root / directory)
        path.mkdir(parents=True, exist_ok=True)

    files = {
        "overview.md": (
            title,
            area_type,
            f"Overview for {title}.",
            "## Overview\n\nDocument the durable area overview here.",
        ),
        "index.md": (
            f"{title} Index",
            "Index",
            f"Progressive-disclosure index for {title}.",
            "\n".join(
                [
                    "## Core",
                    "",
                    "* [Overview](overview.md) - durable area overview",
                    "* [Log](log.md) - chronological area activity",
                    "",
                    "## Sections",
                    "",
                    *[f"* [{directory}]({directory}/) - area notes" for directory in AREA_SUBDIRECTORIES],
                ]
            ),
        ),
        "log.md": (
            f"{title} Log",
            "Log",
            f"Chronological activity log for {title}.",
            f"## {datetime.now().astimezone().date().isoformat()}\n\n* **Initialization**: Created the area skeleton.",
        ),
    }

    for filename, (file_title, doc_type, description, body) in files.items():
        path = ensure_within(config.vault_path, root / filename)
        if path.exists():
            skipped_paths.append(str(path.relative_to(config.vault_path)))
            continue
        frontmatter = frontmatter_for_new_document(
            config,
            project_name,
            scope,
            file_title,
            [slugify(title)],
            doc_type,
            description,
            f"area/{slugify_path(scope.path)}/{path.stem}",
        )
        atomic_write(path, render_document(frontmatter, body))
        refresh_index_entry(config, path)
        created_paths.append(str(path.relative_to(config.vault_path)))

    return {
        "area": scope.path,
        "path": str(root.relative_to(config.vault_path)),
        "created": created_paths,
        "skipped": skipped_paths,
        "directories": [str((root / directory).relative_to(config.vault_path)) for directory in AREA_SUBDIRECTORIES],
    }


def move_document(config: Config, source_arg: str, destination_arg: str, leave_stub: bool = False) -> dict[str, Any]:
    source_path = resolve_doc_path(config, source_arg)
    destination_path = resolve_doc_path(config, destination_arg)
    if not source_path.exists():
        raise FundusError(f"Document does not exist: {source_arg}")
    if destination_path.exists():
        raise FundusError(f"Move destination already exists: {destination_arg}")
    root = fundus_root_dir(config)
    ensure_within(root, source_path)
    ensure_within(root, destination_path)
    if ARCHIVE_DIRNAME in source_path.relative_to(root).parts or ARCHIVE_DIRNAME in destination_path.relative_to(root).parts:
        raise FundusError("Move source and destination must be active Fundus paths, not archive paths.")

    doc = load_document(source_path, config.vault_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    if leave_stub:
        frontmatter = dict(doc.frontmatter)
        frontmatter["updated"] = now_iso()
        frontmatter["moved_to"] = str(destination_path.relative_to(config.vault_path))
        stub_target = str(destination_path.relative_to(config.vault_path))
        stub_body = f"# {doc.title}\n\nMoved to [{destination_path.name}]({stub_target}).\n"
        atomic_write(source_path, render_existing_document(frontmatter, stub_body))
    else:
        source_path.unlink()
        remove_empty_directory(source_path.parent, {fundus_root_dir(config), fundus_archive_dir(config)})
    moved_doc = load_document(destination_path, config.vault_path)
    moved_frontmatter = dict(moved_doc.frontmatter)
    moved_frontmatter["updated"] = now_iso()
    moved_frontmatter["moved_from"] = doc.relative_path
    destination_fundus_relative = destination_path.relative_to(fundus_root_dir(config)).as_posix()
    destination_parent = str(Path(destination_fundus_relative).parent)
    existing_project = str(moved_frontmatter.get("project") or "")
    if destination_parent and (not existing_project or not destination_fundus_relative.startswith(f"{existing_project}/")):
        moved_frontmatter.pop("project", None)
        moved_frontmatter["scope"] = "area"
        moved_frontmatter["scope_path"] = destination_parent
        existing_tags = [
            tag
            for tag in list(moved_frontmatter.get("tags") or [])
            if not str(tag).startswith("project/") and not str(tag).startswith("area/")
        ]
        moved_frontmatter["tags"] = normalize_scope_tags(config, "", area_scope(destination_parent), existing_tags)
    atomic_write(destination_path, render_existing_document(moved_frontmatter, moved_doc.body))
    refresh_index_entry(config, source_path)
    refresh_index_entry(config, destination_path)
    return {
        "path": str(destination_path.relative_to(config.vault_path)),
        "original_path": doc.relative_path,
        "title": doc.title,
        "stub_left": leave_stub,
    }


def archive_status(config: Config, project_name: str, scope: Scope | None = None) -> dict[str, Any]:
    active_scope = scope or project_scope(project_name)
    active_dir = fundus_scope_dir(config, active_scope)
    archive_dir = fundus_archive_scope_dir(config, active_scope)
    active_count = len(list(active_dir.rglob("*.md"))) if active_dir.exists() else 0
    archived_count = len(list(archive_dir.rglob("*.md"))) if archive_dir.exists() else 0
    return {
        "scope": active_scope.kind,
        "scope_path": active_scope.path,
        "project": project_name if active_scope.kind == "project" else None,
        "active_documents": active_count,
        "archived_documents": archived_count,
        "archive_path": str(archive_dir.relative_to(config.vault_path)),
    }


def index_status(config: Config) -> dict[str, Any]:
    path = index_path(config)
    data = load_index(config)
    markdown_paths = iter_fundus_markdown_paths(config)
    markdown_count = len(markdown_paths)
    indexed_count = len(data["documents"]) if data else 0
    indexed_mtimes = {doc.get("path"): doc.get("mtime_ns") for doc in data["documents"]} if data else {}
    stale_paths: list[str] = []
    if data:
        for markdown_path in markdown_paths:
            relative_path = str(markdown_path.relative_to(config.vault_path))
            if indexed_mtimes.get(relative_path) != markdown_path.stat().st_mtime_ns:
                stale_paths.append(relative_path)
        markdown_relative_paths = {str(markdown_path.relative_to(config.vault_path)) for markdown_path in markdown_paths}
        for indexed_path in indexed_mtimes:
            if indexed_path not in markdown_relative_paths:
                stale_paths.append(str(indexed_path))
    return {
        "path": str(path.relative_to(config.vault_path)),
        "exists": path.exists(),
        "valid": data is not None,
        "documents": indexed_count,
        "markdown_documents": markdown_count,
        "generated": data.get("generated") if data else None,
        "stale": data is None or indexed_count != markdown_count or bool(stale_paths),
        "stale_paths": stale_paths[:20],
    }


def resolve_corpus_dir(config: Config, corpus_dir: str) -> Path:
    raw = corpus_dir.strip().strip("/")
    if not raw:
        raise FundusError("Corpus directory must not be empty.")
    path = Path(raw)
    if path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise FundusError("Corpus directory must be a safe path relative to the vault root.")
    return ensure_within(config.vault_path, config.vault_path / path)


def config_with_fundus_dir(config: Config, fundus_dir: str) -> Config:
    return Config(
        vault_path=config.vault_path,
        fundus_dir=fundus_dir.strip("/"),
        default_tags=config.default_tags,
        redaction_enabled=config.redaction_enabled,
        redaction_patterns=config.redaction_patterns,
    )


def archive_relative_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    if ARCHIVE_DIRNAME in parts:
        archive_index = parts.index(ARCHIVE_DIRNAME)
        remaining = parts[archive_index + 1 :]
        return remaining or parts[-1:]
    return parts


def migration_destination_relative_path(relative_path: Path, frontmatter: dict[str, Any]) -> tuple[Path, bool, bool]:
    parts = relative_path.parts
    archived = frontmatter_bool(frontmatter.get("archived")) or ARCHIVE_DIRNAME in parts
    if archived:
        return Path(ARCHIVE_DIRNAME, *archive_relative_parts(parts)), True, False
    reserved = relative_path.name in RESERVED_FILENAMES
    return relative_path, False, reserved


def migration_plan(
    config: Config,
    source_dir: str = DEFAULT_LEGACY_SOURCE_DIR,
    destination_dir: str | None = None,
) -> dict[str, Any]:
    source_root = resolve_corpus_dir(config, source_dir)
    target_dir = destination_dir or config.fundus_dir
    destination_root = resolve_corpus_dir(config, target_dir)
    if not source_root.exists():
        raise FundusError(f"Migration source does not exist: {source_root}")

    documents: list[dict[str, Any]] = []
    destination_paths: set[str] = set()
    duplicate_destinations: set[str] = set()
    counts = {
        "markdown": 0,
        "active": 0,
        "archive": 0,
        "reserved": 0,
        "concept": 0,
        "missing_frontmatter": 0,
        "reserved_with_frontmatter": 0,
    }

    for source_path in sorted(source_root.rglob("*.md")):
        relative_path = source_path.relative_to(source_root)
        frontmatter, _ = parse_frontmatter(source_path.read_text())
        target_relative, archived, reserved = migration_destination_relative_path(relative_path, frontmatter)
        destination_path = str((Path(target_dir) / target_relative).as_posix())
        if destination_path in destination_paths:
            duplicate_destinations.add(destination_path)
        destination_paths.add(destination_path)

        counts["markdown"] += 1
        if archived:
            counts["archive"] += 1
        else:
            counts["active"] += 1
        if reserved:
            counts["reserved"] += 1
            if frontmatter:
                counts["reserved_with_frontmatter"] += 1
        elif not archived:
            counts["concept"] += 1
            if not frontmatter:
                counts["missing_frontmatter"] += 1

        documents.append(
            {
                "source": str((Path(source_dir) / relative_path).as_posix()),
                "destination": destination_path,
                "archived": archived,
                "reserved": reserved,
                "has_frontmatter": bool(frontmatter),
            }
        )

    conflicts: list[dict[str, Any]] = []
    if destination_root.exists() and any(destination_root.iterdir()):
        conflicts.append({"path": str(destination_root), "reason": "destination_exists"})
    for destination in sorted(duplicate_destinations):
        conflicts.append({"path": destination, "reason": "duplicate_destination"})

    return {
        "source_dir": source_dir,
        "destination_dir": target_dir,
        "source_path": str(source_root),
        "destination_path": str(destination_root),
        "counts": counts,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
        "documents": documents,
    }


def render_reserved_without_frontmatter(text: str) -> str:
    frontmatter, body = parse_frontmatter(text)
    if frontmatter:
        return body if body.endswith("\n") else f"{body}\n"
    return text


def copy_migrated_document(
    source_path: Path,
    destination_path: Path,
    staging_config: Config,
    archived: bool,
    reserved: bool,
    canonical_destination: str,
) -> None:
    text = source_path.read_text()
    if reserved:
        atomic_write(destination_path, render_reserved_without_frontmatter(text))
        return

    if archived:
        frontmatter, body = parse_frontmatter(text)
        original_path = archive_original_path_for_destination(canonical_destination)
        if frontmatter and original_path:
            frontmatter["original_path"] = original_path
            atomic_write(destination_path, render_frontmatter_body(frontmatter, body))
            return

    atomic_write(destination_path, text)
    if not archived:
        normalize_frontmatter_for_path(
            staging_config,
            destination_path,
            apply=True,
            add_missing=True,
        )


def render_frontmatter_body(frontmatter: dict[str, Any], body: str) -> str:
    return f"{format_frontmatter(frontmatter)}\n\n{body.lstrip()}"


def archive_original_path_for_destination(destination: str) -> str | None:
    parts = Path(destination).parts
    if len(parts) >= 3 and parts[1] == ARCHIVE_DIRNAME:
        return Path(parts[0], *parts[2:]).as_posix()
    return None


def repair_archive_original_paths(config: Config, target_dir: str) -> list[str]:
    repair_config = config_with_fundus_dir(config, target_dir)
    root = fundus_root_dir(repair_config)
    archive_root = root / ARCHIVE_DIRNAME
    if not archive_root.exists():
        return []

    repaired: list[str] = []
    for path in sorted(archive_root.rglob("*.md")):
        frontmatter, body = parse_frontmatter(path.read_text())
        if not frontmatter:
            continue
        relative_to_root = path.relative_to(root).as_posix()
        original_path = archive_original_path_for_destination(f"{target_dir}/{relative_to_root}")
        if not original_path or frontmatter.get("original_path") == original_path:
            continue
        frontmatter["original_path"] = original_path
        atomic_write(path, render_frontmatter_body(frontmatter, body))
        repaired.append(str(path.relative_to(repair_config.vault_path)))
    return repaired


def retire_migration_source(config: Config, source_dir: str, migration_id: str) -> str:
    source_root = resolve_corpus_dir(config, source_dir)
    retired = ensure_within(config.vault_path, config.vault_path / f"{source_dir}.migrated-{migration_id}")
    if retired.exists():
        raise FundusError(f"Retired source path already exists: {retired}")
    source_root.rename(retired)
    return str(retired)


def verify_fundus_corpus(config: Config, destination_dir: str | None = None) -> dict[str, Any]:
    target_dir = destination_dir or config.fundus_dir
    verify_config = config_with_fundus_dir(config, target_dir)
    root = fundus_root_dir(verify_config)
    issues: list[dict[str, Any]] = []
    counts = {
        "markdown": 0,
        "active": 0,
        "archive": 0,
        "reserved": 0,
        "concept": 0,
    }

    if not root.exists():
        return {
            "destination_dir": target_dir,
            "destination_path": str(root),
            "passed": False,
            "counts": counts,
            "issues": [{"path": str(root), "reason": "destination_missing"}],
            "index": index_status(verify_config),
            "smoke_tests": [],
        }

    for path in sorted(root.rglob("*.md")):
        relative_parts = path.relative_to(root).parts
        if BACKUP_DIRNAME in relative_parts:
            continue
        archived = relative_parts and relative_parts[0] == ARCHIVE_DIRNAME
        reserved = not archived and path.name in RESERVED_FILENAMES
        frontmatter, _ = parse_frontmatter(path.read_text())
        relative_path = str(path.relative_to(verify_config.vault_path))

        counts["markdown"] += 1
        counts["archive" if archived else "active"] += 1
        if reserved:
            counts["reserved"] += 1
            if frontmatter:
                issues.append({"path": relative_path, "reason": "reserved_has_frontmatter"})
            continue
        if not archived:
            counts["concept"] += 1
            if not frontmatter:
                issues.append({"path": relative_path, "reason": "concept_missing_frontmatter"})
            elif not str(frontmatter.get("type") or "").strip():
                issues.append({"path": relative_path, "reason": "concept_missing_type"})

    smoke_specs = [
        ("project", "prompting-service", "prompting-service", project_scope("prompting-service"), False),
        ("ticket", "BACKEND-2291", "prompting-service", project_scope("prompting-service"), False),
        ("epic", "AI Agent Templates", "AI Agent Templates", area_scope("Epics/AI Agent Templates"), False),
        ("domain", "Prompt Authoring", "Prompt Authoring", area_scope("Domains/Prompt Authoring"), False),
        ("archive", "archive", "AI Agent Templates", area_scope("Epics/AI Agent Templates"), True),
    ]
    smoke_tests: list[dict[str, Any]] = []
    for name, query, label, scope, include_archived in smoke_specs:
        selected_scope = scope or project_scope(label)
        results = scan_documents(
            verify_config,
            label,
            query,
            limit=3,
            include_archived=include_archived,
            scope=selected_scope,
        )
        smoke_tests.append(
            {
                "name": name,
                "query": query,
                "scope": selected_scope.kind,
                "scope_path": selected_scope.path,
                "include_archived": include_archived,
                "found": bool(results),
                "result_count": len(results),
                "paths": [result.get("path") for result in results],
            }
        )

    return {
        "destination_dir": target_dir,
        "destination_path": str(root),
        "passed": not issues,
        "counts": counts,
        "issues": issues,
        "index": index_status(verify_config),
        "smoke_tests": smoke_tests,
    }


def apply_wiki_to_fundus_migration(
    config: Config,
    source_dir: str = DEFAULT_LEGACY_SOURCE_DIR,
    destination_dir: str | None = None,
    retire_source: str = "rename",
    backup_label: str | None = None,
) -> dict[str, Any]:
    target_dir = destination_dir or config.fundus_dir
    if retire_source not in {"rename", "keep"}:
        raise FundusError("--retire-source must be 'rename' or 'keep'.")
    plan = migration_plan(config, source_dir, target_dir)
    destination_conflicts = [conflict for conflict in plan["conflicts"] if conflict.get("reason") == "destination_exists"]
    other_conflicts = [conflict for conflict in plan["conflicts"] if conflict.get("reason") != "destination_exists"]
    if destination_conflicts and not other_conflicts:
        migration_id = backup_id_for("wiki-to-fundus-resume")
        repaired_archive_original_paths = repair_archive_original_paths(config, target_dir)
        index_payload = rebuild_index(config_with_fundus_dir(config, target_dir))
        final_verification = verify_fundus_corpus(config, target_dir)
        if not final_verification["passed"]:
            raise FundusError(f"Existing destination verification failed: {final_verification['issues']}")
        backup = create_backup_for_root(
            config,
            resolve_corpus_dir(config, source_dir),
            source_dir,
            backup_label or f"pre-{slugify(source_dir)}-to-{slugify(target_dir)}-resume",
        )
        retired_path = None
        if retire_source == "rename":
            retired_path = retire_migration_source(config, source_dir, migration_id)
        return {
            "migration_id": migration_id,
            "source_dir": source_dir,
            "destination_dir": target_dir,
            "resumed_existing_destination": True,
            "backup": {
                "id": backup["id"],
                "backup_path": backup["backup_path"],
                "file_count": backup["file_count"],
                "byte_count": backup["byte_count"],
            },
            "copied_count": 0,
            "copied_documents": [],
            "repaired_archive_original_paths": repaired_archive_original_paths[:50],
            "index": {
                "path": str(index_path(config_with_fundus_dir(config, target_dir)).relative_to(config.vault_path)),
                "documents": len(index_payload["documents"]),
            },
            "verification": final_verification,
            "retire_source": retire_source,
            "retired_source_path": retired_path,
        }
    if plan["conflicts"]:
        raise FundusError(f"Migration has conflicts: {plan['conflicts']}")
    source_root = resolve_corpus_dir(config, source_dir)
    destination_root = resolve_corpus_dir(config, target_dir)
    migration_id = backup_id_for("wiki-to-fundus")
    backup = create_backup_for_root(
        config,
        source_root,
        source_dir,
        backup_label or f"pre-{slugify(source_dir)}-to-{slugify(target_dir)}",
    )
    staging_root = ensure_within(config.vault_path, migration_staging_root_dir(config) / migration_id)
    staging_destination = ensure_within(config.vault_path, staging_root / target_dir)
    if staging_root.exists():
        raise FundusError(f"Migration staging directory already exists: {staging_root}")
    staging_config = config_with_fundus_dir(config, str(staging_destination.relative_to(config.vault_path)))

    copied_documents: list[str] = []
    for document in plan["documents"]:
        source_relative = Path(document["source"]).relative_to(source_dir)
        destination_relative = Path(document["destination"]).relative_to(target_dir)
        source_path = ensure_within(config.vault_path, source_root / source_relative)
        destination_path = ensure_within(config.vault_path, staging_destination / destination_relative)
        copy_migrated_document(
            source_path,
            destination_path,
            staging_config,
            bool(document["archived"]),
            bool(document["reserved"]),
            document["destination"],
        )
        copied_documents.append(str((Path(target_dir) / destination_relative).as_posix()))

    staging_verification = verify_fundus_corpus(config, str(staging_destination.relative_to(config.vault_path)))
    if not staging_verification["passed"]:
        raise FundusError(f"Staged migration verification failed: {staging_verification['issues']}")

    destination_root.parent.mkdir(parents=True, exist_ok=True)
    if destination_root.exists():
        destination_root.rmdir()
    shutil.move(str(staging_destination), str(destination_root))
    cleanup_empty_directories(config_with_fundus_dir(config, str(migration_staging_root_dir(config).relative_to(config.vault_path))), "", global_scope=True)

    repaired_archive_original_paths = repair_archive_original_paths(config, target_dir)
    index_payload = rebuild_index(config_with_fundus_dir(config, target_dir))
    final_verification = verify_fundus_corpus(config, target_dir)
    if not final_verification["passed"]:
        raise FundusError(f"Final migration verification failed: {final_verification['issues']}")

    retired_path = None
    if retire_source == "rename":
        retired_path = retire_migration_source(config, source_dir, migration_id)

    return {
        "migration_id": migration_id,
        "source_dir": source_dir,
        "destination_dir": target_dir,
        "backup": {
            "id": backup["id"],
            "backup_path": backup["backup_path"],
            "file_count": backup["file_count"],
            "byte_count": backup["byte_count"],
        },
        "copied_count": len(copied_documents),
        "copied_documents": copied_documents[:50],
        "repaired_archive_original_paths": repaired_archive_original_paths[:50],
        "index": {
            "path": str(index_path(config_with_fundus_dir(config, target_dir)).relative_to(config.vault_path)),
            "documents": len(index_payload["documents"]),
            "generated": index_payload["generated"],
        },
        "verification": final_verification,
        "retire_source": retire_source,
        "retired_source_path": retired_path,
    }


def doctor_report(config: Config, project_root: Path, project_name: str) -> dict[str, Any]:
    return doctor_report_for_scope(config, project_root, project_name, project_scope(project_name))


def doctor_report_for_scope(config: Config, project_root: Path, project_name: str, scope: Scope) -> dict[str, Any]:
    root = fundus_root_dir(config)
    scope_dir = fundus_scope_dir(config, scope)
    config_sources = [str(path) for path in project_config_paths(project_root) if path.exists()]
    if SKILL_CONFIG_PATH.exists():
        config_sources.append(str(SKILL_CONFIG_PATH))
    if os.getenv("OBSIDIAN_VAULT_PATH"):
        config_sources.append("OBSIDIAN_VAULT_PATH")

    return {
        "project_root": str(project_root),
        "project": project_name,
        "scope": scope.kind,
        "scope_path": scope.path,
        "config_sources": config_sources,
        "vault_path": str(config.vault_path),
        "fundus_dir": config.fundus_dir,
        "fundus_root": str(root),
        "scope_fundus_dir": str(scope_dir),
        "scope_fundus_exists": scope_dir.exists(),
        "index": index_status(config),
        "writes_possible": root.exists() or os.access(config.vault_path, os.W_OK),
    }


def add_area_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--area", default=argparse.SUPPRESS, help="Target an explicit Fundus area path under the Fundus root.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage persistent Fundus documents for the active project.")
    parser.add_argument("--project", help="Override the auto-detected project name.")
    parser.add_argument("--area", help="Target an explicit Fundus area path under the Fundus root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="List Fundus documents for the active project.")
    add_area_argument(scan_parser)
    scan_parser.add_argument("--query", help="Optional keywords to filter by indexed title, tags, filename, headings, and excerpt.")
    scan_parser.add_argument("--limit", type=int, default=MAX_SCAN_RESULTS, help=f"Maximum results to return. Default: {MAX_SCAN_RESULTS}.")
    scan_parser.add_argument("--include-snippet", action="store_true", help="Include short indexed snippets in scan results.")
    scan_parser.add_argument("--include-archived", action="store_true", help="Include archived documents in scan results.")

    read_parser = subparsers.add_parser("read", help="Read a Fundus document.")
    read_parser.add_argument("--path", required=True, help="Fundus document path relative to the vault root.")

    create_parser = subparsers.add_parser("create", help="Create a new Fundus document.")
    add_area_argument(create_parser)
    create_parser.add_argument("--title", required=True, help="Document title.")
    create_parser.add_argument("--type", dest="doc_type", help="OKF-compatible document type. Default: Note.")
    create_parser.add_argument("--description", help="Short document description. Defaults to the title.")
    create_parser.add_argument("--id", dest="document_id", help="Stable document id. Defaults to a scope/title-derived id.")
    create_parser.add_argument("--alias", action="append", dest="aliases", help="Alias or ticket id to store in frontmatter. May be repeated.")
    create_parser.add_argument("--resource", help="External source URL or resource identifier.")
    create_parser.add_argument("--status", help="Optional note status such as active or stale.")
    create_parser.add_argument("--owner", help="Optional note owner.")
    create_parser.add_argument("--last-verified", help="Date or timestamp for the last source verification.")
    create_parser.add_argument("--content", help="Inline markdown content.")
    create_parser.add_argument("--content-file", help="Path to a markdown file containing the body content.")
    create_parser.add_argument("--tag", action="append", dest="tags", help="Additional tag to add.")

    update_parser = subparsers.add_parser("update", help="Append to, replace a section in, or rewrite a document.")
    add_area_argument(update_parser)
    update_parser.add_argument("--path", required=True, help="Fundus document path relative to the vault root.")
    update_parser.add_argument("--mode", required=True, choices=["append", "replace", "rewrite"], help="Update mode.")
    update_parser.add_argument("--section", help="Section heading to replace when using replace mode.")
    update_parser.add_argument("--content", help="Inline markdown content.")
    update_parser.add_argument("--content-file", help="Path to a markdown file containing the new content.")

    frontmatter_parser = subparsers.add_parser("add-frontmatter", help="Add generated frontmatter to an existing plain Markdown note.")
    add_area_argument(frontmatter_parser)
    frontmatter_parser.add_argument("--path", required=True, help="Fundus document path relative to the vault root.")
    frontmatter_parser.add_argument("--title", help="Title to store in frontmatter. Defaults to the filename title.")
    frontmatter_parser.add_argument("--type", dest="doc_type", help="OKF-compatible document type. Default: Note.")
    frontmatter_parser.add_argument("--description", help="Short document description. Defaults to the title.")
    frontmatter_parser.add_argument("--id", dest="document_id", help="Stable document id. Defaults to a scope/title-derived id.")
    frontmatter_parser.add_argument("--alias", action="append", dest="aliases", help="Alias or ticket id to store in frontmatter. May be repeated.")
    frontmatter_parser.add_argument("--resource", help="External source URL or resource identifier.")
    frontmatter_parser.add_argument("--status", help="Optional note status such as active or stale.")
    frontmatter_parser.add_argument("--owner", help="Optional note owner.")
    frontmatter_parser.add_argument("--last-verified", help="Date or timestamp for the last source verification.")
    frontmatter_parser.add_argument("--tag", action="append", dest="tags", help="Additional tag to add.")

    normalize_frontmatter_parser = subparsers.add_parser(
        "normalize-frontmatter",
        help="Dry-run or apply OKF-compatible frontmatter normalization without changing note bodies.",
    )
    add_area_argument(normalize_frontmatter_parser)
    normalize_frontmatter_parser.add_argument("--path", help="One Fundus document path relative to the vault root.")
    normalize_frontmatter_parser.add_argument("--global", dest="global_scope", action="store_true", help="Normalize all active Fundus documents.")
    normalize_frontmatter_parser.add_argument("--include-archived", action="store_true", help="Include archived documents when normalizing a scope or globally.")
    normalize_frontmatter_parser.add_argument("--add-missing", action="store_true", help="Add generated OKF frontmatter to Markdown documents that have none.")
    normalize_frontmatter_parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, the command only reports planned changes.")
    normalize_frontmatter_parser.add_argument("--limit", type=int, help="Limit the number of documents processed for scoped or global dry-runs.")

    move_parser = subparsers.add_parser("move", help="Move one Fundus note to another active Fundus path for later curation workflows.")
    move_parser.add_argument("--from", dest="source", required=True, help="Source Fundus document path relative to the vault root.")
    move_parser.add_argument("--to", dest="destination", required=True, help="Destination Fundus document path relative to the vault root.")
    move_parser.add_argument("--leave-stub", action="store_true", help="Leave a short moved-note stub at the old path.")

    backup_parser = subparsers.add_parser("backup", help="Create and inspect Fundus backups.")
    backup_subparsers = backup_parser.add_subparsers(dest="backup_command", required=True)
    backup_create_parser = backup_subparsers.add_parser("create", help="Create a backup of the configured Fundus directory.")
    backup_create_parser.add_argument("--label", help="Human label included in the backup id and manifest.")
    backup_subparsers.add_parser("list", help="List available Fundus backups.")
    backup_inspect_parser = backup_subparsers.add_parser("inspect", help="Inspect one backup manifest.")
    backup_inspect_parser.add_argument("--id", required=True, help="Backup id returned by backup create or backup list.")

    area_parser = subparsers.add_parser("area", help="Initialize explicit cross-repository Fundus areas.")
    area_subparsers = area_parser.add_subparsers(dest="area_command", required=True)
    area_init_parser = area_subparsers.add_parser("init", help="Create a safe area skeleton without overwriting existing files.")
    area_init_parser.add_argument("--area", required=True, help="Area path under the Fundus root.")
    area_init_parser.add_argument("--type", dest="area_type", default="Area", help="Overview document type. Default: Area.")
    area_init_parser.add_argument("--title", required=True, help="Human area title.")

    index_parser = subparsers.add_parser("index", help="Manage the lightweight Fundus search index.")
    index_subparsers = index_parser.add_subparsers(dest="index_command", required=True)
    index_subparsers.add_parser("rebuild", help="Rebuild the Fundus search index from Markdown documents.")
    index_subparsers.add_parser("status", help="Report whether the Fundus search index exists and is fresh.")

    migrate_parser = subparsers.add_parser("migrate", help="Run one-time Fundus corpus migrations.")
    migrate_subparsers = migrate_parser.add_subparsers(dest="migration_command", required=True)
    wiki_migration_parser = migrate_subparsers.add_parser("wiki-to-fundus", help="Migrate the legacy Wiki corpus into canonical Fundus.")
    wiki_migration_parser.add_argument("--source-dir", default=DEFAULT_LEGACY_SOURCE_DIR, help=f"Legacy source directory under the vault. Default: {DEFAULT_LEGACY_SOURCE_DIR}.")
    wiki_migration_parser.add_argument("--destination-dir", help="Destination corpus directory under the vault. Defaults to configured fundus_dir.")
    wiki_migration_parser.add_argument("--dry-run", action="store_true", help="Report the migration plan without writing.")
    wiki_migration_parser.add_argument("--apply", action="store_true", help="Apply the migration through a staged destination.")
    wiki_migration_parser.add_argument("--verify", action="store_true", help="Verify the destination corpus structure.")
    wiki_migration_parser.add_argument("--retire-source", choices=["rename", "keep"], default="rename", help="What to do with the legacy source after successful apply. Default: rename.")
    wiki_migration_parser.add_argument("--backup-label", help="Backup label to use before applying the migration.")

    archive_parser = subparsers.add_parser("archive", help="Archive, restore, and inspect old Fundus notes.")
    archive_subparsers = archive_parser.add_subparsers(dest="archive_command", required=True)
    archive_candidates_parser = archive_subparsers.add_parser("candidates", help="List explicit archive candidates without changing files.")
    add_area_argument(archive_candidates_parser)
    archive_candidates_parser.add_argument("--older-than-days", type=int, default=90, help="Minimum note age by updated timestamp. Default: 90.")
    archive_candidates_parser.add_argument("--limit", type=int, default=MAX_SCAN_RESULTS, help=f"Maximum candidates to return. Default: {MAX_SCAN_RESULTS}.")
    archive_candidates_parser.add_argument("--force", action="store_true", help="Include durable notes such as project overviews, architecture notes, runbooks, and glossary entries.")
    archive_candidates_parser.add_argument("--global", dest="global_scope", action="store_true", help="List candidates across all active project Fundus folders.")
    archive_apply_parser = archive_subparsers.add_parser("apply", help="Archive one explicitly selected Fundus note.")
    archive_apply_parser.add_argument("--path", required=True, help="Active Fundus document path relative to the vault root.")
    archive_apply_parser.add_argument("--reason", help="Reason stored in archive frontmatter.")
    archive_restore_parser = archive_subparsers.add_parser("restore", help="Restore one archived Fundus note to its original path.")
    archive_restore_parser.add_argument("--path", required=True, help="Archived Fundus document path relative to the vault root.")
    archive_cleanup_parser = archive_subparsers.add_parser("cleanup", help="Remove empty active and archived Fundus folders.")
    add_area_argument(archive_cleanup_parser)
    archive_cleanup_parser.add_argument("--global", dest="global_scope", action="store_true", help="Remove empty folders across all Fundus project folders.")
    archive_status_parser = archive_subparsers.add_parser("status", help="Show active and archived note counts for the project or area.")
    add_area_argument(archive_status_parser)

    doctor_parser = subparsers.add_parser("doctor", help="Show resolved project, configuration, vault, and index diagnostics.")
    add_area_argument(doctor_parser)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        project_root = discover_project_root()
        config = resolve_config(project_root)
        project_name = args.project or detect_project_name(project_root)
        area_arg = getattr(args, "area", None)
        if args.project and area_arg:
            raise FundusError("--project and --area cannot be used together.")
        scope = resolve_scope(project_name, area_arg)

        if args.command == "scan":
            payload = {
                "project": project_name,
                "scope": scope.kind,
                "scope_path": scope.path,
                "documents": scan_documents(
                    config,
                    project_name,
                    args.query,
                    args.limit,
                    args.include_snippet,
                    args.include_archived,
                    scope,
                ),
            }
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "read":
            print(read_document(config, args.path))
            return 0

        if args.command == "create":
            content = read_content_arg(args.content, args.content_file)
            payload = create_document(
                config,
                project_name,
                args.title,
                content,
                args.tags,
                scope,
                args.doc_type,
                args.description,
                args.document_id,
                args.aliases,
                args.resource,
                args.status,
                args.owner,
                args.last_verified,
            )
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "update":
            content = read_content_arg(args.content, args.content_file)
            payload = update_document(config, project_name, args.path, args.mode, content, args.section, scope)
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "add-frontmatter":
            payload = add_frontmatter_to_document(
                config,
                project_name,
                args.path,
                args.title,
                args.tags,
                scope,
                args.doc_type,
                args.description,
                args.document_id,
                args.aliases,
                args.resource,
                args.status,
                args.owner,
                args.last_verified,
            )
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "normalize-frontmatter":
            payload = normalize_frontmatter_paths(
                config,
                project_name,
                scope,
                args.path,
                args.global_scope,
                args.include_archived,
                args.apply,
                args.add_missing,
                args.limit,
            )
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "move":
            payload = move_document(config, args.source, args.destination, args.leave_stub)
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "backup":
            if args.backup_command == "create":
                payload = create_backup(config, args.label)
                print(
                    json.dumps(
                        {
                            "id": payload["id"],
                            "label": payload["label"],
                            "created": payload["created"],
                            "backup_path": payload["backup_path"],
                            "file_count": payload["file_count"],
                            "byte_count": payload["byte_count"],
                        },
                        indent=2,
                    )
                )
                return 0
            if args.backup_command == "list":
                print(json.dumps({"backups": list_backups(config)}, indent=2))
                return 0
            if args.backup_command == "inspect":
                print(json.dumps(inspect_backup(config, args.id), indent=2))
                return 0

        if args.command == "area":
            if args.area_command == "init":
                payload = area_init(config, project_name, args.area, args.area_type, args.title)
                print(json.dumps(payload, indent=2))
                return 0

        if args.command == "index":
            if args.index_command == "rebuild":
                payload = rebuild_index(config)
                print(
                    json.dumps(
                        {
                            "path": str(index_path(config).relative_to(config.vault_path)),
                            "documents": len(payload["documents"]),
                            "generated": payload["generated"],
                        },
                        indent=2,
                    )
                )
                return 0
            if args.index_command == "status":
                print(json.dumps(index_status(config), indent=2))
                return 0

        if args.command == "migrate":
            if args.migration_command == "wiki-to-fundus":
                if sum(bool(flag) for flag in [args.dry_run, args.apply, args.verify]) != 1:
                    raise FundusError("Choose exactly one of --dry-run, --apply, or --verify.")
                destination_dir = args.destination_dir or config.fundus_dir
                if args.dry_run:
                    print(json.dumps(migration_plan(config, args.source_dir, destination_dir), indent=2))
                    return 0
                if args.verify:
                    print(json.dumps(verify_fundus_corpus(config, destination_dir), indent=2))
                    return 0
                if args.apply:
                    print(
                        json.dumps(
                            apply_wiki_to_fundus_migration(
                                config,
                                args.source_dir,
                                destination_dir,
                                args.retire_source,
                                args.backup_label,
                            ),
                            indent=2,
                        )
                    )
                    return 0

        if args.command == "archive":
            if args.archive_command == "candidates":
                candidates = (
                    archive_candidates_global(config, args.older_than_days, args.limit, args.force)
                    if args.global_scope
                    else archive_candidates(config, project_name, args.older_than_days, args.limit, args.force, scope)
                )
                payload = {
                    "scope": "global" if args.global_scope else scope.kind,
                    "scope_path": None if args.global_scope else scope.path,
                    "project": None if args.global_scope or scope.kind != "project" else project_name,
                    "candidates": candidates,
                }
                print(json.dumps(payload, indent=2))
                return 0
            if args.archive_command == "apply":
                print(json.dumps(archive_document(config, args.path, args.reason), indent=2))
                return 0
            if args.archive_command == "restore":
                print(json.dumps(restore_document(config, args.path), indent=2))
                return 0
            if args.archive_command == "cleanup":
                print(json.dumps(cleanup_empty_directories(config, project_name, args.global_scope, scope), indent=2))
                return 0
            if args.archive_command == "status":
                print(json.dumps(archive_status(config, project_name, scope), indent=2))
                return 0

        if args.command == "doctor":
            print(json.dumps(doctor_report_for_scope(config, project_root, project_name, scope), indent=2))
            return 0

        raise FundusError(f"Unknown command: {args.command}")
    except FundusError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
