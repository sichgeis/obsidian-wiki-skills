#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "fundus.py"


def run_cli(project_root: Path, env: dict[str, str], *arguments: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=project_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Fundus CLI failed for {arguments}: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Fundus CLI returned a non-object for {arguments}")
    return payload


def run_cli_error(project_root: Path, env: dict[str, str], *arguments: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=project_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        raise RuntimeError(f"Fundus CLI unexpectedly succeeded for {arguments}")
    payload = json.loads(result.stderr)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Fundus CLI returned a non-object error for {arguments}")
    return payload


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir).resolve()
        project_root = root / "release-smoke"
        config_dir = project_root / ".codex"
        config_dir.mkdir(parents=True)
        vault = root / "vault"
        (config_dir / "fundus.json").write_text(
            json.dumps({"vault_path": str(vault), "fundus_dir": "Fundus", "default_tags": ["fundus"]})
        )
        env = dict(os.environ)
        env.pop("OBSIDIAN_VAULT_PATH", None)
        env.pop("FUNDUS_CONFIG_PATH", None)
        env["XDG_CONFIG_HOME"] = str(root / "empty-config")
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        doctor = run_cli(project_root, env, "doctor")
        proposal = run_cli(
            project_root,
            env,
            "propose-create",
            "--title",
            "Release Smoke",
            "--alias",
            "SMOKE-200",
            "--content",
            (
                "## Evidence\n\nSTART-SENTINEL\n"
                + ("Temporary release validation with Unicode Grüße 🙂.\n" * 180)
                + "MIDDLE-SENTINEL\n"
                + ("Complete read continuation evidence.\n" * 180)
                + "END-SENTINEL"
            ),
        )
        proposal_path = root / "create-proposal.json"
        proposal_path.write_text(json.dumps(proposal))
        created = run_cli(project_root, env, "apply-create", "--proposal-file", str(proposal_path))
        note_path = str(created["path"])

        search = run_cli(project_root, env, "scan", "--query", "SMOKE-200")
        first_page = run_cli(project_root, env, "read", "--path", note_path, "--paged")
        note_file = vault / note_path
        note_file.write_text(note_file.read_text() + "\n\nDirect temporary-vault edit.\n")
        stale = run_cli_error(
            project_root,
            env,
            "read",
            "--path",
            note_path,
            "--paged",
            "--cursor",
            str(first_page["next_cursor"]),
        )
        pages = []
        cursor = None
        while True:
            arguments = ["read", "--path", note_path, "--paged"]
            if cursor is not None:
                arguments.extend(["--cursor", cursor])
            page = run_cli(project_root, env, *arguments)
            pages.append(page)
            if page["complete"]:
                break
            cursor = str(page["next_cursor"])
        reconstructed = "".join(str(page["content"]) for page in pages)
        read = run_cli(project_root, env, "read", "--path", note_path)
        exact_read_content = note_file.read_text()
        update_proposal = run_cli(
            project_root,
            env,
            "propose-update",
            "--path",
            note_path,
            "--mode",
            "append",
            "--content",
            "Release smoke update.",
        )
        update_path = root / "update-proposal.json"
        update_path.write_text(json.dumps(update_proposal))
        updated = run_cli(project_root, env, "apply-update", "--proposal-file", str(update_path))

        destination = "Fundus/Epics/Release Readiness/references/release-smoke.md"
        moved = run_cli(project_root, env, "move", "--from", note_path, "--to", destination)
        archived = run_cli(project_root, env, "archive", "apply", "--path", destination, "--reason", "smoke")
        restored = run_cli(project_root, env, "archive", "restore", "--path", str(archived["path"]))
        index = run_cli(project_root, env, "index", "rebuild")
        verification = run_cli(project_root, env, "migrate", "wiki-to-fundus", "--verify")

        if not search["documents"] or search["documents"][0]["path"] != note_path:
            raise RuntimeError("release smoke search did not retrieve the created note")
        if stale.get("code") != "READ_CURSOR_STALE":
            raise RuntimeError(f"release smoke stale cursor returned {stale}")
        if len(pages) < 3 or reconstructed != exact_read_content or read["content"] != reconstructed:
            raise RuntimeError("release smoke did not reconstruct the complete paged note")
        if len({page["revision"] for page in pages}) != 1 or not pages[-1]["complete"]:
            raise RuntimeError("release smoke page sequence was not revision-stable and complete")
        if not all(sentinel in reconstructed for sentinel in ("START-SENTINEL", "MIDDLE-SENTINEL", "END-SENTINEL")):
            raise RuntimeError("release smoke paged read lost a sentinel")
        if read["revision"] == updated["revision"]:
            raise RuntimeError("release smoke update did not change the revision")
        if moved["path"] != destination or restored["path"] != destination:
            raise RuntimeError("release smoke move/archive/restore did not preserve the destination")
        if not verification["passed"]:
            raise RuntimeError(f"release smoke corpus verification failed: {verification['issues']}")

        print(
            json.dumps(
                {
                    "ok": True,
                    "temporary_vault": True,
                    "configuration_source": doctor["config_provenance"]["vault_path"],
                    "created_path": note_path,
                    "final_path": destination,
                    "indexed_documents": index["documents"],
                    "corpus_counts": verification["counts"],
                    "read_pages": len(pages),
                    "read_revision": pages[0]["revision"],
                    "stale_cursor_code": stale["code"],
                    "complete": pages[-1]["complete"],
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
