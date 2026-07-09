#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import fundus


ROOT = Path(__file__).resolve().parents[1]


def approx_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def file_measure(path: Path) -> dict[str, object]:
    text = path.read_text()
    return {
        "path": str(path.relative_to(ROOT)),
        "chars": len(text),
        "approx_tokens": approx_tokens(text),
        "lines": text.count("\n") + 1,
    }


def sample_scan_output() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = (Path(temp_dir) / "vault").resolve()
        config = fundus.Config(
            vault_path=vault,
            fundus_dir="Fundus",
            default_tags=["fundus"],
            redaction_enabled=True,
            redaction_patterns=["API_KEY", "SECRET", "TOKEN", "PASSWORD"],
        )
        fundus.create_document(
            config,
            "demo",
            "Prompt Authoring Boundary",
            "## Context\n\nBACKEND-2291 defines a prompt authoring boundary.",
            ["domain"],
            aliases=["BACKEND-2291"],
            resource="https://jira.example/browse/BACKEND-2291",
        )
        fundus.rebuild_index(config)
        output = json.dumps(
            {
                "documents": fundus.scan_documents(config, "demo", "BACKEND-2291", limit=3),
            },
            indent=2,
        )
        return {
            "chars": len(output),
            "approx_tokens": approx_tokens(output),
            "sample": json.loads(output),
        }


def main() -> int:
    files = [
        ROOT / "SKILL.md",
        ROOT / ".mcp.json",
        ROOT / ".codex-plugin" / "plugin.json",
        ROOT / "docs" / "reference" / "fundus-cli-reference.md",
    ]
    payload = {
        "files": [file_measure(path) for path in files if path.exists()],
        "sample_scan_output": sample_scan_output(),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
