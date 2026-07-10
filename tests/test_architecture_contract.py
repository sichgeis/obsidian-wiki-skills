from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class ArchitectureContractTest(unittest.TestCase):
    def test_compatibility_entrypoints_are_thin_and_core_is_packaged(self) -> None:
        for name in ("fundus.py", "fundus_mcp.py"):
            self.assertLessEqual(len((SCRIPTS / name).read_text().splitlines()), 50)
        self.assertTrue((SCRIPTS / "fundus_core" / "runtime.py").exists())
        self.assertTrue((SCRIPTS / "fundus_core" / "mcp_server.py").exists())

    def test_fundus_facade_exposes_core_operations(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        facade = importlib.import_module("fundus")
        runtime = importlib.import_module("fundus_core.runtime")

        self.assertIs(facade.create_document, runtime.create_document)
        self.assertIs(facade.resolve_config, runtime.resolve_config)
        self.assertIs(facade.main, runtime.main)


if __name__ == "__main__":
    unittest.main()
