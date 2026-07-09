#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: build_plugin_marketplace.py <marketplace-dir> <plugin-build-dir> <plugin-name>", file=sys.stderr)
        return 2

    marketplace_dir = Path(sys.argv[1]).resolve()
    plugin_build_dir = Path(sys.argv[2]).resolve()
    plugin_name = sys.argv[3]
    plugins_dir = marketplace_dir / "plugins"
    marketplace_json = marketplace_dir / ".agents" / "plugins" / "marketplace.json"
    destination = plugins_dir / plugin_name

    if not plugin_build_dir.exists():
        print(f"plugin build directory does not exist: {plugin_build_dir}", file=sys.stderr)
        return 1

    marketplace_dir.mkdir(parents=True, exist_ok=True)
    plugins_dir.mkdir(parents=True, exist_ok=True)
    marketplace_json.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(plugin_build_dir, destination)

    marketplace = {
        "name": "fundus-local",
        "interface": {
            "displayName": "Fundus Local",
        },
        "plugins": [
            {
                "name": plugin_name,
                "source": {
                    "source": "local",
                    "path": f"./plugins/{plugin_name}",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            }
        ],
    }
    marketplace_json.write_text(json.dumps(marketplace, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
