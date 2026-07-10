#!/usr/bin/env python3
from __future__ import annotations

import json
import os
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
PERSONAL_PATH_MARKERS = ("/Users/christian", "\\Users\\christian")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def mcp_server_map(mcp: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    if "mcpServers" in mcp:
        errors.append("mcp config uses unsupported camel-case mcpServers wrapper")
        return {}
    if "mcp_servers" in mcp:
        wrapped = mcp.get("mcp_servers")
        if not isinstance(wrapped, dict):
            errors.append("mcp_servers must be an object")
            return {}
        extra_keys = set(mcp) - {"mcp_servers"}
        require(not extra_keys, "wrapped mcp config must contain only mcp_servers", errors)
        return wrapped
    return mcp


def scan_personal_paths(plugin_root: Path, errors: list[str]) -> None:
    for path in sorted(candidate for candidate in plugin_root.rglob("*") if candidate.is_file()):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for marker in PERSONAL_PATH_MARKERS:
            if marker in content:
                errors.append(f"artifact contains personal path marker {marker!r} in {path.relative_to(plugin_root)}")


def validate_plugin(plugin_root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    mcp_path = plugin_root / ".mcp.json"
    require(manifest_path.exists(), "missing .codex-plugin/plugin.json", errors)
    require(mcp_path.exists(), "missing .mcp.json", errors)
    require((plugin_root / "LICENSE").exists(), "missing declared LICENSE", errors)
    require((plugin_root / "THIRD_PARTY_LICENSES.md").exists(), "missing third-party license inventory", errors)
    require((plugin_root / "RELEASE_NOTES.md").exists(), "missing release notes", errors)
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
    release_notes_path = plugin_root / "RELEASE_NOTES.md"
    if release_notes_path.exists() and manifest.get("version"):
        require(
            f"## {manifest['version']}" in release_notes_path.read_text(),
            "release notes do not match manifest version",
            errors,
        )

    if mcp_path.exists():
        mcp = load_json(mcp_path)
        servers = mcp_server_map(mcp, errors)
        require("fundus" in servers, "mcp config missing fundus server", errors)
        raw_server = servers.get("fundus") or {}
        require(isinstance(raw_server, dict), "fundus MCP server config must be an object", errors)
        server = raw_server if isinstance(raw_server, dict) else {}
        require(
            server.get("command") == "./skills/fundus/scripts/fundus_mcp_launcher.sh",
            "fundus MCP command should use the packaged portable launcher",
            errors,
        )
        require(server.get("args") == [], "fundus MCP launcher args should be empty", errors)
        require(server.get("cwd") == ".", "fundus MCP cwd should be the plugin root", errors)

    require((plugin_root / "skills" / "fundus" / "SKILL.md").exists(), "missing packaged skill", errors)
    require((plugin_root / "skills" / "fundus" / "scripts" / "fundus.py").exists(), "missing packaged helper", errors)
    require((plugin_root / "skills" / "fundus" / "scripts" / "fundus_mcp.py").exists(), "missing packaged MCP server", errors)
    require((plugin_root / "skills" / "fundus" / "scripts" / "fundus_core" / "runtime.py").exists(), "missing packaged core runtime", errors)
    require((plugin_root / "skills" / "fundus" / "scripts" / "fundus_core" / "mcp_server.py").exists(), "missing packaged MCP core", errors)
    launcher_path = plugin_root / "skills" / "fundus" / "scripts" / "fundus_mcp_launcher.sh"
    require(launcher_path.exists(), "missing packaged MCP launcher", errors)
    require(launcher_path.exists() and os.access(launcher_path, os.X_OK), "packaged MCP launcher is not executable", errors)
    require(
        (plugin_root / "skills" / "fundus" / "vendor" / "ruamel_yaml-0.19.1.dist-info" / "licenses" / "LICENSE").exists(),
        "missing vendored ruamel.yaml license",
        errors,
    )
    scan_personal_paths(plugin_root, errors)
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
