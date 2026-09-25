#!/usr/bin/env python3
"""Probe official RawTree MCP over stdio, saving sanitized evidence only.

Default: initialize, tools/list, SELECT 1, list-tables (read-only).
An explicit --tool insert-json --arguments-file is a real remote write.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

from rawtree_mcp_stdio import PACKAGE, PROJECT_ROOT as ROOT, load_settings


class Client:
    def __init__(self, timeout: float = 50.0):
        settings = os.environ.copy()
        settings.update(load_settings(ROOT / ".env"))
        self.key = settings.get("RAWTREE_API_KEY", "")
        self.timeout = timeout
        self.counter = 0
        self.buffer = b""
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts/rawtree_mcp_stdio.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def send(self, payload):
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        self.process.stdin.flush()

    def call(self, method, params):
        self.counter += 1
        self.send({"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                try:
                    response = json.loads(line)
                except (json.JSONDecodeError, UnicodeError):
                    continue
                if response.get("id") != self.counter:
                    continue
                if "error" in response:
                    raise RuntimeError("mcp_protocol_error")
                return response.get("result", {})
            if self.selector.select(min(1, max(0, deadline - time.monotonic()))):
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("mcp_server_stream_closed")
                self.buffer += chunk
                if len(self.buffer) > 4 * 1024 * 1024:
                    raise RuntimeError("mcp_response_size_limit")
            elif self.process.poll() is not None:
                raise RuntimeError("mcp_server_exited")
        raise TimeoutError("mcp_response_timeout")

    def initialize(self):
        result = self.call("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "apple-agent-verification", "version": "0.1.0"},
        })
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return result

    def tool(self, name, arguments):
        return self.call("tools/call", {"name": name, "arguments": arguments})

    def sanitize(self, value):
        rendered = json.dumps(value, ensure_ascii=False)
        if self.key:
            rendered = rendered.replace(self.key, "[REDACTED]")
        rendered = re.sub(r"rt_[A-Za-z0-9_.-]{20,}", "[REDACTED]", rendered)
        return json.loads(rendered)

    def close(self):
        self.selector.close()
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait()
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", choices=["list-tables", "run-query", "insert-json"])
    parser.add_argument("--arguments-file", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/catalog/rawtree/stdio_connection.json")
    args = parser.parse_args()
    if args.tool in ("run-query", "insert-json") and not args.arguments_file:
        parser.error("The selected tool requires --arguments-file.")
    record = {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "transport": "stdio", "package": PACKAGE,
        "remote_mutation_requested": args.tool == "insert-json",
    }
    client = None
    try:
        client = Client()
        record["initialize"] = client.initialize()
        listed = client.call("tools/list", {})
        record["tools"] = [tool["name"] for tool in listed.get("tools", [])]
        if args.tool:
            arguments = json.loads(args.arguments_file.read_text()) if args.arguments_file else {}
            record["tool_name"] = args.tool
            record["tool_result"] = client.tool(args.tool, arguments)
            record["ok"] = not record["tool_result"].get("isError", False)
        else:
            record["query"] = client.tool("run-query", {"sql": "SELECT 1 AS connection_ok"})
            record["tables"] = client.tool("list-tables", {})
            record["ok"] = all(not record[name].get("isError", False) for name in ("query", "tables"))
    except Exception as exc:
        # Exception bodies can echo request details. Persist only the type.
        record.update(ok=False, error=type(exc).__name__)
    finally:
        if client:
            record = client.sanitize(record)
            client.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "ok": record["ok"], "output": str(args.output),
        "tools_count": len(record.get("tools", [])), "error": record.get("error"),
    }))
    return 0 if record["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
