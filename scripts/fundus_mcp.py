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

SCRIPT_DIR = Path(__file__).resolve().parent
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


def read_note(path: str, project_root: str | None = None) -> str:
    context = resolve_context(project_root=project_root)
    return fundus_core.read_document(context.config, path)


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
    )


def update_note(
    path: str,
    mode: Literal["append", "replace", "rewrite"],
    content: str,
    section: str | None = None,
    project: str | None = None,
    project_root: str | None = None,
    area: str | None = None,
) -> dict[str, Any]:
    context = resolve_context(project, project_root, area)
    return fundus_core.update_document(context.config, context.project_name, path, mode, content, section, context.scope)


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


def move_note(path: str, destination: str, leave_stub: bool = False, project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.move_document(context.config, path, destination, leave_stub)


def backup_create(label: str | None = None, project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.create_backup(context.config, label)


def backup_list(project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return {"backups": fundus_core.list_backups(context.config)}


def backup_inspect(id: str, project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.inspect_backup(context.config, id)


def area_init(area: str, title: str, type: str = "Area", project: str | None = None, project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project, project_root)
    return fundus_core.area_init(context.config, context.project_name, area, type, title)


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


def archive_apply(path: str, reason: str | None = None, project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.archive_document(context.config, path, reason)


def archive_restore(path: str, project_root: str | None = None) -> dict[str, Any]:
    context = resolve_context(project_root=project_root)
    return fundus_core.restore_document(context.config, path)


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


MCP_PROTOCOL_VERSION = "2025-06-18"
NONE_TYPE = type(None)


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Any


TOOL_DESCRIPTIONS = {
    "scan_fundus": "Search Fundus notes for relevant project, area, ticket, domain, or architecture knowledge.",
    "read_note": "Read a Fundus note by repository-relative vault path.",
    "create_note": "Create a new Fundus note with OKF-compatible retrieval metadata.",
    "update_note": "Append, replace a section, or rewrite an existing Fundus note.",
    "add_frontmatter": "Add OKF-compatible frontmatter to an existing plain Markdown Fundus note.",
    "normalize_frontmatter": "Dry-run or apply frontmatter normalization for active or archived Fundus notes.",
    "move_note": "Move a Fundus note to another active Fundus path, optionally leaving a stub.",
    "backup_create": "Create a JSON-manifested backup of the current Fundus corpus.",
    "backup_list": "List available Fundus backups.",
    "backup_inspect": "Inspect a Fundus backup manifest.",
    "area_init": "Create an explicit cross-repository Fundus area skeleton.",
    "index_status": "Report whether the lightweight Fundus search index is current.",
    "index_rebuild": "Rebuild the lightweight Fundus search index.",
    "migrate_wiki_to_fundus": "Dry-run, apply, or verify the one-time Wiki to Fundus migration.",
    "archive_candidates": "Find active notes that may be ready to archive.",
    "archive_apply": "Archive a Fundus note and add archival metadata.",
    "archive_restore": "Restore an archived Fundus note to its original active path.",
    "archive_cleanup": "Remove empty active Fundus directories left after archival moves.",
    "archive_status": "Summarize archived note counts for the current project or area.",
    "doctor": "Show resolved project, vault, scope, index, and corpus diagnostics.",
}


PARAMETER_DESCRIPTIONS = {
    "query": "Search phrase, ticket key, domain term, alias, or resource URL.",
    "limit": "Maximum number of results to return.",
    "include_snippet": "Include a short matching body excerpt in results.",
    "include_archived": "Include archived notes in retrieval.",
    "project": "Project scope override; cannot be combined with area.",
    "project_root": "Repository or working directory used to resolve Fundus config.",
    "area": "Explicit cross-repository Fundus area path.",
    "path": "Fundus note path relative to the vault, for example Fundus/demo/note.md.",
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


TOOL_FUNCTIONS = [
    scan_fundus,
    read_note,
    create_note,
    update_note,
    add_frontmatter,
    normalize_frontmatter,
    move_note,
    backup_create,
    backup_list,
    backup_inspect,
    area_init,
    index_status,
    index_rebuild,
    migrate_wiki_to_fundus,
    archive_candidates,
    archive_apply,
    archive_restore,
    archive_cleanup,
    archive_status,
    doctor,
]


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


def build_tools() -> list[McpTool]:
    tools: list[McpTool] = []
    for function in TOOL_FUNCTIONS:
        name = function.__name__
        tools.append(
            McpTool(
                name=name,
                description=TOOL_DESCRIPTIONS[name],
                input_schema=input_schema_for_function(function),
                handler=function,
            )
        )
    return tools


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


class JsonRpcMcpServer:
    def __init__(self, name: str, tools: list[McpTool]) -> None:
        self.name = name
        self.tools = {tool.name: tool for tool in tools}

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in self.tools.values()
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            raise fundus_core.FundusError(f"Unknown Fundus tool: {name}")
        try:
            result = tool.handler(**(arguments or {}))
            return {"content": [{"type": "text", "text": tool_result_text(result)}]}
        except Exception as exc:  # MCP tool errors should be surfaced as tool output, not crash the server.
            return {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            }

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        is_notification = "id" not in message
        params = message.get("params") or {}

        if method in {"notifications/initialized", "notifications/cancelled"}:
            return None

        if method == "initialize":
            protocol_version = params.get("protocolVersion") or MCP_PROTOCOL_VERSION
            return json_rpc_result(
                request_id,
                {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": self.name, "version": "0.1.0"},
                    "instructions": "Use Fundus as brief, cited evidence for durable work knowledge; source code remains authoritative.",
                },
            )
        if method == "ping":
            return json_rpc_result(request_id, {})
        if method == "tools/list":
            return json_rpc_result(request_id, {"tools": self.list_tools()})
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str):
                return json_rpc_error(request_id, -32602, "tools/call requires a string tool name.")
            if not isinstance(arguments, dict):
                return json_rpc_error(request_id, -32602, "tools/call arguments must be an object.")
            return json_rpc_result(request_id, self.call_tool(name, arguments))
        if method == "resources/list":
            return json_rpc_result(request_id, {"resources": []})
        if method == "prompts/list":
            return json_rpc_result(request_id, {"prompts": []})
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
            response = self.handle_message(message)
            if response is not None:
                write_stdio_message(sys.stdout.buffer, response)


def parse_header_line(line: bytes) -> tuple[str, str]:
    name, value = line.decode("ascii", errors="replace").split(":", 1)
    return name.strip().lower(), value.strip()


def read_stdio_message(stream: Any) -> dict[str, Any] | None:
    while True:
        first_line = stream.readline()
        if not first_line:
            return None
        if first_line.strip():
            break

    stripped = first_line.lstrip()
    if stripped.startswith(b"{"):
        return json.loads(first_line.decode("utf-8"))

    headers: dict[str, str] = {}
    if b":" not in first_line:
        raise ValueError("Expected JSON-RPC message or Content-Length header.")
    name, value = parse_header_line(first_line)
    headers[name] = value
    while True:
        line = stream.readline()
        if not line:
            raise ValueError("Unexpected EOF while reading message headers.")
        if line in (b"\r\n", b"\n"):
            break
        name, value = parse_header_line(line)
        headers[name] = value

    length_text = headers.get("content-length")
    if length_text is None:
        raise ValueError("Missing Content-Length header.")
    length = int(length_text)
    body = stream.read(length)
    if len(body) != length:
        raise ValueError("Unexpected EOF while reading message body.")
    return json.loads(body.decode("utf-8"))


def write_stdio_message(stream: Any, message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
    stream.write(payload)
    stream.flush()


def build_server() -> JsonRpcMcpServer:
    return JsonRpcMcpServer("fundus", build_tools())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Fundus MCP stdio server.")
    parser.add_argument("--check", action="store_true", help="Validate that the server can be constructed, then exit.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        server = build_server()
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
