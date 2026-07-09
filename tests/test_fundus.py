from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "fundus.py"
SPEC = importlib.util.spec_from_file_location("fundus", SCRIPT_PATH)
assert SPEC and SPEC.loader
fundus = importlib.util.module_from_spec(SPEC)
sys.modules["fundus"] = fundus
SPEC.loader.exec_module(fundus)


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
        self.assertEqual(frontmatter["archived"], "true")
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
        self.assertEqual(frontmatter["scope_path"], "Epics/AI Agent Templates/references")
        self.assertNotIn("project", frontmatter)
        self.assertEqual(frontmatter["tags"], ["fundus", "area/epics/ai-agent-templates/references", "architecture"])

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

    def test_verify_fundus_corpus_reports_reserved_frontmatter_issue(self) -> None:
        (self.vault_path / "Fundus" / "demo").mkdir(parents=True)
        (self.vault_path / "Fundus" / "demo" / "index.md").write_text(
            "---\ntitle: Bad Index\n---\n\n# Bad Index\n"
        )

        verification = fundus.verify_fundus_corpus(self.config)

        self.assertFalse(verification["passed"])
        self.assertEqual(verification["issues"][0]["reason"], "reserved_has_frontmatter")


class ScopeAndAreaTest(FundusTestCase):
    def test_area_path_validation_rejects_unsafe_paths(self) -> None:
        for area in ["", "../Other", "/absolute", "_archive/old", ".fundus-backups/x"]:
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


if __name__ == "__main__":
    unittest.main()
