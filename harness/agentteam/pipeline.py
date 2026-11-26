"""The pipeline: a fixed state machine with explicit gates.

research -> coding -> review -> (debug -> review)* -> (test -> debug -> test)*
        -> flash (optional, plan only)

The pipeline never commits, pushes, publishes or touches a device. Everything it
learns is written into the run directory; the exit code is the only signal that
a caller has to trust.
"""

from __future__ import annotations

import pathlib
import shlex
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence

from . import verdict as verdicts
from .codex import (CodexNotFound, build_command, read_last_message,
                    resolve_binary, run_stage)
from .roles import DEFAULT_CATALOGUE, RoleError, load_catalogue
from .store import RunDirectory

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_USAGE = 2
EXIT_CODEX_MISSING = 3

MAX_STAGES = 24
REQUIRED_ROLES = ("research", "coding", "review")


@dataclass
class RunConfig:
    """Everything one run needs. Defaults are the boring, safe choices."""

    task_text: str
    workdir: pathlib.Path
    out_root: pathlib.Path = pathlib.Path("runs")
    codex_bin: Sequence[str] = ("codex",)
    catalogue_path: Optional[pathlib.Path] = None
    model: str = ""
    max_debug_rounds: int = 2
    allow_flash: bool = False
    dry_run: bool = False


class Pipeline:
    """Execute the roles in order and stop at the first gate that cannot pass."""

    def __init__(self, config: RunConfig):
        if config.max_debug_rounds < 0:
            raise ValueError("max_debug_rounds must be >= 0")
        self.config = config
        self.roles = load_catalogue(config.catalogue_path or DEFAULT_CATALOGUE)
        missing = [role for role in REQUIRED_ROLES if role not in self.roles]
        if missing:
            raise RoleError("role catalogue is missing: %s" % ", ".join(missing))
        self.prefix = list(config.codex_bin)
        self.run_dir: Optional[RunDirectory] = None

    # ------------------------------------------------------------------ run

    def run(self) -> int:
        workdir = pathlib.Path(self.config.workdir).resolve()
        if not workdir.is_dir():
            print("agentteam: workdir is not a directory: %s" % workdir)
            return EXIT_USAGE
        self.config.workdir = workdir

        if not self.config.dry_run:
            try:
                self.prefix = resolve_binary(self.config.codex_bin)
            except CodexNotFound as exc:
                print("agentteam: %s" % exc)
                return EXIT_CODEX_MISSING

        self.run_dir = RunDirectory(self.config.out_root, self.config.task_text)
        self.run_dir.write("task.md", self.config.task_text.strip() + "\n")
        print("agentteam: run %s" % self.run_dir.path)

        if self.config.dry_run:
            self._dry_run()
            return self._finish("pass", EXIT_OK, "dry run only")

        try:
            if not self._passed("research", "the plan is the input of everything else"):
                return self._finish("fail", EXIT_GATE_FAILED, "research stage did not pass")
            if not self._passed("coding", "there is nothing to review"):
                return self._finish("fail", EXIT_GATE_FAILED, "coding stage did not pass")

            stopped = self._gate_loop("review", "review gate")
            if stopped is not None:
                return stopped

            if "test" in self.roles:
                stopped = self._gate_loop("test", "test gate")
                if stopped is not None:
                    return stopped

            self._flash()
        except RuntimeError as exc:
            return self._finish("error", EXIT_GATE_FAILED, str(exc))

        return self._finish("pass", EXIT_OK)

    def _dry_run(self) -> None:
        """Walk the nominal sequence once, writing the argv, calling nothing."""
        sequence = ["research", "coding", "review"]
        if "test" in self.roles:
            sequence.append("test")
        for role_id in sequence:
            self._stage(role_id)
        self._flash()

    def _passed(self, role_id: str, why: str) -> bool:
        record = self._stage(role_id)
        if record["status"] == "pass":
            return True
        print("agentteam: %s did not pass (%s)" % (role_id, why))
        return False

    def _gate_loop(self, role_id: str, label: str) -> Optional[int]:
        """Run a gate, and let the debug stage have N attempts at it."""
        used = 0
        while True:
            gate = self._stage(role_id)
            if gate["status"] == "pass":
                return None
            if used >= self.config.max_debug_rounds:
                reason = gate["summary"] or gate["status"]
                return self._finish(
                    "fail", EXIT_GATE_FAILED,
                    "%s not satisfied after %d debug round(s): %s"
                    % (label, used, reason))
            used += 1
            self._stage("debug", note=self._failure_note(gate))

    def _flash(self) -> None:
        role = self.roles.get("flash")
        if role is None:
            return
        if not self.config.allow_flash:
            self.run_dir.record({
                "index": len(self.run_dir.stage_ids) + 1,
                "role": "flash",
                "name": role.name,
                "sandbox": role.sandbox,
                "gate": role.gate,
                "status": "skipped",
                "exit_code": None,
                "timed_out": False,
                "duration_seconds": 0.0,
                "verdict": "",
                "verdict_source": "",
                "summary": "requires --allow-flash",
                "findings": [],
                "dir": "",
            })
            print("[--] flash    skipped (needs --allow-flash)")
            return
        self._stage("flash")

    # ---------------------------------------------------------------- stage

    def _stage(self, role_id: str, note: str = "") -> dict:
        role = self.roles[role_id]
        assert self.run_dir is not None

        index = len(self.run_dir.stage_ids) + 1
        if index > MAX_STAGES:
            raise RuntimeError("stage budget exhausted (%d stages)" % MAX_STAGES)

        directory = self.run_dir.stage_dir(index, role_id)
        prompt = self._compose(role, note)
        _write(directory / "prompt.md", prompt)

        last_message = directory / "last-message.md"
        argv = build_command(self.prefix, role, self.config.workdir, last_message,
                             role.output_schema, self.config.model)
        _write(directory / "command.txt", " ".join(shlex.quote(arg) for arg in argv) + "\n")

        record = {
            "index": index,
            "role": role_id,
            "name": role.name,
            "sandbox": role.sandbox,
            "gate": role.gate,
            "status": "planned" if self.config.dry_run else "pending",
            "exit_code": None,
            "timed_out": False,
            "duration_seconds": 0.0,
            "verdict": "",
            "verdict_source": "",
            "summary": "",
            "findings": [],
            "dir": directory.name,
        }

        if self.config.dry_run:
            self.run_dir.record(record)
            print("[%02d] %-6s planned" % (index, role_id))
            return record

        before = _git_status(self.config.workdir)
        result = run_stage(argv, prompt, self.config.workdir, role.timeout_seconds)
        _write(directory / "events.jsonl", result.stdout)
        _write(directory / "stderr.log", result.stderr)

        message = read_last_message(last_message) or ""
        parsed = verdicts.parse((message + "\n" + result.stdout) if message else result.stdout)

        record.update({
            "exit_code": result.returncode,
            "timed_out": result.timed_out,
            "duration_seconds": round(result.duration_seconds, 2),
            "verdict": parsed["verdict"],
            "verdict_source": parsed["source"],
            "summary": verdicts.summary(parsed["payload"]),
            "findings": verdicts.findings(parsed["payload"]),
        })

        if result.timed_out:
            record["status"] = "timeout"
        elif result.returncode != 0:
            record["status"] = "error"
        elif role.gate and parsed["verdict"] != verdicts.PASS:
            record["status"] = "fail"
        elif role.gate and verdicts.blocking(parsed["payload"]):
            # A "pass" next to a blocker/major finding is not a pass.
            record["status"] = "fail"
        else:
            record["status"] = "pass"

        if role.read_only:
            after = _git_status(self.config.workdir)
            if before is not None and after is not None and before != after:
                record["status"] = "violation"
                note_text = "read-only role changed the workspace"
                record["summary"] = (record["summary"] + " " + note_text).strip()

        self.run_dir.record(record)
        print("[%02d] %-6s %-9s %5.1fs%s"
              % (index, role_id, record["status"], record["duration_seconds"],
                 "" if not record["summary"] else "  " + record["summary"][:80]))
        return record

    def _compose(self, role, note: str) -> str:
        assert self.run_dir is not None
        previous = self.run_dir.records
        context = ", ".join("%s=%s" % (item["role"], item["status"])
                            for item in previous) or "none"
        parts = [
            role.prompt().strip(),
            "",
            "## Agent role",
            role.id,
            "",
            "## Task",
            self.config.task_text.strip(),
            "",
            "## Run context",
            "- workdir: %s" % self.config.workdir,
            "- run: %s" % self.run_dir.path.name,
            "- previous stages: %s" % context,
            "- sandbox: %s (writes allowed: %s)"
            % (role.sandbox, "yes" if role.writes else "no"),
        ]
        if role.gate:
            parts += [
                "",
                "## Gate",
                "Your final message must be a JSON object matching `%s`. The "
                "orchestrator reads `verdict` from it and either continues or "
                "restarts the pipeline from that value." % role.output_schema.name,
            ]
        if role.requires_flag:
            parts += [
                "",
                "## Constraint",
                "This stage produces a plan only. Nothing may be executed.",
            ]
        if note.strip():
            parts += ["", "## Previous failure", note.strip()]
        return "\n".join(parts) + "\n"

    @staticmethod
    def _failure_note(record: dict) -> str:
        lines = [
            "The %s stage did not pass (status=%s, verdict=%s)."
            % (record["role"], record["status"], record["verdict"] or "n/a"),
        ]
        if record["summary"]:
            lines.append("Summary: %s" % record["summary"])
        detail = verdicts.describe({"findings": record["findings"]})
        if detail:
            lines += ["", detail]
        return "\n".join(lines)

    # ---------------------------------------------------------------- close

    def _finish(self, status: str, exit_code: int, error: str = "") -> int:
        assert self.run_dir is not None
        self.run_dir.finish(status, exit_code, error)
        print("")
        print("agentteam: %s (exit %d)" % (status, exit_code))
        if error:
            print("           %s" % error)
        print("           evidence: %s" % self.run_dir.manifest_path)
        return exit_code


def _write(path: pathlib.Path, text: str) -> None:
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text or "")


def _git_status(workdir) -> Optional[str]:
    """`git status --porcelain`, or None when workdir is not a git tree."""
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout
