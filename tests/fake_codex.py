#!/usr/bin/env python3
"""Stand-in for ``codex exec``, used by the offline self-tests.

It imitates the parts of the CLI the harness depends on: read the prompt from
stdin, report the role from the prompt, and write a final message to the file
named after ``-o``. Behaviour is scripted by environment variables, so a test
can exercise a failing gate without a model and without a network:

    FAKE_CODEX_MODE=pass|crash        crash exits 2 and writes nothing useful
    FAKE_CODEX_FAIL_ROLES=review,test always fail these roles
    FAKE_CODEX_FAIL_ONCE=review       fail only the first attempt of these roles
    FAKE_CODEX_WRITE_ROLE=review      write a file as that role (read-only violation)

The attempt counter is a file next to the last message, so every stage
directory counts on its own.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

ROLE_RE = re.compile(r"^## Agent role\s*\n+\s*(\S+)\s*$", re.MULTILINE)
GATE_ROLES = ("review", "test")


def main(argv):
    if "exec" not in argv:
        sys.stderr.write("fake_codex: not an exec invocation\n")
        return 2
    try:
        last_message = pathlib.Path(argv[argv.index("-o") + 1])
    except (ValueError, IndexError):
        sys.stderr.write("fake_codex: -o <file> is required\n")
        return 2
    workdir = pathlib.Path(argv[argv.index("--cd") + 1]) if "--cd" in argv else pathlib.Path(".")

    prompt = sys.stdin.read()
    match = ROLE_RE.search(prompt)
    role = match.group(1) if match else "unknown"

    mode = os.environ.get("FAKE_CODEX_MODE", "pass")
    if mode == "crash":
        sys.stderr.write("fake_codex: deliberate crash\n")
        return 2

    attempts = _bump_attempts(last_message, role)
    fail_roles = _env_list("FAKE_CODEX_FAIL_ROLES")
    fail_once = _env_list("FAKE_CODEX_FAIL_ONCE")
    failing = role in fail_roles or (role in fail_once and attempts == 1)

    write_role = os.environ.get("FAKE_CODEX_WRITE_ROLE", "")
    if write_role and role == write_role:
        # A unique name per attempt: the harness compares `git status` before
        # and after the stage, so re-touching the same file would look clean.
        junk = "fake-junk-%s-%d.txt" % (role, attempts)
        (workdir / junk).write_text("written by a read-only role\n", encoding="utf-8")

    last_message.parent.mkdir(parents=True, exist_ok=True)
    last_message.write_text(_message(role, failing), encoding="utf-8")

    print(json.dumps({"type": "fake_event", "role": role, "attempt": attempts}))
    return 0


def _bump_attempts(last_message: pathlib.Path, role: str) -> int:
    # The counter lives in the run root, not next to the message: a role can
    # run several times (review, debug, review), and "fail once" must mean the
    # first attempt of that role in this run.
    counter = last_message.parent.parent / (".fake-%s.attempts" % role)
    current = 0
    if counter.is_file():
        try:
            current = int(counter.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            current = 0
    current += 1
    counter.write_text(str(current), encoding="utf-8")
    return current


def _env_list(name: str):
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _message(role: str, failing: bool) -> str:
    if role in GATE_ROLES:
        payload = {
            "verdict": "fail" if failing else "pass",
            "summary": "fake %s gate says %s" % (role, "fail" if failing else "pass"),
            "findings": [] if not failing else [{
                "severity": "blocker",
                "file": "sample.py",
                "line": 7,
                "issue": "the fake gate failed on purpose",
                "suggestion": "make the fake gate pass",
            }],
            "checks": ["fake_codex"],
        }
        return json.dumps(payload, indent=2) + "\n"

    if role == "research":
        return json.dumps({
            "goal": "do the fake task",
            "relevant_paths": ["sample.py"],
            "steps": [{"action": "change sample.py", "rationale": "it is the only file"}],
            "risks": ["none, this is a fake plan"],
            "verification": "python -c 'print(1)'",
        }, indent=2) + "\n"

    if role == "flash":
        return json.dumps({
            "device": "<board>",
            "preconditions": ["backup the current image"],
            "commands": ["flash-tool write <image>"],
            "verification": ["read the version string from the console"],
            "rollback": ["flash the backup image"],
            "warnings": ["this is a fake plan"],
        }, indent=2) + "\n"

    return "## Changed\n- sample.py: fake change\n\n## Verification\n- fake\n"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
