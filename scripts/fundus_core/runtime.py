#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import difflib
import functools
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parents[2]
VENDOR_DIR = SKILL_DIR / "vendor"
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

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
INDEX_VERSION = 4
MAX_INDEX_EXCERPT_CHARS = 600
MAX_SCAN_RESULTS = 20
MAX_PROPOSAL_DIFF_CHARS = 12000
ARCHIVE_DIRNAME = "_archive"
BACKUP_DIRNAME = ".fundus-backups"
JOURNAL_DIRNAME = ".fundus-journal"
LOCK_FILENAME = ".fundus.lock"
LOCK_DIRNAME = ".fundus-locks"
DEFAULT_LOCK_TIMEOUT_SECONDS = 5.0
DEFAULT_STALE_LOCK_SECONDS = 30.0
BACKUP_MANIFEST_FILENAME = "manifest.json"
MIGRATION_STAGING_DIRNAME = ".fundus-migration-staging"
DEFAULT_LEGACY_SOURCE_DIR = "Wiki"
RESERVED_FILENAMES = {"index.md", "log.md"}
RESERVED_FUNDUS_DIRNAMES = {ARCHIVE_DIRNAME, BACKUP_DIRNAME, JOURNAL_DIRNAME}
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
    def __init__(self, message: str, code: str = "FUNDUS_ERROR") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Config:
    vault_path: Path
    fundus_dir: str
    default_tags: list[str]
    redaction_enabled: bool
    redaction_patterns: list[str]
    provenance: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Scope:
    kind: str
    path: str
    display_name: str


@dataclass(frozen=True)
class ScopeClassification:
    scope: Scope
    project: str | None
    active_relative_path: str
    physical_parent: str
    scope_relative_path: str


@dataclass(frozen=True)
class IndexLoadResult:
    data: dict[str, Any] | None
    state: str
    error: str | None = None


@dataclass(frozen=True)
class FundusRoot:
    path: Path

    @classmethod
    def from_config(cls, config: Config) -> FundusRoot:
        return cls(ensure_within(config.vault_path, config.vault_path / config.fundus_dir))


@dataclass(frozen=True)
class ActiveNotePath:
    path: Path

    @classmethod
    def resolve(cls, config: Config, value: str | Path, *, allow_reserved: bool = False) -> ActiveNotePath:
        path, relative_parts = resolve_path_inside_fundus(config, value)
        validate_markdown_note_path(path, relative_parts, allow_reserved=allow_reserved)
        if relative_parts and relative_parts[0] == ARCHIVE_DIRNAME:
            raise FundusError("Expected an active Fundus note path, not an archived path.", "NOTE_PATH_INVALID")
        return cls(path)


@dataclass(frozen=True)
class ArchivedNotePath:
    path: Path

    @classmethod
    def resolve(cls, config: Config, value: str | Path) -> ArchivedNotePath:
        path, relative_parts = resolve_path_inside_fundus(config, value)
        validate_markdown_note_path(path, relative_parts, allow_reserved=False)
        if not relative_parts or relative_parts[0] != ARCHIVE_DIRNAME:
            raise FundusError("Expected a Fundus archive note path.", "NOTE_PATH_INVALID")
        return cls(path)


@dataclass(frozen=True)
class ReservedFilePath:
    path: Path

    @classmethod
    def resolve(cls, config: Config, value: str | Path) -> ReservedFilePath:
        path, relative_parts = resolve_path_inside_fundus(config, value)
        validate_markdown_note_path(path, relative_parts, allow_reserved=True)
        if relative_parts and relative_parts[0] == ARCHIVE_DIRNAME:
            raise FundusError("Reserved files must be active Fundus paths.", "NOTE_PATH_INVALID")
        if path.name not in RESERVED_FILENAMES:
            raise FundusError("Expected index.md or log.md.", "NOTE_PATH_INVALID")
        return cls(path)


@dataclass(frozen=True)
class BackupPath:
    path: Path

    @classmethod
    def resolve(cls, config: Config, value: str | Path) -> BackupPath:
        root = ensure_within(config.vault_path, config.vault_path / BACKUP_DIRNAME)
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        return cls(ensure_within(root, candidate, code="BACKUP_PATH_INVALID"))


@dataclass(frozen=True)
class MigrationSourcePath:
    path: Path

    @classmethod
    def resolve(cls, config: Config, value: str | Path) -> MigrationSourcePath:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = config.vault_path / candidate
        return cls(ensure_within(config.vault_path, candidate, code="MIGRATION_PATH_INVALID"))


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


def user_config_path() -> Path:
    config_home = os.getenv("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path(os.path.expanduser("~/.config"))
    return base / "fundus" / "config.json"


def resolve_config(project_root: Path, explicit_overrides: dict[str, Any] | None = None) -> Config:
    merged: dict[str, Any] = dict(DEFAULT_CONFIG)
    provenance = {
        "fundus_dir": "built-in default",
        "default_tags": "built-in default",
        "redaction": "built-in default",
    }

    def merge_source(data: dict[str, Any], source: str) -> None:
        nonlocal merged
        if not data:
            return
        merged = deep_merge(merged, data)
        for key in data:
            provenance[key] = source

    merge_source(load_json(SKILL_CONFIG_PATH), f"packaged config: {SKILL_CONFIG_PATH}")
    user_path = user_config_path()
    merge_source(load_json(user_path), f"user config: {user_path}")
    for config_path in reversed(project_config_paths(project_root)):
        merge_source(load_json(config_path), f"project config: {config_path}")

    explicit_config_path = os.getenv("FUNDUS_CONFIG_PATH")
    if explicit_config_path:
        custom_path = Path(explicit_config_path).expanduser().resolve()
        if not custom_path.is_file():
            raise FundusError(f"FUNDUS_CONFIG_PATH does not exist: {custom_path}", "CONFIG_FILE_NOT_FOUND")
        merge_source(load_json(custom_path), f"FUNDUS_CONFIG_PATH: {custom_path}")

    env_vault = os.getenv("OBSIDIAN_VAULT_PATH")
    if env_vault:
        merge_source({"vault_path": env_vault}, "OBSIDIAN_VAULT_PATH")
    merge_source(explicit_overrides or {}, "explicit operation argument")

    vault_path = merged.get("vault_path")
    if not vault_path:
        raise FundusError(
            "Missing vault_path. Set an explicit --vault-path, OBSIDIAN_VAULT_PATH, FUNDUS_CONFIG_PATH, "
            "project .codex/fundus.json, or user ~/.config/fundus/config.json.",
            "CONFIG_MISSING",
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
        provenance={
            "vault_path": provenance.get("vault_path", "missing"),
            "fundus_dir": provenance.get("fundus_dir", "built-in default"),
            "default_tags": provenance.get("default_tags", "built-in default"),
            "redaction": provenance.get("redaction", "built-in default"),
        },
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


def ensure_within(root: Path, target: Path, *, code: str = "PATH_OUTSIDE_FUNDUS") -> Path:
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise FundusError(f"Resolved path escapes the allowed root: {target}", code) from exc
    return target_resolved


def normalize_project_name(project_name: str) -> str:
    normalized = project_name.strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or Path(normalized).is_absolute()
        or "/" in normalized
        or "\\" in normalized
        or "\x00" in normalized
        or normalized in RESERVED_FUNDUS_DIRNAMES
        or normalized in AREA_ROOT_DIRNAMES
    ):
        raise FundusError("Project name must be one safe, non-reserved path segment.", "PROJECT_NAME_INVALID")
    return normalized


def fundus_project_dir(config: Config, project_name: str) -> Path:
    project_dir = fundus_root_dir(config) / normalize_project_name(project_name)
    return ensure_within(fundus_root_dir(config), project_dir)


def normalize_area_path(area: str) -> str:
    original = area.strip()
    if Path(original).is_absolute() or "\\" in original or "\x00" in original:
        raise FundusError("--area must be a safe path relative to the Fundus root.", "AREA_PATH_INVALID")
    raw = original.strip("/")
    if not raw:
        raise FundusError("--area must not be empty.", "AREA_PATH_INVALID")
    parts = [part for part in raw.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise FundusError("--area must not contain '.' or '..' path segments.", "AREA_PATH_INVALID")
    if parts[0] in RESERVED_FUNDUS_DIRNAMES:
        raise FundusError(f"--area must not target reserved Fundus directory: {parts[0]}", "AREA_PATH_INVALID")
    if parts[0] not in AREA_ROOT_DIRNAMES or len(parts) != 2:
        allowed = ", ".join(sorted(AREA_ROOT_DIRNAMES))
        raise FundusError(
            f"--area must contain exactly an allowed area root and one logical name: {allowed}",
            "AREA_PATH_INVALID",
        )
    return "/".join(parts)


def project_scope(project_name: str) -> Scope:
    normalized = normalize_project_name(project_name)
    return Scope(kind="project", path=normalized, display_name=normalized)


def area_scope(area: str) -> Scope:
    normalized = normalize_area_path(area)
    return Scope(kind="area", path=normalized, display_name=normalized)


def resolve_scope(project_name: str, area: str | None = None) -> Scope:
    if area:
        return area_scope(area)
    return project_scope(project_name)


def fundus_scope_dir(config: Config, scope: Scope) -> Path:
    return ensure_within(fundus_root_dir(config), fundus_root_dir(config) / scope.path)


def fundus_archive_dir(config: Config) -> Path:
    return ensure_within(fundus_root_dir(config), fundus_root_dir(config) / ARCHIVE_DIRNAME)


def fundus_archive_project_dir(config: Config, project_name: str) -> Path:
    return ensure_within(fundus_archive_dir(config), fundus_archive_dir(config) / normalize_project_name(project_name))


def fundus_archive_scope_dir(config: Config, scope: Scope) -> Path:
    return ensure_within(fundus_archive_dir(config), fundus_archive_dir(config) / scope.path)


def fundus_root_dir(config: Config) -> Path:
    return FundusRoot.from_config(config).path


def fundus_relative_path(config: Config, path: Path) -> str:
    return str(ensure_within(fundus_root_dir(config), path).relative_to(fundus_root_dir(config)))


def fundus_project_names(config: Config) -> list[str]:
    root = fundus_root_dir(config)
    if not root.exists():
        return []
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir()
        and path.name not in RESERVED_FUNDUS_DIRNAMES
        and path.name not in AREA_ROOT_DIRNAMES
    )


def index_path(config: Config) -> Path:
    return ensure_within(fundus_root_dir(config), fundus_root_dir(config) / INDEX_FILENAME)


def backup_root_dir(config: Config) -> Path:
    return ensure_within(config.vault_path, config.vault_path / BACKUP_DIRNAME)


def migration_staging_root_dir(config: Config) -> Path:
    return ensure_within(config.vault_path, config.vault_path / MIGRATION_STAGING_DIRNAME)


FRONTMATTER_LIST_FIELDS = {
    "aliases",
    "projects",
    "repos",
    "supersedes",
    "tags",
    "verified_against",
}
FRONTMATTER_TIMESTAMP_FIELDS = {"archived_at", "created", "last_verified", "timestamp", "updated"}
FRONTMATTER_ORDER = [
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
        "verified_against",
        "source_fingerprint",
        "verification_status",
        "stale_reason",
        "archived",
        "archived_at",
        "archived_reason",
        "original_path",
        "moved_from",
        "moved_to",
        "redirect_to",
        "supersedes",
        "tags",
]


def frontmatter_yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.allow_duplicate_keys = False
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


def normalize_frontmatter_value(key: str, value: Any) -> Any:
    if key in FRONTMATTER_LIST_FIELDS and not isinstance(value, list):
        if value is None:
            return []
        if isinstance(value, (str, int, float, bool, date, datetime)):
            value = [value]
        else:
            raise FundusError(f"Frontmatter field '{key}' must be a scalar or list of scalars.", "FRONTMATTER_INVALID")

    if isinstance(value, list):
        normalized_items: list[Any] = []
        for item in value:
            if isinstance(item, (dict, list, tuple, set)) or not isinstance(item, (str, int, float, bool, date, datetime, type(None))):
                raise FundusError(f"Frontmatter field '{key}' contains an unsupported nested value.", "FRONTMATTER_INVALID")
            normalized_items.append(item.isoformat() if isinstance(item, (date, datetime)) else item)
        return normalized_items
    if isinstance(value, dict) or not isinstance(value, (str, int, float, bool, date, datetime, type(None))):
        raise FundusError(f"Frontmatter field '{key}' contains an unsupported value.", "FRONTMATTER_INVALID")
    if key in FRONTMATTER_TIMESTAMP_FIELDS and isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    opening = re.match(r"\A(?P<bom>\ufeff?)---[ \t]*(?P<newline>\r\n|\n)", text)
    if opening is None:
        return {}, text

    newline = opening.group("newline")
    remainder = text[opening.end() :]
    closing = re.search(r"(?m)^---[ \t]*(?:\r\n|\n|$)", remainder)
    if closing is None:
        raise FundusError("Frontmatter is missing its closing delimiter.", "FRONTMATTER_INVALID")
    raw_frontmatter = remainder[: closing.start()]
    body = remainder[closing.end() :]

    try:
        loaded = frontmatter_yaml().load(raw_frontmatter) if raw_frontmatter.strip() else CommentedMap()
    except (YAMLError, ValueError, TypeError) as exc:
        raise FundusError(f"Invalid YAML frontmatter: {exc}", "FRONTMATTER_INVALID") from exc
    if loaded is None:
        loaded = CommentedMap()
    if not isinstance(loaded, CommentedMap):
        raise FundusError("Frontmatter must be a YAML mapping.", "FRONTMATTER_INVALID")
    for key in list(loaded):
        if not isinstance(key, str) or not key.strip():
            raise FundusError("Frontmatter keys must be non-empty strings.", "FRONTMATTER_INVALID")
        loaded[key] = normalize_frontmatter_value(key, loaded[key])
    loaded._fundus_newline = newline
    loaded._fundus_bom = bool(opening.group("bom"))
    return loaded, body


def format_frontmatter(data: dict[str, Any]) -> str:
    if isinstance(data, CommentedMap):
        rendered_data = data
    else:
        rendered_data = CommentedMap()
        for key in FRONTMATTER_ORDER:
            if key in data:
                rendered_data[key] = data[key]
        for key, value in data.items():
            if key not in rendered_data:
                rendered_data[key] = value
    for key in list(rendered_data):
        rendered_data[key] = normalize_frontmatter_value(key, rendered_data[key])

    newline = getattr(data, "_fundus_newline", "\n")
    bom = "\ufeff" if getattr(data, "_fundus_bom", False) else ""
    stream = io.StringIO()
    if rendered_data:
        frontmatter_yaml().dump(rendered_data, stream)
        payload = stream.getvalue().replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
        if newline != "\n":
            payload = payload.replace("\n", newline)
        return f"{bom}---{newline}{payload}{newline}---"
    return f"{bom}---{newline}---"


def frontmatter_newline(data: dict[str, Any]) -> str:
    return str(getattr(data, "_fundus_newline", "\n"))


def normalize_line_endings(text: str, newline: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized if newline == "\n" else normalized.replace("\n", newline)


def clone_frontmatter(data: dict[str, Any]) -> dict[str, Any]:
    cloned = copy.deepcopy(data)
    for attribute in ("_fundus_newline", "_fundus_bom"):
        if hasattr(data, attribute):
            setattr(cloned, attribute, getattr(data, attribute))
    return cloned


def read_note_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FundusError(f"Fundus note is not valid UTF-8: {path}", "FRONTMATTER_INVALID") from exc


def read_content_arg(content: str | None, content_file: str | None) -> str:
    if bool(content) == bool(content_file):
        raise FundusError("Provide exactly one of --content or --content-file.")
    if content_file:
        path = Path(content_file).expanduser()
        return path.read_text()
    return content or ""


def read_json_object_file(path_arg: str) -> dict[str, Any]:
    path = Path(path_arg).expanduser()
    value = load_json(path)
    if not isinstance(value, dict):
        raise FundusError(f"Expected a JSON object in {path}.", "INVALID_ARGUMENT")
    return value


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
    atomic_write_bytes(path, content.encode("utf-8"))


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_revision(path: Path) -> str:
    return f"sha256:{file_sha256(path)}"


def assert_expected_revision(path: Path, expected_revision: str | None) -> str:
    actual_revision = path_revision(path)
    if expected_revision is not None and expected_revision != actual_revision:
        raise FundusError(
            f"Revision conflict for {path.name}: expected {expected_revision}, found {actual_revision}.",
            "REVISION_CONFLICT",
        )
    return actual_revision


def lock_path(config: Config) -> Path:
    lock_root = ensure_within(config.vault_path, config.vault_path / LOCK_DIRNAME)
    identity = hashlib.sha256(config.fundus_dir.encode("utf-8")).hexdigest()[:12]
    lock_name = slugify(config.fundus_dir.replace("/", "-"))
    return ensure_within(lock_root, lock_root / f"{lock_name}-{identity}.lock")


def journal_root_dir(config: Config) -> Path:
    return ensure_within(fundus_root_dir(config), fundus_root_dir(config) / JOURNAL_DIRNAME)


def process_is_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock_metadata(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


_LOCK_LOCAL = threading.local()


class CorpusMutationLock:
    def __init__(
        self,
        config: Config,
        timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
        stale_after_seconds: float = DEFAULT_STALE_LOCK_SECONDS,
    ) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.stale_after_seconds = stale_after_seconds
        self.path = lock_path(config)
        self.token = uuid.uuid4().hex
        self.reentrant = False

    def __enter__(self) -> CorpusMutationLock:
        held = getattr(_LOCK_LOCAL, "held", {})
        key = str(self.path)
        if key in held:
            token, count = held[key]
            held[key] = (token, count + 1)
            _LOCK_LOCAL.held = held
            self.token = token
            self.reentrant = True
            return self

        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_seconds
        payload = {
            "token": self.token,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "created": now_iso(),
            "created_epoch": time.time(),
        }
        encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        while True:
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                break
            except FileExistsError:
                metadata = read_lock_metadata(self.path)
                try:
                    age_seconds = max(0.0, time.time() - float(metadata.get("created_epoch") or self.path.stat().st_mtime))
                except FileNotFoundError:
                    continue
                owner_alive = process_is_alive(metadata.get("pid") if isinstance(metadata.get("pid"), int) else None)
                same_host = not metadata.get("hostname") or metadata.get("hostname") == socket.gethostname()
                if age_seconds >= self.stale_after_seconds and same_host and not owner_alive:
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise FundusError(
                        f"Timed out waiting for the Fundus mutation lock after {self.timeout_seconds:.3f}s.",
                        "LOCK_TIMEOUT",
                    )
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

        held[key] = (self.token, 1)
        _LOCK_LOCAL.held = held
        try:
            recover_pending_mutations(self.config)
        except Exception:
            self._release_final()
            held.pop(key, None)
            _LOCK_LOCAL.held = held
            raise
        return self

    def _release_final(self) -> None:
        metadata = read_lock_metadata(self.path)
        if metadata.get("token") == self.token:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        held = getattr(_LOCK_LOCAL, "held", {})
        key = str(self.path)
        token, count = held.get(key, (self.token, 1))
        if count > 1:
            held[key] = (token, count - 1)
            _LOCK_LOCAL.held = held
            return
        held.pop(key, None)
        _LOCK_LOCAL.held = held
        self._release_final()


def mutation_lock_status(config: Config) -> dict[str, Any]:
    path = lock_path(config)
    if not path.exists():
        return {"path": str(path), "locked": False}
    metadata = read_lock_metadata(path)
    try:
        age_seconds = max(0.0, time.time() - float(metadata.get("created_epoch") or path.stat().st_mtime))
    except FileNotFoundError:
        return {"path": str(path), "locked": False}
    pid = metadata.get("pid") if isinstance(metadata.get("pid"), int) else None
    return {
        "path": str(path),
        "locked": True,
        "pid": pid,
        "hostname": metadata.get("hostname"),
        "created": metadata.get("created"),
        "age_seconds": round(age_seconds, 3),
        "owner_alive": process_is_alive(pid),
    }


def serialized_mutation(function: Any) -> Any:
    @functools.wraps(function)
    def wrapper(config: Config, *args: Any, **kwargs: Any) -> Any:
        with CorpusMutationLock(config):
            return function(config, *args, **kwargs)

    return wrapper


def serialized_mutation_when(predicate: Any) -> Any:
    def decorator(function: Any) -> Any:
        @functools.wraps(function)
        def wrapper(config: Config, *args: Any, **kwargs: Any) -> Any:
            if not predicate(config, *args, **kwargs):
                return function(config, *args, **kwargs)
            with CorpusMutationLock(config):
                return function(config, *args, **kwargs)

        return wrapper

    return decorator


MUTATION_FAILURE_INJECTOR: Any | None = None


def mutation_checkpoint(operation: str, step: str) -> None:
    if MUTATION_FAILURE_INJECTOR is not None:
        MUTATION_FAILURE_INJECTOR(operation, step)


def restore_mutation_journal(config: Config, journal_dir: Path) -> None:
    manifest_path = journal_dir / "manifest.json"
    try:
        manifest = load_json(manifest_path)
    except FundusError as exc:
        raise FundusError(f"Cannot recover mutation journal {journal_dir.name}.", "MUTATION_RECOVERY_FAILED") from exc
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise FundusError(f"Mutation journal is invalid: {journal_dir.name}", "MUTATION_RECOVERY_FAILED")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise FundusError(f"Mutation journal entry is invalid: {journal_dir.name}", "MUTATION_RECOVERY_FAILED")
        target = ensure_within(config.vault_path, config.vault_path / entry["path"], code="MUTATION_RECOVERY_FAILED")
        if entry.get("existed"):
            snapshot_name = str(entry.get("snapshot") or "")
            snapshot = ensure_within(journal_dir, journal_dir / snapshot_name, code="MUTATION_RECOVERY_FAILED")
            if not snapshot.is_file() or file_sha256(snapshot) != entry.get("sha256"):
                raise FundusError(f"Mutation snapshot is missing or corrupt: {target}", "MUTATION_RECOVERY_FAILED")
            atomic_write_bytes(target, snapshot.read_bytes())
        elif target.exists():
            if not target.is_file():
                raise FundusError(f"Cannot roll back non-file mutation target: {target}", "MUTATION_RECOVERY_FAILED")
            target.unlink()
    shutil.rmtree(journal_dir)


def recover_pending_mutations(config: Config) -> list[str]:
    root = journal_root_dir(config)
    if not root.exists():
        return []
    recovered: list[str] = []
    for journal_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        restore_mutation_journal(config, journal_dir)
        recovered.append(journal_dir.name)
    try:
        root.rmdir()
    except OSError:
        pass
    return recovered


class MutationJournal:
    def __init__(self, config: Config, operation: str, paths: list[Path]) -> None:
        self.config = config
        self.operation = operation
        unique_paths = {ensure_within(config.vault_path, path) for path in paths}
        self.paths = sorted(unique_paths, key=str)
        self.id = f"{datetime.now().astimezone().strftime('%Y%m%dT%H%M%S%f%z')}-{operation}-{uuid.uuid4().hex[:8]}"
        self.directory = journal_root_dir(config) / self.id

    def __enter__(self) -> MutationJournal:
        self.directory.mkdir(parents=True, exist_ok=False)
        entries: list[dict[str, Any]] = []
        for index, path in enumerate(self.paths):
            relative_path = str(path.relative_to(self.config.vault_path))
            if path.exists():
                if not path.is_file():
                    raise FundusError(f"Mutation journal only supports file targets: {path}", "MUTATION_JOURNAL_INVALID")
                snapshot_name = f"snapshot-{index:04d}.bin"
                snapshot = self.directory / snapshot_name
                shutil.copy2(path, snapshot)
                entries.append(
                    {
                        "path": relative_path,
                        "existed": True,
                        "snapshot": snapshot_name,
                        "sha256": file_sha256(snapshot),
                    }
                )
            else:
                entries.append({"path": relative_path, "existed": False})
        manifest = {
            "id": self.id,
            "operation": self.operation,
            "created": now_iso(),
            "state": "prepared",
            "entries": entries,
        }
        atomic_write(self.directory / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return self

    def commit(self) -> None:
        shutil.rmtree(self.directory)
        try:
            self.directory.parent.rmdir()
        except OSError:
            pass

    def rollback(self) -> None:
        restore_mutation_journal(self.config, self.directory)
        try:
            self.directory.parent.rmdir()
        except OSError:
            pass

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()


def backup_id_for(label: str | None, timestamp: datetime | None = None) -> str:
    created = timestamp or datetime.now().astimezone()
    suffix = slugify(label or "backup")
    return f"{created.strftime('%Y%m%dT%H%M%S%f%z')}-{suffix}"


def iter_backup_source_files(config: Config, root: Path | None = None) -> list[Path]:
    root = ensure_within(config.vault_path, root or fundus_root_dir(config))
    if not root.exists():
        raise FundusError(f"Fundus root does not exist: {root}")
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part in {BACKUP_DIRNAME, JOURNAL_DIRNAME} for part in relative_parts) or path.name == LOCK_FILENAME:
            continue
        files.append(path)
    return sorted(files)


@serialized_mutation
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


def verify_backup(config: Config, backup_id: str) -> dict[str, Any]:
    manifest = inspect_backup(config, backup_id)
    backup_directory = ensure_within(
        backup_root_dir(config),
        backup_root_dir(config) / backup_id,
        code="BACKUP_INVALID",
    )
    files = manifest.get("files")
    if not isinstance(files, list):
        raise FundusError("Backup manifest files must be a list.", "BACKUP_INVALID")
    seen_paths: set[str] = set()
    verified_bytes = 0
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise FundusError("Backup manifest contains an invalid file entry.", "BACKUP_INVALID")
        relative_path = entry["path"]
        if relative_path in seen_paths:
            raise FundusError(f"Backup manifest contains a duplicate path: {relative_path}", "BACKUP_INVALID")
        seen_paths.add(relative_path)
        backup_file = ensure_within(backup_directory, backup_directory / relative_path, code="BACKUP_INVALID")
        if not backup_file.is_file():
            raise FundusError(f"Backup file is missing: {relative_path}", "BACKUP_CORRUPT")
        size = backup_file.stat().st_size
        if size != entry.get("size") or file_sha256(backup_file) != entry.get("sha256"):
            raise FundusError(f"Backup checksum mismatch: {relative_path}", "BACKUP_CORRUPT")
        verified_bytes += size
    if len(files) != manifest.get("file_count") or verified_bytes != manifest.get("byte_count"):
        raise FundusError("Backup manifest totals do not match verified files.", "BACKUP_CORRUPT")
    return {
        "id": backup_id,
        "verified": True,
        "file_count": len(files),
        "byte_count": verified_bytes,
        "source_fundus_dir": manifest.get("source_fundus_dir"),
        "manifest_path": manifest["manifest_path"],
    }


@serialized_mutation_when(lambda config, backup_id, apply=False: apply)
def restore_backup(config: Config, backup_id: str, apply: bool = False) -> dict[str, Any]:
    verification = verify_backup(config, backup_id)
    manifest = inspect_backup(config, backup_id)
    source_fundus_dir = str(manifest.get("source_fundus_dir") or "")
    if source_fundus_dir != config.fundus_dir:
        raise FundusError(
            f"Backup targets '{source_fundus_dir}', not configured Fundus directory '{config.fundus_dir}'.",
            "BACKUP_TARGET_MISMATCH",
        )
    target_paths = {
        ensure_within(fundus_root_dir(config), config.vault_path / str(entry["path"]), code="BACKUP_INVALID")
        for entry in manifest["files"]
    }
    current_paths = set(iter_backup_source_files(config, fundus_root_dir(config)))
    plan = {
        "id": backup_id,
        "apply": apply,
        "verified": True,
        "restore_count": len(target_paths),
        "remove_count": len(current_paths - target_paths),
        "verification": verification,
    }
    if not apply:
        return plan

    safety_backup = create_backup(config, f"pre-restore-{backup_id}")
    backup_directory = backup_root_dir(config) / backup_id
    with MutationJournal(
        config,
        "backup-restore",
        [*current_paths, *target_paths, index_path(config)],
    ):
        for current_path in sorted(current_paths - target_paths):
            current_path.unlink()
        mutation_checkpoint("backup-restore", "obsolete_files_removed")
        for entry in manifest["files"]:
            destination = ensure_within(
                fundus_root_dir(config),
                config.vault_path / str(entry["path"]),
                code="BACKUP_INVALID",
            )
            source = ensure_within(backup_directory, backup_directory / str(entry["path"]), code="BACKUP_INVALID")
            atomic_write_bytes(destination, source.read_bytes())
        mutation_checkpoint("backup-restore", "snapshot_copied")
        rebuild_index(config)
        corpus_verification = verify_fundus_corpus(config)
        if not corpus_verification["passed"]:
            raise FundusError(
                f"Restored backup failed corpus verification: {corpus_verification['issues']}",
                "BACKUP_RESTORE_INVALID",
            )
        mutation_checkpoint("backup-restore", "verified")
    return {
        **plan,
        "safety_backup_id": safety_backup["id"],
        "corpus_verification": corpus_verification,
        "index": index_status(config),
    }


def load_document(path: Path, vault_root: Path) -> Document:
    safe_path = ensure_within(vault_root, path)
    text = read_note_text(safe_path)
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
        tags=frontmatter_list(frontmatter.get("tags")),
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
    return [term.casefold() for term in re.findall(r"[^\W_]+", value, flags=re.UNICODE)]


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
        return tuple(ensure_within(fundus_root_dir(config), path).relative_to(fundus_root_dir(config)).parts)
    except (FundusError, ValueError):
        return ()


def active_fundus_relative_path_for_document(config: Config, doc: Document) -> str:
    return classify_document_scope(config, doc.path, doc.frontmatter).active_relative_path


def scope_metadata_for_document(config: Config, doc: Document) -> dict[str, Any]:
    classification = classify_document_scope(config, doc.path, doc.frontmatter)
    return {
        "scope": classification.scope.kind,
        "scope_path": classification.scope.path,
        "project": classification.project,
        "area": classification.scope.path if classification.scope.kind == "area" else None,
        "physical_parent": classification.physical_parent,
        "scope_relative_path": classification.scope_relative_path,
    }


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
            str(doc.frontmatter.get("verification_status") or ""),
            str(doc.frontmatter.get("source_fingerprint") or ""),
            " ".join(frontmatter_list(doc.frontmatter.get("verified_against"))),
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
    redirect = is_redirect_frontmatter(doc.frontmatter)
    kind = "redirect" if redirect else ("reserved" if doc.path.name in RESERVED_FILENAMES else "concept")
    stat = doc.path.stat()
    return {
        "path": doc.relative_path,
        "project": doc.project,
        **scope_metadata,
        "id": doc.frontmatter.get("id"),
        "type": doc.frontmatter.get("type"),
        "kind": kind,
        "redirect_to": doc.frontmatter.get("redirect_to") if redirect else None,
        "title": doc.title,
        "tags": doc.tags,
        "description": doc.frontmatter.get("description"),
        "aliases": aliases,
        "resource": resource or None,
        "status": doc.frontmatter.get("status"),
        "owner": doc.frontmatter.get("owner"),
        "last_verified": doc.frontmatter.get("last_verified"),
        "verification_status": doc.frontmatter.get("verification_status") or "unverified",
        "source_fingerprint": doc.frontmatter.get("source_fingerprint"),
        "verified_against": frontmatter_list(doc.frontmatter.get("verified_against")),
        "stale_reason": doc.frontmatter.get("stale_reason"),
        "projects": frontmatter_list(doc.frontmatter.get("projects")),
        "repos": frontmatter_list(doc.frontmatter.get("repos")),
        "updated": doc.updated,
        "headings": extract_headings(doc.body)[:20],
        "excerpt": make_excerpt(doc.body),
        "tokens": sorted(set(tokenize(source_text))),
        "ticket_ids": extract_ticket_ids(source_text),
        "revision": f"sha256:{file_sha256(doc.path)}",
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
        "size": stat.st_size,
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
        and JOURNAL_DIRNAME not in path.relative_to(root).parts
    ]
    archive_paths = list(fundus_archive_dir(config).rglob("*.md")) if fundus_archive_dir(config).exists() else []
    return sorted([*active_paths, *archive_paths])


def load_index_result(config: Config) -> IndexLoadResult:
    path = index_path(config)
    if not path.exists():
        return IndexLoadResult(None, "missing")
    try:
        data = load_json(path)
    except FundusError as exc:
        return IndexLoadResult(None, "corrupt", str(exc))
    if data.get("version") != INDEX_VERSION or not isinstance(data.get("documents"), list):
        return IndexLoadResult(None, "incompatible")

    seen_paths: set[str] = set()
    for record in data["documents"]:
        if not isinstance(record, dict):
            return IndexLoadResult(None, "corrupt", "Index documents must be objects.")
        record_path = record.get("path")
        if not isinstance(record_path, str) or not record_path or record_path in seen_paths:
            return IndexLoadResult(None, "corrupt", "Index document paths must be unique non-empty strings.")
        seen_paths.add(record_path)
        if (
            not isinstance(record.get("mtime_ns"), int)
            or not isinstance(record.get("ctime_ns"), int)
            or not isinstance(record.get("size"), int)
        ):
            return IndexLoadResult(None, "corrupt", f"Index fingerprint is invalid for {record_path}.")
        if not str(record.get("revision") or "").startswith("sha256:"):
            return IndexLoadResult(None, "corrupt", f"Index revision is invalid for {record_path}.")
    return IndexLoadResult(data, "current")


def load_index(config: Config) -> dict[str, Any] | None:
    return load_index_result(config).data


def write_index(config: Config, documents: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "version": INDEX_VERSION,
        "generated": now_iso(),
        "fundus_dir": config.fundus_dir,
        "documents": sorted(documents, key=lambda doc: str(doc.get("path", ""))),
    }
    atomic_write(index_path(config), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


@serialized_mutation
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

    safe_path = ensure_within(fundus_root_dir(config), path)
    relative_path = str(safe_path.relative_to(config.vault_path))
    documents = [doc for doc in existing_index["documents"] if doc.get("path") != relative_path]
    if safe_path.exists():
        documents.append(index_entry_for_document(config, load_document(safe_path, config.vault_path)))
    write_index(config, documents)


def index_record_is_fresh(record: dict[str, Any], path: Path) -> bool:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False
    return (
        record.get("mtime_ns") == stat.st_mtime_ns
        and record.get("ctime_ns") == stat.st_ctime_ns
        and record.get("size") == stat.st_size
        and str(record.get("revision") or "").startswith("sha256:")
    )


def search_records_for_scope(config: Config, scope: Scope, include_archived: bool) -> list[dict[str, Any]]:
    index_result = load_index_result(config)
    cached_by_path = {
        str(record.get("path")): record
        for record in (index_result.data or {}).get("documents", [])
        if isinstance(record, dict)
    }
    records: list[dict[str, Any]] = []
    for path in markdown_paths_for_scope(config, scope, include_archived):
        relative_path = str(path.relative_to(config.vault_path))
        record = cached_by_path.get(relative_path)
        if record is None or not index_record_is_fresh(record, path):
            record = index_entry_for_document(config, load_document(path, config.vault_path))
        if not entry_matches_scope(config, record, scope):
            continue
        if record.get("kind") in {"redirect", "reserved"} or record.get("redirect_to"):
            continue
        if record.get("archived") and not include_archived:
            continue
        records.append(record)
    return records


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
        "id": entry.get("id"),
        "title": entry.get("title"),
        "tags": entry.get("tags") or [],
        "updated": entry.get("updated"),
        "revision": entry.get("revision"),
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
    if entry.get("verification_status"):
        payload["verification_status"] = entry.get("verification_status")
    if entry.get("source_fingerprint"):
        payload["source_fingerprint"] = entry.get("source_fingerprint")
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


def resolve_path_inside_fundus(config: Config, value: str | Path) -> tuple[Path, tuple[str, ...]]:
    raw_path = Path(value).expanduser()
    root = fundus_root_dir(config)
    if raw_path.is_absolute():
        candidate = raw_path
    else:
        raw_parts = raw_path.parts
        fundus_parts = Path(config.fundus_dir).parts
        if raw_parts[: len(fundus_parts)] == fundus_parts:
            candidate = config.vault_path / raw_path
        else:
            raise FundusError(
                f"Fundus note paths must start with {config.fundus_dir}/.",
                "PATH_OUTSIDE_FUNDUS",
            )
    resolved = ensure_within(root, candidate, code="PATH_OUTSIDE_FUNDUS")
    return resolved, tuple(resolved.relative_to(root).parts)


def validate_markdown_note_path(
    path: Path,
    relative_parts: tuple[str, ...],
    *,
    allow_reserved: bool,
) -> None:
    if not relative_parts:
        raise FundusError("A Fundus note path must not be the Fundus root.", "NOTE_PATH_INVALID")
    if relative_parts[0] in {BACKUP_DIRNAME, JOURNAL_DIRNAME}:
        raise FundusError("Fundus internal-state paths are not note paths.", "NOTE_PATH_INVALID")
    if path.suffix.casefold() != ".md":
        raise FundusError("Fundus note paths must use the .md suffix.", "NOTE_PATH_INVALID")
    if path.exists() and not path.is_file():
        raise FundusError("Fundus note path resolves to a directory.", "NOTE_PATH_INVALID")
    if not allow_reserved and path.name in RESERVED_FILENAMES:
        raise FundusError("index.md and log.md are reserved Fundus files.", "NOTE_PATH_INVALID")


def resolve_active_note_path(config: Config, path_arg: str | Path, *, allow_reserved: bool = False) -> Path:
    return ActiveNotePath.resolve(config, path_arg, allow_reserved=allow_reserved).path


def resolve_archived_note_path(config: Config, path_arg: str | Path) -> Path:
    return ArchivedNotePath.resolve(config, path_arg).path


def resolve_fundus_note_path(config: Config, path_arg: str | Path, *, allow_reserved: bool = False) -> Path:
    path, relative_parts = resolve_path_inside_fundus(config, path_arg)
    validate_markdown_note_path(path, relative_parts, allow_reserved=allow_reserved)
    return path


def active_relative_parts_for_path(
    config: Config,
    path: Path,
    frontmatter: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    root = fundus_root_dir(config)
    parts = tuple(ensure_within(root, path).relative_to(root).parts)
    if not parts:
        raise FundusError("Cannot classify the Fundus root as a note scope.", "SCOPE_PATH_INVALID")
    if parts[0] != ARCHIVE_DIRNAME:
        return parts

    original_path = str((frontmatter or {}).get("original_path") or "")
    if original_path:
        try:
            original = resolve_active_note_path(config, original_path)
            return tuple(original.relative_to(root).parts)
        except FundusError:
            pass
    archived_parts = parts[1:]
    if not archived_parts:
        raise FundusError("Archived note path is missing its active scope path.", "SCOPE_PATH_INVALID")
    return archived_parts


def classify_document_scope(
    config: Config,
    path: Path,
    frontmatter: dict[str, Any] | None = None,
) -> ScopeClassification:
    parts = active_relative_parts_for_path(config, path, frontmatter)
    if parts[0] in RESERVED_FUNDUS_DIRNAMES:
        raise FundusError(f"Cannot classify reserved Fundus path: {'/'.join(parts)}", "SCOPE_PATH_INVALID")

    if len(parts) == 1 and parts[0] in RESERVED_FILENAMES:
        scope = Scope(kind="global", path="", display_name=config.fundus_dir)
        scope_parts: tuple[str, ...] = ()
        project = None
    elif parts[0] in AREA_ROOT_DIRNAMES:
        if len(parts) < 3:
            raise FundusError(
                "Area notes must live below an allowed area root and one logical area name.",
                "SCOPE_PATH_INVALID",
            )
        scope = area_scope("/".join(parts[:2]))
        scope_parts = parts[:2]
        project = None
    else:
        if len(parts) < 2:
            raise FundusError("Project notes must live below a project directory.", "SCOPE_PATH_INVALID")
        project = normalize_project_name(parts[0])
        scope = project_scope(project)
        scope_parts = parts[:1]

    active_relative_path = "/".join(parts)
    physical_parent = Path(active_relative_path).parent.as_posix()
    if physical_parent == ".":
        physical_parent = ""
    scope_relative_path = "/".join(parts[len(scope_parts) :])
    return ScopeClassification(
        scope=scope,
        project=project,
        active_relative_path=active_relative_path,
        physical_parent=physical_parent,
        scope_relative_path=scope_relative_path,
    )


def apply_canonical_scope_metadata(
    config: Config,
    frontmatter: dict[str, Any],
    classification: ScopeClassification,
) -> None:
    scope = classification.scope
    frontmatter["scope"] = scope.kind
    frontmatter["scope_path"] = scope.path
    if classification.project:
        frontmatter["project"] = classification.project
    else:
        frontmatter.pop("project", None)
    frontmatter["tags"] = normalize_scope_tags(
        config,
        classification.project or "",
        scope,
        scope_neutral_tags(frontmatter_list(frontmatter.get("tags"))),
    )


def is_redirect_frontmatter(frontmatter: dict[str, Any]) -> bool:
    return str(frontmatter.get("type") or "").casefold() == "redirect" or bool(
        str(frontmatter.get("redirect_to") or "").strip()
    )


def resolve_doc_path(config: Config, path_arg: str) -> Path:
    """Compatibility alias for any validated Fundus Markdown note path."""
    return resolve_fundus_note_path(config, path_arg)


def entry_matches_scope(config: Config, entry: dict[str, Any], scope: Scope) -> bool:
    return entry.get("scope") == scope.kind and entry.get("scope_path") == scope.path


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
    scope_dir = fundus_scope_dir(config, active_scope)
    archive_scope_dir = fundus_archive_scope_dir(config, active_scope)
    if not scope_dir.exists() and not (include_archived and archive_scope_dir.exists()):
        return []

    matches: list[tuple[int, str, dict[str, Any]]] = []
    for record in search_records_for_scope(config, active_scope, include_archived):
        score, reason = score_index_entry(record, query)
        if score <= 0:
            continue
        matches.append((score, reason, record))

    matches.sort(
        key=lambda item: (
            -item[0],
            str(item[2].get("title", "")).casefold(),
            str(item[2].get("path", "")),
        )
    )
    return [present_index_entry(entry, score, reason, include_snippet) for score, reason, entry in matches[:limit]]


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
    verified_against: list[str] | None = None,
    source_fingerprint: str | None = None,
    verification_status: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    scope_project = scope.path if scope.kind == "project" else project_name
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
        "tags": normalize_scope_tags(config, scope_project, scope, extra_tags),
        "verification_status": (verification_status or "unverified").strip() or "unverified",
    }
    if scope.kind == "project":
        frontmatter["project"] = scope_project
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
    clean_verified_against = [value.strip() for value in verified_against or [] if value.strip()]
    if clean_verified_against:
        frontmatter["verified_against"] = clean_verified_against
    if source_fingerprint and source_fingerprint.strip():
        frontmatter["source_fingerprint"] = source_fingerprint.strip()
    return frontmatter


@serialized_mutation
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
    verified_against: list[str] | None = None,
    source_fingerprint: str | None = None,
    verification_status: str | None = None,
) -> dict[str, Any]:
    requested_scope = scope or project_scope(project_name)
    project_dir = fundus_scope_dir(config, requested_scope)
    slug = slugify(title)
    path = resolve_active_note_path(config, project_dir / f"{slug}.md")
    if path.exists():
        raise FundusError(f"Document already exists: {path.relative_to(config.vault_path)}", "NOTE_ALREADY_EXISTS")
    classification = classify_document_scope(config, path)
    active_scope = classification.scope

    frontmatter = frontmatter_for_new_document(
        config,
        classification.project or project_name,
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
        verified_against,
        source_fingerprint,
        verification_status,
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
        "revision": path_revision(path),
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


ALLOWED_METADATA_UPDATE_FIELDS = {
    "aliases",
    "description",
    "last_verified",
    "owner",
    "resource",
    "source_fingerprint",
    "stale_reason",
    "status",
    "verification_status",
    "verified_against",
}


def apply_metadata_changes(frontmatter: dict[str, Any], metadata_changes: dict[str, Any] | None) -> None:
    for key, value in (metadata_changes or {}).items():
        if key not in ALLOWED_METADATA_UPDATE_FIELDS:
            raise FundusError(f"Metadata field cannot be changed through update proposals: {key}", "METADATA_FIELD_INVALID")
        if value is None or value == "" or value == []:
            frontmatter.pop(key, None)
            continue
        if key == "verification_status" and value not in {"current", "stale", "unverified"}:
            raise FundusError("verification_status must be current, stale, or unverified.", "METADATA_FIELD_INVALID")
        frontmatter[key] = normalize_frontmatter_value(key, value)


def updated_body_for_mode(body: str, mode: str, new_content: str, section: str | None) -> str:
    if mode == "append":
        return append_body(body, new_content)
    if mode == "replace":
        if not section:
            raise FundusError("--section is required when mode is replace.")
        return replace_section(body, section, new_content)
    if mode == "rewrite":
        return new_content.strip()
    raise FundusError(f"Unknown update mode: {mode}")


@serialized_mutation
def update_document(
    config: Config,
    project_name: str,
    path_arg: str,
    mode: str,
    new_content: str,
    section: str | None,
    scope: Scope | None = None,
    expected_revision: str | None = None,
    metadata_changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = resolve_active_note_path(config, path_arg)
    if not path.exists():
        raise FundusError(f"Document does not exist: {path_arg}", "NOTE_NOT_FOUND")
    previous_revision = assert_expected_revision(path, expected_revision)

    text = read_note_text(path)
    frontmatter, body = parse_frontmatter(text)
    if not frontmatter:
        raise FundusError(f"Document is missing expected frontmatter: {path}")

    redacted_content = redact_secrets(new_content, config)
    updated_body = updated_body_for_mode(body, mode, redacted_content, section)

    frontmatter["updated"] = now_iso()
    frontmatter["timestamp"] = frontmatter["updated"]
    classification = classify_document_scope(config, path, frontmatter)
    apply_canonical_scope_metadata(config, frontmatter, classification)
    apply_metadata_changes(frontmatter, metadata_changes)

    rendered = render_existing_document(frontmatter, updated_body)
    atomic_write(path, rendered)
    refresh_index_entry(config, path)
    return {
        "path": str(path.relative_to(config.vault_path)),
        "title": frontmatter.get("title"),
        "updated": frontmatter.get("updated"),
        "mode": mode,
        "section": section,
        "previous_revision": previous_revision,
        "revision": path_revision(path),
    }


def resolve_redirect_document_path(config: Config, path: Path, max_hops: int = 32) -> Path:
    current = path
    visited: set[Path] = set()
    for _ in range(max_hops + 1):
        resolved = current.resolve(strict=False)
        if resolved in visited:
            raise FundusError(f"Redirect loop detected at: {current}", "REDIRECT_LOOP")
        visited.add(resolved)
        if not current.exists():
            raise FundusError(f"Redirect target does not exist: {current}", "REDIRECT_TARGET_NOT_FOUND")

        frontmatter, _ = parse_frontmatter(read_note_text(current))
        if not is_redirect_frontmatter(frontmatter):
            return current
        target_arg = str(frontmatter.get("redirect_to") or "").strip()
        if not target_arg:
            raise FundusError(f"Redirect is missing redirect_to: {current}", "REDIRECT_INVALID")
        try:
            current = resolve_active_note_path(config, target_arg)
        except FundusError as exc:
            raise FundusError(f"Redirect target is invalid: {target_arg}", "REDIRECT_INVALID") from exc

    raise FundusError(f"Redirect chain exceeds {max_hops} hops.", "REDIRECT_LOOP")


def read_document_result(config: Config, path_arg: str) -> dict[str, Any]:
    path = resolve_fundus_note_path(config, path_arg)
    if not path.exists():
        raise FundusError(f"Document does not exist: {path_arg}", "NOTE_NOT_FOUND")
    resolved_path = resolve_redirect_document_path(config, path)
    return {
        "path": str(path.relative_to(config.vault_path)),
        "resolved_path": str(resolved_path.relative_to(config.vault_path)),
        "content": read_note_text(resolved_path),
        "revision": path_revision(resolved_path),
        "redirected": resolved_path != path,
    }


def read_document(config: Config, path_arg: str) -> str:
    """Compatibility helper returning only content; operation surfaces use read_document_result."""
    return str(read_document_result(config, path_arg)["content"])


def proposal_digest(kind: str, request: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"kind": kind, "request": request},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def body_diff(before: str, after: str, path: str) -> str:
    rendered = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    if len(rendered) <= MAX_PROPOSAL_DIFF_CHARS:
        return rendered
    return f"{rendered[:MAX_PROPOSAL_DIFF_CHARS]}\n... diff truncated by Fundus ...\n"


def duplicate_candidates(
    config: Config,
    proposed: dict[str, Any],
    exclude_path: str | None = None,
) -> list[dict[str, Any]]:
    proposed_title = str(proposed.get("title") or "").strip()
    proposed_id = str(proposed.get("id") or "").strip()
    proposed_aliases = {value.casefold() for value in frontmatter_list(proposed.get("aliases"))}
    proposed_resource = str(proposed.get("resource") or "").strip().casefold()
    proposed_text = " ".join(
        [
            proposed_title,
            str(proposed.get("description") or ""),
            " ".join(proposed_aliases),
            proposed_resource,
            str(proposed.get("body") or ""),
        ]
    )
    proposed_tickets = set(extract_ticket_ids(proposed_text))
    proposed_tokens = set(tokenize(f"{proposed_title} {proposed.get('description') or ''}"))
    candidates: list[dict[str, Any]] = []
    for path in iter_fundus_markdown_paths(config):
        doc = load_document(path, config.vault_path)
        record = index_entry_for_document(config, doc)
        if record.get("archived") or record.get("kind") in {"redirect", "reserved"}:
            continue
        if exclude_path and record.get("path") == exclude_path:
            continue
        reasons: list[str] = []
        if proposed_title and proposed_title.casefold() == str(record.get("title") or "").casefold():
            reasons.append("title")
        if proposed_id and proposed_id == str(record.get("id") or ""):
            reasons.append("id")
        record_aliases = {value.casefold() for value in frontmatter_list(record.get("aliases"))}
        if proposed_aliases.intersection(record_aliases):
            reasons.append("alias")
        if proposed_resource and proposed_resource == str(record.get("resource") or "").casefold():
            reasons.append("resource")
        shared_tickets = sorted(proposed_tickets.intersection(set(record.get("ticket_ids") or [])))
        if shared_tickets:
            reasons.extend(f"ticket:{ticket}" for ticket in shared_tickets)
        record_tokens = set(tokenize(f"{record.get('title') or ''} {record.get('description') or ''}"))
        union = proposed_tokens.union(record_tokens)
        similarity = len(proposed_tokens.intersection(record_tokens)) / len(union) if union else 0.0
        title_similarity = difflib.SequenceMatcher(
            None,
            proposed_title.casefold(),
            str(record.get("title") or "").casefold(),
        ).ratio()
        if not reasons and (similarity >= 0.8 or title_similarity >= 0.9):
            reasons.append("high_confidence_similarity")
        if reasons:
            candidates.append(
                {
                    "path": record.get("path"),
                    "id": record.get("id"),
                    "title": record.get("title"),
                    "reasons": reasons,
                    "confidence": "high",
                    "similarity": round(max(similarity, title_similarity), 3),
                }
            )
    return sorted(candidates, key=lambda candidate: str(candidate.get("path") or ""))


def require_duplicate_review(
    candidates: list[dict[str, Any]],
    duplicate_override: bool,
    reviewed_duplicate_paths: list[str] | None,
) -> None:
    if not candidates:
        return
    candidate_paths = {str(candidate.get("path") or "") for candidate in candidates}
    reviewed_paths = {str(path) for path in reviewed_duplicate_paths or []}
    if not duplicate_override or not candidate_paths.issubset(reviewed_paths):
        raise FundusError(
            "Duplicate candidates require explicit override after reviewing every candidate path.",
            "DUPLICATE_REVIEW_REQUIRED",
        )


def scope_from_proposal_request(request: dict[str, Any]) -> Scope:
    scope_kind = str(request.get("scope") or "")
    scope_path = str(request.get("scope_path") or "")
    if scope_kind == "project":
        return project_scope(scope_path)
    if scope_kind == "area":
        return area_scope(scope_path)
    raise FundusError("Proposal scope is invalid.", "PROPOSAL_INVALID")


def propose_create_document(
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
    verified_against: list[str] | None = None,
    source_fingerprint: str | None = None,
    verification_status: str | None = None,
) -> dict[str, Any]:
    active_scope = scope or project_scope(project_name)
    redacted_body = redact_secrets(body, config)
    request = {
        "project_name": project_name,
        "scope": active_scope.kind,
        "scope_path": active_scope.path,
        "title": title.strip(),
        "body": redacted_body,
        "tags": list(extra_tags or []),
        "doc_type": doc_type,
        "description": description,
        "document_id": document_id,
        "aliases": list(aliases or []),
        "resource": resource,
        "status": status,
        "owner": owner,
        "last_verified": last_verified,
        "verified_against": list(verified_against or []),
        "source_fingerprint": source_fingerprint,
        "verification_status": verification_status or "unverified",
    }
    proposed_id = (document_id or default_document_id(active_scope, title)).strip()
    proposed = {
        "title": title,
        "description": description or title,
        "id": proposed_id,
        "aliases": aliases or [],
        "resource": resource,
        "body": redacted_body,
    }
    path = fundus_scope_dir(config, active_scope) / f"{slugify(title)}.md"
    relative_path = str(path.relative_to(config.vault_path))
    duplicates = duplicate_candidates(config, proposed)
    return {
        "proposal_version": 1,
        "kind": "create",
        "proposal_id": proposal_digest("create", request),
        "path": relative_path,
        "scope": active_scope.kind,
        "scope_path": active_scope.path,
        "request": request,
        "diff": body_diff("", redacted_body, relative_path),
        "duplicate_candidates": duplicates,
        "requires_duplicate_override": bool(duplicates),
        "warnings": ["CONTENT_REDACTED"] if redacted_body != body else [],
    }


@serialized_mutation
def apply_create_proposal(
    config: Config,
    proposal: dict[str, Any],
    duplicate_override: bool = False,
    reviewed_duplicate_paths: list[str] | None = None,
) -> dict[str, Any]:
    if proposal.get("kind") != "create" or not isinstance(proposal.get("request"), dict):
        raise FundusError("Expected a create proposal.", "PROPOSAL_INVALID")
    request = dict(proposal["request"])
    if proposal.get("proposal_id") != proposal_digest("create", request):
        raise FundusError("Create proposal integrity check failed.", "PROPOSAL_INVALID")
    regenerated = propose_create_document(
        config,
        str(request["project_name"]),
        str(request["title"]),
        str(request["body"]),
        list(request.get("tags") or []),
        scope_from_proposal_request(request),
        request.get("doc_type"),
        request.get("description"),
        request.get("document_id"),
        list(request.get("aliases") or []),
        request.get("resource"),
        request.get("status"),
        request.get("owner"),
        request.get("last_verified"),
        list(request.get("verified_against") or []),
        request.get("source_fingerprint"),
        request.get("verification_status"),
    )
    require_duplicate_review(regenerated["duplicate_candidates"], duplicate_override, reviewed_duplicate_paths)
    result = create_document(
        config,
        str(request["project_name"]),
        str(request["title"]),
        str(request["body"]),
        list(request.get("tags") or []),
        scope_from_proposal_request(request),
        request.get("doc_type"),
        request.get("description"),
        request.get("document_id"),
        list(request.get("aliases") or []),
        request.get("resource"),
        request.get("status"),
        request.get("owner"),
        request.get("last_verified"),
        list(request.get("verified_against") or []),
        request.get("source_fingerprint"),
        request.get("verification_status"),
    )
    return {"proposal_id": proposal["proposal_id"], "applied": True, **result}


def propose_update_document(
    config: Config,
    path_arg: str,
    mode: str,
    new_content: str,
    section: str | None = None,
    metadata_changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = resolve_active_note_path(config, path_arg)
    if not path.exists():
        raise FundusError(f"Document does not exist: {path_arg}", "NOTE_NOT_FOUND")
    expected_revision = path_revision(path)
    frontmatter, body = parse_frontmatter(read_note_text(path))
    if not frontmatter:
        raise FundusError(f"Document is missing expected frontmatter: {path}")
    redacted_content = redact_secrets(new_content, config)
    proposed_body = updated_body_for_mode(body, mode, redacted_content, section)
    proposed_frontmatter = clone_frontmatter(frontmatter)
    apply_metadata_changes(proposed_frontmatter, metadata_changes)
    request = {
        "path": str(path.relative_to(config.vault_path)),
        "mode": mode,
        "content": redacted_content,
        "section": section,
        "metadata_changes": metadata_changes or {},
        "expected_revision": expected_revision,
    }
    duplicates = duplicate_candidates(
        config,
        {
            "title": proposed_frontmatter.get("title"),
            "description": proposed_frontmatter.get("description"),
            "id": proposed_frontmatter.get("id"),
            "aliases": proposed_frontmatter.get("aliases"),
            "resource": proposed_frontmatter.get("resource"),
            "body": proposed_body,
        },
        exclude_path=request["path"],
    )
    return {
        "proposal_version": 1,
        "kind": "update",
        "proposal_id": proposal_digest("update", request),
        "path": request["path"],
        "expected_revision": expected_revision,
        "request": request,
        "diff": body_diff(body, proposed_body, request["path"]),
        "metadata_changes": metadata_changes or {},
        "duplicate_candidates": duplicates,
        "requires_duplicate_override": bool(duplicates),
        "warnings": ["CONTENT_REDACTED"] if redacted_content != new_content else [],
    }


@serialized_mutation
def apply_update_proposal(
    config: Config,
    proposal: dict[str, Any],
    duplicate_override: bool = False,
    reviewed_duplicate_paths: list[str] | None = None,
) -> dict[str, Any]:
    if proposal.get("kind") != "update" or not isinstance(proposal.get("request"), dict):
        raise FundusError("Expected an update proposal.", "PROPOSAL_INVALID")
    request = dict(proposal["request"])
    if proposal.get("proposal_id") != proposal_digest("update", request):
        raise FundusError("Update proposal integrity check failed.", "PROPOSAL_INVALID")
    path = resolve_active_note_path(config, str(request.get("path") or ""))
    if not path.exists():
        raise FundusError(f"Document does not exist: {request.get('path')}", "NOTE_NOT_FOUND")
    assert_expected_revision(path, str(request.get("expected_revision") or ""))
    regenerated = propose_update_document(
        config,
        str(request["path"]),
        str(request["mode"]),
        str(request["content"]),
        request.get("section"),
        dict(request.get("metadata_changes") or {}),
    )
    if regenerated["proposal_id"] != proposal["proposal_id"]:
        raise FundusError("Update proposal no longer matches current state.", "REVISION_CONFLICT")
    require_duplicate_review(regenerated["duplicate_candidates"], duplicate_override, reviewed_duplicate_paths)
    result = update_document(
        config,
        "",
        str(request["path"]),
        str(request["mode"]),
        str(request["content"]),
        request.get("section"),
        None,
        str(request["expected_revision"]),
        dict(request.get("metadata_changes") or {}),
    )
    return {"proposal_id": proposal["proposal_id"], "applied": True, "diff": proposal.get("diff") or "", **result}


@serialized_mutation
def update_note_metadata(
    config: Config,
    path_arg: str,
    metadata_changes: dict[str, Any],
    expected_revision: str | None = None,
) -> dict[str, Any]:
    path = resolve_active_note_path(config, path_arg)
    if not path.exists():
        raise FundusError(f"Document does not exist: {path_arg}", "NOTE_NOT_FOUND")
    previous_revision = assert_expected_revision(path, expected_revision)
    frontmatter, body = parse_frontmatter(read_note_text(path))
    if not frontmatter:
        raise FundusError(f"Document is missing expected frontmatter: {path}")
    apply_metadata_changes(frontmatter, metadata_changes)
    frontmatter["updated"] = now_iso()
    frontmatter["timestamp"] = frontmatter["updated"]
    atomic_write(path, render_existing_document_preserving_body(frontmatter, body))
    refresh_index_entry(config, path)
    return {
        "path": str(path.relative_to(config.vault_path)),
        "metadata_changes": metadata_changes,
        "previous_revision": previous_revision,
        "revision": path_revision(path),
    }


def mark_note_stale(
    config: Config,
    path_arg: str,
    reason: str,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    if not reason.strip():
        raise FundusError("A stale reason is required.", "METADATA_FIELD_INVALID")
    return update_note_metadata(
        config,
        path_arg,
        {"status": "stale", "verification_status": "stale", "stale_reason": reason.strip()},
        expected_revision,
    )


def verify_note(
    config: Config,
    path_arg: str,
    verified_against: list[str] | None = None,
    source_fingerprint: str | None = None,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    if not verified_against and not (source_fingerprint and source_fingerprint.strip()):
        raise FundusError("Verification requires verified_against or source_fingerprint evidence.", "VERIFICATION_EVIDENCE_REQUIRED")
    changes: dict[str, Any] = {
        "status": "active",
        "verification_status": "current",
        "last_verified": datetime.now().astimezone().date().isoformat(),
        "stale_reason": None,
    }
    if verified_against:
        changes["verified_against"] = verified_against
    if source_fingerprint:
        changes["source_fingerprint"] = source_fingerprint
    return update_note_metadata(config, path_arg, changes, expected_revision)


def filesystem_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()


@serialized_mutation
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
    expected_revision: str | None = None,
) -> dict[str, Any]:
    path = resolve_active_note_path(config, path_arg)
    if not path.exists():
        raise FundusError(f"Document does not exist: {path_arg}", "NOTE_NOT_FOUND")
    previous_revision = assert_expected_revision(path, expected_revision)

    text = read_note_text(path)
    existing_frontmatter, body = parse_frontmatter(text)
    if existing_frontmatter:
        raise FundusError(f"Document already has frontmatter: {path.relative_to(config.vault_path)}")

    timestamp = filesystem_timestamp(path)
    classification = classify_document_scope(config, path)
    active_scope = classification.scope
    note_title = (title or path.stem.replace("-", " ").title()).strip()
    frontmatter = frontmatter_for_new_document(
        config,
        classification.project or project_name,
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
        "previous_revision": previous_revision,
        "revision": path_revision(path),
    }


def fundus_relative_parts_for_active_document(config: Config, path: Path, frontmatter: dict[str, Any]) -> tuple[str, ...]:
    return active_relative_parts_for_path(config, path, frontmatter)


def infer_scope_from_document_path(config: Config, path: Path, frontmatter: dict[str, Any]) -> tuple[Scope, str | None]:
    classification = classify_document_scope(config, path, frontmatter)
    return classification.scope, classification.project


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
    return f"{format_frontmatter(frontmatter)}{frontmatter_newline(frontmatter)}{body}"


@serialized_mutation_when(lambda config, path, apply=False, add_missing=False, expected_revision=None: apply)
def normalize_frontmatter_for_path(
    config: Config,
    path: Path,
    apply: bool = False,
    add_missing: bool = False,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    safe_path = resolve_fundus_note_path(config, str(path))
    if safe_path.suffix != ".md":
        raise FundusError(f"Can only normalize Markdown documents: {safe_path.relative_to(config.vault_path)}")
    ensure_within(fundus_root_dir(config), safe_path)
    if not safe_path.exists():
        raise FundusError(f"Document does not exist: {path}")
    previous_revision = assert_expected_revision(safe_path, expected_revision)

    text = read_note_text(safe_path)
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
    classification = classify_document_scope(config, safe_path, before_frontmatter)
    active_scope = classification.scope
    title = str(frontmatter.get("title") or safe_path.stem.replace("-", " ").title()).strip()
    timestamp = str(frontmatter.get("updated") or frontmatter.get("created") or filesystem_timestamp(safe_path))
    created = str(frontmatter.get("created") or timestamp)
    updated = str(frontmatter.get("updated") or timestamp)
    raw_tags = frontmatter.get("tags") or []
    existing_tags = raw_tags if isinstance(raw_tags, list) else [str(raw_tags)]
    normalized = clone_frontmatter(frontmatter)
    normalized["type"] = infer_doc_type_from_path(config, safe_path, frontmatter, active_scope)
    normalized["title"] = title
    normalized["description"] = str(normalized.get("description") or title).strip()
    normalized["id"] = str(normalized.get("id") or default_document_id(active_scope, title)).strip()
    normalized["created"] = created
    normalized["updated"] = updated
    normalized["timestamp"] = str(normalized.get("timestamp") or updated)
    normalized["tags"] = existing_tags
    apply_canonical_scope_metadata(config, normalized, classification)

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

    previous_scope_path = str(before_frontmatter.get("scope_path") or "")
    scope_path_change = None
    if previous_scope_path and previous_scope_path != active_scope.path:
        reason = (
            "physical_subfolder_overload"
            if previous_scope_path.startswith(f"{active_scope.path}/")
            else "scope_path_mismatch"
        )
        scope_path_change = {"before": previous_scope_path, "after": active_scope.path, "reason": reason}

    return {
        "path": str(safe_path.relative_to(config.vault_path)),
        "title": title,
        "changed": bool(changes),
        "applied": bool(apply and changes),
        "skipped": False,
        "scope": active_scope.kind,
        "scope_path": active_scope.path,
        "physical_parent": classification.physical_parent,
        "scope_relative_path": classification.scope_relative_path,
        "scope_path_change": scope_path_change,
        "previous_revision": previous_revision,
        "revision": path_revision(safe_path),
        "body_sha256": body_sha256,
        "body_unchanged": body_unchanged,
        "changes": changes,
    }


@serialized_mutation_when(
    lambda config, project_name, scope, path_arg=None, global_scope=False, include_archived=False, apply=False, add_missing=False, limit=None: apply
)
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
        paths = [resolve_fundus_note_path(config, path_arg)]
        scope_name = "path"
        scope_path = path_arg
    elif global_scope:
        root = fundus_root_dir(config)
        paths = [
            path
            for path in sorted(root.rglob("*.md"))
            if BACKUP_DIRNAME not in path.relative_to(root).parts
            and JOURNAL_DIRNAME not in path.relative_to(root).parts
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
    scope_path_change_count = sum(1 for doc in documents if doc.get("scope_path_change"))
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
        "scope_path_change_count": scope_path_change_count,
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
    return ensure_within(fundus_archive_dir(config), fundus_archive_dir(config) / relative_path)


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
    newline = frontmatter_newline(frontmatter)
    cleaned_body = normalize_line_endings(body.strip(), newline)
    if not cleaned_body:
        return f"{format_frontmatter(frontmatter)}{newline}"
    return f"{format_frontmatter(frontmatter)}{newline}{newline}{cleaned_body}{newline}"


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


@serialized_mutation
def cleanup_empty_directories(
    config: Config,
    project_name: str,
    global_scope: bool = False,
    scope: Scope | None = None,
) -> dict[str, Any]:
    root = fundus_root_dir(config)
    archive_root = fundus_archive_dir(config)
    protected_directories = {root, archive_root}
    active_scope = None if global_scope else (scope or project_scope(project_name))
    candidate_roots = (
        [root]
        if global_scope
        else [fundus_scope_dir(config, active_scope), fundus_archive_scope_dir(config, active_scope)]
    )
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


@serialized_mutation
def archive_document(
    config: Config,
    path_arg: str,
    reason: str | None,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    source_path = resolve_active_note_path(config, path_arg)
    if not source_path.exists():
        raise FundusError(f"Document does not exist: {path_arg}", "NOTE_NOT_FOUND")
    previous_revision = assert_expected_revision(source_path, expected_revision)

    doc = load_document(source_path, config.vault_path)
    if not doc.frontmatter:
        raise FundusError(f"Document is missing expected frontmatter: {source_path}")
    if frontmatter_bool(doc.frontmatter.get("archived")):
        raise FundusError(f"Document is already archived: {doc.relative_path}")

    destination_path = archive_destination_for(config, doc)
    if destination_path.exists():
        raise FundusError(f"Archive destination already exists: {destination_path.relative_to(config.vault_path)}")

    timestamp = now_iso()
    frontmatter = clone_frontmatter(doc.frontmatter)
    classification = classify_document_scope(config, source_path, frontmatter)
    apply_canonical_scope_metadata(config, frontmatter, classification)
    frontmatter["updated"] = timestamp
    frontmatter["archived"] = True
    frontmatter["archived_at"] = timestamp
    frontmatter["archived_reason"] = reason or "archived"
    frontmatter["original_path"] = doc.relative_path

    with MutationJournal(config, "archive", [source_path, destination_path, index_path(config)]):
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.replace(destination_path)
        mutation_checkpoint("archive", "renamed")
        atomic_write(destination_path, render_existing_document_preserving_body(frontmatter, doc.body))
        mutation_checkpoint("archive", "metadata_written")
        active_directory_removed = remove_empty_directory(
            source_path.parent,
            {fundus_root_dir(config), fundus_archive_dir(config)},
        )
        refresh_index_entry(config, source_path)
        refresh_index_entry(config, destination_path)
        mutation_checkpoint("archive", "index_written")
    return {
        "path": str(destination_path.relative_to(config.vault_path)),
        "original_path": doc.relative_path,
        "title": doc.title,
        "archived_at": timestamp,
        "reason": frontmatter["archived_reason"],
        "active_directory_removed": active_directory_removed,
        "previous_revision": previous_revision,
        "revision": path_revision(destination_path),
    }


@serialized_mutation
def restore_document(
    config: Config,
    path_arg: str,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    archive_path = resolve_archived_note_path(config, path_arg)
    if not archive_path.exists():
        raise FundusError(f"Document does not exist: {path_arg}", "NOTE_NOT_FOUND")
    previous_revision = assert_expected_revision(archive_path, expected_revision)

    doc = load_document(archive_path, config.vault_path)
    if not doc.frontmatter:
        raise FundusError(f"Document is missing expected frontmatter: {archive_path}")
    if not frontmatter_bool(doc.frontmatter.get("archived")):
        raise FundusError(f"Document is not archived: {doc.relative_path}")

    original_path = str(doc.frontmatter.get("original_path") or "")
    if not original_path:
        raise FundusError(f"Archived document is missing original_path: {doc.relative_path}")
    destination_path = resolve_active_note_path(config, original_path)
    if destination_path.exists():
        raise FundusError(f"Restore destination already exists: {original_path}")

    frontmatter = clone_frontmatter(doc.frontmatter)
    timestamp = now_iso()
    frontmatter["updated"] = timestamp
    for key in ["archived", "archived_at", "archived_reason", "original_path"]:
        frontmatter.pop(key, None)
    classification = classify_document_scope(config, destination_path, frontmatter)
    apply_canonical_scope_metadata(config, frontmatter, classification)

    with MutationJournal(config, "restore", [archive_path, destination_path, index_path(config)]):
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.replace(destination_path)
        mutation_checkpoint("restore", "renamed")
        atomic_write(destination_path, render_existing_document_preserving_body(frontmatter, doc.body))
        mutation_checkpoint("restore", "metadata_written")
        archive_directory_removed = remove_empty_directory(
            archive_path.parent,
            {fundus_archive_dir(config), fundus_root_dir(config)},
        )
        refresh_index_entry(config, archive_path)
        refresh_index_entry(config, destination_path)
        mutation_checkpoint("restore", "index_written")
    return {
        "path": str(destination_path.relative_to(config.vault_path)),
        "archived_path": doc.relative_path,
        "title": doc.title,
        "restored_at": timestamp,
        "archive_directory_removed": archive_directory_removed,
        "previous_revision": previous_revision,
        "revision": path_revision(destination_path),
    }


@serialized_mutation
def area_init(config: Config, project_name: str, area: str, area_type: str, title: str) -> dict[str, Any]:
    scope = area_scope(area)
    root = fundus_scope_dir(config, scope)
    created_paths: list[str] = []
    skipped_paths: list[str] = []

    for directory in AREA_SUBDIRECTORIES:
        path = ensure_within(root, root / directory)
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
        path = ensure_within(root, root / filename)
        if path.exists():
            skipped_paths.append(str(path.relative_to(config.vault_path)))
            continue
        if filename in RESERVED_FILENAMES:
            reserved_path = ReservedFilePath.resolve(config, path).path
            atomic_write(reserved_path, f"# {file_title}\n\n{body.strip()}\n")
            refresh_index_entry(config, reserved_path)
            created_paths.append(str(reserved_path.relative_to(config.vault_path)))
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
        note_path = resolve_active_note_path(config, path)
        atomic_write(note_path, render_document(frontmatter, body))
        refresh_index_entry(config, note_path)
        created_paths.append(str(note_path.relative_to(config.vault_path)))

    return {
        "area": scope.path,
        "path": str(root.relative_to(config.vault_path)),
        "created": created_paths,
        "skipped": skipped_paths,
        "directories": [str((root / directory).relative_to(config.vault_path)) for directory in AREA_SUBDIRECTORIES],
    }


def redirect_frontmatter_for_move(
    config: Config,
    doc: Document,
    source_classification: ScopeClassification,
    destination_path: Path,
) -> dict[str, Any]:
    timestamp = now_iso()
    destination = str(destination_path.relative_to(config.vault_path))
    source_id_path = Path(source_classification.active_relative_path).with_suffix("").as_posix()
    frontmatter: dict[str, Any] = {
        "type": "Redirect",
        "title": doc.title,
        "description": f"Redirect to {destination}.",
        "id": f"redirect/{slugify_path(source_id_path)}",
        "scope": source_classification.scope.kind,
        "scope_path": source_classification.scope.path,
        "created": str(doc.frontmatter.get("created") or timestamp),
        "updated": timestamp,
        "timestamp": timestamp,
        "redirect_to": destination,
        "moved_to": destination,
        "tags": normalize_scope_tags(
            config,
            source_classification.project or "",
            source_classification.scope,
            ["redirect"],
        ),
    }
    if source_classification.project:
        frontmatter["project"] = source_classification.project
    return frontmatter


@serialized_mutation
def move_document(
    config: Config,
    source_arg: str,
    destination_arg: str,
    leave_stub: bool = False,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    source_path = resolve_active_note_path(config, source_arg)
    destination_path = resolve_active_note_path(config, destination_arg)
    if not source_path.exists():
        raise FundusError(f"Document does not exist: {source_arg}", "NOTE_NOT_FOUND")
    previous_revision = assert_expected_revision(source_path, expected_revision)
    if destination_path.exists():
        raise FundusError(f"Move destination already exists: {destination_arg}")
    root = fundus_root_dir(config)
    ensure_within(root, source_path)
    ensure_within(root, destination_path)
    if ARCHIVE_DIRNAME in source_path.relative_to(root).parts or ARCHIVE_DIRNAME in destination_path.relative_to(root).parts:
        raise FundusError("Move source and destination must be active Fundus paths, not archive paths.")

    doc = load_document(source_path, config.vault_path)
    if is_redirect_frontmatter(doc.frontmatter):
        raise FundusError("Move the redirect target instead of a redirect stub.", "REDIRECT_MOVE_INVALID")
    source_classification = classify_document_scope(config, source_path, doc.frontmatter)
    destination_classification = classify_document_scope(config, destination_path, doc.frontmatter)
    moved_frontmatter = clone_frontmatter(doc.frontmatter)
    moved_frontmatter["updated"] = now_iso()
    moved_frontmatter["moved_from"] = doc.relative_path
    apply_canonical_scope_metadata(config, moved_frontmatter, destination_classification)

    with MutationJournal(config, "move", [source_path, destination_path, index_path(config)]):
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.replace(destination_path)
        mutation_checkpoint("move", "renamed")
        atomic_write(destination_path, render_existing_document_preserving_body(moved_frontmatter, doc.body))
        mutation_checkpoint("move", "metadata_written")
        if leave_stub:
            redirect_frontmatter = redirect_frontmatter_for_move(
                config,
                doc,
                source_classification,
                destination_path,
            )
            relative_target = Path(os.path.relpath(destination_path, start=source_path.parent)).as_posix()
            stub_body = f"# {doc.title}\n\nMoved to [{destination_path.name}]({relative_target}).\n"
            atomic_write(source_path, render_existing_document(redirect_frontmatter, stub_body))
            mutation_checkpoint("move", "redirect_written")
        else:
            remove_empty_directory(source_path.parent, {fundus_root_dir(config), fundus_archive_dir(config)})
        refresh_index_entry(config, source_path)
        refresh_index_entry(config, destination_path)
        mutation_checkpoint("move", "index_written")
    return {
        "path": str(destination_path.relative_to(config.vault_path)),
        "original_path": doc.relative_path,
        "title": doc.title,
        "stub_left": leave_stub,
        "scope": destination_classification.scope.kind,
        "scope_path": destination_classification.scope.path,
        "redirect_path": doc.relative_path if leave_stub else None,
        "previous_revision": previous_revision,
        "revision": path_revision(destination_path),
        "redirect_revision": path_revision(source_path) if leave_stub else None,
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
    load_result = load_index_result(config)
    data = load_result.data
    markdown_paths = iter_fundus_markdown_paths(config)
    markdown_count = len(markdown_paths)
    indexed_count = len(data["documents"]) if data else 0
    indexed_records = {str(doc.get("path")): doc for doc in data["documents"]} if data else {}
    stale_paths: list[str] = []
    if data:
        for markdown_path in markdown_paths:
            relative_path = str(markdown_path.relative_to(config.vault_path))
            record = indexed_records.get(relative_path)
            if record is None or not index_record_is_fresh(record, markdown_path):
                stale_paths.append(relative_path)
        markdown_relative_paths = {str(markdown_path.relative_to(config.vault_path)) for markdown_path in markdown_paths}
        for indexed_path in indexed_records:
            if indexed_path not in markdown_relative_paths:
                stale_paths.append(str(indexed_path))
    elif markdown_paths:
        stale_paths.extend(str(markdown_path.relative_to(config.vault_path)) for markdown_path in markdown_paths)
    return {
        "path": str(path.relative_to(config.vault_path)),
        "exists": path.exists(),
        "valid": load_result.state == "current",
        "state": load_result.state,
        "error": load_result.error,
        "documents": indexed_count,
        "markdown_documents": markdown_count,
        "generated": data.get("generated") if data else None,
        "stale": load_result.state != "current" or indexed_count != markdown_count or bool(stale_paths),
        "stale_paths": sorted(set(stale_paths))[:20],
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
        provenance={**config.provenance, "fundus_dir": "explicit operation argument"},
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
        frontmatter, _ = parse_frontmatter(read_note_text(source_path))
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
    text = read_note_text(source_path)
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
    return render_existing_document_preserving_body(frontmatter, body)


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
        frontmatter, body = parse_frontmatter(read_note_text(path))
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
        frontmatter, _ = parse_frontmatter(read_note_text(path))
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
            else:
                try:
                    classification = classify_document_scope(verify_config, path, frontmatter)
                except FundusError as exc:
                    issues.append({"path": relative_path, "reason": "scope_path_invalid", "code": exc.code})
                    continue
                metadata_matches = (
                    frontmatter.get("scope") == classification.scope.kind
                    and frontmatter.get("scope_path") == classification.scope.path
                    and (
                        str(frontmatter.get("project") or "") == (classification.project or "")
                    )
                )
                expected_scope_tag = (
                    f"project/{classification.project}"
                    if classification.project
                    else f"area/{slugify_path(classification.scope.path)}"
                )
                tags = frontmatter_list(frontmatter.get("tags"))
                if not metadata_matches or expected_scope_tag not in tags:
                    issues.append({"path": relative_path, "reason": "scope_metadata_mismatch"})
                if is_redirect_frontmatter(frontmatter):
                    try:
                        resolve_redirect_document_path(verify_config, path)
                    except FundusError as exc:
                        issues.append({"path": relative_path, "reason": "redirect_invalid", "code": exc.code})

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


@serialized_mutation
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
    mutation_checkpoint("migration", "promoted")
    cleanup_empty_directories(config_with_fundus_dir(config, str(migration_staging_root_dir(config).relative_to(config.vault_path))), "", global_scope=True)

    repaired_archive_original_paths = repair_archive_original_paths(config, target_dir)
    index_payload = rebuild_index(config_with_fundus_dir(config, target_dir))
    final_verification = verify_fundus_corpus(config, target_dir)
    if not final_verification["passed"]:
        raise FundusError(f"Final migration verification failed: {final_verification['issues']}")
    mutation_checkpoint("migration", "verified")

    retired_path = None
    if retire_source == "rename":
        retired_path = retire_migration_source(config, source_dir, migration_id)
        mutation_checkpoint("migration", "source_retired")

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
    config_sources = sorted(set(config.provenance.values()))

    return {
        "project_root": str(project_root),
        "project": project_name,
        "project_name_valid": True,
        "scope": scope.kind,
        "scope_path": scope.path,
        "scope_classification": {
            "kind": scope.kind,
            "logical_root": scope.path,
            "allowed_area_roots": sorted(AREA_ROOT_DIRNAMES),
        },
        "config_sources": config_sources,
        "config_provenance": dict(config.provenance),
        "vault_path": str(config.vault_path),
        "fundus_dir": config.fundus_dir,
        "fundus_root": str(root),
        "python_executable": sys.executable,
        "plugin_root": str(SKILL_DIR.parent.parent if (SKILL_DIR.parent.parent / ".codex-plugin").exists() else SKILL_DIR),
        "fundus_root_exists": root.exists(),
        "scope_fundus_dir": str(scope_dir),
        "scope_fundus_exists": scope_dir.exists(),
        "path_policy": {
            "ordinary_notes_root": str(root),
            "archive_root": str(fundus_archive_dir(config)),
            "reserved_files": sorted(RESERVED_FILENAMES),
            "markdown_required": True,
            "symlink_escape_protection": True,
        },
        "index": index_status(config),
        "mutation_lock": mutation_lock_status(config),
        "pending_mutation_journals": (
            len([path for path in journal_root_dir(config).iterdir() if path.is_dir()])
            if journal_root_dir(config).exists()
            else 0
        ),
        "writes_possible": root.exists() or os.access(config.vault_path, os.W_OK),
    }


def add_area_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--area", default=argparse.SUPPRESS, help="Target an explicit Fundus area path under the Fundus root.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage persistent Fundus documents for the active project.")
    parser.add_argument("--project", help="Override the auto-detected project name.")
    parser.add_argument("--area", help="Target an explicit Fundus area path under the Fundus root.")
    parser.add_argument("--vault-path", help="Override the configured Obsidian vault path for this operation.")
    parser.add_argument("--fundus-dir", help="Override the configured Fundus directory for this operation.")
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

    propose_create_parser = subparsers.add_parser("propose-create", help="Plan a create and report duplicate candidates without writing.")
    add_area_argument(propose_create_parser)
    propose_create_parser.add_argument("--title", required=True)
    propose_create_parser.add_argument("--type", dest="doc_type")
    propose_create_parser.add_argument("--description")
    propose_create_parser.add_argument("--id", dest="document_id")
    propose_create_parser.add_argument("--alias", action="append", dest="aliases")
    propose_create_parser.add_argument("--resource")
    propose_create_parser.add_argument("--status")
    propose_create_parser.add_argument("--owner")
    propose_create_parser.add_argument("--last-verified")
    propose_create_parser.add_argument("--verified-against", action="append", dest="verified_against")
    propose_create_parser.add_argument("--source-fingerprint")
    propose_create_parser.add_argument("--verification-status", choices=["current", "stale", "unverified"])
    propose_create_parser.add_argument("--content")
    propose_create_parser.add_argument("--content-file")
    propose_create_parser.add_argument("--tag", action="append", dest="tags")

    apply_create_parser = subparsers.add_parser("apply-create", help="Apply a create proposal after duplicate review.")
    apply_create_parser.add_argument("--proposal-file", required=True)
    apply_create_parser.add_argument("--duplicate-override", action="store_true")
    apply_create_parser.add_argument("--reviewed-duplicate", action="append", dest="reviewed_duplicate_paths")

    update_parser = subparsers.add_parser("update", help="Append to, replace a section in, or rewrite a document.")
    add_area_argument(update_parser)
    update_parser.add_argument("--path", required=True, help="Fundus document path relative to the vault root.")
    update_parser.add_argument("--mode", required=True, choices=["append", "replace", "rewrite"], help="Update mode.")
    update_parser.add_argument("--section", help="Section heading to replace when using replace mode.")
    update_parser.add_argument("--content", help="Inline markdown content.")
    update_parser.add_argument("--content-file", help="Path to a markdown file containing the new content.")
    update_parser.add_argument("--expected-revision", help="SHA-256 revision returned by read or scan.")

    propose_update_parser = subparsers.add_parser("propose-update", help="Plan a revision-bound note update without writing.")
    propose_update_parser.add_argument("--path", required=True)
    propose_update_parser.add_argument("--mode", required=True, choices=["append", "replace", "rewrite"])
    propose_update_parser.add_argument("--section")
    propose_update_parser.add_argument("--content")
    propose_update_parser.add_argument("--content-file")
    propose_update_parser.add_argument("--metadata-file", help="JSON object containing allowed metadata changes.")

    apply_update_parser = subparsers.add_parser("apply-update", help="Apply an update proposal at its expected revision.")
    apply_update_parser.add_argument("--proposal-file", required=True)
    apply_update_parser.add_argument("--duplicate-override", action="store_true")
    apply_update_parser.add_argument("--reviewed-duplicate", action="append", dest="reviewed_duplicate_paths")

    mark_stale_parser = subparsers.add_parser("mark-stale", help="Record that a note no longer matches current evidence.")
    mark_stale_parser.add_argument("--path", required=True)
    mark_stale_parser.add_argument("--reason", required=True)
    mark_stale_parser.add_argument("--expected-revision")

    verify_note_parser = subparsers.add_parser("verify-note", help="Record current source evidence for a note.")
    verify_note_parser.add_argument("--path", required=True)
    verify_note_parser.add_argument("--verified-against", action="append", dest="verified_against")
    verify_note_parser.add_argument("--source-fingerprint")
    verify_note_parser.add_argument("--expected-revision")

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
    frontmatter_parser.add_argument("--expected-revision", help="SHA-256 revision returned by read or scan.")

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
    move_parser.add_argument("--expected-revision", help="SHA-256 revision returned by read or scan.")

    backup_parser = subparsers.add_parser("backup", help="Create and inspect Fundus backups.")
    backup_subparsers = backup_parser.add_subparsers(dest="backup_command", required=True)
    backup_create_parser = backup_subparsers.add_parser("create", help="Create a backup of the configured Fundus directory.")
    backup_create_parser.add_argument("--label", help="Human label included in the backup id and manifest.")
    backup_subparsers.add_parser("list", help="List available Fundus backups.")
    backup_inspect_parser = backup_subparsers.add_parser("inspect", help="Inspect one backup manifest.")
    backup_inspect_parser.add_argument("--id", required=True, help="Backup id returned by backup create or backup list.")
    backup_verify_parser = backup_subparsers.add_parser("verify", help="Verify one backup against its checksums.")
    backup_verify_parser.add_argument("--id", required=True, help="Backup id returned by backup create or backup list.")
    backup_restore_parser = backup_subparsers.add_parser("restore", help="Dry-run or apply a verified full Fundus restore.")
    backup_restore_parser.add_argument("--id", required=True, help="Backup id returned by backup create or backup list.")
    backup_restore_parser.add_argument("--apply", action="store_true", help="Apply the restore after verification and a safety backup.")

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
    archive_apply_parser.add_argument("--expected-revision", help="SHA-256 revision returned by read or scan.")
    archive_restore_parser = archive_subparsers.add_parser("restore", help="Restore one archived Fundus note to its original path.")
    archive_restore_parser.add_argument("--path", required=True, help="Archived Fundus document path relative to the vault root.")
    archive_restore_parser.add_argument("--expected-revision", help="SHA-256 revision returned by read or scan.")
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
        explicit_config = {
            key: value
            for key, value in {
                "vault_path": args.vault_path,
                "fundus_dir": args.fundus_dir,
            }.items()
            if value is not None
        }
        config = resolve_config(project_root, explicit_config)
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
            print(json.dumps(read_document_result(config, args.path), indent=2))
            return 0

        if args.command == "propose-create":
            content = read_content_arg(args.content, args.content_file)
            proposal = propose_create_document(
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
                args.verified_against,
                args.source_fingerprint,
                args.verification_status,
            )
            print(json.dumps(proposal, indent=2))
            return 0

        if args.command == "apply-create":
            proposal = read_json_object_file(args.proposal_file)
            print(
                json.dumps(
                    apply_create_proposal(
                        config,
                        proposal,
                        args.duplicate_override,
                        args.reviewed_duplicate_paths,
                    ),
                    indent=2,
                )
            )
            return 0

        if args.command == "propose-update":
            content = read_content_arg(args.content, args.content_file)
            metadata_changes = read_json_object_file(args.metadata_file) if args.metadata_file else None
            print(
                json.dumps(
                    propose_update_document(
                        config,
                        args.path,
                        args.mode,
                        content,
                        args.section,
                        metadata_changes,
                    ),
                    indent=2,
                )
            )
            return 0

        if args.command == "apply-update":
            proposal = read_json_object_file(args.proposal_file)
            print(
                json.dumps(
                    apply_update_proposal(
                        config,
                        proposal,
                        args.duplicate_override,
                        args.reviewed_duplicate_paths,
                    ),
                    indent=2,
                )
            )
            return 0

        if args.command == "mark-stale":
            print(json.dumps(mark_note_stale(config, args.path, args.reason, args.expected_revision), indent=2))
            return 0

        if args.command == "verify-note":
            print(
                json.dumps(
                    verify_note(
                        config,
                        args.path,
                        args.verified_against,
                        args.source_fingerprint,
                        args.expected_revision,
                    ),
                    indent=2,
                )
            )
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
            payload = update_document(
                config,
                project_name,
                args.path,
                args.mode,
                content,
                args.section,
                scope,
                args.expected_revision,
            )
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
                args.expected_revision,
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
            payload = move_document(config, args.source, args.destination, args.leave_stub, args.expected_revision)
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
            if args.backup_command == "verify":
                print(json.dumps(verify_backup(config, args.id), indent=2))
                return 0
            if args.backup_command == "restore":
                print(json.dumps(restore_backup(config, args.id, args.apply), indent=2))
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
                print(json.dumps(archive_document(config, args.path, args.reason, args.expected_revision), indent=2))
                return 0
            if args.archive_command == "restore":
                print(json.dumps(restore_document(config, args.path, args.expected_revision), indent=2))
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
        print(json.dumps({"error": str(exc), "code": exc.code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
