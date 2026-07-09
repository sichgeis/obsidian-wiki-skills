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
        self.assertIn("Token handling details.", body)

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
        self.assertIn("type: Epic", body)

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
        self.assertIn("aliases:", body)
        self.assertIn("resource: https://jira.example/browse/BACKEND-2291", body)

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
        self.assertIn("API_KEY: [REDACTED]", body)
        self.assertNotIn("super-secret-token", body)

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
        area_doctor = fundus_mcp.doctor(area="Epics/AI Agent Templates", project_root=str(self.project_root))

        self.assertEqual(backups["backups"][0]["id"], backup["id"])
        self.assertEqual(inspected["id"], backup["id"])
        self.assertEqual(area_doctor["scope"], "area")
        self.assertEqual(area_doctor["scope_path"], "Epics/AI Agent Templates")

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
    def test_server_initializes_and_lists_tools_without_external_sdk(self) -> None:
        server = fundus_mcp.build_server()

        initialized = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
        listed = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        self.assertEqual(initialized["result"]["serverInfo"]["name"], "fundus")
        self.assertIn("tools", initialized["result"]["capabilities"])
        self.assertIn("migrate_wiki_to_fundus", tools)
        self.assertEqual(tools["create_note"]["inputSchema"]["properties"]["aliases"]["type"], "array")
        self.assertEqual(tools["update_note"]["inputSchema"]["properties"]["mode"]["enum"], ["append", "replace", "rewrite"])

    def test_tool_call_returns_text_content_payload(self) -> None:
        server = fundus_mcp.build_server()

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
        self.assertTrue((self.vault_path / "Fundus" / "demo" / "workbench-note.md").exists())

    def test_stdio_message_framing_round_trips(self) -> None:
        message = {"jsonrpc": "2.0", "id": 4, "method": "ping"}
        stream = io.BytesIO()

        fundus_mcp.write_stdio_message(stream, message)
        stream.seek(0)

        self.assertEqual(fundus_mcp.read_stdio_message(stream), message)


if __name__ == "__main__":
    unittest.main()
