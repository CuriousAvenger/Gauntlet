#!/usr/bin/env python3
"""Gauntlet MCP server launcher. Point any MCP client at:  python3 /path/to/Gauntlet/server.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gauntlet.tools import serve  # noqa: E402

serve()
