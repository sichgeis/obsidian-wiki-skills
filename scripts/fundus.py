#!/usr/bin/env python3
"""Compatibility CLI and import facade for the modular Fundus runtime."""
from __future__ import annotations

import sys
import types
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fundus_core import runtime as _runtime


class _FundusFacade(types.ModuleType):
    """Forward reads and test-hook writes to the compatibility runtime module."""

    def __getattr__(self, name: str) -> object:
        return getattr(_runtime, name)

    def __setattr__(self, name: str, value: object) -> None:
        if not name.startswith("__") and hasattr(_runtime, name):
            setattr(_runtime, name, value)
        super().__setattr__(name, value)

    def __dir__(self) -> list[str]:
        return sorted(set(super().__dir__()) | set(dir(_runtime)))


sys.modules[__name__].__class__ = _FundusFacade
main = _runtime.main


if __name__ == "__main__":
    raise SystemExit(main())
