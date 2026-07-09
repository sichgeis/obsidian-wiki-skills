from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
