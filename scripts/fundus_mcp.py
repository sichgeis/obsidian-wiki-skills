#!/usr/bin/env python3
"""Compatibility entrypoint for the Fundus MCP server."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fundus_core.mcp_server import *  # noqa: F401,F403
from fundus_core.mcp_server import main


if __name__ == "__main__":
    raise SystemExit(main())
