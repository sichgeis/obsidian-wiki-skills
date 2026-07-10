from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTest(unittest.TestCase):
    def test_skill_forbids_raw_markdown_fallback_when_fundus_tools_are_missing(self) -> None:
        skill = (ROOT / "SKILL.md").read_text()

        self.assertIn("Fundus does not depend on a separate Obsidian MCP", skill)
        self.assertIn("Never edit Fundus notes directly", skill)
        self.assertIn("Do not use generic Obsidian tools", skill)
        self.assertIn("Do not create, update, or rewrite Markdown directly as a fallback", skill)
        self.assertIn("If you cannot locate the helper path", skill)

    def test_skill_requires_complete_revision_stable_paged_reads(self) -> None:
        skill = (ROOT / "SKILL.md").read_text()

        self.assertIn("until `complete` is `true`", skill)
        self.assertIn("Never infer completeness", skill)
        self.assertIn("On `READ_CURSOR_STALE`, discard every collected page and restart", skill)
        self.assertIn("never combine revisions", skill)
        self.assertIn("For CLI fallback, use `read --paged`", skill)

    def test_agent_evaluation_fixture_covers_proposal_duplicate_and_stale_flows(self) -> None:
        fixture = json.loads((ROOT / "tests" / "fixtures" / "agent_evaluations.json").read_text())
        cases = {case["name"]: case for case in fixture["cases"]}

        self.assertEqual(fixture["version"], 1)
        self.assertIn("duplicate-create-needs-review", cases)
        self.assertIn("stale-evidence-without-write-intent", cases)
        self.assertIn("long-read-requires-completion", cases)
        self.assertIn("apply_create_without_reviewed_override", cases["duplicate-create-needs-review"]["must_not"])
        self.assertEqual(cases["broad-update-intent"]["expected_operations"], ["propose_update", "apply_update"])
        self.assertEqual(cases["long-read-requires-completion"]["expected_completion"], True)


if __name__ == "__main__":
    unittest.main()
