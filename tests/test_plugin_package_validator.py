from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate_plugin_package.py"
SPEC = importlib.util.spec_from_file_location("validate_plugin_package", VALIDATOR_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
sys.modules["validate_plugin_package"] = validator
SPEC.loader.exec_module(validator)


class PluginPackageValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.plugin_root = Path(self.temp_dir.name) / "fundus-plugin"
        (self.plugin_root / ".codex-plugin").mkdir(parents=True)
        (self.plugin_root / "skills" / "fundus" / "scripts").mkdir(parents=True)
        (self.plugin_root / "skills" / "fundus" / "scripts" / "fundus_core").mkdir(parents=True)
        (self.plugin_root / "skills" / "fundus" / "vendor" / "ruamel_yaml-0.19.1.dist-info" / "licenses").mkdir(parents=True)
        (self.plugin_root / "skills" / "fundus" / "SKILL.md").write_text("# Fundus\n")
        (self.plugin_root / "skills" / "fundus" / "scripts" / "fundus.py").write_text("")
        (self.plugin_root / "skills" / "fundus" / "scripts" / "fundus_mcp.py").write_text("")
        (self.plugin_root / "skills" / "fundus" / "scripts" / "fundus_core" / "runtime.py").write_text("")
        (self.plugin_root / "skills" / "fundus" / "scripts" / "fundus_core" / "mcp_server.py").write_text("")
        launcher = self.plugin_root / "skills" / "fundus" / "scripts" / "fundus_mcp_launcher.sh"
        launcher.write_text("#!/bin/sh\n")
        launcher.chmod(0o755)
        (self.plugin_root / "skills" / "fundus" / "vendor" / "ruamel_yaml-0.19.1.dist-info" / "licenses" / "LICENSE").write_text("MIT\n")
        (self.plugin_root / "LICENSE").write_text("MIT\n")
        (self.plugin_root / "THIRD_PARTY_LICENSES.md").write_text("# Third-party licenses\n")
        (self.plugin_root / "RELEASE_NOTES.md").write_text("# Release notes\n\n## 0.1.0\n")
        (self.plugin_root / ".codex-plugin" / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "fundus",
                    "version": "0.1.0",
                    "description": "Fundus test package",
                    "author": {"name": "Test"},
                    "skills": "./skills/",
                    "mcpServers": "./.mcp.json",
                    "interface": {
                        "displayName": "Fundus",
                        "shortDescription": "Short",
                        "longDescription": "Long",
                        "developerName": "Test",
                        "category": "Productivity",
                        "capabilities": ["Write"],
                        "defaultPrompt": ["Search Fundus"],
                        "brandColor": "#000000",
                    },
                }
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def server_config() -> dict:
        return {
            "fundus": {
                "command": "./skills/fundus/scripts/fundus_mcp_launcher.sh",
                "args": [],
                "cwd": ".",
            }
        }

    def write_mcp(self, payload: dict) -> None:
        (self.plugin_root / ".mcp.json").write_text(json.dumps(payload))

    def test_accepts_documented_direct_server_map(self) -> None:
        self.write_mcp(self.server_config())

        self.assertEqual(validator.validate_plugin(self.plugin_root), [])

    def test_accepts_documented_mcp_servers_wrapper(self) -> None:
        self.write_mcp({"mcp_servers": self.server_config()})

        self.assertEqual(validator.validate_plugin(self.plugin_root), [])

    def test_rejects_undocumented_camel_case_wrapper(self) -> None:
        self.write_mcp({"mcpServers": self.server_config()})

        errors = validator.validate_plugin(self.plugin_root)

        self.assertIn("mcp config uses unsupported camel-case mcpServers wrapper", errors)
        self.assertIn("mcp config missing fundus server", errors)

    def test_rejects_personal_path_in_distributable_artifact(self) -> None:
        self.write_mcp(self.server_config())
        (self.plugin_root / "skills" / "fundus" / "config.json").write_text(
            '{"vault_path":"/Users/christian/vault/private"}\n'
        )

        errors = validator.validate_plugin(self.plugin_root)

        self.assertTrue(any("personal path marker" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
