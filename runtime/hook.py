#!/usr/bin/env python3
"""Entry point for Gauntlet's Claude Code hooks: hook.py <pre-tool-use|subagent-stop|stop|session-start>."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gauntlet.hooks import main  # noqa: E402

sys.exit(main())
