#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parent.parent
SKILL_CONFIG_PATH = SKILL_DIR / "config.json"
DEFAULT_CONFIG = {
    "wiki_dir": "Wiki",
    "default_tags": ["wiki"],
    "redaction": {
        "enabled": True,
        "patterns": ["API_KEY", "SECRET", "TOKEN", "PASSWORD"],
    },
}


class WikiError(Exception):
    pass


@dataclass
class Config:
    vault_path: Path
    wiki_dir: str
    default_tags: list[str]
    redaction_enabled: bool
    redaction_patterns: list[str]


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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise WikiError(f"Invalid JSON config at {path}: {exc}") from exc


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
        if (path / ".codex" / "obsidian-wiki.json").exists() or (path / ".git").exists():
            return path

    return candidate


def project_config_path(project_root: Path) -> Path:
    return project_root / ".codex" / "obsidian-wiki.json"


def resolve_config(project_root: Path) -> Config:
    merged: dict[str, Any] = deep_merge(DEFAULT_CONFIG, load_json(SKILL_CONFIG_PATH))
    merged = deep_merge(merged, load_json(project_config_path(project_root)))

    env_vault = os.getenv("OBSIDIAN_VAULT_PATH")
    if env_vault:
        merged["vault_path"] = env_vault

    vault_path = merged.get("vault_path")
    if not vault_path:
        raise WikiError(
            "Missing vault_path. Set OBSIDIAN_VAULT_PATH or add it to .codex/obsidian-wiki.json or the skill config."
        )

    wiki_dir = merged.get("wiki_dir") or DEFAULT_CONFIG["wiki_dir"]
    default_tags = merged.get("default_tags") or list(DEFAULT_CONFIG["default_tags"])
    redaction = merged.get("redaction") or {}

    return Config(
        vault_path=Path(vault_path).expanduser().resolve(),
        wiki_dir=str(wiki_dir).strip("/") or DEFAULT_CONFIG["wiki_dir"],
        default_tags=list(default_tags),
        redaction_enabled=bool(redaction.get("enabled", True)),
        redaction_patterns=list(redaction.get("patterns") or DEFAULT_CONFIG["redaction"]["patterns"]),
    )


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise WikiError("Title must contain at least one alphanumeric character.")
    return slug


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
        raise WikiError(f"Resolved path escapes the vault root: {target}") from exc
    return target_resolved


def wiki_project_dir(config: Config, project_name: str) -> Path:
    project_dir = config.vault_path / config.wiki_dir / project_name
    return ensure_within(config.vault_path, project_dir)


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
    for key in ["title", "created", "updated", "project", "tags"]:
        value = data.get(key)
        if key == "tags":
            lines.append("tags:")
            for tag in value or []:
                lines.append(f"  - {tag}")
            continue
        if value is not None:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def read_content_arg(content: str | None, content_file: str | None) -> str:
    if bool(content) == bool(content_file):
        raise WikiError("Provide exactly one of --content or --content-file.")
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
    )


def resolve_doc_path(config: Config, path_arg: str) -> Path:
    raw_path = Path(path_arg).expanduser()
    if raw_path.is_absolute():
        return ensure_within(config.vault_path, raw_path)
    return ensure_within(config.vault_path, config.vault_path / raw_path)


def scan_documents(config: Config, project_name: str, query: str | None) -> list[dict[str, Any]]:
    project_dir = wiki_project_dir(config, project_name)
    if not project_dir.exists():
        return []

    query_terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_-]+", query or "")]
    documents: list[dict[str, Any]] = []

    for path in sorted(project_dir.glob("*.md")):
        doc = load_document(path, config.vault_path)
        haystack = " ".join([doc.title, *doc.tags, path.name]).lower()
        if query_terms and not all(term in haystack for term in query_terms):
            continue
        documents.append(
            {
                "path": doc.relative_path,
                "title": doc.title,
                "tags": doc.tags,
                "updated": doc.updated,
            }
        )

    return documents


def render_document(frontmatter: dict[str, Any], body: str) -> str:
    cleaned_body = body.strip()
    return f"{format_frontmatter(frontmatter)}\n\n# {frontmatter['title']}\n\n{cleaned_body}\n"


def create_document(config: Config, project_name: str, title: str, body: str, extra_tags: list[str] | None) -> dict[str, Any]:
    project_dir = wiki_project_dir(config, project_name)
    slug = slugify(title)
    path = ensure_within(config.vault_path, project_dir / f"{slug}.md")
    if path.exists():
        raise WikiError(f"Document already exists: {path.relative_to(config.vault_path)}")

    timestamp = now_iso()
    frontmatter = {
        "title": title.strip(),
        "created": timestamp,
        "updated": timestamp,
        "project": project_name,
        "tags": normalize_tags(config, project_name, extra_tags),
    }
    content = render_document(frontmatter, redact_secrets(body, config))
    atomic_write(path, content)
    return {
        "path": str(path.relative_to(config.vault_path)),
        "title": title.strip(),
        "created": timestamp,
        "updated": timestamp,
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
) -> dict[str, Any]:
    path = resolve_doc_path(config, path_arg)
    if not path.exists():
        raise WikiError(f"Document does not exist: {path_arg}")

    text = path.read_text()
    frontmatter, body = parse_frontmatter(text)
    if not frontmatter:
        raise WikiError(f"Document is missing expected frontmatter: {path}")

    redacted_content = redact_secrets(new_content, config)
    if mode == "append":
        updated_body = append_body(body, redacted_content)
    else:
        if not section:
            raise WikiError("--section is required when mode is replace.")
        updated_body = replace_section(body, section, redacted_content)

    frontmatter["updated"] = now_iso()
    if not frontmatter.get("project"):
        frontmatter["project"] = project_name
    if not frontmatter.get("tags"):
        frontmatter["tags"] = normalize_tags(config, project_name, [])

    rendered = f"{format_frontmatter(frontmatter)}\n\n{updated_body.strip()}\n"
    atomic_write(path, rendered)
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
        raise WikiError(f"Document does not exist: {path_arg}")
    return path.read_text()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage persistent Obsidian wiki documents for the active project.")
    parser.add_argument("--project", help="Override the auto-detected project name.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="List wiki documents for the active project.")
    scan_parser.add_argument("--query", help="Optional keywords to filter by title, tags, or filename.")

    read_parser = subparsers.add_parser("read", help="Read a wiki document.")
    read_parser.add_argument("--path", required=True, help="Wiki document path relative to the vault root.")

    create_parser = subparsers.add_parser("create", help="Create a new wiki document.")
    create_parser.add_argument("--title", required=True, help="Document title.")
    create_parser.add_argument("--content", help="Inline markdown content.")
    create_parser.add_argument("--content-file", help="Path to a markdown file containing the body content.")
    create_parser.add_argument("--tag", action="append", dest="tags", help="Additional tag to add.")

    update_parser = subparsers.add_parser("update", help="Append to or replace a document section.")
    update_parser.add_argument("--path", required=True, help="Wiki document path relative to the vault root.")
    update_parser.add_argument("--mode", required=True, choices=["append", "replace"], help="Update mode.")
    update_parser.add_argument("--section", help="Section heading to replace when using replace mode.")
    update_parser.add_argument("--content", help="Inline markdown content.")
    update_parser.add_argument("--content-file", help="Path to a markdown file containing the new content.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        project_root = discover_project_root()
        config = resolve_config(project_root)
        project_name = args.project or detect_project_name(project_root)

        if args.command == "scan":
            payload = {
                "project": project_name,
                "documents": scan_documents(config, project_name, args.query),
            }
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "read":
            print(read_document(config, args.path))
            return 0

        if args.command == "create":
            content = read_content_arg(args.content, args.content_file)
            payload = create_document(config, project_name, args.title, content, args.tags)
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "update":
            content = read_content_arg(args.content, args.content_file)
            payload = update_document(config, project_name, args.path, args.mode, content, args.section)
            print(json.dumps(payload, indent=2))
            return 0

        raise WikiError(f"Unknown command: {args.command}")
    except WikiError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
