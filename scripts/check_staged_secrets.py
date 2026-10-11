"""Scan staged blobs, never print credential values. Exit nonzero to block a commit."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)


def main() -> int:
    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    secrets = []
    for name in (".env", ".evn"):
        path = root / name
        if path.is_file():
            values = dotenv_values(path, interpolate=False)
            secrets.extend(
                value.encode()
                for key, value in values.items()
                if re.search(r"KEY|SECRET|TOKEN|PASSWORD", key, re.I) and value and len(value) >= 8
            )
    paths = [
        path.decode() for path in git("diff", "--cached", "--name-only", "-z").split(b"\0") if path
    ]
    patterns = [
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        rb"gh[pousr]_[A-Za-z0-9]{30,}",
        rb"github_pat_[A-Za-z0-9_]{40,}",
        rb"AKIA[0-9A-Z]{16}",
        rb"sk-(?:proj-)?[A-Za-z0-9_-]{40,}",
    ]
    failures = []
    for path in paths:
        lowered = path.lower()
        components = Path(lowered).parts
        forbidden = lowered != ".env.example" and any(
            item == ".env"
            or item.startswith(".env.")
            or item == ".evn"
            or item.startswith(".evn.")
            or item in {"data", ".venv"}
            or ".sqlite3" in item
            for item in components
        )
        if forbidden:
            failures.append((path, "forbidden artifact path"))
            continue
        # Deleted paths have no staged content.
        if not git("ls-files", "--stage", "--", path):
            continue
        content = git("show", f":{path}")
        if any(secret in content for secret in secrets):
            failures.append((path, "matches a configured local credential"))
        elif any(re.search(pattern, content) for pattern in patterns):
            failures.append((path, "matches a credential signature"))
    print(f"Staged credential scan: {len(paths)} paths, {len(failures)} findings")
    for path, reason in failures:
        print(f"BLOCKED: {path}: {reason}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
