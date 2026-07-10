from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

MCP_PATH = SCRIPTS_DIR / "fundus_mcp.py"
SPEC = importlib.util.spec_from_file_location("fundus_mcp", MCP_PATH)
assert SPEC and SPEC.loader
fundus_mcp = importlib.util.module_from_spec(SPEC)
sys.modules["fundus_mcp"] = fundus_mcp
SPEC.loader.exec_module(fundus_mcp)
fundus = fundus_mcp.fundus_core


class McpFundusTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.project_root = self.root / "demo-project"
        self.project_root.mkdir()
        self.vault_path = self.root / "vault"
        config_dir = self.project_root / ".codex"
        config_dir.mkdir()
        (config_dir / "fundus.json").write_text(
            json.dumps(
                {
                    "vault_path": str(self.vault_path),
                    "fundus_dir": "Fundus",
                    "default_tags": ["fundus"],
                }
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()


class McpContextTest(McpFundusTestCase):
    def test_resolve_context_uses_project_root_and_project_override(self) -> None:
        context = fundus_mcp.resolve_context(
            project="manual-project",
            project_root=str(self.project_root),
        )

        self.assertEqual(context.project_root, self.project_root)
        self.assertEqual(context.project_name, "manual-project")
        self.assertEqual(context.config.vault_path, self.vault_path)

    def test_resolve_context_detects_project_from_project_root(self) -> None:
        context = fundus_mcp.resolve_context(project_root=str(self.project_root))

        self.assertEqual(context.project_name, "demo-project")


class McpWrapperTest(McpFundusTestCase):
    def test_create_scan_and_read_note_use_existing_domain_behavior(self) -> None:
        created = fundus_mcp.create_note(
            "Authentication Flow",
            "## Overview\n\nToken handling details.",
            ["auth"],
            project="demo",
            project_root=str(self.project_root),
        )

        scanned = fundus_mcp.scan_fundus(
            query="Authentication",
            project="demo",
            project_root=str(self.project_root),
        )
        body = fundus_mcp.read_note(created["path"], project_root=str(self.project_root))

        self.assertEqual(created["path"], "Fundus/demo/authentication-flow.md")
        self.assertEqual(scanned["project"], "demo")
        self.assertEqual(scanned["documents"][0]["title"], "Authentication Flow")
        self.assertIn("Token handling details.", body["content"])
        self.assertTrue(body["revision"].startswith("sha256:"))

    def test_create_and_scan_area_note(self) -> None:
        created = fundus_mcp.create_note(
            "Story Map",
            "Body",
            ["story-map"],
            type="Epic",
            description="Story map for the epic.",
            id="epic/ai-agent-templates/story-map",
            area="Epics/AI Agent Templates",
            project_root=str(self.project_root),
        )

        scanned = fundus_mcp.scan_fundus(
            query="Story",
            area="Epics/AI Agent Templates",
            project_root=str(self.project_root),
        )
        body = fundus_mcp.read_note(created["path"], project_root=str(self.project_root))

        self.assertEqual(created["path"], "Fundus/Epics/AI Agent Templates/story-map.md")
        self.assertEqual(scanned["scope"], "area")
        self.assertEqual(scanned["scope_path"], "Epics/AI Agent Templates")
        self.assertEqual(scanned["documents"][0]["path"], created["path"])
        self.assertIn("type: Epic", body["content"])

    def test_create_note_supports_retrieval_metadata(self) -> None:
        created = fundus_mcp.create_note(
            "Prompt Boundary",
            "Body",
            ["domain"],
            aliases=["Prompt Surface"],
            resource="https://jira.example/browse/BACKEND-2291",
            last_verified="2026-07-09",
            project="demo",
            project_root=str(self.project_root),
        )
        fundus_mcp.index_rebuild(project_root=str(self.project_root))

        scanned = fundus_mcp.scan_fundus(
            query="prompt surface",
            project="demo",
            project_root=str(self.project_root),
        )
        body = fundus_mcp.read_note(created["path"], project_root=str(self.project_root))

        self.assertEqual(scanned["documents"][0]["aliases"], ["Prompt Surface"])
        self.assertEqual(scanned["documents"][0]["last_verified"], "2026-07-09")
        self.assertIn("aliases:", body["content"])
        self.assertIn("resource: https://jira.example/browse/BACKEND-2291", body["content"])

    def test_proposal_apply_and_verification_wrappers(self) -> None:
        create_proposal = fundus_mcp.propose_create(
            "Proposed Wrapper",
            "Body",
            ["domain"],
            verified_against=["jira:BACKEND-1"],
            source_fingerprint="jira:BACKEND-1@v1",
            verification_status="current",
            project="demo",
            project_root=str(self.project_root),
        )
        created = fundus_mcp.apply_create(create_proposal, project_root=str(self.project_root))
        update_proposal = fundus_mcp.propose_update(
            created["path"],
            "append",
            "Follow-up",
            metadata_changes={"verification_status": "unverified"},
            project_root=str(self.project_root),
        )
        updated = fundus_mcp.apply_update(update_proposal, project_root=str(self.project_root))
        stale = fundus_mcp.mark_stale(
            created["path"],
            "Evidence changed",
            updated["revision"],
            project_root=str(self.project_root),
        )
        verified = fundus_mcp.verify_note(
            created["path"],
            ["github:org/repo@abc"],
            "github:org/repo:path@sha256:def",
            stale["revision"],
            project_root=str(self.project_root),
        )

        self.assertTrue(created["applied"])
        self.assertTrue(updated["applied"])
        self.assertTrue(verified["revision"].startswith("sha256:"))

    def test_update_note_redacts_and_refreshes_existing_index(self) -> None:
        created = fundus_mcp.create_note(
            "Existing Ticket",
            "## Context\n\nOld.",
            ["ticket"],
            project="demo",
            project_root=str(self.project_root),
        )
        fundus_mcp.index_rebuild(project_root=str(self.project_root))

        fundus_mcp.update_note(
            created["path"],
            "append",
            "## Follow Up\n\nAPI_KEY=super-secret-token\n\nNew searchable phrase.",
            project="demo",
            project_root=str(self.project_root),
        )

        scanned = fundus_mcp.scan_fundus(
            query="searchable phrase",
            project="demo",
            project_root=str(self.project_root),
        )
        body = fundus_mcp.read_note(created["path"], project_root=str(self.project_root))

        self.assertEqual(scanned["documents"][0]["title"], "Existing Ticket")
        self.assertIn("API_KEY: [REDACTED]", body["content"])
        self.assertNotIn("super-secret-token", body["content"])

    def test_archive_wrappers_move_restore_and_report_status(self) -> None:
        created = fundus_mcp.create_note(
            "Old Ticket",
            "Body",
            ["ticket"],
            project="demo",
            project_root=str(self.project_root),
        )

        archived = fundus_mcp.archive_apply(
            created["path"],
            "superseded",
            project_root=str(self.project_root),
        )
        archived_status = fundus_mcp.archive_status(project="demo", project_root=str(self.project_root))
        restored = fundus_mcp.archive_restore(
            archived["path"],
            project_root=str(self.project_root),
        )

        self.assertEqual(archived["path"], "Fundus/_archive/demo/old-ticket.md")
        self.assertEqual(archived_status["archived_documents"], 1)
        self.assertEqual(restored["path"], created["path"])

    def test_update_note_surfaces_existing_fundus_errors(self) -> None:
        created = fundus_mcp.create_note(
            "Needs Section",
            "Body",
            project="demo",
            project_root=str(self.project_root),
        )

        with self.assertRaisesRegex(fundus.FundusError, "--section is required"):
            fundus_mcp.update_note(
                created["path"],
                "replace",
                "New",
                project="demo",
                project_root=str(self.project_root),
            )

    def test_backup_and_doctor_wrappers(self) -> None:
        fundus_mcp.create_note(
            "Backed Up",
            "Body",
            project="demo",
            project_root=str(self.project_root),
        )

        backup = fundus_mcp.backup_create("mcp", project_root=str(self.project_root))
        backups = fundus_mcp.backup_list(project_root=str(self.project_root))
        inspected = fundus_mcp.backup_inspect(backup["id"], project_root=str(self.project_root))
        verified = fundus_mcp.backup_verify(backup["id"], project_root=str(self.project_root))
        restore_plan = fundus_mcp.backup_restore(backup["id"], project_root=str(self.project_root))
        area_doctor = fundus_mcp.doctor(area="Epics/AI Agent Templates", project_root=str(self.project_root))

        self.assertEqual(backups["backups"][0]["id"], backup["id"])
        self.assertEqual(inspected["id"], backup["id"])
        self.assertTrue(verified["verified"])
        self.assertFalse(restore_plan["apply"])
        self.assertEqual(area_doctor["scope"], "area")
        self.assertEqual(area_doctor["scope_path"], "Epics/AI Agent Templates")
        self.assertFalse(area_doctor["mutation_lock"]["locked"])

    def test_area_init_wrapper_creates_skeleton(self) -> None:
        result = fundus_mcp.area_init(
            "Epics/AI Agent Templates",
            "AI Agent Templates",
            "Epic",
            project_root=str(self.project_root),
        )

        self.assertIn("Fundus/Epics/AI Agent Templates/index.md", result["created"])

    def test_normalize_frontmatter_wrapper_dry_run_and_apply(self) -> None:
        note_path = self.vault_path / "Fundus" / "demo" / "legacy.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(
            "---\n"
            "title: Legacy\n"
            "created: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-02T00:00:00+00:00\n"
            "project: old\n"
            "tags:\n"
            "  - wiki\n"
            "  - project/old\n"
            "---\n\n"
            "# Legacy\n\nBody\n"
        )

        dry_run = fundus_mcp.normalize_frontmatter(
            path="Fundus/demo/legacy.md",
            project_root=str(self.project_root),
        )
        applied = fundus_mcp.normalize_frontmatter(
            path="Fundus/demo/legacy.md",
            apply=True,
            project_root=str(self.project_root),
        )

        frontmatter, body = fundus.parse_frontmatter(note_path.read_text())
        self.assertEqual(dry_run["changed_count"], 1)
        self.assertEqual(dry_run["applied_count"], 0)
        self.assertEqual(applied["applied_count"], 1)
        self.assertEqual(frontmatter["scope_path"], "demo")
        self.assertEqual(frontmatter["project"], "demo")
        self.assertEqual(body, "\n# Legacy\n\nBody\n")

    def test_migration_wrapper_dry_run_apply_and_verify(self) -> None:
        wiki_note = self.vault_path / "Wiki" / "demo" / "legacy.md"
        wiki_note.parent.mkdir(parents=True, exist_ok=True)
        wiki_note.write_text(
            "---\n"
            "title: Legacy\n"
            "created: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-02T00:00:00+00:00\n"
            "project: old\n"
            "tags:\n"
            "  - wiki\n"
            "---\n\n"
            "# Legacy\n\nBody\n"
        )

        dry_run = fundus_mcp.migrate_wiki_to_fundus("dry-run", project_root=str(self.project_root))
        applied = fundus_mcp.migrate_wiki_to_fundus("apply", retire_source="keep", project_root=str(self.project_root))
        verified = fundus_mcp.migrate_wiki_to_fundus("verify", project_root=str(self.project_root))

        self.assertEqual(dry_run["counts"]["markdown"], 1)
        self.assertEqual(applied["copied_count"], 1)
        self.assertTrue(verified["passed"])
        self.assertTrue((self.vault_path / "Wiki").exists())
        self.assertTrue((self.vault_path / "Fundus" / "demo" / "legacy.md").exists())


class McpProtocolTest(McpFundusTestCase):
    def initialize_server(self, server, protocol_version: str = "2025-11-25") -> dict:
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "fundus-test", "version": "1.0.0"},
                },
            }
        )
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        )
        return response

    def test_server_initializes_and_lists_tools_without_external_sdk(self) -> None:
        server = fundus_mcp.build_server()

        initialized = self.initialize_server(server, "2025-06-18")
        listed = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        self.assertEqual(initialized["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "fundus")
        manifest_version = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())["version"]
        self.assertEqual(initialized["result"]["serverInfo"]["version"], manifest_version)
        self.assertIn("tools", initialized["result"]["capabilities"])
        self.assertIn("never through raw Markdown", initialized["result"]["instructions"])
        self.assertEqual(
            set(tools),
            {
                "search",
                "read",
                "propose_create",
                "apply_create",
                "propose_update",
                "apply_update",
                "move",
                "archive",
                "restore",
                "mark_stale",
                "verify_note",
                "doctor",
            },
        )
        self.assertEqual(
            tools["search"]["annotations"],
            {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        )
        self.assertEqual(tools["propose_create"]["inputSchema"]["properties"]["aliases"]["type"], "array")
        self.assertEqual(tools["propose_update"]["inputSchema"]["properties"]["mode"]["enum"], ["append", "replace", "rewrite"])
        self.assertEqual(tools["apply_update"]["inputSchema"]["properties"]["proposal"]["type"], "object")
        for tool in tools.values():
            self.assertTrue(tool["title"])
            self.assertLess(len(tool["description"]), 160)
            self.assertEqual(set(tool["annotations"]), {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"})
            self.assertEqual(tool["outputSchema"]["type"], "object")

        admin_server = fundus_mcp.build_server(include_admin=True)
        self.initialize_server(admin_server)
        admin_listed = admin_server.handle_message({"jsonrpc": "2.0", "id": 9, "method": "tools/list"})
        admin_names = {tool["name"] for tool in admin_listed["result"]["tools"]}
        self.assertIn("migrate_wiki_to_fundus", admin_names)
        self.assertIn("backup_restore", admin_names)

    def test_read_contract_is_bounded_lossless_and_schema_validated(self) -> None:
        server = fundus_mcp.build_server()
        self.initialize_server(server)
        content = "START\n" + ("ordinary markdown with Grüße and 🙂\\\"\n" * 250) + "END\n"
        created = fundus_mcp.create_note(
            "Paged MCP Note",
            content,
            project="demo",
            project_root=str(self.project_root),
        )

        read_tool = server.tools["read"]
        properties = read_tool.output_schema["properties"]
        self.assertIn("cursor", read_tool.input_schema["properties"])
        self.assertEqual(
            {
                "path",
                "resolved_path",
                "content",
                "revision",
                "redirected",
                "offset",
                "next_offset",
                "total_characters",
                "complete",
                "next_cursor",
            },
            set(properties),
        )
        self.assertEqual(read_tool.annotations, fundus_mcp.behavior_annotations(True, False, True))

        pages = []
        cursor = None
        maximum_wire_bytes = 0
        while True:
            arguments = {"path": created["path"], "project_root": str(self.project_root)}
            if cursor is not None:
                arguments["cursor"] = cursor
            response = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": len(pages) + 10,
                    "method": "tools/call",
                    "params": {"name": "read", "arguments": arguments},
                }
            )
            maximum_wire_bytes = max(
                maximum_wire_bytes,
                len(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
            )
            page = response["result"]["structuredContent"]
            self.assertEqual(page, json.loads(response["result"]["content"][0]["text"]))
            self.assertIsNone(fundus_mcp.validate_schema_value(page, read_tool.output_schema))
            pages.append(page)
            if page["complete"]:
                self.assertNotIn("next_cursor", page)
                break
            self.assertTrue(page["next_cursor"])
            cursor = page["next_cursor"]

        exact = (self.vault_path / created["path"]).read_text()
        self.assertGreaterEqual(len(pages), 3)
        self.assertEqual("".join(page["content"] for page in pages), exact)
        self.assertLessEqual(maximum_wire_bytes, 32768)

        multibyte = fundus_mcp.create_note(
            "Multibyte Page Budget",
            "🙂終ü\\\"\n" * 1200,
            project="demo",
            project_root=str(self.project_root),
        )
        multibyte_response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {
                    "name": "read",
                    "arguments": {
                        "path": multibyte["path"],
                        "project_root": str(self.project_root),
                    },
                },
            }
        )
        multibyte_wire_bytes = len(
            json.dumps(multibyte_response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        self.assertEqual(
            len(multibyte_response["result"]["structuredContent"]["content"]),
            fundus.READ_PAGE_MAX_CHARACTERS,
        )
        self.assertLessEqual(multibyte_wire_bytes, 32768)

        alias_page = server.call_tool(
            "read_note",
            {"path": created["path"], "project_root": str(self.project_root)},
        )["structuredContent"]
        self.assertEqual(alias_page["complete"], False)
        self.assertEqual(len(alias_page["content"]), fundus.READ_PAGE_MAX_CHARACTERS)

    def test_read_tool_reports_invalid_and_stale_cursor_codes_without_content(self) -> None:
        server = fundus_mcp.build_server()
        self.initialize_server(server)
        secret = "DO-NOT-LEAK-THIS-PAYLOAD"
        created = fundus_mcp.create_note(
            "Cursor Safety",
            secret + (" x" * (fundus.READ_PAGE_MAX_CHARACTERS * 2)),
            project="demo",
            project_root=str(self.project_root),
        )
        arguments = {"path": created["path"], "project_root": str(self.project_root)}
        first_page = server.call_tool("read", arguments)["structuredContent"]

        invalid = server.call_tool("read", {**arguments, "cursor": "malformed"})
        note_path = self.vault_path / created["path"]
        note_path.write_text(note_path.read_text() + "\nexternal edit\n")
        stale = server.call_tool("read", {**arguments, "cursor": first_page["next_cursor"]})

        self.assertEqual(invalid["structuredContent"]["code"], "READ_CURSOR_INVALID")
        self.assertEqual(stale["structuredContent"]["code"], "READ_CURSOR_STALE")
        self.assertNotIn(secret, invalid["content"][0]["text"])
        self.assertNotIn(secret, stale["content"][0]["text"])

    def test_operation_registry_contracts_are_complete_and_consistent(self) -> None:
        registry = fundus_mcp.build_operation_registry(include_admin=True)
        names = [operation.name for operation in registry]

        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(any(operation.category == "compatibility" and operation.deprecated for operation in registry))
        for operation in registry:
            self.assertEqual(operation.input_schema["type"], "object")
            self.assertEqual(operation.output_schema["type"], "object")
            self.assertEqual(
                set(operation.annotations),
                {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"},
            )
            self.assertFalse(operation.annotations["openWorldHint"])
            if operation.annotations["readOnlyHint"]:
                self.assertFalse(operation.annotations["destructiveHint"])

        bad_operation = fundus_mcp.OperationSpec(
            name="bad_output",
            title="Bad Output",
            description="Test invalid output handling.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema={
                "type": "object",
                "properties": {"required_value": {"type": "string"}},
                "required": ["required_value"],
                "additionalProperties": False,
            },
            handler=lambda: {"wrong": True},
            annotations=fundus_mcp.behavior_annotations(True, False, True),
            category="workbench",
        )
        bad_result = fundus_mcp.JsonRpcMcpServer("test", [bad_operation]).call_tool("bad_output", {})
        self.assertTrue(bad_result["isError"])
        self.assertEqual(bad_result["structuredContent"]["code"], "OUTPUT_SCHEMA_MISMATCH")

    def test_tool_call_returns_text_content_payload(self) -> None:
        server = fundus_mcp.build_server()
        self.initialize_server(server)

        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "create_note",
                    "arguments": {
                        "title": "Workbench Note",
                        "content": "Body",
                        "project": "demo",
                        "project_root": str(self.project_root),
                    },
                },
            }
        )
        payload = json.loads(response["result"]["content"][0]["text"])

        self.assertEqual(payload["path"], "Fundus/demo/workbench-note.md")
        self.assertEqual(response["result"]["structuredContent"], payload)
        self.assertIsNone(
            fundus_mcp.validate_schema_value(payload, server.tools["create_note"].output_schema)
        )
        self.assertTrue((self.vault_path / "Fundus" / "demo" / "workbench-note.md").exists())

    def test_unsupported_protocol_version_negotiates_latest_supported_version(self) -> None:
        server = fundus_mcp.build_server()

        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2099-01-01",
                    "capabilities": {},
                    "clientInfo": {"name": "future-client", "version": "1.0.0"},
                },
            }
        )

        self.assertEqual(response["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(server.negotiated_protocol_version, "2025-11-25")
        self.assertEqual(
            fundus_mcp.SUPPORTED_MCP_PROTOCOL_VERSIONS,
            ("2025-11-25", "2025-06-18"),
        )

    def test_lifecycle_blocks_operations_until_initialized_notification(self) -> None:
        server = fundus_mcp.build_server()

        before_initialize = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        ping = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        initialized = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0.0"},
                },
            }
        )
        before_notification = server.handle_message(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}
        )
        repeated_initialize = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0.0"},
                },
            }
        )

        self.assertEqual(before_initialize["error"]["code"], fundus_mcp.SERVER_NOT_INITIALIZED)
        self.assertEqual(ping["result"], {})
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(before_notification["error"]["code"], fundus_mcp.SERVER_NOT_INITIALIZED)
        self.assertEqual(repeated_initialize["error"]["code"], -32600)

        server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
        listed = server.handle_message({"jsonrpc": "2.0", "id": 6, "method": "tools/list"})
        self.assertIn("tools", listed["result"])

    def test_unknown_tool_is_protocol_error_and_server_remains_alive(self) -> None:
        server = fundus_mcp.build_server()
        self.initialize_server(server)

        unknown = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "does_not_exist", "arguments": {}},
            }
        )
        ping = server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "ping"})

        self.assertEqual(unknown["error"]["code"], -32602)
        self.assertEqual(unknown["error"]["message"], "Unknown tool: does_not_exist")
        self.assertEqual(ping["result"], {})

    def test_malformed_requests_return_protocol_errors(self) -> None:
        server = fundus_mcp.build_server()

        not_an_object = server.handle_message([])
        wrong_jsonrpc = server.handle_message(
            {"jsonrpc": "1.0", "id": 1, "method": "ping"}
        )
        invalid_params = server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": []}
        )
        missing_client_info = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
            }
        )

        self.assertEqual(not_an_object["error"]["code"], -32600)
        self.assertEqual(wrong_jsonrpc["error"]["code"], -32600)
        self.assertEqual(invalid_params["error"]["code"], -32602)
        self.assertEqual(missing_client_info["error"]["code"], -32602)

    def test_tool_argument_validation_and_business_errors_are_tool_errors(self) -> None:
        server = fundus_mcp.build_server()
        self.initialize_server(server)
        created = fundus_mcp.create_note(
            "Conflict Tool Note",
            "Body",
            project="demo",
            project_root=str(self.project_root),
        )
        conflict_path = self.vault_path / created["path"]
        conflict_path.write_text(conflict_path.read_text() + "\nHuman edit.\n")

        missing_required = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "create_note", "arguments": {}},
            }
        )
        business_error = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "read_note",
                    "arguments": {
                        "path": "Fundus/demo/missing.md",
                        "project_root": str(self.project_root),
                    },
                },
            }
        )
        revision_conflict = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "update",
                    "arguments": {
                        "path": created["path"],
                        "mode": "rewrite",
                        "content": "Overwrite",
                        "expected_revision": created["revision"],
                        "project": "demo",
                        "project_root": str(self.project_root),
                    },
                },
            }
        )

        self.assertTrue(missing_required["result"]["isError"])
        self.assertIn("Missing required argument", missing_required["result"]["content"][0]["text"])
        self.assertEqual(missing_required["result"]["structuredContent"]["code"], "INVALID_ARGUMENT")
        self.assertTrue(business_error["result"]["isError"])
        self.assertIn("does not exist", business_error["result"]["content"][0]["text"])
        self.assertEqual(business_error["result"]["structuredContent"]["code"], "NOTE_NOT_FOUND")
        self.assertEqual(revision_conflict["result"]["structuredContent"]["code"], "REVISION_CONFLICT")

    def test_stdio_messages_are_newline_delimited_utf8(self) -> None:
        message = {"jsonrpc": "2.0", "id": 4, "method": "ping", "params": {"text": "Grüße"}}
        stream = io.BytesIO()

        fundus_mcp.write_stdio_message(stream, message)
        raw = stream.getvalue()
        stream.seek(0)

        self.assertEqual(raw, json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
        self.assertNotIn(b"Content-Length", raw)
        self.assertEqual(fundus_mcp.read_stdio_message(stream), message)

    def test_stdio_reader_skips_blank_lines_and_preserves_escaped_newlines(self) -> None:
        message = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "ping",
            "params": {"text": "first\nsecond"},
        }
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        stream = io.BytesIO(b"\n\r\n" + payload + b"\n")

        self.assertEqual(fundus_mcp.read_stdio_message(stream), message)
        self.assertIsNone(fundus_mcp.read_stdio_message(stream))

    def test_stdio_reader_rejects_content_length_framing_and_malformed_json(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            fundus_mcp.read_stdio_message(io.BytesIO(b"Content-Length: 2\r\n\r\n{}"))
        with self.assertRaises(json.JSONDecodeError):
            fundus_mcp.read_stdio_message(io.BytesIO(b"{not-json}\n"))


if __name__ == "__main__":
    unittest.main()
