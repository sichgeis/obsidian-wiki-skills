from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


class IndependentStdioMcpClient:
    """Minimal test client that does not import or reuse the Fundus MCP adapter."""

    def __init__(self, command: list[str], cwd: Path) -> None:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self.process.stdin and self.process.stdout and self.process.stderr

    def send(self, message: dict[str, Any]) -> None:
        assert self.process.stdin
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.process.stdin.write(payload + b"\n")
        self.process.stdin.flush()

    def receive(self, timeout: float = 5.0) -> dict[str, Any]:
        assert self.process.stdout
        readable, _, _ = select.select([self.process.stdout], [], [], timeout)
        if not readable:
            self.fail_with_process_output("Timed out waiting for MCP response")
        line = self.process.stdout.readline()
        if not line:
            self.fail_with_process_output("MCP server exited before responding")
        if line.startswith(b"Content-Length"):
            self.fail_with_process_output("MCP server used Content-Length framing")
        response = json.loads(line.decode("utf-8"))
        if not isinstance(response, dict):
            self.fail_with_process_output("MCP response was not a JSON object")
        return response

    def request(self, request_id: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self.send(message)
        return self.receive()

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)

    def close(self) -> tuple[int, str]:
        assert self.process.stdin and self.process.stdout and self.process.stderr
        self.process.stdin.close()
        return_code = self.process.wait(timeout=5)
        stderr = self.process.stderr.read().decode("utf-8", errors="replace")
        self.process.stdout.close()
        self.process.stderr.close()
        return return_code, stderr

    def fail_with_process_output(self, message: str) -> None:
        assert self.process.stdout and self.process.stderr
        self.process.terminate()
        self.process.wait(timeout=5)
        stderr = self.process.stderr.read().decode("utf-8", errors="replace")
        self.process.stdout.close()
        self.process.stderr.close()
        raise AssertionError(f"{message}. stderr={stderr!r}")


class McpProcessIntegrationMixin:
    def exercise_server(self, command: list[str], cwd: Path) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_root = root / "demo-project"
            config_dir = project_root / ".codex"
            config_dir.mkdir(parents=True)
            vault_path = root / "vault"
            (config_dir / "fundus.json").write_text(
                json.dumps(
                    {
                        "vault_path": str(vault_path),
                        "fundus_dir": "Fundus",
                        "default_tags": ["fundus"],
                    }
                )
            )

            client = IndependentStdioMcpClient(command, cwd)
            initialized = client.request(
                1,
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "independent-fundus-test", "version": "1.0.0"},
                },
            )
            client.notify("notifications/initialized")
            listed = client.request(2, "tools/list")
            called = client.request(
                3,
                "tools/call",
                {
                    "name": "create_note",
                    "arguments": {
                        "title": "Independent Client Note",
                        "content": "Unicode content: Grüße",
                        "project": "demo",
                        "project_root": str(project_root),
                    },
                },
            )
            unknown = client.request(
                4,
                "tools/call",
                {"name": "does_not_exist", "arguments": {}},
            )
            ping = client.request(5, "ping")
            return_code, stderr = client.close()

            self.assertEqual(return_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(initialized["result"]["protocolVersion"], "2025-11-25")
            self.assertIn("create", {tool["name"] for tool in listed["result"]["tools"]})
            created = json.loads(called["result"]["content"][0]["text"])
            self.assertEqual(created["path"], "Fundus/demo/independent-client-note.md")
            self.assertTrue((vault_path / created["path"]).exists())
            self.assertEqual(unknown["error"]["code"], -32602)
            self.assertEqual(ping["result"], {})
            return {
                "protocol_version": initialized["result"]["protocolVersion"],
                "server_version": initialized["result"]["serverInfo"]["version"],
                "tool_count": len(listed["result"]["tools"]),
            }


class SourceMcpIntegrationTest(unittest.TestCase, McpProcessIntegrationMixin):
    def test_independent_client_completes_lifecycle_tool_call_and_error_recovery(self) -> None:
        evidence = self.exercise_server(
            [sys.executable, str(ROOT / "scripts" / "fundus_mcp.py")],
            ROOT,
        )

        self.assertEqual(evidence["protocol_version"], "2025-11-25")


class PackagedMcpIntegrationTest(unittest.TestCase, McpProcessIntegrationMixin):
    def test_exact_packaged_command_completes_independent_client_flow(self) -> None:
        configured_root = os.environ.get("FUNDUS_PLUGIN_ROOT")
        if not configured_root:
            self.skipTest("FUNDUS_PLUGIN_ROOT is required for packaged MCP integration")
        plugin_root = Path(configured_root).resolve()
        mcp = json.loads((plugin_root / ".mcp.json").read_text())
        servers = mcp.get("mcp_servers", mcp)
        server = servers["fundus"]
        command = [server["command"], *server.get("args", [])]
        cwd = (plugin_root / server.get("cwd", ".")).resolve()

        evidence = self.exercise_server(command, cwd)

        manifest = json.loads((plugin_root / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(evidence["server_version"], manifest["version"])


if __name__ == "__main__":
    unittest.main()
