#!/usr/bin/env python3
"""Launch Gauntlet's MCP server (stdio). Used by the plugin's .mcp.json and by other runners."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gauntlet.mcp.tools import server  # noqa: E402

server.serve()
