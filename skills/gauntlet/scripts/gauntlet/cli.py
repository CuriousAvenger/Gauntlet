"""Shared output for the scripts: one JSON object on stdout; exit 0 = done, 1 = refused, 2 = misuse."""

from __future__ import annotations

import json
import sys
from typing import Any, NoReturn


def finish(result: dict[str, Any], code: int = 0) -> NoReturn:
    print(json.dumps(result, indent=1, ensure_ascii=False))
    sys.exit(code)


def fail(message: str, code: int = 2) -> NoReturn:
    finish({"error": message}, code)
