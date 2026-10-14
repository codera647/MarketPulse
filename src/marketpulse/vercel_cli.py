"""Invoke the reviewed CLI without cmd.exe interpreting URL percent signs/newlines."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

VERSION = "63.1.2"


def command() -> list[str]:
    if os.name != "nt":
        return ["npx", "--yes", f"vercel@{VERSION}"]
    # npx.cmd is a shell wrapper. Native node invocation preserves literal curl
    # arguments, especially percent-encoded query strings and write-out formats.
    cache = Path(os.environ["LOCALAPPDATA"]) / "npm-cache" / "_npx"
    for directory in sorted(cache.iterdir()):
        package = directory / "node_modules" / "vercel" / "package.json"
        if not package.is_file():
            continue
        metadata = json.loads(package.read_text(encoding="utf-8"))
        if metadata.get("name") != "vercel" or metadata.get("version") != VERSION:
            continue
        entry = (package.parent / metadata["bin"]["vercel"]).resolve()
        if not entry.is_relative_to(package.parent.resolve()) or not entry.is_file():
            raise ValueError("reviewed CLI entrypoint is invalid")
        node = shutil.which("node")
        if node is None:
            raise ValueError("node is not installed")
        return [node, str(entry)]
    raise ValueError("reviewed Vercel CLI is not cached; install the pinned version first")
