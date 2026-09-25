#!/usr/bin/env python3
"""Start the official RawTree MCP server without putting a key in argv/config.

Reads only RawTree settings from this project's .env. Does not source shell code,
print credentials, or perform a database operation. Standard input/output belong
exclusively to the MCP server. --check validates local prerequisites only.
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "@rawtree/mcp@0.3.2"
ALLOWED_KEYS = frozenset(
    {"RAWTREE_API_KEY", "RAWTREE_API_URL", "RAWTREE_DATABASE", "RAWTREE_ORG"}
)


def load_settings(path: Path) -> dict[str, str]:
    """Parse selected one-line dotenv assignments; never expand/evaluate values."""
    settings: dict[str, str] = {}
    if not path.exists():
        return settings
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, raw_value = line.partition("=")
        name = name.strip()
        if not separator or name not in ALLOWED_KEYS:
            continue
        try:
            parts = shlex.split(raw_value, comments=True, posix=True)
        except ValueError:
            raise ValueError("Invalid RawTree dotenv assignment; check quoting.") from None
        if len(parts) > 1:
            raise ValueError("RawTree dotenv values containing spaces must be quoted.")
        settings[name] = parts[0] if parts else ""
    return settings


def main() -> int:
    if sys.argv[1:] not in ([], ["--check"]):
        print("Usage: rawtree_mcp_stdio.py [--check]", file=sys.stderr)
        return 2
    env = os.environ.copy()
    try:
        # Project credentials take precedence over stale parent-shell values.
        env.update(load_settings(PROJECT_ROOT / ".env"))
    except (OSError, UnicodeError, ValueError):
        print("Cannot read RawTree settings from project .env; check file and quoting.", file=sys.stderr)
        return 2
    if not env.get("RAWTREE_API_KEY", "").strip():
        print("RAWTREE_API_KEY is missing or empty in project .env/environment.", file=sys.stderr)
        return 2
    npx = shutil.which("npx")
    if npx is None:
        print("npx is unavailable; install Node.js/npm or update the MCP process PATH.", file=sys.stderr)
        return 2
    if sys.argv[1:] == ["--check"]:
        print("RawTree local prerequisites ready; remote authentication not tested.", file=sys.stderr)
        return 0
    # The secret is passed only in the child environment, never as a CLI flag.
    # exec preserves the MCP stdio streams and forwards process signals directly.
    try:
        os.execve(npx, [npx, "--yes", PACKAGE], env)
    except OSError:
        print("Could not start the RawTree MCP server.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
