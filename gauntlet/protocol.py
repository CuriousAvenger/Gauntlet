"""A dependency-free MCP server (stdio transport; tools and prompts).

Implements the subset of the Model Context Protocol Gauntlet needs:
``initialize``, ``ping``, ``tools/list``, ``tools/call``, ``prompts/list`` and
``prompts/get`` over newline-delimited JSON-RPC 2.0. Standard library only, so any
MCP client can launch it with a plain ``python3`` and nothing to install.

Tools are registered with :func:`tool`. Arguments are validated against the
tool's JSON Schema before the handler runs; a :class:`ToolError` becomes an
``isError`` result whose text tells the agent how to fix the call.
"""

from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Callable

SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


class ToolError(Exception):
    """An expected failure the agent can act on. The message is shown to it."""


@dataclass
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    fn: Callable[..., Any]
    read_only: bool = False

    def spec(self) -> dict[str, Any]:
        out = {"name": self.name, "description": self.description, "inputSchema": self.schema}
        out["annotations"] = {"readOnlyHint": self.read_only}
        return out


@dataclass
class Prompt:
    name: str
    description: str
    arguments: list[dict[str, Any]]
    fn: Callable[..., str]


class Server:
    def __init__(self, name: str, version: str, instructions: str = ""):
        self.name, self.version, self.instructions = name, version, instructions
        self.tools: dict[str, Tool] = {}
        self.prompts: dict[str, Prompt] = {}

    def prompt(self, name: str, description: str, arguments: list[dict[str, Any]] = ()):
        def deco(fn):
            self.prompts[name] = Prompt(name, description.strip(), list(arguments), fn)
            return fn
        return deco

    def tool(self, name: str, description: str, properties: dict[str, Any], required: list[str] | tuple = (),
             read_only: bool = False):
        schema = {"type": "object", "properties": properties, "required": list(required),
                  "additionalProperties": False}

        def deco(fn):
            self.tools[name] = Tool(name, description.strip(), schema, fn, read_only)
            return fn
        return deco

    # ---- protocol --------------------------------------------------------------
    def handle(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        mid = msg.get("id")
        method = msg.get("method")
        if mid is None:  # notification (initialized, cancelled, ...): nothing to send
            return None
        try:
            if method == "initialize":
                result = self._initialize(msg.get("params") or {})
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [t.spec() for t in self.tools.values()]}
            elif method == "tools/call":
                result = self._call(msg.get("params") or {})
            elif method == "prompts/list":
                result = {"prompts": [{"name": p.name, "description": p.description, "arguments": p.arguments}
                                      for p in self.prompts.values()]}
            elif method == "prompts/get":
                result = self._get_prompt(msg.get("params") or {})
            else:
                return _error(mid, -32601, f"method not found: {method}")
        except _RpcError as e:
            return _error(mid, e.code, str(e))
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        out = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
            "serverInfo": {"name": self.name, "version": self.version},
        }
        if self.instructions:
            out["instructions"] = self.instructions
        return out

    def _call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        tool = self.tools.get(name)
        if tool is None:
            raise _RpcError(-32602, f"unknown tool: {name}")
        args = params.get("arguments") or {}
        problems = validate(args, tool.schema)
        if problems:
            return _text_result("Invalid arguments:\n- " + "\n- ".join(problems), error=True)
        try:
            value = tool.fn(**args)
        except ToolError as e:
            return _text_result(str(e), error=True)
        except Exception as e:  # never kill the server on a handler bug
            traceback.print_exc(file=sys.stderr)
            return _text_result(f"internal error in {name}: {type(e).__name__}: {e}", error=True)
        if isinstance(value, str):
            return _text_result(value)
        return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=1)}],
                "structuredContent": value if isinstance(value, dict) else {"result": value},
                "isError": False}

    def _get_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        p = self.prompts.get(params.get("name"))
        if p is None:
            raise _RpcError(-32602, f"unknown prompt: {params.get('name')}")
        args = params.get("arguments") or {}
        missing = [a["name"] for a in p.arguments if a.get("required") and a["name"] not in args]
        if missing:
            raise _RpcError(-32602, f"missing prompt arguments: {missing}")
        text = p.fn(**args)
        return {"description": p.description,
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}

    def serve(self, stdin=None, stdout=None) -> None:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                _write(stdout, _error(None, -32700, "parse error"))
                continue
            batch = msg if isinstance(msg, list) else [msg]
            replies = [r for r in (self.handle(m) for m in batch if isinstance(m, dict)) if r is not None]
            if replies:
                _write(stdout, replies if isinstance(msg, list) else replies[0])


class _RpcError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


def _text_result(text: str, error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": error}


def _error(mid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _write(stdout, obj: Any) -> None:
    stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    stdout.flush()


# ---- minimal JSON Schema validation (the subset our tools use) ---------------------

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
          "array": list, "object": dict}


def validate(value: Any, schema: dict[str, Any], path: str = "") -> list[str]:
    problems: list[str] = []
    where = path or "arguments"
    t = schema.get("type")
    if t:
        py = _TYPES[t]
        ok = isinstance(value, py) and not (t in ("integer", "number") and isinstance(value, bool))
        if not ok:
            return [f"{where}: expected {t}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{where}: must be one of {schema['enum']}, got {value!r}")
    if t == "string" and "minLength" in schema and len(value) < schema["minLength"]:
        problems.append(f"{where}: must be at least {schema['minLength']} characters")
    if t == "object":
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                problems.append(f"{where}: missing required field '{req}'")
        for k, v in value.items():
            if k in props:
                problems += validate(v, props[k], f"{path}.{k}" if path else k)
            elif schema.get("additionalProperties") is False:
                problems.append(f"{where}: unknown field '{k}' (allowed: {', '.join(props)})")
    if t == "array" and "items" in schema:
        for i, item in enumerate(value):
            problems += validate(item, schema["items"], f"{where}[{i}]")
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append(f"{where}: needs at least {schema['minItems']} item(s)")
    return problems
