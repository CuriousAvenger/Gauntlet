#!/usr/bin/env python3
"""Gauntlet MCP server. Point any MCP client at:  python3 /path/to/gauntlet/server.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gauntlet.tools import server  # noqa: E402

server.serve()
