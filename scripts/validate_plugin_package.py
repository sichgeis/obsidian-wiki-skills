#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_INTERFACE_FIELDS = [
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    "defaultPrompt",
    "brandColor",
]


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_plugin(plugin_root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    mcp_path = plugin_root / ".mcp.json"
    require(manifest_path.exists(), "missing .codex-plugin/plugin.json", errors)
    require(mcp_path.exists(), "missing .mcp.json", errors)
    if not manifest_path.exists():
        return errors

    raw_manifest = manifest_path.read_text()
    require("[TODO:" not in raw_manifest, "manifest contains TODO placeholder", errors)
    manifest = load_json(manifest_path)
    require(manifest.get("name") == plugin_root.name.removesuffix("-plugin"), "manifest name does not match plugin package", errors)
    require(bool(manifest.get("version")), "manifest missing version", errors)
    require(bool(manifest.get("description")), "manifest missing description", errors)
    require(bool((manifest.get("author") or {}).get("name")), "manifest missing author.name", errors)
    require(manifest.get("skills") == "./skills/", "manifest skills path should be ./skills/", errors)
    require(manifest.get("mcpServers") == "./.mcp.json", "manifest mcpServers path should be ./.mcp.json", errors)

    interface = manifest.get("interface") or {}
    for field in REQUIRED_INTERFACE_FIELDS:
        require(field in interface and interface[field] not in ["", []], f"interface missing {field}", errors)

    if mcp_path.exists():
        mcp = load_json(mcp_path)
        servers = mcp.get("mcpServers") or {}
        require("fundus" in servers, "mcp config missing fundus server", errors)
        server = servers.get("fundus") or {}
        require(server.get("command") in {"python", "python3"}, "fundus MCP command should be python or python3", errors)
        require("./skills/fundus/scripts/fundus_mcp.py" in (server.get("args") or []), "fundus MCP args should launch packaged server", errors)

    require((plugin_root / "skills" / "fundus" / "SKILL.md").exists(), "missing packaged skill", errors)
    require((plugin_root / "skills" / "fundus" / "scripts" / "fundus.py").exists(), "missing packaged helper", errors)
    require((plugin_root / "skills" / "fundus" / "scripts" / "fundus_mcp.py").exists(), "missing packaged MCP server", errors)
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_plugin_package.py <plugin-root>", file=sys.stderr)
        return 2
    plugin_root = Path(sys.argv[1]).resolve()
    errors = validate_plugin(plugin_root)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "plugin": str(plugin_root)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
