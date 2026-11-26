#!/usr/bin/env python3
"""End-to-end pipeline tests against the fake codex CLI: no model, no network."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from agentteam.pipeline import (EXIT_CODEX_MISSING, EXIT_GATE_FAILED,  # noqa: E402
                                EXIT_OK, Pipeline, RunConfig)

FAKE = str(ROOT / "tests" / "fake_codex.py")

# Every fake_codex switch, explicitly cleared: os.environ is inherited by the
# fake, so a value left behind by an earlier test would silently change a later
# one.
CLEAN = {
    "FAKE_CODEX_MODE": "",
    "FAKE_CODEX_FAIL_ROLES": "",
    "FAKE_CODEX_FAIL_ONCE": "",
    "FAKE_CODEX_WRITE_ROLE": "",
}


def make_workdir(root: pathlib.Path) -> pathlib.Path:
    workdir = root / "target"
    workdir.mkdir()
    (workdir / "sample.py").write_text("print('hi')\n", encoding="utf-8")
    git = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com"]
    subprocess.run(["git", "init", "-q"], cwd=str(workdir), check=True)
    subprocess.run(git + ["add", "-A"], cwd=str(workdir), check=True)
    subprocess.run(git + ["commit", "-q", "-m", "init"], cwd=str(workdir), check=True)
    return workdir


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.workdir = make_workdir(self.root)
        self.out = self.root / "runs"

    def tearDown(self):
        self.tmp.cleanup()

    def run_pipeline(self, env=None, **overrides):
        config = dict(
            task_text="# Fake task\n\nmake the gate pass",
            workdir=self.workdir,
            out_root=self.out,
            codex_bin=[sys.executable, FAKE],
        )
        config.update(overrides)
        merged = dict(CLEAN)
        merged.update(env or {})
        captured = io.StringIO()
        with mock.patch.dict(os.environ, merged, clear=False):
            with contextlib.redirect_stdout(captured):
                code = Pipeline(RunConfig(**config)).run()
        return code, captured.getvalue()

    def manifest(self):
        runs = list(self.out.iterdir())
        self.assertEqual(len(runs), 1, "expected exactly one run directory")
        path = runs[0] / "manifest.json"
        return json.loads(path.read_text(encoding="utf-8")), runs[0]

    @staticmethod
    def roles(manifest):
        return [stage["role"] for stage in manifest["stages"]]

    # ------------------------------------------------------------ happy path

    def test_happy_path_runs_every_stage_and_passes(self):
        code, output = self.run_pipeline()
        self.assertEqual(code, EXIT_OK, output)

        manifest, run = self.manifest()
        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["exit_code"], 0)
        self.assertEqual(self.roles(manifest),
                         ["research", "coding", "review", "test", "flash"])
        self.assertEqual(manifest["stages"][-1]["status"], "skipped")

        stage = run / "03-review"
        for name in ("prompt.md", "command.txt", "last-message.md", "events.jsonl"):
            self.assertTrue((stage / name).is_file(), name)
        command = (stage / "command.txt").read_text(encoding="utf-8")
        self.assertIn("--sandbox read-only", command)
        # codex runs with --cd <workdir>, so every path it is given must be
        # absolute or it will write somewhere else than this harness reads.
        # Read it the way a shell would: shlex.quote leaves a plain POSIX
        # path unquoted, so splitting on a quote character only worked on
        # Windows, where the path always contains a backslash.
        argv = shlex.split(command)
        for argument in ("-o", "--output-schema"):
            value = argv[argv.index(argument) + 1]
            self.assertTrue(os.path.isabs(value), "%s %s" % (argument, value))
        self.assertTrue((run / "task.md").is_file())

    def test_coding_stage_gets_the_workspace_write_sandbox(self):
        self.run_pipeline()
        _, run = self.manifest()
        command = (run / "02-coding" / "command.txt").read_text(encoding="utf-8")
        self.assertIn("--sandbox workspace-write", command)

    def test_gate_verdict_is_recorded_with_its_source(self):
        self.run_pipeline()
        manifest, _ = self.manifest()
        review = next(s for s in manifest["stages"] if s["role"] == "review")
        self.assertEqual(review["verdict"], "pass")
        self.assertEqual(review["verdict_source"], "json")
        self.assertEqual(review["status"], "pass")

    # ---------------------------------------------------------- debug rounds

    def test_failed_review_is_sent_to_debug_and_can_recover(self):
        code, output = self.run_pipeline({"FAKE_CODEX_FAIL_ONCE": "review"})
        self.assertEqual(code, EXIT_OK, output)
        manifest, _ = self.manifest()
        self.assertEqual(self.roles(manifest),
                         ["research", "coding", "review", "debug", "review",
                          "test", "flash"])

    def test_debug_prompt_carries_the_findings(self):
        self.run_pipeline({"FAKE_CODEX_FAIL_ONCE": "review"})
        _, run = self.manifest()
        debug = next(path for path in run.iterdir() if path.name.endswith("-debug"))
        prompt = (debug / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("## Previous failure", prompt)
        self.assertIn("the fake gate failed on purpose", prompt)
        self.assertIn("sample.py:7", prompt)

    def test_exhausted_review_budget_fails_the_run(self):
        code, _ = self.run_pipeline({"FAKE_CODEX_FAIL_ROLES": "review"},
                                    max_debug_rounds=1)
        self.assertEqual(code, EXIT_GATE_FAILED)
        manifest, _ = self.manifest()
        self.assertEqual(manifest["status"], "fail")
        self.assertIn("review gate", manifest["error"])
        self.assertEqual(self.roles(manifest),
                         ["research", "coding", "review", "debug", "review"])

    def test_failed_test_gate_is_sent_to_debug(self):
        code, output = self.run_pipeline({"FAKE_CODEX_FAIL_ONCE": "test"})
        self.assertEqual(code, EXIT_OK, output)
        manifest, _ = self.manifest()
        self.assertEqual(self.roles(manifest),
                         ["research", "coding", "review", "test", "debug",
                          "test", "flash"])

    def test_zero_debug_rounds_still_allows_a_clean_run(self):
        code, _ = self.run_pipeline(max_debug_rounds=0)
        self.assertEqual(code, EXIT_OK)

    # --------------------------------------------------------------- safety

    def test_read_only_role_editing_the_workspace_is_a_violation(self):
        code, _ = self.run_pipeline({"FAKE_CODEX_WRITE_ROLE": "review"})
        self.assertEqual(code, EXIT_GATE_FAILED)
        manifest, _ = self.manifest()
        statuses = [s["status"] for s in manifest["stages"] if s["role"] == "review"]
        self.assertIn("violation", statuses)

    def test_flash_is_skipped_without_the_flag(self):
        self.run_pipeline()
        manifest, _ = self.manifest()
        flash = next(s for s in manifest["stages"] if s["role"] == "flash")
        self.assertEqual(flash["status"], "skipped")
        self.assertIn("--allow-flash", flash["summary"])

    def test_flash_runs_as_a_plan_when_allowed(self):
        code, _ = self.run_pipeline(allow_flash=True)
        self.assertEqual(code, EXIT_OK)
        manifest, run = self.manifest()
        flash = manifest["stages"][-1]
        self.assertEqual(flash["role"], "flash")
        self.assertEqual(flash["status"], "pass")
        message = (run / "05-flash" / "last-message.md").read_text(encoding="utf-8")
        self.assertEqual(json.loads(message)["device"], "<board>")
        self.assertIn("--sandbox read-only",
                      (run / "05-flash" / "command.txt").read_text(encoding="utf-8"))

    # ------------------------------------------------------------ failure modes

    def test_crashing_agent_stops_before_the_next_stage(self):
        code, _ = self.run_pipeline({"FAKE_CODEX_MODE": "crash"})
        self.assertEqual(code, EXIT_GATE_FAILED)
        manifest, _ = self.manifest()
        self.assertEqual(self.roles(manifest), ["research"])
        self.assertEqual(manifest["stages"][0]["status"], "error")

    def test_missing_codex_binary_is_a_distinct_exit_code(self):
        code, output = self.run_pipeline(codex_bin=["definitely-not-a-real-codex-binary"])
        self.assertEqual(code, EXIT_CODEX_MISSING, output)

    def test_dry_run_needs_no_binary_and_calls_nothing(self):
        code, output = self.run_pipeline(codex_bin=["this-binary-does-not-exist"],
                                        dry_run=True)
        self.assertEqual(code, EXIT_OK, output)
        manifest, run = self.manifest()
        self.assertEqual(manifest["status"], "pass")
        statuses = [s["status"] for s in manifest["stages"]]
        self.assertEqual(statuses, ["planned", "planned", "planned", "planned", "skipped"])
        self.assertEqual(list(run.rglob("last-message.md")), [])
        self.assertTrue((run / "01-research" / "command.txt").is_file())

    def test_bad_workdir_is_a_usage_error(self):
        code, _ = self.run_pipeline(workdir=self.root / "does-not-exist")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
