#!/usr/bin/env python3
"""Translate a Beadloom guard verdict into the JSON a Cursor hook must print.

The decision stays in ``beadloom guard``. This script reads the hook event,
passes the edit's path or command through, and maps the verdict onto Cursor's
``permission`` field. A warn or an unresolved guard allows the edit, as the
guard's own exit codes do. A block or an error denies it.
"""

from __future__ import annotations

import json
import subprocess
import sys

_DEFAULT_GUARDS = ("bead-claimed", "working-branch")
_ALLOW = frozenset({"pass", "skip", "warn", "unresolved"})


def _event() -> dict[str, object]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _context(event: dict[str, object]) -> list[str]:
    tool_input = event.get("tool_input")
    fields: dict[str, object] = tool_input if isinstance(tool_input, dict) else {}
    path = fields.get("file_path") or fields.get("path") or event.get("file_path") or ""
    command = fields.get("command") or event.get("command") or ""
    pairs: list[str] = []
    if isinstance(path, str) and path:
        pairs.append(f"path={path}")
    if isinstance(command, str) and command:
        pairs.append(f"command={command}")
    return pairs


def _verdict(guard: str, context: list[str]) -> tuple[str, str]:
    completed = subprocess.run(
        ["beadloom", "guard", guard, "--json", *[arg for pair in context for arg in ("--context", pair)]],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    outcome = str(payload.get("outcome") or "")
    if not outcome:
        outcome = "block" if completed.returncode == 2 else "unresolved"
    why = str(payload.get("why") or completed.stderr or "").strip()
    remediation = str(payload.get("remediation") or "").strip()
    detail = why if not remediation else f"{why} — {remediation}"
    return outcome, detail or f"{guard} exited {completed.returncode}"


def _answer(permission: str, message: str) -> None:
    body: dict[str, object] = {"permission": permission}
    if message:
        body["user_message"] = message
        body["agent_message"] = message
    json.dump(body, sys.stdout)
    sys.stdout.write("\n")


def main() -> int:
    guards = tuple(sys.argv[1:]) or _DEFAULT_GUARDS
    context = _context(_event())
    denied: list[str] = []
    warned: list[str] = []
    for guard in guards:
        outcome, detail = _verdict(guard, context)
        line = f"{guard}: {detail}"
        if outcome in _ALLOW:
            if outcome == "warn":
                warned.append(line)
            continue
        denied.append(line)
    if denied:
        _answer("deny", "\n".join(denied))
        return 0
    _answer("allow", "\n".join(warned))
    return 0


if __name__ == "__main__":
    sys.exit(main())
