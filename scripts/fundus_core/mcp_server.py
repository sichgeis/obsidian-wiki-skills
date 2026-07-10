#!/usr/bin/env python3
from __future__ import annotations

import argparse
import inspect
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import fundus as fundus_core


@dataclass(frozen=True)
class FundusContext:
    project_root: Path
    config: fundus_core.Config
    project_name: str
    scope: fundus_core.Scope


def resolve_context(project: str | None = None, project_root: str | None = None, area: str | None = None) -> FundusContext:
    if project and area:
        raise fundus_core.FundusError("project and area cannot both be provided.")
    start = Path(project_root).expanduser().resolve() if project_root else Path.cwd()
    resolved_root = fundus_core.discover_project_root(start)
    config = fundus_core.resolve_config(resolved_root)
    project_name = project or fundus_core.detect_project_name(resolved_root)
    return FundusContext(
        project_root=resolved_root,
        config=config,
        project_name=project_name,
        scope=fundus_core.resolve_scope(project_name, area),
    )


def scan_fundus(
    query: str | None = None,
    limit: int = fundus_core.MAX_SCAN_RESULTS,
    include_snippet: bool = False,
    include_archived: bool = False,
    project: str | None = None,
    project_root: str | None = None,
    area: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    return {
        "project": context.project_name,
        "scope": context.scope.kind,
        "scope_path": context.scope.path,
        "documents": fundus_core.scan_documents(
            context.config,
            context.project_name,
            query,
            limit,
            include_snippet,
            include_archived,
            context.scope,
        ),
    }


def read_note(
    path: str,
    cursor: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.read_document_page(context.config, path, cursor)


def create_note(
    title: str,
    content: str,
    tags: list[str] | None = None,
    type: str | None = None,
    description: str | None = None,
    id: str | None = None,
    aliases: list[str] | None = None,
    resource: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    last_verified: str | None = None,
    verified_against: list[str] | None = None,
    source_fingerprint: str | None = None,
    verification_status: str | None = None,
    project: str | None = None,
    project_root: str | None = None,
    area: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    return fundus_core.create_document(
        context.config,
        context.project_name,
        title,
        content,
        tags,
        context.scope,
        type,
        description,
        id,
        aliases,
        resource,
        status,
        owner,
        last_verified,
        verified_against,
        source_fingerprint,
        verification_status,
    )


def propose_create(
    title: str,
    content: str,
    tags: list[str] | None = None,
    type: str | None = None,
    description: str | None = None,
    id: str | None = None,
    aliases: list[str] | None = None,
    resource: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    last_verified: str | None = None,
    verified_against: list[str] | None = None,
    source_fingerprint: str | None = None,
    verification_status: str | None = None,
    project: str | None = None,
    project_root: str | None = None,
    area: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    return fundus_core.propose_create_document(
        context.config,
        context.project_name,
        title,
        content,
        tags,
        context.scope,
        type,
        description,
        id,
        aliases,
        resource,
        status,
        owner,
        last_verified,
        verified_against,
        source_fingerprint,
        verification_status,
    )


def apply_create(
    proposal: dict[str, Any],
    duplicate_override: bool = False,
    reviewed_duplicate_paths: list[str] | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.apply_create_proposal(
        context.config,
        proposal,
        duplicate_override,
        reviewed_duplicate_paths,
    )


def update_note(
    path: str,
    mode: Literal["append", "replace", "rewrite"],
    content: str,
    section: str | None = None,
    project: str | None = None,
    project_root: str | None = None,
    area: str | None = None,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    return fundus_core.update_document(
        context.config,
        context.project_name,
        path,
        mode,
        content,
        section,
        context.scope,
        expected_revision,
    )


def propose_update(
    path: str,
    mode: Literal["append", "replace", "rewrite"],
    content: str,
    section: str | None = None,
    metadata_changes: dict[str, Any] | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.propose_update_document(
        context.config,
        path,
        mode,
        content,
        section,
        metadata_changes,
    )


def apply_update(
    proposal: dict[str, Any],
    duplicate_override: bool = False,
    reviewed_duplicate_paths: list[str] | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.apply_update_proposal(
        context.config,
        proposal,
        duplicate_override,
        reviewed_duplicate_paths,
    )


def mark_stale(
    path: str,
    reason: str,
    expected_revision: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.mark_note_stale(context.config, path, reason, expected_revision)


def verify_note(
    path: str,
    verified_against: list[str] | None = None,
    source_fingerprint: str | None = None,
    expected_revision: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.verify_note(
        context.config,
        path,
        verified_against,
        source_fingerprint,
        expected_revision,
    )


def add_frontmatter(
    path: str,
    title: str | None = None,
    tags: list[str] | None = None,
    type: str | None = None,
    description: str | None = None,
    id: str | None = None,
    aliases: list[str] | None = None,
    resource: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    last_verified: str | None = None,
    project: str | None = None,
    project_root: str | None = None,
    area: str | None = None,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    return fundus_core.add_frontmatter_to_document(
        context.config,
        context.project_name,
        path,
        title,
        tags,
        context.scope,
        type,
        description,
        id,
        aliases,
        resource,
        status,
        owner,
        last_verified,
        expected_revision,
    )


def normalize_frontmatter(
    path: str | None = None,
    apply: bool = False,
    add_missing: bool = False,
    include_archived: bool = False,
    global_scope: bool = False,
    limit: int | None = None,
    project: str | None = None,
    project_root: str | None = None,
    area: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    return fundus_core.normalize_frontmatter_paths(
        context.config,
        context.project_name,
        context.scope,
        path,
        global_scope,
        include_archived,
        apply,
        add_missing,
        limit,
    )


def move_note(
    path: str,
    destination: str,
    leave_stub: bool = False,
    expected_revision: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.move_document(context.config, path, destination, leave_stub, expected_revision)


def backup_create(label: str | None = None, project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.create_backup(context.config, label)


def backup_list(project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return {"backups": fundus_core.list_backups(context.config)}


def backup_inspect(id: str, project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.inspect_backup(context.config, id)


def backup_verify(id: str, project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.verify_backup(context.config, id)


def backup_restore(id: str, apply: bool = False, project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.restore_backup(context.config, id, apply)


def area_init(
    area: str,
    title: str,
    type: str = "Area",
    project: str | None = None,
    project_root: str | None = None,
    with_index: bool = False,
    with_log: bool = False,
) -> dict[str, Any]:
    context = resolve_context(project, project_root)
    return fundus_core.area_init(context.config, context.project_name, area, type, title, with_index, with_log)


def index_status(project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.index_status(context.config)


def index_rebuild(project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    payload = fundus_core.rebuild_index(context.config)
    return {
        "path": str(fundus_core.index_path(context.config).relative_to(context.config.vault_path)),
        "documents": len(payload["documents"]),
        "generated": payload["generated"],
    }


def migrate_wiki_to_fundus(
    mode: Literal["dry-run", "apply", "verify"] = "dry-run",
    source_dir: str = fundus_core.DEFAULT_LEGACY_SOURCE_DIR,
    destination_dir: str | None = None,
    retire_source: Literal["rename", "keep"] = "rename",
    backup_label: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    target_dir = destination_dir or context.config.fundus_dir
    if mode == "dry-run":
        return fundus_core.migration_plan(context.config, source_dir, target_dir)
    if mode == "verify":
        return fundus_core.verify_fundus_corpus(context.config, target_dir)
    if mode == "apply":
        return fundus_core.apply_wiki_to_fundus_migration(
            context.config,
            source_dir,
            target_dir,
            retire_source,
            backup_label,
        )
    raise fundus_core.FundusError("mode must be dry-run, apply, or verify.")


def archive_candidates(
    older_than_days: int = 90,
    limit: int = fundus_core.MAX_SCAN_RESULTS,
    force: bool = False,
    global_scope: bool = False,
    project: str | None = None,
    project_root: str | None = None,
    area: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    candidates = (
        fundus_core.archive_candidates_global(context.config, older_than_days, limit, force)
        if global_scope
        else fundus_core.archive_candidates(context.config, context.project_name, older_than_days, limit, force, context.scope)
    )
    return {
        "scope": "global" if global_scope else context.scope.kind,
        "scope_path": None if global_scope else context.scope.path,
        "project": None if global_scope or context.scope.kind != "project" else context.project_name,
        "candidates": candidates,
    }


def archive_apply(
    path: str,
    reason: str | None = None,
    expected_revision: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.archive_document(context.config, path, reason, expected_revision)


def archive_restore(
    path: str,
    expected_revision: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.restore_document(context.config, path, expected_revision)


def archive_cleanup(
    global_scope: bool = False,
    project: str | None = None,
    project_root: str | None = None,
    area: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    return fundus_core.cleanup_empty_directories(context.config, context.project_name, global_scope, context.scope)


def archive_status(project: str | None = None, project_root: str | None = None, area: str | None = None) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    return fundus_core.archive_status(context.config, context.project_name, context.scope)


def doctor(project: str | None = None, project_root: str | None = None, area: str | None = None) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    return fundus_core.doctor_report_for_scope(context.config, context.project_root, context.project_name, context.scope)


SUPPORTED_MCP_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18")
MCP_PROTOCOL_VERSION = SUPPORTED_MCP_PROTOCOL_VERSIONS[0]
DEFAULT_SERVER_VERSION = "0.0.0+unknown"
SERVER_NOT_INITIALIZED = -32002
NONE_TYPE = type(None)


def discover_server_version() -> str:
    for root in SCRIPT_DIR.parents:
        manifest_path = root / ".codex-plugin" / "plugin.json"
        if not manifest_path.exists():
            continue
        try:
            version = json.loads(manifest_path.read_text()).get("version")
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(version, str) and version:
            return version
    return DEFAULT_SERVER_VERSION


@dataclass(frozen=True)
class OperationSpec:
    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Any
    annotations: dict[str, bool]
    category: Literal["workbench", "admin", "compatibility"]
    listed: bool = True
    deprecated: bool = False


PARAMETER_DESCRIPTIONS = {
    "query": "Search phrase, ticket key, domain term, alias, or resource URL.",
    "limit": "Maximum number of results to return.",
    "include_snippet": "Include a short matching body excerpt in results.",
    "include_archived": "Include archived notes in retrieval.",
    "project": "Project scope override; cannot be combined with area.",
    "project_root": "Repository or working directory used to resolve Fundus config.",
    "area": "Explicit cross-repository Fundus area path.",
    "path": "Fundus note path relative to the vault, for example Fundus/demo/note.md.",
    "cursor": "Opaque continuation cursor from the previous read page; omit to start or restart.",
    "title": "Human-readable note title.",
    "content": "Markdown content to create or write.",
    "tags": "Additional tags beyond configured Fundus defaults.",
    "type": "Knowledge type such as Concept, Decision, Ticket, Epic, Area, or Guide.",
    "description": "Short retrieval-oriented note summary.",
    "id": "Stable OKF-style identifier.",
    "aliases": "Alternative names, ticket keys, or phrases that should retrieve this note.",
    "resource": "Canonical external resource URL such as Jira, GitHub, Slack, or Confluence.",
    "status": "Lifecycle status such as active or stale.",
    "owner": "Person or system responsible for keeping the note useful.",
    "last_verified": "Date when the note was last checked against source truth.",
    "verified_against": "Evidence identifiers used to verify this note.",
    "source_fingerprint": "Stable source identifier including revision or content hash.",
    "verification_status": "Verification state: current, stale, or unverified.",
    "expected_revision": "SHA-256 revision returned by read or scan; mismatches fail without writing.",
    "proposal": "Proposal object returned by the matching propose operation.",
    "duplicate_override": "Apply after explicitly reviewing all returned duplicate candidates.",
    "reviewed_duplicate_paths": "Every duplicate candidate path reviewed before override.",
    "metadata_changes": "Allowed retrieval, provenance, status, and verification metadata changes.",
    "mode": "Operation mode.",
    "section": "Markdown section heading to replace.",
    "apply": "Whether to write changes; false means dry-run.",
    "add_missing": "Add generated frontmatter to notes that have none.",
    "global_scope": "Operate across the whole Fundus corpus instead of the current scope.",
    "destination": "Target active Fundus path.",
    "leave_stub": "Leave a short moved-note stub at the old path.",
    "label": "Optional backup label.",
    "source_dir": "Legacy source directory under the vault.",
    "destination_dir": "Canonical destination directory under the vault.",
    "retire_source": "Whether to rename or keep the legacy source after migration.",
    "backup_label": "Optional label for the migration backup.",
    "older_than_days": "Candidate age threshold.",
    "force": "Ignore protective archive heuristics.",
    "reason": "Short archive reason.",
}


def json_schema_for_annotation(annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in (types.UnionType, Union):
        non_none_args = [arg for arg in args if arg is not NONE_TYPE]
        if len(non_none_args) == 1:
            return json_schema_for_annotation(non_none_args[0])

    if origin is Literal:
        values = list(args)
        value_types = {type(value) for value in values}
        schema_type = "string"
        if value_types == {int}:
            schema_type = "integer"
        elif value_types == {bool}:
            schema_type = "boolean"
        return {"type": schema_type, "enum": values}

    if origin is list:
        item_annotation = args[0] if args else str
        return {"type": "array", "items": json_schema_for_annotation(item_annotation)}

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is float:
        return {"type": "number"}
    if annotation is dict or origin is dict:
        return {"type": "object"}
    return {"type": "string"}


def input_schema_for_function(function: Any) -> dict[str, Any]:
    signature = inspect.signature(function)
    type_hints = get_type_hints(function)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in signature.parameters.items():
        annotation = type_hints.get(name, str)
        schema = json_schema_for_annotation(annotation)
        description = PARAMETER_DESCRIPTIONS.get(name)
        if description:
            schema = {**schema, "description": description}
        properties[name] = schema
        if parameter.default is inspect.Signature.empty:
            required.append(name)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def object_output_schema(
    properties: dict[str, dict[str, Any]] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": True,
    }
    if required:
        schema["required"] = required
    return schema


GENERIC_OUTPUT_SCHEMA = object_output_schema()
WORKBENCH_OUTPUT_SCHEMAS = {
    "search": object_output_schema(
        {
            "project": {"type": "string"},
            "scope": {"type": "string"},
            "scope_path": {"type": "string"},
            "documents": {"type": "array", "items": {"type": "object"}},
        },
        ["project", "scope", "scope_path", "documents"],
    ),
    "read": object_output_schema(
        {
            "path": {"type": "string"},
            "resolved_path": {"type": "string"},
            "content": {"type": "string"},
            "revision": {"type": "string"},
            "redirected": {"type": "boolean"},
            "offset": {"type": "integer"},
            "next_offset": {"type": "integer"},
            "total_characters": {"type": "integer"},
            "complete": {"type": "boolean"},
            "next_cursor": {"type": "string"},
        },
        [
            "path",
            "resolved_path",
            "content",
            "revision",
            "redirected",
            "offset",
            "next_offset",
            "total_characters",
            "complete",
        ],
    ),
    "propose_create": object_output_schema(
        {
            "proposal_id": {"type": "string"},
            "kind": {"type": "string"},
            "path": {"type": "string"},
            "duplicate_candidates": {"type": "array", "items": {"type": "object"}},
        },
        ["proposal_id", "kind", "path", "duplicate_candidates"],
    ),
    "apply_create": object_output_schema(
        {"proposal_id": {"type": "string"}, "path": {"type": "string"}, "revision": {"type": "string"}, "applied": {"type": "boolean"}},
        ["proposal_id", "path", "revision", "applied"],
    ),
    "propose_update": object_output_schema(
        {"proposal_id": {"type": "string"}, "path": {"type": "string"}, "expected_revision": {"type": "string"}, "diff": {"type": "string"}},
        ["proposal_id", "path", "expected_revision", "diff"],
    ),
    "apply_update": object_output_schema(
        {"proposal_id": {"type": "string"}, "path": {"type": "string"}, "revision": {"type": "string"}, "applied": {"type": "boolean"}},
        ["proposal_id", "path", "revision", "applied"],
    ),
    "create": object_output_schema(
        {"path": {"type": "string"}, "title": {"type": "string"}, "revision": {"type": "string"}},
        ["path", "title", "revision"],
    ),
    "update": object_output_schema(
        {"path": {"type": "string"}, "title": {"type": "string"}, "revision": {"type": "string"}},
        ["path", "title", "revision"],
    ),
    "move": object_output_schema(
        {"path": {"type": "string"}, "original_path": {"type": "string"}, "revision": {"type": "string"}},
        ["path", "original_path", "revision"],
    ),
    "archive": object_output_schema(
        {"path": {"type": "string"}, "original_path": {"type": "string"}, "revision": {"type": "string"}},
        ["path", "original_path", "revision"],
    ),
    "restore": object_output_schema(
        {"path": {"type": "string"}, "archived_path": {"type": "string"}, "revision": {"type": "string"}},
        ["path", "archived_path", "revision"],
    ),
    "mark_stale": object_output_schema(
        {"path": {"type": "string"}, "revision": {"type": "string"}},
        ["path", "revision"],
    ),
    "verify_note": object_output_schema(
        {"path": {"type": "string"}, "revision": {"type": "string"}},
        ["path", "revision"],
    ),
    "doctor": object_output_schema(
        {"fundus_root": {"type": "string"}, "index": {"type": "object"}},
        ["fundus_root", "index"],
    ),
}


def behavior_annotations(read_only: bool, destructive: bool, idempotent: bool) -> dict[str, bool]:
    return {
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": False,
    }


def make_operation(
    name: str,
    title: str,
    description: str,
    handler: Any,
    annotations: dict[str, bool],
    output_schema: dict[str, Any],
    category: Literal["workbench", "admin", "compatibility"],
    *,
    listed: bool = True,
    deprecated: bool = False,
) -> OperationSpec:
    return OperationSpec(
        name=name,
        title=title,
        description=description,
        input_schema=input_schema_for_function(handler),
        output_schema=output_schema,
        handler=handler,
        annotations=annotations,
        category=category,
        listed=listed,
        deprecated=deprecated,
    )


def build_operation_registry(include_admin: bool = False) -> list[OperationSpec]:
    registry: list[OperationSpec] = []
    workbench_definitions = [
        ("search", "Search Fundus", "Find current Fundus evidence in a project or area.", scan_fundus, True, False, True),
        (
            "read",
            "Read Fundus Note",
            "Read one bounded note page; follow next_cursor until complete is true.",
            read_note,
            True,
            False,
            True,
        ),
        ("propose_create", "Propose Fundus Create", "Plan a note and return duplicate candidates without writing.", propose_create, True, False, True),
        ("apply_create", "Apply Fundus Create", "Apply an integrity-checked create proposal after duplicate review.", apply_create, False, False, False),
        ("propose_update", "Propose Fundus Update", "Plan content and metadata changes with a deterministic diff.", propose_update, True, False, True),
        ("apply_update", "Apply Fundus Update", "Apply a proposal only at its expected note revision.", apply_update, False, True, False),
        ("move", "Move Fundus Note", "Move a note while preserving identity and optionally leaving a redirect.", move_note, False, True, False),
        ("archive", "Archive Fundus Note", "Move one selected note into the recoverable Fundus archive.", archive_apply, False, True, False),
        ("restore", "Restore Fundus Note", "Restore one archived note to its validated active path.", archive_restore, False, False, False),
        ("mark_stale", "Mark Fundus Note Stale", "Record that a note no longer matches current evidence.", mark_stale, False, False, False),
        ("verify_note", "Verify Fundus Note", "Record current source evidence and verification provenance.", verify_note, False, False, False),
        ("doctor", "Diagnose Fundus", "Report resolved scope, configuration, index, lock, and path policy.", doctor, True, False, True),
    ]
    for name, title, description, handler, read_only, destructive, idempotent in workbench_definitions:
        annotations = behavior_annotations(read_only, destructive, idempotent)
        output_schema = WORKBENCH_OUTPUT_SCHEMAS[name]
        registry.append(
            make_operation(name, title, description, handler, annotations, output_schema, "workbench")
        )
        legacy_name = handler.__name__
        if legacy_name != name:
            registry.append(
                make_operation(
                    legacy_name,
                    f"Deprecated: {title}",
                    f"Deprecated compatibility alias for `{name}`.",
                    handler,
                    annotations,
                    output_schema,
                    "compatibility",
                    listed=False,
                    deprecated=True,
                )
            )

    for name, title, handler, output_schema in [
        ("create", "Deprecated: Create Fundus Note", create_note, WORKBENCH_OUTPUT_SCHEMAS["create"]),
        ("create_note", "Deprecated: Create Fundus Note", create_note, WORKBENCH_OUTPUT_SCHEMAS["create"]),
        ("update", "Deprecated: Update Fundus Note", update_note, WORKBENCH_OUTPUT_SCHEMAS["update"]),
        ("update_note", "Deprecated: Update Fundus Note", update_note, WORKBENCH_OUTPUT_SCHEMAS["update"]),
    ]:
        registry.append(
            make_operation(
                name,
                title,
                "Deprecated immediate mutation alias; prefer proposal and apply operations.",
                handler,
                behavior_annotations(False, name.startswith("update"), False),
                output_schema,
                "compatibility",
                listed=False,
                deprecated=True,
            )
        )

    admin_definitions = [
        ("add_frontmatter", "Add Frontmatter", "Add typed frontmatter to an existing plain note.", add_frontmatter, False, True, False),
        ("normalize_frontmatter", "Normalize Frontmatter", "Plan or apply bulk frontmatter normalization.", normalize_frontmatter, False, True, True),
        ("backup_create", "Create Backup", "Create a checksummed Fundus corpus backup.", backup_create, False, False, False),
        ("backup_list", "List Backups", "List available Fundus backups.", backup_list, True, False, True),
        ("backup_inspect", "Inspect Backup", "Read one Fundus backup manifest.", backup_inspect, True, False, True),
        ("backup_verify", "Verify Backup", "Verify all backup sizes and checksums.", backup_verify, True, False, True),
        ("backup_restore", "Restore Backup", "Plan or apply a verified full-corpus restore.", backup_restore, False, True, False),
        ("area_init", "Initialize Area", "Create a lean Fundus area without overwriting files.", area_init, False, False, True),
        ("index_status", "Index Status", "Report index validity and stale paths.", index_status, True, False, True),
        ("index_rebuild", "Rebuild Index", "Persist a complete derived search index rebuild.", index_rebuild, False, False, True),
        ("migrate_wiki_to_fundus", "Migrate Wiki", "Plan, apply, or verify the legacy Wiki migration.", migrate_wiki_to_fundus, False, True, False),
        ("archive_candidates", "Archive Candidates", "List possible archive candidates without changing notes.", archive_candidates, True, False, True),
        ("archive_cleanup", "Clean Archive Folders", "Remove empty folders left by archive operations.", archive_cleanup, False, True, True),
        ("archive_status", "Archive Status", "Summarize active and archived note counts.", archive_status, True, False, True),
    ]
    for name, title, description, handler, read_only, destructive, idempotent in admin_definitions:
        registry.append(
            make_operation(
                name,
                title,
                description,
                handler,
                behavior_annotations(read_only, destructive, idempotent),
                GENERIC_OUTPUT_SCHEMA,
                "admin",
                listed=include_admin,
            )
        )
    return registry


def build_tools(include_admin: bool = False) -> list[OperationSpec]:
    return build_operation_registry(include_admin)


def json_rpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def json_rpc_error(request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def tool_result_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


def tool_error(message: str, code: str = "FUNDUS_ERROR") -> dict[str, Any]:
    structured = {"error": message, "code": code}
    return {
        "content": [{"type": "text", "text": tool_result_text(structured)}],
        "structuredContent": structured,
        "isError": True,
    }


def json_type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def validate_schema_value(value: Any, schema: dict[str, Any], path: str = "$") -> str | None:
    expected_type = schema.get("type")
    if expected_type and not json_type_matches(value, expected_type):
        return f"{path} must be of type {expected_type}."
    allowed_values = schema.get("enum")
    if allowed_values is not None and value not in allowed_values:
        return f"{path} must be one of: {', '.join(map(str, allowed_values))}."
    if expected_type == "object" and isinstance(value, dict):
        properties = schema.get("properties") or {}
        missing = [name for name in schema.get("required") or [] if name not in value]
        if missing:
            return f"{path} is missing required field(s): {', '.join(missing)}."
        if schema.get("additionalProperties") is False:
            unexpected = sorted(set(value) - set(properties))
            if unexpected:
                return f"{path} has unexpected field(s): {', '.join(unexpected)}."
        for name, child_schema in properties.items():
            if name in value:
                error = validate_schema_value(value[name], child_schema, f"{path}.{name}")
                if error:
                    return error
    if expected_type == "array" and isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            error = validate_schema_value(item, schema["items"], f"{path}[{index}]")
            if error:
                return error
    return None


def validate_tool_arguments(tool: OperationSpec, arguments: dict[str, Any]) -> str | None:
    schema = tool.input_schema
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    missing = [name for name in required if name not in arguments]
    if missing:
        return f"Missing required argument(s): {', '.join(missing)}"
    if schema.get("additionalProperties") is False:
        unexpected = sorted(set(arguments) - set(properties))
        if unexpected:
            return f"Unexpected argument(s): {', '.join(unexpected)}"
    for name, value in arguments.items():
        property_schema = properties.get(name) or {}
        expected_type = property_schema.get("type")
        if expected_type and not json_type_matches(value, expected_type):
            return f"Argument '{name}' must be of type {expected_type}."
        allowed_values = property_schema.get("enum")
        if allowed_values is not None and value not in allowed_values:
            return f"Argument '{name}' must be one of: {', '.join(map(str, allowed_values))}."
    return None


class JsonRpcMcpServer:
    def __init__(self, name: str, tools: list[OperationSpec]) -> None:
        self.name = name
        self.tools = {tool.name: tool for tool in tools}
        self.initialization_state = "new"
        self.negotiated_protocol_version: str | None = None

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "title": tool.title,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "outputSchema": tool.output_schema,
                "annotations": tool.annotations,
            }
            for tool in self.tools.values()
            if tool.listed
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            return tool_error(f"Unknown Fundus tool: {name}", "UNKNOWN_OPERATION")
        validation_error = validate_tool_arguments(tool, arguments or {})
        if validation_error:
            return tool_error(validation_error, "INVALID_ARGUMENT")
        try:
            result = tool.handler(**(arguments or {}))
            if not isinstance(result, dict):
                return tool_error("Operation returned a non-object result.", "OUTPUT_SCHEMA_MISMATCH")
            output_error = validate_schema_value(result, tool.output_schema)
            if output_error:
                return tool_error(output_error, "OUTPUT_SCHEMA_MISMATCH")
            return {
                "content": [{"type": "text", "text": tool_result_text(result)}],
                "structuredContent": result,
            }
        except fundus_core.FundusError as exc:
            return tool_error(str(exc), exc.code)
        except Exception as exc:  # MCP tool errors should be surfaced as tool output, not crash the server.
            return tool_error(str(exc), "INTERNAL_ERROR")

    def handle_message(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return json_rpc_error(None, -32600, "Invalid Request: expected a JSON object.")

        request_id = message.get("id") if "id" in message else None
        is_notification = "id" not in message
        if message.get("jsonrpc") != "2.0":
            return None if is_notification else json_rpc_error(request_id, -32600, "Invalid Request: jsonrpc must be '2.0'.")
        if "id" in message and (request_id is None or isinstance(request_id, bool) or not isinstance(request_id, (str, int))):
            return json_rpc_error(None, -32600, "Invalid Request: id must be a string or integer.")

        method = message.get("method")
        if not isinstance(method, str):
            return None if is_notification else json_rpc_error(request_id, -32600, "Invalid Request: method must be a string.")
        if "params" in message and not isinstance(message["params"], dict):
            return None if is_notification else json_rpc_error(request_id, -32602, "Invalid params: expected an object.")
        params = message.get("params") or {}

        if method == "notifications/initialized":
            if not is_notification:
                return json_rpc_error(request_id, -32600, "notifications/initialized must be a notification.")
            if self.initialization_state == "awaiting_initialized":
                self.initialization_state = "ready"
            return None

        if method == "initialize":
            if is_notification:
                return None
            if self.initialization_state != "new":
                return json_rpc_error(request_id, -32600, "Invalid Request: server is already initialized.")
            requested_version = params.get("protocolVersion")
            client_capabilities = params.get("capabilities")
            client_info = params.get("clientInfo")
            if not isinstance(requested_version, str) or not requested_version:
                return json_rpc_error(request_id, -32602, "initialize requires a protocolVersion string.")
            if not isinstance(client_capabilities, dict):
                return json_rpc_error(request_id, -32602, "initialize requires a capabilities object.")
            if not isinstance(client_info, dict):
                return json_rpc_error(request_id, -32602, "initialize requires a clientInfo object.")
            protocol_version = (
                requested_version
                if requested_version in SUPPORTED_MCP_PROTOCOL_VERSIONS
                else MCP_PROTOCOL_VERSION
            )
            self.negotiated_protocol_version = protocol_version
            self.initialization_state = "awaiting_initialized"
            return json_rpc_result(
                request_id,
                {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": self.name, "version": discover_server_version()},
                    "instructions": (
                        "Use Fundus as brief, cited evidence for durable work knowledge; source code remains authoritative. "
                        "Write Fundus notes only through these tools or the Fundus CLI helper, never through raw Markdown or generic Obsidian edits."
                    ),
                },
            )
        if method == "ping":
            return None if is_notification else json_rpc_result(request_id, {})
        if method == "notifications/cancelled":
            return None
        if self.initialization_state != "ready":
            if is_notification:
                return None
            detail = (
                "Server not initialized."
                if self.initialization_state == "new"
                else "Server is waiting for notifications/initialized."
            )
            return json_rpc_error(request_id, SERVER_NOT_INITIALIZED, detail)
        if method == "tools/list":
            return None if is_notification else json_rpc_result(request_id, {"tools": self.list_tools()})
        if method == "tools/call":
            if is_notification:
                return None
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str):
                return json_rpc_error(request_id, -32602, "tools/call requires a string tool name.")
            if not isinstance(arguments, dict):
                return json_rpc_error(request_id, -32602, "tools/call arguments must be an object.")
            if name not in self.tools:
                return json_rpc_error(request_id, -32602, f"Unknown tool: {name}")
            return json_rpc_result(request_id, self.call_tool(name, arguments))
        if is_notification:
            return None
        return json_rpc_error(request_id, -32601, f"Unsupported method: {method}")

    def run(self) -> None:
        while True:
            try:
                message = read_stdio_message(sys.stdin.buffer)
            except Exception as exc:
                write_stdio_message(sys.stdout.buffer, json_rpc_error(None, -32700, "Parse error", str(exc)))
                continue
            if message is None:
                return
            try:
                response = self.handle_message(message)
            except Exception:
                request_id = message.get("id") if isinstance(message, dict) else None
                response = json_rpc_error(request_id, -32603, "Internal error")
            if response is not None:
                write_stdio_message(sys.stdout.buffer, response)


def read_stdio_message(stream: Any) -> dict[str, Any] | None:
    while True:
        line = stream.readline()
        if not line:
            return None
        if line.strip():
            break
    return json.loads(line.decode("utf-8"))


def write_stdio_message(stream: Any, message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    stream.write(payload)
    stream.flush()


def build_server(include_admin: bool = False) -> JsonRpcMcpServer:
    return JsonRpcMcpServer("fundus", build_tools(include_admin))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Fundus MCP stdio server.")
    parser.add_argument("--check", action="store_true", help="Validate that the server can be constructed, then exit.")
    parser.add_argument("--admin", action="store_true", help="Expose explicit administrative tools in tools/list.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        server = build_server(args.admin)
        if args.check:
            print(json.dumps({"ok": True, "server": "fundus"}))
            return 0
        server.run()
        return 0
    except (RuntimeError, fundus_core.FundusError) as exc:
        if args.check:
            print(json.dumps({"ok": False, "server": "fundus", "error": str(exc)}))
            return 0
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
