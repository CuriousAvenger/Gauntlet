import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_generated_files_are_current():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/build.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_plugin_manifests():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert plugin["name"] == "gauntlet"
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert market["owner"]["name"] and market["plugins"][0]["source"].startswith("./")
    mcp = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]["gauntlet"]
    assert mcp["args"][0].startswith("${CLAUDE_PLUGIN_ROOT}/")
    hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
    assert {"PreToolUse", "SubagentStop", "Stop", "SessionStart"} <= set(hooks)
    for groups in hooks.values():
        for g in groups:
            for h in g["hooks"]:
                event = h["command"].rsplit(" ", 1)[-1]
                from gauntlet.hooks import HANDLERS
                assert event in HANDLERS


def test_agents_and_skill_frontmatter():
    for f in (ROOT / "agents").glob("*.md"):
        fm = re.match(r"---\n(.*?)\n---", f.read_text(), re.S).group(1)
        assert re.search(r"^name: \w+$", fm, re.M) and "description:" in fm and "model:" in fm, f
    skill = (ROOT / "skills/research/SKILL.md").read_text()
    assert skill.startswith("---\nname: research\ndescription: ")
    desc = re.search(r"^description: (.*)$", skill, re.M).group(1)
    assert len(desc) <= 1536
