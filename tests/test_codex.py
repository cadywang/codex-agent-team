#!/usr/bin/env python3
"""The command line handed to ``codex exec`` is a contract; pin it."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from agentteam.codex import (CodexNotFound, build_command, read_last_message,  # noqa: E402
                             resolve_binary, run_stage)
from agentteam.roles import load_catalogue  # noqa: E402


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.roles = load_catalogue()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_gate_role_command(self):
        role = self.roles["review"]
        argv = build_command(["codex"], role, self.dir, self.dir / "last.md")
        self.assertEqual(argv[0], "codex")
        self.assertEqual(argv[1], "exec")
        self.assertIn("--cd", argv)
        self.assertEqual(argv[argv.index("--cd") + 1], str(self.dir))
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertEqual(argv[argv.index("-o") + 1], str(self.dir / "last.md"))
        self.assertEqual(argv[-1], "-")
        schema = argv[argv.index("--output-schema") + 1]
        self.assertTrue(schema.endswith("verdict.schema.json"))
        self.assertIn("--skip-git-repo-check", argv)
        self.assertIn("never", argv[argv.index("--color") + 1])

    def test_writable_role_gets_workspace_write(self):
        argv = build_command(["codex"], self.roles["coding"], self.dir, self.dir / "l.md")
        self.assertEqual(argv[argv.index("--sandbox") + 1], "workspace-write")
        self.assertNotIn("--output-schema", argv)

    def test_model_override(self):
        argv = build_command(["codex"], self.roles["coding"], self.dir,
                             self.dir / "l.md", model="gpt-5-codex")
        self.assertEqual(argv[argv.index("--model") + 1], "gpt-5-codex")

    def test_prompt_never_goes_on_the_command_line(self):
        argv = build_command(["codex"], self.roles["coding"], self.dir, self.dir / "l.md")
        self.assertEqual(argv[-1], "-")
        self.assertFalse(any("write a file" in arg for arg in argv))

    def test_missing_binary_is_reported(self):
        with self.assertRaises(CodexNotFound):
            resolve_binary(["definitely-not-a-real-codex-binary"])

    def test_resolve_keeps_extra_arguments(self):
        argv = resolve_binary([sys.executable, "-c", "print(1)"])
        self.assertEqual(argv[0], sys.executable)
        self.assertEqual(argv[1:], ["-c", "print(1)"])


class RunTests(unittest.TestCase):
    def test_prompt_is_piped_through_stdin(self):
        argv = [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"]
        with tempfile.TemporaryDirectory() as tmp:
            result = run_stage(argv, "hello", tmp, timeout=30)
        self.assertTrue(result.ok, result.stderr)
        self.assertEqual(result.stdout, "HELLO")

    def test_timeout_is_a_result_not_an_exception(self):
        argv = [sys.executable, "-c", "import time; time.sleep(5)"]
        with tempfile.TemporaryDirectory() as tmp:
            result = run_stage(argv, "", tmp, timeout=1)
        self.assertFalse(result.ok)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, -1)

    def test_missing_last_message_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_last_message(pathlib.Path(tmp) / "absent.md"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
