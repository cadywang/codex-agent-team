"""Build and run one ``codex exec`` invocation.

The argument set is frozen here on purpose: it is the contract between this
harness and the CLI (codex-cli 0.172.0 at the time of writing). Upgrading the
CLI means re-checking this file, and ``python -m agentteam run --dry-run``
prints the exact command line without spending a token.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

# `codex exec -` reads the prompt from stdin. Passing it as an argument would
# run into Windows quoting rules as soon as the task contains a newline.
PROMPT_FROM_STDIN = "-"


class CodexNotFound(RuntimeError):
    """The configured codex binary cannot be executed."""


@dataclass
class StageResult:
    """What one ``codex exec`` call produced."""

    returncode: int
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.returncode == 0


def build_command(codex_bin: Sequence[str], role, workdir, last_message,
                  schema=None, model: str = "",
                  extra_args: Sequence[str] = ()) -> List[str]:
    """Return the argv for one stage. The prompt itself goes over stdin."""
    argv = list(codex_bin)
    if schema is None:
        schema = role.output_schema
    argv += [
        "exec",
        "--cd", str(workdir),
        "--sandbox", role.sandbox,
        "--color", "never",
        "--skip-git-repo-check",
        "-o", str(last_message),
    ]
    if schema:
        argv += ["--output-schema", str(schema)]
    if model:
        argv += ["--model", model]
    argv += list(role.extra_args)
    argv += list(extra_args)
    argv.append(PROMPT_FROM_STDIN)
    return argv


def resolve_binary(codex_bin: Sequence[str]) -> List[str]:
    """Return the argv prefix to use, or raise :class:`CodexNotFound`."""
    argv = list(codex_bin)
    if not argv:
        raise CodexNotFound("no codex binary configured")
    first = argv[0]
    looks_like_path = (os.sep in first or "/" in first
                       or (os.altsep is not None and os.altsep in first))
    if looks_like_path:
        if pathlib.Path(first).is_file():
            return argv
        raise CodexNotFound("codex binary not found: %s" % first)
    found = shutil.which(first)
    if not found:
        raise CodexNotFound("codex binary not on PATH: %s" % first)
    return [found] + argv[1:]


def run_stage(argv: Sequence[str], prompt: str, cwd, timeout: int) -> StageResult:
    """Run one stage and never raise on a timeout."""
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(argv),
            input=prompt,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return StageResult(
            returncode=completed.returncode,
            timed_out=False,
            duration_seconds=time.monotonic() - started,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
    except subprocess.TimeoutExpired as exc:
        note = "\n[harness] stage timed out after %d second(s)\n" % timeout
        return StageResult(
            returncode=-1,
            timed_out=True,
            duration_seconds=time.monotonic() - started,
            stdout=_as_text(exc.stdout),
            stderr=_as_text(exc.stderr) + note,
        )
    except OSError as exc:
        return StageResult(
            returncode=-1,
            timed_out=False,
            duration_seconds=time.monotonic() - started,
            stdout="",
            stderr="[harness] could not start codex: %s\n" % exc,
        )


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def read_last_message(path) -> Optional[str]:
    """Read the file ``codex exec -o`` writes, or None when it is absent."""
    target = pathlib.Path(path)
    if not target.is_file():
        return None
    return target.read_text(encoding="utf-8", errors="replace")
