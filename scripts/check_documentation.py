#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKBENCH_TOOLS = (
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
)


def main() -> int:
    errors: list[str] = []
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
    version = manifest["version"]
    release_notes = (ROOT / "RELEASE_NOTES.md").read_text()
    readme = (ROOT / "README.md").read_text()
    skill = (ROOT / "SKILL.md").read_text()
    reference = (ROOT / "docs" / "reference" / "fundus-cli-reference.md").read_text()
    tracker = (ROOT / "docs" / "agent-implementation-tracker.md").read_text()

    if f"## {version}" not in release_notes:
        errors.append(f"RELEASE_NOTES.md has no section for manifest version {version}")
    for tool in WORKBENCH_TOOLS:
        if tool not in readme:
            errors.append(f"README.md does not name workbench tool {tool}")
        if tool not in reference:
            errors.append(f"CLI reference does not name workbench tool {tool}")
    for token in ("FUNDUS_CONFIG_PATH", "OBSIDIAN_VAULT_PATH", "config_provenance"):
        if token not in readme + reference:
            errors.append(f"configuration documentation omits {token}")
    for phase in range(11, 20):
        board_row = next((line for line in tracker.splitlines() if line.startswith(f"| P{phase} ")), "")
        if "| done |" not in board_row:
            errors.append(f"P{phase} is not done on the phase board")
    for entrypoint in (ROOT / "scripts" / "fundus.py", ROOT / "scripts" / "fundus_mcp.py"):
        lines = entrypoint.read_text().splitlines()
        if len(lines) > 50:
            errors.append(f"compatibility entrypoint is not thin: {entrypoint.relative_to(ROOT)} ({len(lines)} lines)")
    for required in (
        ROOT / "scripts" / "fundus_core" / "runtime.py",
        ROOT / "scripts" / "fundus_core" / "mcp_server.py",
        ROOT / "scripts" / "fundus_core" / "README.md",
        ROOT / "LICENSE",
        ROOT / "THIRD_PARTY_LICENSES.md",
    ):
        if not required.exists():
            errors.append(f"documented release file is missing: {required.relative_to(ROOT)}")
    if '"command": "python"' in readme:
        errors.append("README.md still documents the pre-launcher MCP command")
    if "migrate wiki-to-fundus --apply" in readme:
        errors.append("README.md still presents migration apply in normal onboarding")
    if "config_provenance" not in skill and "configuration source" not in skill.lower():
        errors.append("SKILL.md does not tell agents that doctor exposes configuration sources")

    payload = {"ok": not errors, "version": version, "errors": errors}
    print(json.dumps(payload, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
