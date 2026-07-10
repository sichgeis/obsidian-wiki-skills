#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
MARKETPLACE = "fundus-local"
PLUGIN = "fundus"


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    source_version = str(json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))["version"])
    cache_root = Path.home() / ".codex" / "plugins" / "cache" / MARKETPLACE / PLUGIN
    candidates = sorted(
        (path for path in cache_root.glob(f"{source_version}+codex.*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if not candidates:
        fail(f"No installed {PLUGIN} cache matches source version {source_version}: {cache_root}")
    installed_root = candidates[0]
    installed_manifest_path = installed_root / ".codex-plugin" / "plugin.json"
    required = [
        installed_manifest_path,
        installed_root / ".mcp.json",
        installed_root / "RELEASE_NOTES.md",
        installed_root / "skills" / PLUGIN / "SKILL.md",
        installed_root / "skills" / PLUGIN / "config.json",
        installed_root / "skills" / PLUGIN / "requirements.txt",
        installed_root / "skills" / PLUGIN / "agents" / "openai.yaml",
        installed_root / "skills" / PLUGIN / "docs" / "reference" / "fundus-cli-reference.md",
        installed_root / "skills" / PLUGIN / "docs" / "reference" / "fundus-workbench-examples.md",
        installed_root / "skills" / PLUGIN / "scripts" / "fundus.py",
        installed_root / "skills" / PLUGIN / "scripts" / "fundus_mcp.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        fail(f"Installed plugin is incomplete: {missing}")

    installed_version = str(json.loads(installed_manifest_path.read_text(encoding="utf-8"))["version"])
    if not installed_version.startswith(f"{source_version}+codex."):
        fail(f"Installed version {installed_version} does not match source {source_version}.")

    listing = subprocess.run(
        ["codex", "plugin", "list"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    installed_pattern = re.compile(
        rf"^{re.escape(PLUGIN)}@{re.escape(MARKETPLACE)}\s+installed, enabled\s+{re.escape(installed_version)}\s+",
        re.MULTILINE,
    )
    if installed_pattern.search(listing) is None:
        fail(f"{PLUGIN}@{MARKETPLACE} {installed_version} is not installed and enabled.")

    mcp_script = installed_root / "skills" / PLUGIN / "scripts" / "fundus_mcp.py"
    check = subprocess.run(
        [sys.executable, str(mcp_script), "--check"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    check_payload = json.loads(check.stdout)
    if check_payload != {"ok": True, "server": "fundus"}:
        fail(f"Installed MCP check returned an unexpected result: {check_payload}")

    print(
        json.dumps(
            {
                "ok": True,
                "plugin": f"{PLUGIN}@{MARKETPLACE}",
                "source_version": source_version,
                "installed_version": installed_version,
                "installed_root": str(installed_root),
                "mcp": check_payload,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
