#!/usr/bin/env python3
"""Self-test for tools/check-commits.py (the kernel-style commit gate).

Uses the ``--commit-msg-file`` mode, so no commit is created and the test runs
identically on every platform.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check-commits.py"

SIGNOFF = "Signed-off-by: cadywang <cadywang@users.noreply.github.com>"


class CommitMessageTests(unittest.TestCase):
    def check(self, message: str, strict_dco: bool = True):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "COMMIT_EDITMSG"
            path.write_text(message, encoding="utf-8")
            argv = [sys.executable, str(CHECKER), "--commit-msg-file", str(path)]
            if strict_dco:
                argv.append("--strict-dco")
            return subprocess.run(argv, cwd=str(ROOT), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace")

    def assert_ok(self, message: str):
        result = self.check(message)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_rejected(self, message: str, expected: str):
        result = self.check(message)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(expected, result.stdout + result.stderr)

    # ----------------------------------------------------------- accepted

    def test_good_message(self):
        self.assert_ok(
            "harness: add the debug gate\n"
            "\n"
            "A failing review used to end the run. Now the debug stage gets a\n"
            "bounded number of attempts before the pipeline gives up.\n"
            "\n" + SIGNOFF + "\n")

    def test_fixes_tag_is_accepted(self):
        self.assert_ok(
            "harness: keep the verdict source\n"
            "\n"
            "Fixes: 0d75a9b (\"harness: drop the verdict source\")\n"
            + SIGNOFF + "\n")

    def test_merge_commit_is_skipped(self):
        self.assert_ok("Merge branch 'main' into harness/debug-gate\n")

    def test_revert_is_skipped(self):
        self.assert_ok('Revert "harness: add the debug gate"\n')

    # ----------------------------------------------------------- rejected

    def test_conventional_tag_is_rejected(self):
        self.assert_rejected("feat: add the debug gate\n\n" + SIGNOFF + "\n",
                             "conventional-commit")

    def test_missing_subsystem_is_rejected(self):
        self.assert_rejected("add the debug gate\n\n" + SIGNOFF + "\n",
                             'subject must start with "<subsystem>: "')

    def test_trailing_period_is_rejected(self):
        self.assert_rejected("harness: add the debug gate.\n\n" + SIGNOFF + "\n",
                             "must not end with a period")

    def test_past_tense_is_rejected(self):
        self.assert_rejected("harness: added the debug gate\n\n" + SIGNOFF + "\n",
                             "imperative")

    def test_long_subject_is_rejected(self):
        subject = "harness: " + "x" * 70
        self.assert_rejected(subject + "\n\n" + SIGNOFF + "\n", "max 72")

    def test_missing_signoff_is_rejected(self):
        self.assert_rejected("harness: add the debug gate\n", "Signed-off-by")

    def test_signoff_must_match_the_author(self):
        self.assert_rejected(
            "harness: add the debug gate\n\n"
            "Signed-off-by: someone else <else@example.com>\n",
            "must match the author")

    def test_long_body_line_is_rejected(self):
        self.assert_rejected(
            "harness: add the debug gate\n\n" + ("y" * 90) + "\n\n" + SIGNOFF + "\n",
            "wrap it")

    def test_malformed_fixes_tag_is_rejected(self):
        self.assert_rejected(
            "harness: keep the verdict source\n\nFixes: 0d75a9b\n\n" + SIGNOFF + "\n",
            "malformed Fixes")



class GitHookTests(unittest.TestCase):
    """The hooks are the local half of the same rules."""

    def run_git(self, repo, *args):
        return subprocess.run(["git"] + list(args), cwd=str(repo), capture_output=True,
                              text=True, encoding="utf-8", errors="replace")

    def make_repo(self, tmp):
        repo = pathlib.Path(tmp)
        self.run_git(repo, "init", "-q", "-b", "main")
        self.run_git(repo, "config", "user.name", "cadywang")
        self.run_git(repo, "config", "user.email",
                     "cadywang@users.noreply.github.com")
        self.run_git(repo, "config", "core.hooksPath",
                     str(ROOT / "tools" / "git-hooks"))
        (repo / "a.txt").write_text("x\n", encoding="utf-8")
        self.run_git(repo, "add", "-A")
        return repo

    def commit(self, repo, message):
        path = repo / "msg.txt"
        path.write_text(message, encoding="utf-8")
        return self.run_git(repo, "commit", "-F", str(path))

    def test_prepare_commit_msg_adds_the_trailer(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            result = self.commit(repo, "tools: add the hook\n\nBody text.\n")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            body = self.run_git(repo, "log", "-1", "--format=%B").stdout
            self.assertIn("Signed-off-by: cadywang <cadywang@users.noreply.github.com>", body)

    def test_commit_msg_hook_rejects_a_bad_subject(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            result = self.commit(repo, "Added the hook\n\nBody text.\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("commit message does not follow", result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main(verbosity=2)
