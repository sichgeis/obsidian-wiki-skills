#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import platform
import resource
import statistics
import tempfile
import time
from pathlib import Path

import fundus


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def generate_corpus(config: fundus.Config, note_count: int) -> None:
    scope = fundus.project_scope("benchmark")
    root = fundus.fundus_scope_dir(config, scope)
    root.mkdir(parents=True, exist_ok=True)
    for index in range(note_count):
        title = f"Benchmark Note {index:04d}"
        frontmatter = fundus.frontmatter_for_new_document(
            config,
            "benchmark",
            scope,
            title,
            ["benchmark", f"shard-{index % 50}"],
            aliases=[f"BENCH-{index:04d}"],
        )
        body = (
            "## Benchmark Context\n\n"
            f"Deterministic benchmark payload for shard {index % 50}. "
            f"Ticket BACKEND-{10000 + index} contains shared retrieval detail."
        )
        fundus.atomic_write(root / f"benchmark-note-{index:04d}.md", fundus.render_document(frontmatter, body))


def run_benchmark(note_count: int, iterations: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = (Path(temp_dir) / "vault").resolve()
        config = fundus.Config(
            vault_path=vault,
            fundus_dir="Fundus",
            default_tags=["fundus"],
            redaction_enabled=True,
            redaction_patterns=[],
        )
        generate_started = time.perf_counter()
        generate_corpus(config, note_count)
        generate_ms = (time.perf_counter() - generate_started) * 1000

        rebuild_started = time.perf_counter()
        fundus.rebuild_index(config)
        rebuild_ms = (time.perf_counter() - rebuild_started) * 1000

        durations_ms: list[float] = []
        for iteration in range(iterations):
            query = f"shard {iteration % 50} shared retrieval"
            started = time.perf_counter()
            results = fundus.scan_documents(config, "benchmark", query, limit=10)
            durations_ms.append((time.perf_counter() - started) * 1000)
            if not results:
                raise RuntimeError(f"Benchmark query returned no results: {query}")

        changed_path = vault / "Fundus" / "benchmark" / "benchmark-note-0000.md"
        changed_path.write_text(changed_path.read_text().replace("shared retrieval detail", "freshincrementaltoken"))
        incremental_started = time.perf_counter()
        incremental_results = fundus.scan_documents(config, "benchmark", "freshincrementaltoken", limit=3)
        incremental_ms = (time.perf_counter() - incremental_started) * 1000
        if not incremental_results or incremental_results[0]["path"] != "Fundus/benchmark/benchmark-note-0000.md":
            raise RuntimeError("Incremental refresh did not expose the externally edited note.")

        index_file = vault / "Fundus" / fundus.INDEX_FILENAME
        return {
            "notes": note_count,
            "iterations": iterations,
            "generation_ms": round(generate_ms, 3),
            "full_rebuild_ms": round(rebuild_ms, 3),
            "warm_search_p50_ms": round(statistics.median(durations_ms), 3),
            "warm_search_p95_ms": round(percentile(durations_ms, 0.95), 3),
            "warm_search_max_ms": round(max(durations_ms), 3),
            "one_file_in_memory_refresh_ms": round(incremental_ms, 3),
            "index_bytes": index_file.stat().st_size,
            "max_rss_raw": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "search_repair_policy": "read-only in-memory; explicit rebuild persists",
            "python": platform.python_version(),
            "platform": platform.platform(),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark deterministic Fundus index rebuild and warm search.")
    parser.add_argument("--notes", type=int, default=2000)
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--assert-p95-ms", type=float)
    parser.add_argument("--output", type=Path, help="Also write the JSON report to this path.")
    args = parser.parse_args()
    if args.notes < 1 or args.iterations < 1:
        parser.error("--notes and --iterations must be positive")

    payload = run_benchmark(args.notes, args.iterations)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    if args.assert_p95_ms is not None and float(payload["warm_search_p95_ms"]) > args.assert_p95_ms:
        print(
            f"Warm search p95 {payload['warm_search_p95_ms']} ms exceeds {args.assert_p95_ms} ms.",
            flush=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
