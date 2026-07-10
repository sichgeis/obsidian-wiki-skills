from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "tests" / "fixtures"
SCRIPT_PATH = ROOT / "scripts" / "fundus.py"
SPEC = importlib.util.spec_from_file_location("fundus", SCRIPT_PATH)
assert SPEC and SPEC.loader
fundus = importlib.util.module_from_spec(SPEC)
sys.modules["fundus"] = fundus
SPEC.loader.exec_module(fundus)


def concurrent_update_worker(
    vault_path: str,
    note_path: str,
    expected_revision: str,
    content: str,
    start_event: object,
    result_queue: object,
) -> None:
    config = fundus.Config(
        vault_path=Path(vault_path),
        fundus_dir="Fundus",
        default_tags=["fundus"],
        redaction_enabled=True,
        redaction_patterns=[],
    )
    start_event.wait(10)
    try:
        result = fundus.update_document(
            config,
            "demo",
            note_path,
            "append",
            content,
            None,
            fundus.project_scope("demo"),
            expected_revision,
        )
        result_queue.put(("ok", result["revision"]))
    except fundus.FundusError as exc:
        result_queue.put(("error", exc.code))


class FundusTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.temp_dir.name).resolve()
        self.config = fundus.Config(
            vault_path=self.vault_path,
            fundus_dir="Fundus",
            default_tags=["fundus"],
            redaction_enabled=True,
            redaction_patterns=["API_KEY", "SECRET", "TOKEN", "PASSWORD"],
        )
        self.path = self.vault_path / "Fundus" / "demo" / "article.md"
        self.path.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def read_document_body(self, path: Path) -> str:
        _, body = fundus.parse_frontmatter(path.read_text())
        return body.strip()


class ConfigurationResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.project_root = self.root / "project"
        self.project_root.mkdir()
        self.config_home = self.root / "config"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def environment(self, **values: str) -> dict[str, str]:
        return {
            "HOME": str(self.root / "home"),
            "XDG_CONFIG_HOME": str(self.config_home),
            **values,
        }

    def write_json(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))

    def test_configuration_precedence_and_provenance(self) -> None:
        user_config = self.config_home / "fundus" / "config.json"
        project_config = self.project_root / ".codex" / "fundus.json"
        custom_config = self.root / "custom.json"
        self.write_json(user_config, {"vault_path": str(self.root / "user-vault"), "fundus_dir": "UserFundus"})
        self.write_json(project_config, {"vault_path": str(self.root / "project-vault")})
        self.write_json(custom_config, {"vault_path": str(self.root / "custom-vault"), "fundus_dir": "CustomFundus"})

        with patch.dict(
            os.environ,
            self.environment(
                FUNDUS_CONFIG_PATH=str(custom_config),
                OBSIDIAN_VAULT_PATH=str(self.root / "environment-vault"),
            ),
            clear=True,
        ):
            explicit = fundus.resolve_config(
                self.project_root,
                {"vault_path": str(self.root / "explicit-vault"), "fundus_dir": "ExplicitFundus"},
            )
            self.assertEqual(explicit.vault_path, self.root / "explicit-vault")
            self.assertEqual(explicit.fundus_dir, "ExplicitFundus")
            self.assertEqual(explicit.provenance["vault_path"], "explicit operation argument")

            compatible = fundus.resolve_config(self.project_root)
            self.assertEqual(compatible.vault_path, self.root / "environment-vault")
            self.assertEqual(compatible.fundus_dir, "CustomFundus")
            self.assertEqual(compatible.provenance["vault_path"], "OBSIDIAN_VAULT_PATH")

            del os.environ["OBSIDIAN_VAULT_PATH"]
            custom = fundus.resolve_config(self.project_root)
            self.assertEqual(custom.vault_path, self.root / "custom-vault")
            self.assertTrue(custom.provenance["vault_path"].startswith("FUNDUS_CONFIG_PATH:"))

            del os.environ["FUNDUS_CONFIG_PATH"]
            project = fundus.resolve_config(self.project_root)
            self.assertEqual(project.vault_path, self.root / "project-vault")
            self.assertEqual(project.fundus_dir, "UserFundus")
            self.assertTrue(project.provenance["vault_path"].startswith("project config:"))
            self.assertTrue(project.provenance["fundus_dir"].startswith("user config:"))

    def test_user_config_supports_new_machine_doctor(self) -> None:
        vault = self.root / "new-vault"
        vault.mkdir()
        self.write_json(
            self.config_home / "fundus" / "config.json",
            {"vault_path": str(vault), "fundus_dir": "Knowledge"},
        )

        with patch.dict(os.environ, self.environment(), clear=True):
            config = fundus.resolve_config(self.project_root)
            report = fundus.doctor_report(config, self.project_root, "demo")

        self.assertEqual(report["fundus_root"], str(vault / "Knowledge"))
        self.assertTrue(report["config_provenance"]["vault_path"].startswith("user config:"))
        self.assertEqual(report["python_executable"], sys.executable)
        self.assertTrue(report["config_sources"])

    def test_missing_vault_configuration_is_actionable(self) -> None:
        with patch.dict(os.environ, self.environment(), clear=True):
            with self.assertRaises(fundus.FundusError) as raised:
                fundus.resolve_config(self.project_root)

        self.assertEqual(raised.exception.code, "CONFIG_MISSING")


class FrontmatterCodecTest(FundusTestCase):
    def assert_semantic_round_trip(self, text: str) -> dict[str, object]:
        frontmatter, body = fundus.parse_frontmatter(text)
        rendered = fundus.render_existing_document_preserving_body(frontmatter, body)
        reparsed, reparsed_body = fundus.parse_frontmatter(rendered)
        self.assertEqual(dict(reparsed), dict(frontmatter))
        self.assertEqual(reparsed_body, body)
        return frontmatter

    def test_supported_yaml_shapes_round_trip_semantically(self) -> None:
        fixtures = json.loads((FIXTURES_DIR / "frontmatter_cases.json").read_text())["supported"]

        for fixture in fixtures:
            with self.subTest(fixture=fixture["name"]):
                self.assert_semantic_round_trip(fixture["document"])

    def test_known_list_field_normalizes_scalar_to_list(self) -> None:
        frontmatter = self.assert_semantic_round_trip("---\ntitle: Note\ntags: ticket\n---\nBody\n")

        self.assertEqual(frontmatter["tags"], ["ticket"])

    def test_generated_supported_values_round_trip(self) -> None:
        scalar_values = [
            "plain",
            "colon: value",
            "hash # value",
            "apostrophe's and \"quotes\"",
            "Café 日本語",
            True,
            False,
            0,
            42,
            3.5,
            None,
        ]

        for index, value in enumerate(scalar_values):
            with self.subTest(index=index, value=value):
                source = {"unknown_key": value, "tags": [value]}
                rendered = fundus.render_existing_document(source, "Body")
                parsed, body = fundus.parse_frontmatter(rendered)
                rerendered = fundus.render_existing_document_preserving_body(parsed, body)
                reparsed, reparsed_body = fundus.parse_frontmatter(rerendered)
                self.assertEqual(dict(reparsed), dict(parsed))
                self.assertEqual(reparsed_body, body)

    def test_comments_and_unknown_keys_survive_metadata_render(self) -> None:
        text = "---\n# document comment\ntitle: \"A: # value\" # inline comment\nunknown_key: keep-me\ntags: ticket\n---\n\nBody\n"
        frontmatter, body = fundus.parse_frontmatter(text)
        frontmatter["updated"] = "2026-07-10T12:00:00+02:00"

        rendered = fundus.render_existing_document_preserving_body(frontmatter, body)
        reparsed, _ = fundus.parse_frontmatter(rendered)

        self.assertIn("# document comment", rendered)
        self.assertIn("# inline comment", rendered)
        self.assertEqual(reparsed["unknown_key"], "keep-me")
        self.assertEqual(reparsed["title"], "A: # value")

    def test_unsupported_yaml_fails_with_stable_error_code(self) -> None:
        fixtures = json.loads((FIXTURES_DIR / "frontmatter_cases.json").read_text())["unsupported"]

        for fixture in fixtures:
            with self.subTest(fixture=fixture["name"]):
                with self.assertRaises(fundus.FundusError) as raised:
                    fundus.parse_frontmatter(fixture["document"])
                self.assertEqual(raised.exception.code, "FRONTMATTER_INVALID")

    def test_bom_crlf_normalization_preserves_body_bytes(self) -> None:
        original = (
            "\ufeff---\r\n"
            "# preserved comment\r\n"
            "title: Article\r\n"
            "tags: ticket\r\n"
            "unknown_key: \"value: # literal\"\r\n"
            "---\r\n"
            "\r\n# Article\r\n\r\nBody with trailing spaces.  \r\n"
        )
        self.path.write_bytes(original.encode("utf-8"))
        _, original_body = fundus.parse_frontmatter(original)

        result = fundus.normalize_frontmatter_for_path(self.config, self.path, apply=True)

        rendered_bytes = self.path.read_bytes()
        rendered = rendered_bytes.decode("utf-8")
        frontmatter, rendered_body = fundus.parse_frontmatter(rendered)
        self.assertTrue(result["body_unchanged"])
        self.assertEqual(rendered_body.encode("utf-8"), original_body.encode("utf-8"))
        self.assertTrue(rendered_bytes.startswith(b"\xef\xbb\xbf---\r\n"))
        self.assertNotIn(b"\n", rendered_bytes.replace(b"\r\n", b""))
        self.assertIn("# preserved comment", rendered)
        self.assertEqual(frontmatter["unknown_key"], "value: # literal")
        self.assertEqual(frontmatter["tags"], ["fundus", "project/demo", "ticket"])


class CreateDocumentTest(FundusTestCase):
    def create_article(self, title: str, body: str) -> Path:
        result = fundus.create_document(self.config, "demo", title, body, None)
        return self.vault_path / result["path"]

    def test_create_removes_duplicate_leading_title_heading(self) -> None:
        path = self.create_article("Authentication Flow", "# Authentication Flow\n\n## Overview\n\nDetails")

        self.assertEqual(
            self.read_document_body(path),
            "# Authentication Flow\n\n## Overview\n\nDetails",
        )

    def test_create_removes_duplicate_title_heading_case_insensitively(self) -> None:
        path = self.create_article("Authentication Flow", "# authentication flow\n\nDetails")

        self.assertEqual(self.read_document_body(path), "# Authentication Flow\n\nDetails")

    def test_create_preserves_non_matching_leading_h1(self) -> None:
        path = self.create_article("Authentication Flow", "# Session Flow\n\nDetails")

        self.assertEqual(self.read_document_body(path), "# Authentication Flow\n\n# Session Flow\n\nDetails")

    def test_create_preserves_lower_level_heading_content(self) -> None:
        path = self.create_article("Authentication Flow", "## Overview\n\nDetails")

        self.assertEqual(self.read_document_body(path), "# Authentication Flow\n\n## Overview\n\nDetails")

    def test_create_preserves_plain_body_content(self) -> None:
        path = self.create_article("Authentication Flow", "Details")

        self.assertEqual(self.read_document_body(path), "# Authentication Flow\n\nDetails")


class IndexSearchTest(FundusTestCase):
    def create_article(self, title: str, body: str, tags: list[str] | None = None) -> Path:
        result = fundus.create_document(self.config, "demo", title, body, tags)
        return self.vault_path / result["path"]

    def test_rebuild_index_includes_document_metadata_headings_and_excerpt(self) -> None:
        self.create_article(
            "Allow Full Fundus Article Rewrite",
            "## Refined Ticket\n\nAllow replacing the complete article body.",
            ["ticket"],
        )

        payload = fundus.rebuild_index(self.config)

        self.assertEqual(len(payload["documents"]), 1)
        entry = payload["documents"][0]
        self.assertEqual(entry["title"], "Allow Full Fundus Article Rewrite")
        self.assertEqual(entry["project"], "demo")
        self.assertIn("Refined Ticket", entry["headings"])
        self.assertIn("article", entry["tokens"])
        self.assertTrue(entry["revision"].startswith("sha256:"))
        self.assertGreater(entry["size"], 0)
        self.assertTrue((self.vault_path / "Fundus" / fundus.INDEX_FILENAME).exists())

    def test_scan_uses_index_for_body_and_heading_matches(self) -> None:
        self.create_article(
            "Allow Full Fundus Article Rewrite",
            "## Refined Ticket\n\nAllow replacing the complete article body.",
            ["ticket"],
        )
        fundus.rebuild_index(self.config)

        results = fundus.scan_documents(self.config, "demo", "article body replace")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Allow Full Fundus Article Rewrite")
        self.assertEqual(results[0]["reason"], "title,body")

    def test_scan_matches_ticket_id_from_body(self) -> None:
        self.create_article(
            "LLM OCR Fallback Ticket",
            "## Context\n\nImplement BACKEND-2242 page-aware retry budgets.",
            ["ticket"],
        )
        fundus.rebuild_index(self.config)

        results = fundus.scan_documents(self.config, "demo", "backend-2242")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "LLM OCR Fallback Ticket")
        self.assertIn("ticket:BACKEND-2242", results[0]["reason"])

    def test_scan_matches_alias_and_resource_metadata(self) -> None:
        fundus.create_document(
            self.config,
            "demo",
            "Prompt Authoring Boundary",
            "## Context\n\nDurable context.",
            ["domain"],
            aliases=["BACKEND-2291", "Workbench Alias"],
            resource="https://jira.example/browse/BACKEND-2291",
            status="active",
            owner="Christian",
            last_verified="2026-07-09",
        )
        fundus.rebuild_index(self.config)

        alias_results = fundus.scan_documents(self.config, "demo", "workbench alias")
        resource_results = fundus.scan_documents(self.config, "demo", "jira example")

        self.assertEqual(alias_results[0]["title"], "Prompt Authoring Boundary")
        self.assertIn("alias", alias_results[0]["reason"])
        self.assertEqual(alias_results[0]["confidence"], "medium")
        self.assertEqual(alias_results[0]["aliases"], ["BACKEND-2291", "Workbench Alias"])
        self.assertEqual(alias_results[0]["resource"], "https://jira.example/browse/BACKEND-2291")
        self.assertEqual(alias_results[0]["last_verified"], "2026-07-09")
        self.assertEqual(resource_results[0]["title"], "Prompt Authoring Boundary")

    def test_create_refreshes_existing_index_entry(self) -> None:
        fundus.rebuild_index(self.config)

        self.create_article("New Ticket", "## Context\n\nFresh indexed content.", ["ticket"])

        results = fundus.scan_documents(self.config, "demo", "fresh indexed")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "New Ticket")

    def test_update_refreshes_existing_index_entry(self) -> None:
        path = self.create_article("Existing Ticket", "## Context\n\nOld content.", ["ticket"])
        fundus.rebuild_index(self.config)

        fundus.update_document(
            self.config,
            "demo",
            str(path.relative_to(self.vault_path)),
            "append",
            "## Follow Up\n\nNew searchable phrase.",
            None,
        )

        results = fundus.scan_documents(self.config, "demo", "searchable phrase")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Existing Ticket")

    def test_index_status_reports_fresh_index(self) -> None:
        self.create_article("Existing Ticket", "Body", ["ticket"])
        fundus.rebuild_index(self.config)

        status = fundus.index_status(self.config)

        self.assertTrue(status["exists"])
        self.assertTrue(status["valid"])
        self.assertFalse(status["stale"])
        self.assertEqual(status["documents"], 1)

    def test_index_status_reports_changed_document_as_stale(self) -> None:
        path = self.create_article("Existing Ticket", "Body", ["ticket"])
        fundus.rebuild_index(self.config)
        path.write_text(path.read_text() + "\nChanged outside the tool.\n")

        status = fundus.index_status(self.config)

        self.assertTrue(status["stale"])
        self.assertEqual(status["stale_paths"], ["Fundus/demo/existing-ticket.md"])

    def test_no_index_and_current_index_search_are_equivalent(self) -> None:
        self.create_article("Architecture Alpha", "## Router Heading\n\nShared body phrase.", ["architecture"])
        fundus.create_document(
            self.config,
            "demo",
            "Prompt Boundary",
            "## Context\n\nBACKEND-2291 prompt details.",
            ["domain"],
            aliases=["Workbench Alias"],
            resource="https://jira.example/BACKEND-2291",
        )
        self.create_article("Café Résumé", "## Überprüfung\n\nUnicode naïve façade.", ["unicode"])
        archived_path = self.create_article("Historical Ticket", "Archived searchable evidence.", ["ticket"])
        fundus.archive_document(self.config, str(archived_path.relative_to(self.vault_path)), "historical")
        redirect_source = fundus.create_document(
            self.config,
            "demo",
            "Redirect Source",
            "Redirect-only phrase.",
            ["redirect-test"],
        )
        fundus.move_document(
            self.config,
            redirect_source["path"],
            "Fundus/Epics/Search Quality/redirect-source.md",
            leave_stub=True,
        )
        queries = [
            ("router heading", False),
            ("shared body phrase", False),
            ("BACKEND-2291", False),
            ("workbench alias", False),
            ("jira example", False),
            ("café résumé", False),
            ("unicode naïve façade", False),
            ("archived searchable", True),
            (None, False),
        ]

        without_index = {
            (query, archived): fundus.scan_documents(
                self.config,
                "demo",
                query,
                include_archived=archived,
                include_snippet=True,
            )
            for query, archived in queries
        }
        fundus.rebuild_index(self.config)
        with_index = {
            (query, archived): fundus.scan_documents(
                self.config,
                "demo",
                query,
                include_archived=archived,
                include_snippet=True,
            )
            for query, archived in queries
        }

        self.assertEqual(with_index, without_index)
        self.assertFalse(any(result["path"] == redirect_source["path"] for results in with_index.values() for result in results))
        self.assertTrue(all(result["revision"].startswith("sha256:") for results in with_index.values() for result in results))

    def test_search_repairs_external_edit_add_and_delete_in_memory(self) -> None:
        changed_path = self.create_article("Externally Changed", "Old indexed phrase.", ["ticket"])
        deleted_path = self.create_article("Externally Deleted", "Deletedonlytoken.", ["ticket"])
        fundus.rebuild_index(self.config)
        index_file = self.vault_path / "Fundus" / fundus.INDEX_FILENAME
        original_index_bytes = index_file.read_bytes()

        changed_path.write_text(
            changed_path.read_text().replace("Externally Changed", "Current External Title").replace(
                "Old indexed phrase.", "Current external body phrase."
            )
        )
        added_path = self.vault_path / "Fundus" / "demo" / "externally-added.md"
        added_frontmatter = fundus.frontmatter_for_new_document(
            self.config,
            "demo",
            fundus.project_scope("demo"),
            "Externally Added",
            ["ticket"],
        )
        added_path.write_text(fundus.render_document(added_frontmatter, "Newlyindexedaddition phrase."))
        deleted_path.unlink()

        changed_results = fundus.scan_documents(self.config, "demo", "current external body")
        added_results = fundus.scan_documents(self.config, "demo", "newlyindexedaddition")
        deleted_results = fundus.scan_documents(self.config, "demo", "deletedonlytoken")

        self.assertEqual(changed_results[0]["title"], "Current External Title")
        self.assertEqual([result["path"] for result in added_results], ["Fundus/demo/externally-added.md"])
        self.assertEqual(deleted_results, [])
        self.assertEqual(index_file.read_bytes(), original_index_bytes)
        self.assertTrue(fundus.index_status(self.config)["stale"])

    def test_corrupt_and_incompatible_indexes_fall_back_without_writing(self) -> None:
        self.create_article("Fallback Search", "Corrupt index fallback phrase.", ["ticket"])
        index_file = self.vault_path / "Fundus" / fundus.INDEX_FILENAME
        expected = fundus.scan_documents(self.config, "demo", "fallback phrase")

        corrupt = b"{not-json\n"
        index_file.write_bytes(corrupt)
        corrupt_results = fundus.scan_documents(self.config, "demo", "fallback phrase")
        corrupt_status = fundus.index_status(self.config)
        self.assertEqual(corrupt_results, expected)
        self.assertEqual(index_file.read_bytes(), corrupt)
        self.assertEqual(corrupt_status["state"], "corrupt")
        self.assertFalse(corrupt_status["valid"])

        incompatible = b'{"version": 999, "documents": []}\n'
        index_file.write_bytes(incompatible)
        incompatible_results = fundus.scan_documents(self.config, "demo", "fallback phrase")
        incompatible_status = fundus.index_status(self.config)
        self.assertEqual(incompatible_results, expected)
        self.assertEqual(index_file.read_bytes(), incompatible)
        self.assertEqual(incompatible_status["state"], "incompatible")

    def test_equal_score_results_have_deterministic_title_path_order(self) -> None:
        self.create_article("Zulu Candidate", "Shared deterministic phrase.", ["ticket"])
        self.create_article("Alpha Candidate", "Shared deterministic phrase.", ["ticket"])

        direct = fundus.scan_documents(self.config, "demo", "shared deterministic")
        fundus.rebuild_index(self.config)
        indexed = fundus.scan_documents(self.config, "demo", "shared deterministic")

        self.assertEqual([result["title"] for result in direct], ["Alpha Candidate", "Zulu Candidate"])
        self.assertEqual(indexed, direct)


class ArchiveDocumentTest(FundusTestCase):
    def create_article(self, title: str, body: str, tags: list[str] | None = None) -> Path:
        result = fundus.create_document(self.config, "demo", title, body, tags)
        return self.vault_path / result["path"]

    def write_article_with_updated(self, title: str, updated: str, tags: list[str]) -> Path:
        path = self.vault_path / "Fundus" / "demo" / f"{fundus.slugify(title)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        tag_lines = "\n".join(f"  - {tag}" for tag in tags)
        path.write_text(
            "\n".join(
                [
                    "---",
                    f"title: {title}",
                    "created: 2025-01-01T00:00:00+00:00",
                    f"updated: {updated}",
                    "project: demo",
                    "tags:",
                    tag_lines,
                    "---",
                    "",
                    f"# {title}",
                    "",
                    "Body",
                    "",
                ]
            )
        )
        return path

    def test_archive_candidates_excludes_durable_tags_by_default(self) -> None:
        self.write_article_with_updated("Old Ticket", "2025-01-01T00:00:00+00:00", ["fundus", "project/demo", "ticket"])
        self.write_article_with_updated("Architecture Overview", "2025-01-01T00:00:00+00:00", ["fundus", "project/demo", "architecture"])
        self.create_article("Fresh Ticket", "Body", ["ticket"])

        candidates = fundus.archive_candidates(self.config, "demo", 90, 10)

        self.assertEqual([candidate["title"] for candidate in candidates], ["Old Ticket"])
        self.assertEqual(candidates[0]["reason"], "old_ticket_or_investigation")

    def test_archive_candidates_force_includes_durable_tags(self) -> None:
        self.write_article_with_updated("Old Ticket", "2025-01-01T00:00:00+00:00", ["fundus", "project/demo", "ticket"])
        self.write_article_with_updated("Architecture Overview", "2025-01-01T00:00:00+00:00", ["fundus", "project/demo", "architecture"])

        candidates = fundus.archive_candidates(self.config, "demo", 90, 10, force=True)
        reasons_by_title = {candidate["title"]: candidate["reason"] for candidate in candidates}

        self.assertEqual(
            reasons_by_title,
            {
                "Old Ticket": "old_ticket_or_investigation",
                "Architecture Overview": "old_durable_note",
            },
        )

    def test_archive_candidates_global_lists_old_notes_across_projects(self) -> None:
        self.write_article_with_updated("Demo Old Ticket", "2025-01-01T00:00:00+00:00", ["fundus", "project/demo", "ticket"])
        other_project_path = self.vault_path / "Fundus" / "other" / "other-old-note.md"
        other_project_path.parent.mkdir(parents=True, exist_ok=True)
        other_project_path.write_text(
            "\n".join(
                [
                    "---",
                    "title: Other Old Note",
                    "created: 2025-01-01T00:00:00+00:00",
                    "updated: 2025-01-02T00:00:00+00:00",
                    "project: other",
                    "tags:",
                    "  - wiki",
                    "  - project/other",
                    "---",
                    "",
                    "# Other Old Note",
                    "",
                    "Body",
                    "",
                ]
            )
        )

        candidates = fundus.archive_candidates_global(self.config, 90, 10)

        self.assertEqual(
            {candidate["title"]: candidate["project"] for candidate in candidates},
            {
                "Demo Old Ticket": "demo",
                "Other Old Note": "other",
            },
        )

    def test_archive_apply_moves_note_and_marks_frontmatter(self) -> None:
        path = self.create_article("Old Ticket", "Body", ["ticket"])
        fundus.rebuild_index(self.config)

        result = fundus.archive_document(
            self.config,
            str(path.relative_to(self.vault_path)),
            "superseded",
        )

        archive_path = self.vault_path / "Fundus" / "_archive" / "demo" / "old-ticket.md"
        self.assertFalse(path.exists())
        self.assertTrue(archive_path.exists())
        self.assertEqual(result["path"], "Fundus/_archive/demo/old-ticket.md")
        frontmatter, body = fundus.parse_frontmatter(archive_path.read_text())
        self.assertIs(frontmatter["archived"], True)
        self.assertEqual(frontmatter["archived_reason"], "superseded")
        self.assertEqual(frontmatter["original_path"], "Fundus/demo/old-ticket.md")
        self.assertIn("Body", body)

    def test_archive_apply_removes_empty_active_project_directory(self) -> None:
        path = self.create_article("Old Ticket", "Body", ["ticket"])

        result = fundus.archive_document(self.config, str(path.relative_to(self.vault_path)), "old")

        self.assertTrue(result["active_directory_removed"])
        self.assertFalse((self.vault_path / "Fundus" / "demo").exists())

    def test_archive_apply_keeps_active_project_directory_when_not_empty(self) -> None:
        path = self.create_article("Old Ticket", "Body", ["ticket"])
        self.create_article("Remaining Note", "Body", ["ticket"])

        result = fundus.archive_document(self.config, str(path.relative_to(self.vault_path)), "old")

        self.assertFalse(result["active_directory_removed"])
        self.assertTrue((self.vault_path / "Fundus" / "demo").exists())
        self.assertTrue((self.vault_path / "Fundus" / "demo" / "remaining-note.md").exists())

    def test_scan_excludes_archived_notes_by_default(self) -> None:
        path = self.create_article("Old Ticket", "Searchable archived body", ["ticket"])
        fundus.rebuild_index(self.config)
        fundus.archive_document(self.config, str(path.relative_to(self.vault_path)), "old")

        active_results = fundus.scan_documents(self.config, "demo", "searchable", include_archived=False)
        archived_results = fundus.scan_documents(self.config, "demo", "searchable", include_archived=True)

        self.assertEqual(active_results, [])
        self.assertEqual(len(archived_results), 1)
        self.assertTrue(archived_results[0]["archived"])
        self.assertEqual(archived_results[0]["path"], "Fundus/_archive/demo/old-ticket.md")

    def test_restore_moves_archived_note_to_original_path(self) -> None:
        path = self.create_article("Old Ticket", "Body", ["ticket"])
        fundus.rebuild_index(self.config)
        archive_result = fundus.archive_document(self.config, str(path.relative_to(self.vault_path)), "old")

        restore_result = fundus.restore_document(self.config, archive_result["path"])

        restored_path = self.vault_path / "Fundus" / "demo" / "old-ticket.md"
        archive_path = self.vault_path / "Fundus" / "_archive" / "demo" / "old-ticket.md"
        self.assertTrue(restored_path.exists())
        self.assertFalse(archive_path.exists())
        self.assertEqual(restore_result["path"], "Fundus/demo/old-ticket.md")
        self.assertTrue(restore_result["archive_directory_removed"])
        self.assertTrue((self.vault_path / "Fundus" / "demo").exists())
        self.assertFalse((self.vault_path / "Fundus" / "_archive" / "demo").exists())
        self.assertTrue((self.vault_path / "Fundus" / "_archive").exists())
        frontmatter, _ = fundus.parse_frontmatter(restored_path.read_text())
        self.assertNotIn("archived", frontmatter)
        self.assertNotIn("original_path", frontmatter)

    def test_restore_keeps_archive_project_directory_when_not_empty(self) -> None:
        first_path = self.create_article("First Ticket", "Body", ["ticket"])
        second_path = self.create_article("Second Ticket", "Body", ["ticket"])
        first_archive = fundus.archive_document(self.config, str(first_path.relative_to(self.vault_path)), "old")
        fundus.archive_document(self.config, str(second_path.relative_to(self.vault_path)), "old")

        result = fundus.restore_document(self.config, first_archive["path"])

        self.assertFalse(result["archive_directory_removed"])
        self.assertTrue((self.vault_path / "Fundus" / "demo").exists())
        self.assertTrue((self.vault_path / "Fundus" / "_archive" / "demo").exists())
        self.assertTrue((self.vault_path / "Fundus" / "_archive" / "demo" / "second-ticket.md").exists())

    def test_archive_cleanup_removes_empty_project_and_archive_directories(self) -> None:
        active_empty = self.vault_path / "Fundus" / "demo" / "empty" / "nested"
        archive_empty = self.vault_path / "Fundus" / "_archive" / "demo" / "empty"
        active_empty.mkdir(parents=True)
        archive_empty.mkdir(parents=True)

        result = fundus.cleanup_empty_directories(self.config, "demo")

        self.assertEqual(result["scope"], "project")
        self.assertEqual(result["project"], "demo")
        self.assertEqual(result["removed_count"], 5)
        self.assertFalse((self.vault_path / "Fundus" / "demo").exists())
        self.assertFalse((self.vault_path / "Fundus" / "_archive" / "demo").exists())
        self.assertTrue((self.vault_path / "Fundus").exists())
        self.assertTrue((self.vault_path / "Fundus" / "_archive").exists())

    def test_archive_cleanup_keeps_non_empty_directories(self) -> None:
        path = self.create_article("Remaining Note", "Body", ["ticket"])
        empty_archive = self.vault_path / "Fundus" / "_archive" / "demo" / "empty"
        empty_archive.mkdir(parents=True)

        result = fundus.cleanup_empty_directories(self.config, "demo")

        self.assertEqual(result["removed_directories"], ["Fundus/_archive/demo", "Fundus/_archive/demo/empty"])
        self.assertTrue(path.exists())
        self.assertTrue((self.vault_path / "Fundus" / "demo").exists())

    def test_archive_cleanup_global_removes_empty_directories_across_projects(self) -> None:
        (self.vault_path / "Fundus" / "demo" / "empty").mkdir(parents=True)
        (self.vault_path / "Fundus" / "other" / "empty").mkdir(parents=True)
        kept_path = self.vault_path / "Fundus" / "kept" / "note.md"
        kept_path.parent.mkdir(parents=True)
        kept_path.write_text("Body")

        result = fundus.cleanup_empty_directories(self.config, "demo", global_scope=True)

        self.assertEqual(result["scope"], "global")
        self.assertIsNone(result["project"])
        self.assertFalse((self.vault_path / "Fundus" / "demo").exists())
        self.assertFalse((self.vault_path / "Fundus" / "other").exists())
        self.assertTrue(kept_path.exists())
        self.assertTrue((self.vault_path / "Fundus").exists())

    def test_restore_fails_when_destination_exists(self) -> None:
        path = self.create_article("Old Ticket", "Body", ["ticket"])
        archive_result = fundus.archive_document(self.config, str(path.relative_to(self.vault_path)), "old")
        self.create_article("Old Ticket", "Replacement", ["ticket"])

        with self.assertRaisesRegex(fundus.FundusError, "Restore destination already exists"):
            fundus.restore_document(self.config, archive_result["path"])

    def test_index_status_remains_fresh_after_archive_and_restore(self) -> None:
        path = self.create_article("Old Ticket", "Body", ["ticket"])
        fundus.rebuild_index(self.config)
        archive_result = fundus.archive_document(self.config, str(path.relative_to(self.vault_path)), "old")

        archived_status = fundus.index_status(self.config)
        self.assertFalse(archived_status["stale"])
        self.assertEqual(archived_status["documents"], 1)

        fundus.restore_document(self.config, archive_result["path"])
        restored_status = fundus.index_status(self.config)
        self.assertFalse(restored_status["stale"])
        self.assertEqual(restored_status["documents"], 1)


class UpdateDocumentTest(FundusTestCase):
    def write_article(self, body: str, frontmatter: str | None = None) -> None:
        metadata = frontmatter or "\n".join(
            [
                "---",
                "title: Article",
                "created: 2026-01-01T00:00:00+00:00",
                "updated: 2026-01-01T00:00:00+00:00",
                "project: demo",
                "tags:",
                "  - fundus",
                "  - project/demo",
                "---",
            ]
        )
        self.path.write_text(f"{metadata}\n\n{body}\n")

    def read_body(self) -> str:
        return self.read_document_body(self.path)

    def read_frontmatter(self) -> dict[str, object]:
        frontmatter, _ = fundus.parse_frontmatter(self.path.read_text())
        return frontmatter

    def test_append_mode_adds_content_to_existing_body(self) -> None:
        self.write_article("# Article\n\nExisting")

        fundus.update_document(
            self.config,
            "demo",
            "Fundus/demo/article.md",
            "append",
            "## New Findings\n\nMore detail",
            None,
        )

        self.assertEqual(self.read_body(), "# Article\n\nExisting\n\n## New Findings\n\nMore detail")

    def test_replace_mode_replaces_named_section(self) -> None:
        self.write_article("# Article\n\n## Details\n\nOld\n\n## Other\n\nKeep")

        fundus.update_document(
            self.config,
            "demo",
            "Fundus/demo/article.md",
            "replace",
            "New",
            "Details",
        )

        self.assertEqual(self.read_body(), "# Article\n\n## Details\n\nNew\n## Other\n\nKeep")

    def test_replace_mode_requires_section(self) -> None:
        self.write_article("# Article")

        with self.assertRaisesRegex(fundus.FundusError, "--section is required"):
            fundus.update_document(
                self.config,
                "demo",
                "Fundus/demo/article.md",
                "replace",
                "New",
                None,
            )

    def test_rewrite_mode_replaces_complete_body(self) -> None:
        self.write_article("# Article\n\n## Old\n\nStale")

        result = fundus.update_document(
            self.config,
            "demo",
            "Fundus/demo/article.md",
            "rewrite",
            "## Overview\n\nNew complete article body.",
            None,
        )

        self.assertEqual(result["mode"], "rewrite")
        self.assertIsNone(result["section"])
        self.assertEqual(self.read_body(), "## Overview\n\nNew complete article body.")

    def test_rewrite_mode_preserves_frontmatter_and_refreshes_updated(self) -> None:
        self.write_article("# Article\n\nOld")

        fundus.update_document(
            self.config,
            "demo",
            "Fundus/demo/article.md",
            "rewrite",
            "New",
            None,
        )

        frontmatter = self.read_frontmatter()
        self.assertEqual(frontmatter["title"], "Article")
        self.assertEqual(frontmatter["created"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(frontmatter["project"], "demo")
        self.assertEqual(frontmatter["tags"], ["fundus", "project/demo"])
        self.assertNotEqual(frontmatter["updated"], "2026-01-01T00:00:00+00:00")

    def test_rewrite_mode_fills_missing_project_and_tags(self) -> None:
        self.write_article(
            "# Article\n\nOld",
            "\n".join(
                [
                    "---",
                    "title: Article",
                    "created: 2026-01-01T00:00:00+00:00",
                    "updated: 2026-01-01T00:00:00+00:00",
                    "---",
                ]
            ),
        )

        fundus.update_document(
            self.config,
            "demo",
            "Fundus/demo/article.md",
            "rewrite",
            "New",
            None,
        )

        frontmatter = self.read_frontmatter()
        self.assertEqual(frontmatter["project"], "demo")
        self.assertEqual(frontmatter["tags"], ["fundus", "project/demo"])

    def test_rewrite_mode_redacts_secrets(self) -> None:
        self.write_article("# Article\n\nOld")

        fundus.update_document(
            self.config,
            "demo",
            "Fundus/demo/article.md",
            "rewrite",
            "API_KEY=super-secret-token",
            None,
        )

        self.assertEqual(self.read_body(), "API_KEY: [REDACTED]")

    def test_update_missing_document_raises_error(self) -> None:
        with self.assertRaisesRegex(fundus.FundusError, "Document does not exist"):
            fundus.update_document(
                self.config,
                "demo",
                "Fundus/demo/missing.md",
                "rewrite",
                "New",
                None,
            )

    def test_update_document_without_frontmatter_raises_error(self) -> None:
        self.path.write_text("# Article\n\nNo frontmatter\n")

        with self.assertRaisesRegex(fundus.FundusError, "missing expected frontmatter"):
            fundus.update_document(
                self.config,
                "demo",
                "Fundus/demo/article.md",
                "rewrite",
                "New",
                None,
            )


class AddFrontmatterTest(FundusTestCase):
    def test_add_frontmatter_preserves_body_and_uses_file_mtime(self) -> None:
        self.path.write_text("# Existing Title\n\nBody\n")
        os.utime(self.path, (1_700_000_000, 1_700_000_000))
        original_timestamp = fundus.filesystem_timestamp(self.path)

        result = fundus.add_frontmatter_to_document(
            self.config,
            "demo",
            "Fundus/demo/article.md",
            "Article",
            ["repair"],
        )

        frontmatter, body = fundus.parse_frontmatter(self.path.read_text())
        self.assertEqual(result["path"], "Fundus/demo/article.md")
        self.assertEqual(frontmatter["title"], "Article")
        self.assertEqual(frontmatter["project"], "demo")
        self.assertEqual(frontmatter["tags"], ["fundus", "project/demo", "repair"])
        self.assertEqual(frontmatter["created"], frontmatter["updated"])
        self.assertEqual(frontmatter["updated"], original_timestamp)
        self.assertEqual(body.strip(), "# Existing Title\n\nBody")

    def test_add_frontmatter_rejects_document_with_existing_frontmatter(self) -> None:
        self.path.write_text(
            "---\n"
            "title: Article\n"
            "---\n\n"
            "# Article\n"
        )

        with self.assertRaisesRegex(fundus.FundusError, "already has frontmatter"):
            fundus.add_frontmatter_to_document(
                self.config,
                "demo",
                "Fundus/demo/article.md",
                None,
                None,
            )


class NormalizeFrontmatterTest(FundusTestCase):
    def write_legacy_note(self, relative_path: str, title: str = "Article", project: str = "demo") -> Path:
        path = self.vault_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "---",
                    f"title: {title}",
                    "created: 2026-01-01T00:00:00+00:00",
                    "updated: 2026-01-02T00:00:00+00:00",
                    f"project: {project}",
                    "tags:",
                    "  - wiki",
                    f"  - project/{project}",
                    "  - architecture",
                    "---",
                    "",
                    f"# {title}",
                    "",
                    "Body with exact spacing.",
                    "",
                ]
            )
        )
        return path

    def test_normalize_frontmatter_dry_run_reports_changes_without_writing(self) -> None:
        path = self.write_legacy_note("Fundus/demo/article.md")
        original_text = path.read_text()

        result = fundus.normalize_frontmatter_paths(
            self.config,
            "demo",
            fundus.project_scope("demo"),
            "Fundus/demo/article.md",
        )

        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(result["applied_count"], 0)
        self.assertEqual(path.read_text(), original_text)
        document = result["documents"][0]
        self.assertTrue(document["body_unchanged"])
        changed_keys = {change["key"] for change in document["changes"]}
        self.assertIn("type", changed_keys)
        self.assertIn("scope_path", changed_keys)

    def test_normalize_frontmatter_apply_preserves_body_and_uses_path_project(self) -> None:
        path = self.write_legacy_note(
            "Fundus/extraction-services/article.md",
            "Extraction Router",
            "old-project",
        )
        _, original_body = fundus.parse_frontmatter(path.read_text())
        fundus.rebuild_index(self.config)

        result = fundus.normalize_frontmatter_paths(
            self.config,
            "Hypatos",
            fundus.project_scope("Hypatos"),
            "Fundus/extraction-services/article.md",
            apply=True,
        )

        frontmatter, body = fundus.parse_frontmatter(path.read_text())
        status = fundus.index_status(self.config)
        self.assertEqual(result["applied_count"], 1)
        self.assertEqual(body, original_body)
        self.assertEqual(frontmatter["type"], "Architecture")
        self.assertEqual(frontmatter["description"], "Extraction Router")
        self.assertEqual(frontmatter["id"], "project/extraction-services/extraction-router")
        self.assertEqual(frontmatter["scope"], "project")
        self.assertEqual(frontmatter["scope_path"], "extraction-services")
        self.assertEqual(frontmatter["project"], "extraction-services")
        self.assertEqual(frontmatter["created"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(frontmatter["updated"], "2026-01-02T00:00:00+00:00")
        self.assertEqual(frontmatter["timestamp"], "2026-01-02T00:00:00+00:00")
        self.assertEqual(frontmatter["tags"], ["fundus", "project/extraction-services", "architecture"])
        self.assertFalse(status["stale"])

    def test_normalize_frontmatter_infers_area_and_removes_stale_project(self) -> None:
        path = self.write_legacy_note(
            "Fundus/Epics/AI Agent Templates/references/source-notes.md",
            "Source Notes",
            "backend-2032",
        )

        fundus.normalize_frontmatter_paths(
            self.config,
            "demo",
            fundus.area_scope("Epics/AI Agent Templates"),
            str(path.relative_to(self.vault_path)),
            apply=True,
        )

        frontmatter, _ = fundus.parse_frontmatter(path.read_text())
        self.assertEqual(frontmatter["type"], "Reference")
        self.assertEqual(frontmatter["scope"], "area")
        self.assertEqual(frontmatter["scope_path"], "Epics/AI Agent Templates")
        self.assertNotIn("project", frontmatter)
        self.assertEqual(frontmatter["tags"], ["fundus", "area/epics/ai-agent-templates", "architecture"])

    def test_normalize_frontmatter_dry_run_identifies_subfolder_scope_overload(self) -> None:
        path = self.vault_path / "Fundus" / "Epics" / "AI Agent Templates" / "references" / "source.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "---\n"
            "type: Reference\n"
            "title: Source\n"
            "description: Source\n"
            "id: epic/ai-agent-templates/source\n"
            "scope: area\n"
            "scope_path: Epics/AI Agent Templates/references\n"
            "tags: [fundus, area/epics/ai-agent-templates/references, source]\n"
            "---\n\n# Source\n\nBody\n"
        )
        original = path.read_text()

        plan = fundus.normalize_frontmatter_paths(
            self.config,
            "demo",
            fundus.area_scope("Epics/AI Agent Templates"),
            str(path.relative_to(self.vault_path)),
        )

        self.assertEqual(path.read_text(), original)
        self.assertEqual(plan["scope_path_change_count"], 1)
        self.assertEqual(
            plan["documents"][0]["scope_path_change"],
            {
                "before": "Epics/AI Agent Templates/references",
                "after": "Epics/AI Agent Templates",
                "reason": "physical_subfolder_overload",
            },
        )
        self.assertEqual(plan["documents"][0]["physical_parent"], "Epics/AI Agent Templates/references")
        self.assertEqual(plan["documents"][0]["scope_relative_path"], "references/source.md")

    def test_normalize_frontmatter_can_add_missing_frontmatter_when_explicit(self) -> None:
        self.path.write_text("# Plain Note\n\nBody\n")

        dry_run = fundus.normalize_frontmatter_paths(
            self.config,
            "demo",
            fundus.project_scope("demo"),
            "Fundus/demo/article.md",
        )
        applied = fundus.normalize_frontmatter_paths(
            self.config,
            "demo",
            fundus.project_scope("demo"),
            "Fundus/demo/article.md",
            apply=True,
            add_missing=True,
        )

        frontmatter, body = fundus.parse_frontmatter(self.path.read_text())
        self.assertEqual(dry_run["skipped_count"], 1)
        self.assertEqual(applied["applied_count"], 1)
        self.assertEqual(frontmatter["title"], "Article")
        self.assertEqual(frontmatter["scope_path"], "demo")
        self.assertEqual(body, "# Plain Note\n\nBody\n")

    def test_global_normalize_skips_reserved_files(self) -> None:
        self.write_legacy_note("Fundus/demo/article.md")
        reserved_root = self.vault_path / "Fundus" / "demo"
        (reserved_root / "index.md").write_text("# Index\n")
        (reserved_root / "log.md").write_text("# Log\n")

        result = fundus.normalize_frontmatter_paths(
            self.config,
            "demo",
            fundus.project_scope("demo"),
            global_scope=True,
        )

        self.assertEqual(result["document_count"], 1)
        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(result["documents"][0]["path"], "Fundus/demo/article.md")
        self.assertEqual((reserved_root / "index.md").read_text(), "# Index\n")
        self.assertEqual((reserved_root / "log.md").read_text(), "# Log\n")


class LegacyFrontmatterRepairTest(FundusTestCase):
    def test_repair_is_narrow_dry_run_first_and_body_preserving(self) -> None:
        active = self.vault_path / "Fundus" / "demo" / "ticket.md"
        active.parent.mkdir(parents=True, exist_ok=True)
        active.write_bytes(
            b"---\r\ntitle: BACKEND-1: Broken title\r\ntags: [fundus]\r\n---\r\n\r\n# Body\r\n\r\nKeep me.  \r\n"
        )
        archived = self.vault_path / "Fundus" / "_archive" / "demo" / "old.md"
        archived.parent.mkdir(parents=True)
        archived.write_text(
            "---\n"
            "title: Old\n"
            "archived_reason: weekly cleanup: stale note\n"
            "---\n\n# Old\n\nArchive body.\n"
        )
        unsupported = self.vault_path / "Fundus" / "demo" / "nested.md"
        unsupported.write_text("---\nnested:\n  child: value\n---\n\n# Nested\n")
        unsafe_flow = self.vault_path / "Fundus" / "demo" / "flow.md"
        unsafe_flow.write_text("---\ntitle: {unsafe: mapping}\n---\n\n# Flow\n")
        original_active = active.read_bytes()
        original_archived = archived.read_bytes()
        original_unsupported = unsupported.read_bytes()

        dry_run = fundus.repair_legacy_frontmatter(self.config)

        self.assertEqual(dry_run["invalid_count"], 4)
        self.assertEqual(dry_run["repairable_count"], 2)
        self.assertEqual(dry_run["unrepairable_count"], 2)
        self.assertEqual(dry_run["applied_count"], 0)
        self.assertEqual(active.read_bytes(), original_active)
        self.assertEqual(archived.read_bytes(), original_archived)

        applied = fundus.repair_legacy_frontmatter(self.config, apply=True)

        self.assertEqual(applied["applied_count"], 2)
        active_frontmatter, active_body = fundus.parse_frontmatter(active.read_bytes().decode("utf-8"))
        archive_frontmatter, archive_body = fundus.parse_frontmatter(archived.read_text())
        self.assertEqual(active_frontmatter["title"], "BACKEND-1: Broken title")
        self.assertEqual(archive_frontmatter["archived_reason"], "weekly cleanup: stale note")
        self.assertEqual(active_body, "\r\n# Body\r\n\r\nKeep me.  \r\n")
        self.assertEqual(archive_body, "\n# Old\n\nArchive body.\n")
        self.assertEqual(unsupported.read_bytes(), original_unsupported)
        self.assertFalse(fundus.journal_root_dir(self.config).exists())


class BackupTest(FundusTestCase):
    def test_backup_create_list_and_inspect_manifest(self) -> None:
        result = fundus.create_document(self.config, "demo", "Backed Up", "Body", ["ticket"])
        fundus.rebuild_index(self.config)

        manifest = fundus.create_backup(self.config, "pre okf")
        listed = fundus.list_backups(self.config)
        inspected = fundus.inspect_backup(self.config, manifest["id"])

        self.assertEqual(manifest["label"], "pre okf")
        self.assertEqual(listed[0]["id"], manifest["id"])
        self.assertEqual(inspected["id"], manifest["id"])
        self.assertTrue((Path(manifest["backup_path"]) / result["path"]).exists())
        paths = {file["path"] for file in manifest["files"]}
        self.assertIn(result["path"], paths)
        self.assertIn("Fundus/.fundus-index.json", paths)

    def test_backup_manifest_contains_checksums_and_excludes_backup_dir(self) -> None:
        result = fundus.create_document(self.config, "demo", "Backed Up", "Body", ["ticket"])

        manifest = fundus.create_backup(self.config, "checksum")

        entry = next(file for file in manifest["files"] if file["path"] == result["path"])
        self.assertEqual(entry["sha256"], fundus.file_sha256(self.vault_path / result["path"]))
        self.assertFalse(any(fundus.BACKUP_DIRNAME in file["path"] for file in manifest["files"]))


class MutationSafetyTest(FundusTestCase):
    def create_article(self, title: str, body: str = "Body") -> tuple[dict[str, object], Path]:
        result = fundus.create_document(self.config, "demo", title, body, ["ticket"])
        return result, self.vault_path / str(result["path"])

    def test_read_result_and_search_return_same_revision(self) -> None:
        created, _ = self.create_article("Revision Note")

        read = fundus.read_document_result(self.config, str(created["path"]))
        search = fundus.scan_documents(self.config, "demo", "Revision Note")

        self.assertEqual(read["revision"], created["revision"])
        self.assertEqual(search[0]["revision"], created["revision"])
        self.assertEqual(read["resolved_path"], created["path"])

    def test_external_edit_causes_revision_conflict_without_write(self) -> None:
        created, path = self.create_article("Conflict Note", "Original body")
        path.write_text(path.read_text() + "\nHuman edit.\n")
        human_bytes = path.read_bytes()

        with self.assertRaises(fundus.FundusError) as raised:
            fundus.update_document(
                self.config,
                "demo",
                str(created["path"]),
                "rewrite",
                "Agent overwrite",
                None,
                fundus.project_scope("demo"),
                str(created["revision"]),
            )

        self.assertEqual(raised.exception.code, "REVISION_CONFLICT")
        self.assertEqual(path.read_bytes(), human_bytes)
        self.assertFalse(fundus.lock_path(self.config).exists())

    def test_lock_timeout_release_and_stale_recovery(self) -> None:
        lock = fundus.lock_path(self.config)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(
            json.dumps(
                {
                    "token": "live",
                    "pid": os.getpid(),
                    "hostname": fundus.socket.gethostname(),
                    "created": fundus.now_iso(),
                    "created_epoch": fundus.time.time(),
                }
            )
        )
        with self.assertRaises(fundus.FundusError) as timeout:
            with fundus.CorpusMutationLock(self.config, timeout_seconds=0.05, stale_after_seconds=30):
                pass
        self.assertEqual(timeout.exception.code, "LOCK_TIMEOUT")
        lock.unlink()

        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(
            json.dumps(
                {
                    "token": "stale",
                    "pid": 99999999,
                    "hostname": fundus.socket.gethostname(),
                    "created": "old",
                    "created_epoch": fundus.time.time() - 3600,
                }
            )
        )
        with fundus.CorpusMutationLock(self.config, timeout_seconds=0.2, stale_after_seconds=1):
            self.assertTrue(lock.exists())
        self.assertFalse(lock.exists())

        with self.assertRaisesRegex(RuntimeError, "boom"):
            with fundus.CorpusMutationLock(self.config):
                raise RuntimeError("boom")
        self.assertFalse(lock.exists())

    def test_pending_journal_is_recovered_on_next_mutation_lock(self) -> None:
        _, path = self.create_article("Journal Recovery", "Original")
        original = path.read_bytes()
        with fundus.CorpusMutationLock(self.config):
            journal = fundus.MutationJournal(self.config, "test-crash", [path])
            journal.__enter__()
            path.write_text("simulated partial write")

        self.assertNotEqual(path.read_bytes(), original)
        with fundus.CorpusMutationLock(self.config):
            self.assertEqual(path.read_bytes(), original)
        self.assertFalse(fundus.journal_root_dir(self.config).exists())

    def test_move_archive_and_restore_roll_back_at_every_checkpoint(self) -> None:
        fundus.rebuild_index(self.config)
        operation_steps = {
            "move": ["renamed", "metadata_written", "index_written"],
            "archive": ["renamed", "metadata_written", "index_written"],
            "restore": ["renamed", "metadata_written", "index_written"],
        }

        for operation, steps in operation_steps.items():
            for step in steps:
                with self.subTest(operation=operation, step=step):
                    created, active_path = self.create_article(f"{operation} {step}", "Rollback body")
                    if operation == "move":
                        source_path = active_path
                        destination_path = self.vault_path / "Fundus" / "other" / active_path.name
                        invoke = lambda: fundus.move_document(
                            self.config,
                            str(created["path"]),
                            str(destination_path.relative_to(self.vault_path)),
                        )
                    elif operation == "archive":
                        source_path = active_path
                        destination_path = self.vault_path / "Fundus" / "_archive" / "demo" / active_path.name
                        invoke = lambda: fundus.archive_document(self.config, str(created["path"]), "test")
                    else:
                        archived = fundus.archive_document(self.config, str(created["path"]), "test")
                        source_path = self.vault_path / str(archived["path"])
                        destination_path = active_path
                        invoke = lambda: fundus.restore_document(self.config, str(archived["path"]))

                    source_bytes = source_path.read_bytes()
                    index_bytes = fundus.index_path(self.config).read_bytes()

                    def fail_at_checkpoint(reached_operation: str, reached_step: str) -> None:
                        if reached_operation == operation and reached_step == step:
                            raise RuntimeError(f"injected {operation}:{step}")

                    fundus.MUTATION_FAILURE_INJECTOR = fail_at_checkpoint
                    try:
                        with self.assertRaisesRegex(RuntimeError, f"injected {operation}:{step}"):
                            invoke()
                    finally:
                        fundus.MUTATION_FAILURE_INJECTOR = None

                    self.assertTrue(source_path.exists())
                    self.assertEqual(source_path.read_bytes(), source_bytes)
                    self.assertFalse(destination_path.exists())
                    self.assertEqual(fundus.index_path(self.config).read_bytes(), index_bytes)
                    self.assertFalse(fundus.journal_root_dir(self.config).exists())

    def test_multi_process_updates_preserve_index_and_reject_same_revision(self) -> None:
        first, _ = self.create_article("Concurrent First", "First")
        second, _ = self.create_article("Concurrent Second", "Second")
        fundus.rebuild_index(self.config)
        context = multiprocessing.get_context("spawn")

        def run_workers(specs: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
            start_event = context.Event()
            result_queue = context.Queue()
            processes = [
                context.Process(
                    target=concurrent_update_worker,
                    args=(str(self.vault_path), path, revision, content, start_event, result_queue),
                )
                for path, revision, content in specs
            ]
            for process in processes:
                process.start()
            start_event.set()
            results = [result_queue.get(timeout=15) for _ in processes]
            for process in processes:
                process.join(timeout=15)
                self.assertEqual(process.exitcode, 0)
            return results

        different_results = run_workers(
            [
                (str(first["path"]), str(first["revision"]), "First worker"),
                (str(second["path"]), str(second["revision"]), "Second worker"),
            ]
        )
        self.assertEqual([status for status, _ in different_results], ["ok", "ok"])
        self.assertFalse(fundus.index_status(self.config)["stale"])

        same, _ = self.create_article("Concurrent Same", "Same")
        same_results = run_workers(
            [
                (str(same["path"]), str(same["revision"]), "Winner one"),
                (str(same["path"]), str(same["revision"]), "Winner two"),
            ]
        )
        self.assertEqual(sorted(status for status, _ in same_results), ["error", "ok"])
        self.assertEqual([value for status, value in same_results if status == "error"], ["REVISION_CONFLICT"])
        self.assertFalse(fundus.index_status(self.config)["stale"])

    def test_backup_verification_restore_and_corruption_guard(self) -> None:
        created, path = self.create_article("Backup Restore", "Original snapshot body")
        backup = fundus.create_backup(self.config, "restorable")
        verification = fundus.verify_backup(self.config, backup["id"])
        fundus.update_document(
            self.config,
            "demo",
            str(created["path"]),
            "rewrite",
            "Changed after backup",
            None,
            fundus.project_scope("demo"),
            str(created["revision"]),
        )

        plan = fundus.restore_backup(self.config, backup["id"])
        restored = fundus.restore_backup(self.config, backup["id"], apply=True)

        self.assertTrue(verification["verified"])
        self.assertFalse(plan["apply"])
        self.assertIn("Original snapshot body", path.read_text())
        self.assertTrue(restored["corpus_verification"]["passed"])
        self.assertTrue(fundus.inspect_backup(self.config, restored["safety_backup_id"]))

        changed_revision = fundus.read_document_result(self.config, str(created["path"]))["revision"]
        fundus.update_document(
            self.config,
            "demo",
            str(created["path"]),
            "rewrite",
            "State before injected restore failure",
            None,
            fundus.project_scope("demo"),
            changed_revision,
        )
        pre_failure_bytes = path.read_bytes()

        def fail_restore(operation: str, step: str) -> None:
            if operation == "backup-restore" and step == "snapshot_copied":
                raise RuntimeError("injected backup restore")

        fundus.MUTATION_FAILURE_INJECTOR = fail_restore
        try:
            with self.assertRaisesRegex(RuntimeError, "injected backup restore"):
                fundus.restore_backup(self.config, backup["id"], apply=True)
        finally:
            fundus.MUTATION_FAILURE_INJECTOR = None
        self.assertEqual(path.read_bytes(), pre_failure_bytes)
        self.assertFalse(fundus.journal_root_dir(self.config).exists())

        corrupt_backup = fundus.create_backup(self.config, "corrupt-me")
        manifest = fundus.inspect_backup(self.config, corrupt_backup["id"])
        note_entry = next(entry for entry in manifest["files"] if str(entry["path"]).endswith(".md"))
        backup_note = Path(manifest["backup_path"]) / str(note_entry["path"])
        backup_note.write_bytes(backup_note.read_bytes() + b"corruption")
        current_bytes = path.read_bytes()

        with self.assertRaises(fundus.FundusError) as corrupt:
            fundus.verify_backup(self.config, corrupt_backup["id"])
        with self.assertRaises(fundus.FundusError) as blocked_restore:
            fundus.restore_backup(self.config, corrupt_backup["id"], apply=True)
        self.assertEqual(corrupt.exception.code, "BACKUP_CORRUPT")
        self.assertEqual(blocked_restore.exception.code, "BACKUP_CORRUPT")
        self.assertEqual(path.read_bytes(), current_bytes)


class ProposalWorkflowTest(FundusTestCase):
    def test_propose_create_is_read_only_and_apply_records_provenance(self) -> None:
        before = sorted(str(path.relative_to(self.vault_path)) for path in self.vault_path.rglob("*"))

        proposal = fundus.propose_create_document(
            self.config,
            "demo",
            "Proposed Note",
            "Body with API_KEY=secret-value",
            ["domain"],
            verified_against=["jira:BACKEND-2291", "github:org/repo@abc123"],
            source_fingerprint="github:org/repo:path@sha256:1234",
            verification_status="current",
        )
        repeated = fundus.propose_create_document(
            self.config,
            "demo",
            "Proposed Note",
            "Body with API_KEY=secret-value",
            ["domain"],
            verified_against=["jira:BACKEND-2291", "github:org/repo@abc123"],
            source_fingerprint="github:org/repo:path@sha256:1234",
            verification_status="current",
        )

        after_proposal = sorted(str(path.relative_to(self.vault_path)) for path in self.vault_path.rglob("*"))
        self.assertEqual(after_proposal, before)
        self.assertEqual(proposal["kind"], "create")
        self.assertEqual(repeated["proposal_id"], proposal["proposal_id"])
        self.assertEqual(repeated["diff"], proposal["diff"])
        self.assertTrue(proposal["proposal_id"].startswith("sha256:"))
        self.assertIn("CONTENT_REDACTED", proposal["warnings"])
        self.assertFalse(proposal["duplicate_candidates"])

        applied = fundus.apply_create_proposal(self.config, proposal)
        frontmatter, body = fundus.parse_frontmatter((self.vault_path / applied["path"]).read_text())

        self.assertTrue(applied["applied"])
        self.assertEqual(frontmatter["verification_status"], "current")
        self.assertEqual(frontmatter["verified_against"], ["jira:BACKEND-2291", "github:org/repo@abc123"])
        self.assertEqual(frontmatter["source_fingerprint"], "github:org/repo:path@sha256:1234")
        self.assertIn("API_KEY: [REDACTED]", body)

    def test_duplicate_signals_require_reviewed_override(self) -> None:
        existing = fundus.create_document(
            self.config,
            "demo",
            "Prompt Boundary",
            "BACKEND-2291 prompt authoring boundary.",
            ["domain"],
            document_id="domain/prompt-boundary",
            aliases=["Shared Alias", "BACKEND-2291"],
            resource="https://jira.example/BACKEND-2291",
        )
        proposal = fundus.propose_create_document(
            self.config,
            "demo",
            "Prompt Boundary Copy",
            "BACKEND-2291 prompt authoring boundary details.",
            ["domain"],
            document_id="domain/prompt-boundary",
            aliases=["Shared Alias"],
            resource="https://jira.example/BACKEND-2291",
        )
        candidate = proposal["duplicate_candidates"][0]

        self.assertEqual(candidate["path"], existing["path"])
        self.assertIn("id", candidate["reasons"])
        self.assertIn("alias", candidate["reasons"])
        self.assertIn("resource", candidate["reasons"])
        self.assertIn("ticket:BACKEND-2291", candidate["reasons"])
        with self.assertRaises(fundus.FundusError) as blocked:
            fundus.apply_create_proposal(self.config, proposal)
        with self.assertRaises(fundus.FundusError):
            fundus.apply_create_proposal(self.config, proposal, True, ["Fundus/demo/not-reviewed.md"])
        self.assertEqual(blocked.exception.code, "DUPLICATE_REVIEW_REQUIRED")

        applied = fundus.apply_create_proposal(self.config, proposal, True, [str(existing["path"])])
        self.assertTrue((self.vault_path / applied["path"]).exists())

    def test_high_confidence_similarity_is_a_duplicate_signal(self) -> None:
        fundus.create_document(self.config, "demo", "Payment Authorization Flow", "Body", ["domain"])

        proposal = fundus.propose_create_document(
            self.config,
            "demo",
            "Payment Authorisation Flow",
            "Different body",
            ["domain"],
        )

        self.assertEqual(proposal["duplicate_candidates"][0]["reasons"], ["high_confidence_similarity"])

    def test_update_proposals_cover_modes_metadata_and_stale_rejection(self) -> None:
        created = fundus.create_document(
            self.config,
            "demo",
            "Update Proposal",
            "## Context\n\nOriginal.\n\n## Tail\n\nKeep.",
            ["ticket"],
        )
        proposals = {
            "append": fundus.propose_update_document(
                self.config,
                str(created["path"]),
                "append",
                "## Added\n\nAppend body.",
                metadata_changes={
                    "verified_against": ["jira:BACKEND-1"],
                    "source_fingerprint": "jira:BACKEND-1@v2",
                    "verification_status": "current",
                },
            ),
            "replace": fundus.propose_update_document(
                self.config,
                str(created["path"]),
                "replace",
                "Replaced context.",
                "Context",
            ),
            "rewrite": fundus.propose_update_document(
                self.config,
                str(created["path"]),
                "rewrite",
                "Complete replacement.",
            ),
        }

        for mode, proposal in proposals.items():
            with self.subTest(mode=mode):
                self.assertEqual(proposal["request"]["mode"], mode)
                self.assertIn("---", proposal["diff"])
                self.assertTrue(proposal["expected_revision"].startswith("sha256:"))

        applied = fundus.apply_update_proposal(self.config, proposals["append"])
        frontmatter, body = fundus.parse_frontmatter((self.vault_path / str(created["path"])).read_text())
        self.assertTrue(applied["applied"])
        self.assertIn("Append body.", body)
        self.assertEqual(frontmatter["verification_status"], "current")
        self.assertEqual(frontmatter["source_fingerprint"], "jira:BACKEND-1@v2")

        stale_proposal = fundus.propose_update_document(
            self.config,
            str(created["path"]),
            "rewrite",
            "Agent replacement",
        )
        path = self.vault_path / str(created["path"])
        path.write_text(path.read_text() + "\nHuman edit.\n")
        human_bytes = path.read_bytes()
        with self.assertRaises(fundus.FundusError) as conflict:
            fundus.apply_update_proposal(self.config, stale_proposal)
        self.assertEqual(conflict.exception.code, "REVISION_CONFLICT")
        self.assertEqual(path.read_bytes(), human_bytes)

    def test_proposal_integrity_and_verification_lifecycle(self) -> None:
        proposal = fundus.propose_create_document(self.config, "demo", "Integrity", "Body", [])
        proposal["request"]["title"] = "Tampered"
        with self.assertRaises(fundus.FundusError) as invalid:
            fundus.apply_create_proposal(self.config, proposal)
        self.assertEqual(invalid.exception.code, "PROPOSAL_INVALID")

        created = fundus.create_document(self.config, "demo", "Lifecycle", "Body", [])
        stale = fundus.mark_note_stale(self.config, str(created["path"]), "Source changed", str(created["revision"]))
        stale_frontmatter, _ = fundus.parse_frontmatter((self.vault_path / str(created["path"])).read_text())
        self.assertEqual(stale_frontmatter["verification_status"], "stale")
        self.assertEqual(stale_frontmatter["stale_reason"], "Source changed")

        verified = fundus.verify_note(
            self.config,
            str(created["path"]),
            ["github:org/repo@abc"],
            "github:org/repo:path@sha256:def",
            stale["revision"],
        )
        verified_frontmatter, _ = fundus.parse_frontmatter((self.vault_path / str(created["path"])).read_text())
        search = fundus.scan_documents(self.config, "demo", "Lifecycle")
        self.assertEqual(verified_frontmatter["verification_status"], "current")
        self.assertNotIn("stale_reason", verified_frontmatter)
        self.assertEqual(search[0]["verification_status"], "current")
        self.assertEqual(search[0]["source_fingerprint"], "github:org/repo:path@sha256:def")
        self.assertTrue(verified["revision"].startswith("sha256:"))


class MigrationTest(FundusTestCase):
    def setUp(self) -> None:
        super().setUp()
        shutil.rmtree(self.vault_path / "Fundus")

    def write_wiki_note(self, relative_path: str, text: str) -> Path:
        path = self.vault_path / "Wiki" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def write_legacy_project_note(self) -> None:
        self.write_wiki_note(
            "demo/legacy-ticket.md",
            "\n".join(
                [
                    "---",
                    "title: Legacy Ticket",
                    "created: 2026-01-01T00:00:00+00:00",
                    "updated: 2026-01-02T00:00:00+00:00",
                    "project: old-demo",
                    "tags:",
                    "  - wiki",
                    "  - project/old-demo",
                    "  - ticket",
                    "---",
                    "",
                    "# Legacy Ticket",
                    "",
                    "BACKEND-2291 durable context.",
                    "",
                ]
            ),
        )

    def write_reserved_index(self) -> None:
        self.write_wiki_note(
            "demo/index.md",
            "---\ntitle: Demo Index\ntype: Index\n---\n\n# Demo Index\n\nLinks.\n",
        )

    def write_archived_note(self) -> None:
        self.write_wiki_note(
            "_archive/demo/old-note.md",
            f"---\ntitle: Old Note\narchived: true\noriginal_path: {self.vault_path}/Wiki/demo/old-note.md\n---\n\n# Old Note\n\nHistorical.\n",
        )

    def test_migration_plan_reports_counts_and_conflicts_without_writing(self) -> None:
        self.write_legacy_project_note()
        self.write_reserved_index()
        self.write_archived_note()

        plan = fundus.migration_plan(self.config)

        self.assertEqual(plan["source_dir"], "Wiki")
        self.assertEqual(plan["destination_dir"], "Fundus")
        self.assertEqual(plan["counts"]["markdown"], 3)
        self.assertEqual(plan["counts"]["active"], 2)
        self.assertEqual(plan["counts"]["archive"], 1)
        self.assertEqual(plan["counts"]["reserved"], 1)
        self.assertEqual(plan["counts"]["concept"], 1)
        self.assertEqual(plan["counts"]["reserved_with_frontmatter"], 1)
        self.assertEqual(plan["conflict_count"], 0)
        self.assertFalse((self.vault_path / "Fundus").exists())

    def test_migration_apply_stages_transforms_verifies_indexes_and_retires_source(self) -> None:
        self.write_legacy_project_note()
        self.write_reserved_index()
        self.write_archived_note()

        result = fundus.apply_wiki_to_fundus_migration(self.config)

        migrated_note = self.vault_path / "Fundus" / "demo" / "legacy-ticket.md"
        migrated_index = self.vault_path / "Fundus" / "demo" / "index.md"
        migrated_archive = self.vault_path / "Fundus" / "_archive" / "demo" / "old-note.md"
        frontmatter, body = fundus.parse_frontmatter(migrated_note.read_text())
        index_frontmatter, index_body = fundus.parse_frontmatter(migrated_index.read_text())
        archive_frontmatter, archive_body = fundus.parse_frontmatter(migrated_archive.read_text())

        self.assertTrue(result["verification"]["passed"])
        self.assertEqual(result["copied_count"], 3)
        self.assertEqual(result["index"]["documents"], 3)
        self.assertTrue(Path(result["backup"]["backup_path"]).exists())
        self.assertFalse((self.vault_path / "Wiki").exists())
        self.assertTrue(Path(result["retired_source_path"]).exists())
        self.assertEqual(frontmatter["type"], "Research")
        self.assertEqual(frontmatter["scope"], "project")
        self.assertEqual(frontmatter["scope_path"], "demo")
        self.assertEqual(frontmatter["project"], "demo")
        self.assertEqual(frontmatter["tags"], ["fundus", "project/demo", "ticket"])
        self.assertIn("BACKEND-2291", body)
        self.assertEqual(index_frontmatter, {})
        self.assertEqual(index_body, "\n# Demo Index\n\nLinks.\n")
        self.assertEqual(archive_frontmatter["title"], "Old Note")
        self.assertEqual(archive_frontmatter["original_path"], "Fundus/demo/old-note.md")
        self.assertNotIn("type", archive_frontmatter)
        self.assertIn("Historical.", archive_body)
        self.assertFalse(fundus.index_status(self.config)["stale"])

    def test_migration_apply_can_keep_source_when_requested(self) -> None:
        self.write_legacy_project_note()

        result = fundus.apply_wiki_to_fundus_migration(self.config, retire_source="keep")

        self.assertEqual(result["retire_source"], "keep")
        self.assertIsNone(result["retired_source_path"])
        self.assertTrue((self.vault_path / "Wiki").exists())

    def test_migration_apply_resumes_existing_destination_and_retires_source(self) -> None:
        self.write_legacy_project_note()
        self.write_archived_note()
        first = fundus.apply_wiki_to_fundus_migration(self.config, retire_source="keep")

        resumed = fundus.apply_wiki_to_fundus_migration(self.config)

        self.assertEqual(first["retire_source"], "keep")
        self.assertTrue(resumed["resumed_existing_destination"])
        self.assertEqual(resumed["copied_count"], 0)
        self.assertFalse((self.vault_path / "Wiki").exists())
        self.assertTrue(Path(resumed["retired_source_path"]).exists())
        self.assertFalse(fundus.index_status(self.config)["stale"])

    def test_migration_promotion_failure_leaves_resumable_verified_destination(self) -> None:
        self.write_legacy_project_note()

        def fail_after_promotion(operation: str, step: str) -> None:
            if operation == "migration" and step == "promoted":
                raise RuntimeError("injected migration promotion")

        fundus.MUTATION_FAILURE_INJECTOR = fail_after_promotion
        try:
            with self.assertRaisesRegex(RuntimeError, "injected migration promotion"):
                fundus.apply_wiki_to_fundus_migration(self.config)
        finally:
            fundus.MUTATION_FAILURE_INJECTOR = None

        self.assertTrue((self.vault_path / "Fundus" / "demo" / "legacy-ticket.md").exists())
        self.assertTrue((self.vault_path / "Wiki").exists())

        resumed = fundus.apply_wiki_to_fundus_migration(self.config)

        self.assertTrue(resumed["resumed_existing_destination"])
        self.assertTrue(resumed["verification"]["passed"])
        self.assertFalse((self.vault_path / "Wiki").exists())

    def test_verify_fundus_corpus_reports_reserved_frontmatter_issue(self) -> None:
        (self.vault_path / "Fundus" / "demo").mkdir(parents=True)
        (self.vault_path / "Fundus" / "demo" / "index.md").write_text(
            "---\ntitle: Bad Index\n---\n\n# Bad Index\n"
        )

        verification = fundus.verify_fundus_corpus(self.config)

        self.assertFalse(verification["passed"])
        self.assertEqual(verification["issues"][0]["reason"], "reserved_has_frontmatter")

    def test_verify_fundus_corpus_reports_invalid_frontmatter_path_without_aborting(self) -> None:
        path = self.vault_path / "Fundus" / "demo" / "broken.md"
        path.parent.mkdir(parents=True)
        path.write_text("---\ntitle: Broken: title\n---\n\n# Body\n")

        verification = fundus.verify_fundus_corpus(self.config)

        issue = next(issue for issue in verification["issues"] if issue["path"] == "Fundus/demo/broken.md")
        self.assertFalse(verification["passed"])
        self.assertEqual(issue["reason"], "frontmatter_invalid")
        self.assertEqual(issue["code"], "FRONTMATTER_INVALID")


class ScopeAndAreaTest(FundusTestCase):
    def test_area_path_validation_rejects_unsafe_paths(self) -> None:
        for area in ["", "../Other", "/absolute", "_archive/old", ".fundus-backups/x", "Epics/Name/subfolder"]:
            with self.subTest(area=area):
                with self.assertRaises(fundus.FundusError):
                    fundus.area_scope(area)

    def test_area_create_writes_okf_compatible_frontmatter(self) -> None:
        scope = fundus.area_scope("Epics/AI Agent Templates")

        result = fundus.create_document(
            self.config,
            "demo",
            "Story Map",
            "Body",
            ["story-map"],
            scope,
            "Epic",
            "Story map for the epic.",
            "epic/ai-agent-templates/story-map",
        )

        self.assertEqual(result["path"], "Fundus/Epics/AI Agent Templates/story-map.md")
        frontmatter, body = fundus.parse_frontmatter((self.vault_path / result["path"]).read_text())
        self.assertEqual(frontmatter["type"], "Epic")
        self.assertEqual(frontmatter["description"], "Story map for the epic.")
        self.assertEqual(frontmatter["id"], "epic/ai-agent-templates/story-map")
        self.assertEqual(frontmatter["scope"], "area")
        self.assertEqual(frontmatter["scope_path"], "Epics/AI Agent Templates")
        self.assertNotIn("project", frontmatter)
        self.assertIn("area/epics/ai-agent-templates", frontmatter["tags"])
        self.assertIn("# Story Map", body)

    def test_area_scan_uses_nested_paths_with_and_without_index(self) -> None:
        area = fundus.area_scope("Epics/AI Agent Templates")
        fundus.create_document(self.config, "demo", "Story Map", "Body", ["story-map"], area)
        project_result = fundus.create_document(self.config, "demo", "Story Map", "Project body", ["ticket"])

        area_results = fundus.scan_documents(self.config, "demo", "Story", scope=area)
        project_results = fundus.scan_documents(self.config, "demo", "Story")
        fundus.rebuild_index(self.config)
        indexed_area_results = fundus.scan_documents(self.config, "demo", "Story", scope=area)

        self.assertEqual([result["path"] for result in area_results], ["Fundus/Epics/AI Agent Templates/story-map.md"])
        self.assertEqual([result["path"] for result in project_results], [project_result["path"]])
        self.assertEqual([result["path"] for result in indexed_area_results], ["Fundus/Epics/AI Agent Templates/story-map.md"])

    def test_recursive_index_status_tracks_nested_area_notes(self) -> None:
        area = fundus.area_scope("Epics/AI Agent Templates")
        result = fundus.create_document(self.config, "demo", "Story Map", "Body", ["story-map"], area)
        nested_path = self.vault_path / "Fundus" / "Epics" / "AI Agent Templates" / "stories" / "backend-2292.md"
        nested_path.parent.mkdir(parents=True)
        nested_path.write_text((self.vault_path / result["path"]).read_text().replace("Story Map", "Backend 2292"))

        payload = fundus.rebuild_index(self.config)
        status = fundus.index_status(self.config)

        self.assertEqual(len(payload["documents"]), 2)
        self.assertFalse(status["stale"])
        self.assertEqual(status["documents"], 2)

    def test_archive_area_note_mirrors_nested_path_and_restores(self) -> None:
        area = fundus.area_scope("Epics/AI Agent Templates")
        result = fundus.create_document(self.config, "demo", "Story Map", "Body", ["story-map"], area)
        fundus.rebuild_index(self.config)

        archived = fundus.archive_document(self.config, result["path"], "old")
        restored = fundus.restore_document(self.config, archived["path"])

        self.assertEqual(archived["path"], "Fundus/_archive/Epics/AI Agent Templates/story-map.md")
        self.assertEqual(restored["path"], result["path"])
        self.assertTrue((self.vault_path / result["path"]).exists())

    def test_area_init_creates_skeleton_without_overwriting(self) -> None:
        result = fundus.area_init(self.config, "demo", "Epics/AI Agent Templates", "Epic", "AI Agent Templates")
        second = fundus.area_init(self.config, "demo", "Epics/AI Agent Templates", "Epic", "AI Agent Templates")

        self.assertIn("Fundus/Epics/AI Agent Templates/overview.md", result["created"])
        self.assertIn("Fundus/Epics/AI Agent Templates/index.md", second["skipped"])
        for filename in fundus.RESERVED_FILENAMES:
            reserved = self.vault_path / "Fundus" / "Epics" / "AI Agent Templates" / filename
            frontmatter, _ = fundus.parse_frontmatter(reserved.read_text())
            self.assertEqual(frontmatter, {})
        self.assertTrue(fundus.verify_fundus_corpus(self.config)["passed"])
        for directory in fundus.AREA_SUBDIRECTORIES:
            self.assertTrue((self.vault_path / "Fundus" / "Epics" / "AI Agent Templates" / directory).is_dir())

    def test_move_document_moves_note_and_refreshes_index(self) -> None:
        result = fundus.create_document(self.config, "demo", "Movable", "Body", ["ticket"])
        destination = "Fundus/Epics/AI Agent Templates/movable.md"
        fundus.rebuild_index(self.config)

        moved = fundus.move_document(self.config, result["path"], destination)
        scan_results = fundus.scan_documents(self.config, "demo", "Movable", scope=fundus.area_scope("Epics/AI Agent Templates"))
        project_results = fundus.scan_documents(self.config, "demo", "Movable")
        frontmatter, _ = fundus.parse_frontmatter((self.vault_path / destination).read_text())

        self.assertEqual(moved["path"], destination)
        self.assertFalse((self.vault_path / result["path"]).exists())
        self.assertTrue((self.vault_path / destination).exists())
        self.assertEqual(scan_results[0]["path"], destination)
        self.assertEqual(project_results, [])
        self.assertEqual(frontmatter["scope"], "area")
        self.assertEqual(frontmatter["scope_path"], "Epics/AI Agent Templates")
        self.assertNotIn("project", frontmatter)

    def test_move_matrix_preserves_id_and_reclassifies_scope(self) -> None:
        epic = fundus.area_scope("Epics/AI Agent Templates")
        domain = fundus.area_scope("Domains/Prompt Authoring")
        cases = [
            ("project-same", fundus.project_scope("demo"), "Fundus/demo/research/project-same.md", "project", "demo", "demo"),
            ("project-other", fundus.project_scope("demo"), "Fundus/other/project-other.md", "project", "other", "other"),
            ("project-area", fundus.project_scope("demo"), "Fundus/Epics/AI Agent Templates/references/project-area.md", "area", epic.path, None),
            ("area-same", epic, "Fundus/Epics/AI Agent Templates/stories/area-same.md", "area", epic.path, None),
            ("area-other", epic, "Fundus/Domains/Prompt Authoring/references/area-other.md", "area", domain.path, None),
            ("area-project", epic, "Fundus/demo/research/area-project.md", "project", "demo", "demo"),
        ]
        fundus.rebuild_index(self.config)

        for name, source_scope, destination, expected_kind, expected_scope_path, expected_project in cases:
            with self.subTest(name=name):
                title = name.replace("-", " ").title()
                created = fundus.create_document(
                    self.config,
                    source_scope.path if source_scope.kind == "project" else "demo",
                    title,
                    f"Body for {name}",
                    ["neutral"],
                    source_scope,
                )
                source_path = self.vault_path / created["path"]
                original_frontmatter, _ = fundus.parse_frontmatter(source_path.read_text())

                result = fundus.move_document(self.config, created["path"], destination)

                destination_path = self.vault_path / destination
                moved_frontmatter, _ = fundus.parse_frontmatter(destination_path.read_text())
                classification = fundus.classify_document_scope(self.config, destination_path, moved_frontmatter)
                index_entry = next(
                    entry for entry in fundus.load_index(self.config)["documents"] if entry["path"] == destination
                )
                expected_scope_tag = (
                    f"project/{expected_project}"
                    if expected_project
                    else f"area/{fundus.slugify_path(expected_scope_path)}"
                )
                scope_tags = [
                    tag for tag in moved_frontmatter["tags"] if tag.startswith("project/") or tag.startswith("area/")
                ]

                self.assertFalse(source_path.exists())
                self.assertEqual(result["scope"], expected_kind)
                self.assertEqual(result["scope_path"], expected_scope_path)
                self.assertEqual(moved_frontmatter["id"], original_frontmatter["id"])
                self.assertEqual(moved_frontmatter["scope"], expected_kind)
                self.assertEqual(moved_frontmatter["scope_path"], expected_scope_path)
                self.assertEqual(moved_frontmatter.get("project"), expected_project)
                self.assertIn("neutral", moved_frontmatter["tags"])
                self.assertEqual(scope_tags, [expected_scope_tag])
                self.assertEqual(classification.scope.path, expected_scope_path)
                self.assertEqual(index_entry["id"], original_frontmatter["id"])
                self.assertEqual(index_entry["scope_path"], expected_scope_path)
                self.assertEqual(index_entry["physical_parent"], Path(destination.removeprefix("Fundus/")).parent.as_posix())
                self.assertTrue(fundus.verify_fundus_corpus(self.config)["passed"])

    def test_move_redirect_is_quiet_and_resolves_on_read(self) -> None:
        created = fundus.create_document(
            self.config,
            "demo",
            "Redirected Note",
            "Unique redirect destination body",
            ["neutral"],
        )
        source_path = self.vault_path / created["path"]
        original_frontmatter, _ = fundus.parse_frontmatter(source_path.read_text())
        destination = "Fundus/Epics/AI Agent Templates/references/redirected-note.md"

        moved = fundus.move_document(self.config, created["path"], destination, leave_stub=True)

        redirect_frontmatter, redirect_body = fundus.parse_frontmatter(source_path.read_text())
        destination_frontmatter, _ = fundus.parse_frontmatter((self.vault_path / destination).read_text())
        direct_project_results = fundus.scan_documents(self.config, "demo", "Redirected Note")
        direct_area_results = fundus.scan_documents(
            self.config,
            "demo",
            "Redirected Note",
            scope=fundus.area_scope("Epics/AI Agent Templates"),
        )
        fundus.rebuild_index(self.config)
        indexed_project_results = fundus.scan_documents(self.config, "demo", "Redirected Note")
        source_entry = next(
            entry for entry in fundus.load_index(self.config)["documents"] if entry["path"] == created["path"]
        )

        self.assertEqual(moved["redirect_path"], created["path"])
        self.assertEqual(redirect_frontmatter["type"], "Redirect")
        self.assertEqual(redirect_frontmatter["redirect_to"], destination)
        self.assertNotEqual(redirect_frontmatter["id"], original_frontmatter["id"])
        self.assertEqual(destination_frontmatter["id"], original_frontmatter["id"])
        self.assertIn("../Epics/AI Agent Templates/references/redirected-note.md", redirect_body)
        self.assertEqual(fundus.read_document(self.config, created["path"]), (self.vault_path / destination).read_text())
        self.assertEqual(direct_project_results, [])
        self.assertEqual(indexed_project_results, [])
        self.assertEqual([result["path"] for result in direct_area_results], [destination])
        self.assertEqual(source_entry["kind"], "redirect")
        self.assertEqual(source_entry["redirect_to"], destination)
        self.assertTrue(fundus.verify_fundus_corpus(self.config)["passed"])

    def test_redirect_loop_and_invalid_target_fail_safely(self) -> None:
        paths = [self.vault_path / "Fundus" / "demo" / name for name in ["a.md", "b.md"]]
        targets = ["Fundus/demo/b.md", "Fundus/demo/a.md"]
        for path, target in zip(paths, targets, strict=True):
            frontmatter = fundus.frontmatter_for_new_document(
                self.config,
                "demo",
                fundus.project_scope("demo"),
                path.stem.upper(),
                ["redirect"],
                "Redirect",
            )
            frontmatter["redirect_to"] = target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fundus.render_existing_document(frontmatter, "Redirect"))

        with self.assertRaises(fundus.FundusError) as loop:
            fundus.read_document(self.config, "Fundus/demo/a.md")
        self.assertEqual(loop.exception.code, "REDIRECT_LOOP")

        frontmatter, body = fundus.parse_frontmatter(paths[1].read_text())
        frontmatter["redirect_to"] = "Other/outside.md"
        paths[1].write_text(fundus.render_existing_document(frontmatter, body))
        with self.assertRaises(fundus.FundusError) as invalid:
            fundus.read_document(self.config, "Fundus/demo/b.md")
        self.assertEqual(invalid.exception.code, "REDIRECT_INVALID")


class PathSafetyTest(FundusTestCase):
    def test_project_names_must_be_safe_non_reserved_segments(self) -> None:
        fixture = json.loads((FIXTURES_DIR / "path_security_cases.json").read_text())
        for project in fixture["invalid_projects"]:
            with self.subTest(project=project):
                with self.assertRaises(fundus.FundusError) as raised:
                    fundus.project_scope(project)
                self.assertEqual(raised.exception.code, "PROJECT_NAME_INVALID")

    def test_area_paths_require_an_explicit_allowed_root_and_name(self) -> None:
        fixture = json.loads((FIXTURES_DIR / "path_security_cases.json").read_text())
        for area in fixture["invalid_areas"]:
            with self.subTest(area=area):
                with self.assertRaises(fundus.FundusError) as raised:
                    fundus.area_scope(area)
                self.assertEqual(raised.exception.code, "AREA_PATH_INVALID")

    def test_note_operations_reject_vault_paths_outside_fundus(self) -> None:
        outside = self.vault_path / "Other" / "private.md"
        outside.parent.mkdir()
        outside.write_text("do not touch")

        operations = [
            lambda: fundus.read_document(self.config, "Other/private.md"),
            lambda: fundus.update_document(self.config, "demo", "Other/private.md", "rewrite", "changed", None),
            lambda: fundus.archive_document(self.config, "Other/private.md", "unsafe"),
            lambda: fundus.move_document(self.config, "Other/private.md", "Fundus/demo/private.md"),
        ]
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(fundus.FundusError) as raised:
                    operation()
                self.assertEqual(raised.exception.code, "PATH_OUTSIDE_FUNDUS")
        self.assertEqual(outside.read_text(), "do not touch")

    def test_note_paths_reject_traversal_non_markdown_directories_and_reserved_files(self) -> None:
        directory = self.vault_path / "Fundus" / "demo" / "folder.md"
        directory.mkdir(parents=True)
        fixture = json.loads((FIXTURES_DIR / "path_security_cases.json").read_text())
        for path in fixture["invalid_note_paths"]:
            with self.subTest(path=path):
                with self.assertRaises(fundus.FundusError):
                    fundus.resolve_fundus_note_path(self.config, path)

    def test_restore_treats_original_path_as_untrusted_active_path(self) -> None:
        created = fundus.create_document(self.config, "demo", "Archived", "Body", None)
        archived = fundus.archive_document(self.config, created["path"], "old")
        archive_path = self.vault_path / archived["path"]
        frontmatter, body = fundus.parse_frontmatter(archive_path.read_text())
        frontmatter["original_path"] = "Other/escaped.md"
        archive_path.write_text(fundus.render_existing_document(frontmatter, body))

        with self.assertRaises(fundus.FundusError) as raised:
            fundus.restore_document(self.config, archived["path"])

        self.assertEqual(raised.exception.code, "PATH_OUTSIDE_FUNDUS")
        self.assertTrue(archive_path.exists())
        self.assertFalse((self.vault_path / "Other" / "escaped.md").exists())

    def test_symlinked_note_parent_cannot_escape_fundus(self) -> None:
        outside = self.vault_path / "outside"
        outside.mkdir()
        (outside / "secret.md").write_text("secret")
        project = self.vault_path / "Fundus" / "demo"
        project.mkdir(parents=True, exist_ok=True)
        link = project / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")

        with self.assertRaises(fundus.FundusError) as raised:
            fundus.read_document(self.config, "Fundus/demo/linked/secret.md")

        self.assertEqual(raised.exception.code, "PATH_OUTSIDE_FUNDUS")

    def test_global_project_enumeration_excludes_area_and_reserved_roots(self) -> None:
        root = self.vault_path / "Fundus"
        for name in ["demo", "another", "Epics", "Domains", "Decisions", "Interviews", "References", "Logs", "Operations", "_archive"]:
            (root / name).mkdir(parents=True, exist_ok=True)

        self.assertEqual(fundus.fundus_project_names(self.config), ["another", "demo"])

    def test_doctor_reports_resolved_path_policy_and_scope_classification(self) -> None:
        report = fundus.doctor_report_for_scope(
            self.config,
            self.vault_path / "repo",
            "demo",
            fundus.project_scope("demo"),
        )

        self.assertEqual(report["scope_classification"]["kind"], "project")
        self.assertEqual(report["path_policy"]["ordinary_notes_root"], str(self.vault_path / "Fundus"))
        self.assertTrue(report["path_policy"]["symlink_escape_protection"])


if __name__ == "__main__":
    unittest.main()
