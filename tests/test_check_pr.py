#!/usr/bin/env python3
"""Self-test for tools/check-pr.py (title style + merge checklist)."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check-pr.py"
TEMPLATE = ROOT / ".github" / "pull_request_template.md"

GOOD_TITLE = "harness: add the debug gate"


def ticked_body() -> str:
    """The template with every checkbox ticked, i.e. what a good PR looks like."""
    return TEMPLATE.read_text(encoding="utf-8").replace("- [ ]", "- [x]")


class PullRequestGateTests(unittest.TestCase):
    def check(self, title: str, body: str, author: str = "cadywang"):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "pr.md"
            path.write_text(body, encoding="utf-8")
            argv = [sys.executable, str(CHECKER), "--title", title,
                    "--body-file", str(path), "--author", author]
            return subprocess.run(argv, cwd=str(ROOT), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace")

    def test_complete_pull_request_passes(self):
        result = self.check(GOOD_TITLE, ticked_body())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unticked_checklist_blocks_the_merge(self):
        body = ticked_body().replace("- [x] 已更新 `CHANGELOG.md`（如面向用户的行为有变化）",
                                     "- [ ] 已更新 `CHANGELOG.md`（如面向用户的行为有变化）")
        result = self.check(GOOD_TITLE, body)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unticked", result.stdout)

    def test_empty_body_blocks_the_merge(self):
        result = self.check(GOOD_TITLE, "")
        self.assertEqual(result.returncode, 1)
        self.assertIn("body is empty", result.stdout)

    def test_title_must_follow_the_kernel_style(self):
        for bad in ("Add the debug gate", "harness: Added the debug gate",
                    "harness: add the debug gate.", "feat: add the debug gate"):
            result = self.check(bad, ticked_body())
            self.assertEqual(result.returncode, 1, bad)
            self.assertIn("title", result.stdout, bad)

    def test_bot_pull_requests_are_skipped(self):
        result = self.check("ci: bump actions/checkout from 4 to 5", "", author="dependabot[bot]")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_template_itself_has_a_checklist(self):
        result = self.check(GOOD_TITLE, ticked_body())
        self.assertIn("checklist items look fine", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
