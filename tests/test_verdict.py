#!/usr/bin/env python3
"""One place decides what a verdict means; these are its rules."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from agentteam import verdict  # noqa: E402


class ParseTests(unittest.TestCase):
    def test_plain_json(self):
        parsed = verdict.parse('{"verdict": "pass", "summary": "ok"}')
        self.assertEqual(parsed["verdict"], "pass")
        self.assertEqual(parsed["source"], "json")

    def test_json_inside_prose_or_fence(self):
        text = 'Here you go:\n```json\n{"verdict": "fail", "summary": "no"}\n```\n'
        parsed = verdict.parse(text)
        self.assertEqual(parsed["verdict"], "fail")
        self.assertEqual(parsed["source"], "json")

    def test_marker_fallback(self):
        parsed = verdict.parse("some prose\n\nVERDICT: PASS\n")
        self.assertEqual(parsed["verdict"], "pass")
        self.assertEqual(parsed["source"], "marker")

    def test_review_marker_is_accepted(self):
        self.assertEqual(verdict.parse("REVIEW_VERDICT: FAIL")["verdict"], "fail")

    def test_unparseable_is_unknown(self):
        parsed = verdict.parse("I think this is probably fine?")
        self.assertEqual(parsed["verdict"], "unknown")
        self.assertEqual(parsed["source"], "none")

    def test_empty_message_is_unknown(self):
        self.assertEqual(verdict.parse(None)["verdict"], "unknown")

    def test_json_without_verdict_does_not_win(self):
        parsed = verdict.parse('{"findings": []}\nVERDICT: FAIL')
        self.assertEqual(parsed["verdict"], "fail")
        self.assertEqual(parsed["source"], "marker")

    def test_first_verdict_wins(self):
        text = '{"verdict": "fail"}\n{"verdict": "pass"}'
        self.assertEqual(verdict.parse(text)["verdict"], "fail")


class FindingTests(unittest.TestCase):
    payload = {
        "verdict": "fail",
        "summary": "two problems",
        "findings": [
            {"severity": "nit", "file": "a.py", "line": 1, "issue": "taste",
             "suggestion": "ignore"},
            {"severity": "blocker", "file": "b.py", "line": 9, "issue": "corrupts data",
             "suggestion": None},
        ],
    }

    def test_findings_are_sorted_worst_first(self):
        items = verdict.findings(self.payload)
        self.assertEqual(items[0]["severity"], "blocker")
        self.assertEqual(items[1]["severity"], "nit")

    def test_blocking_means_blocker_or_major(self):
        self.assertTrue(verdict.blocking(self.payload))
        self.assertFalse(verdict.blocking({"findings": [
            {"severity": "minor", "file": "a", "line": None, "issue": "x"}]}))

    def test_describe_mentions_location_and_issue(self):
        text = verdict.describe(self.payload)
        self.assertIn("b.py:9", text)
        self.assertIn("corrupts data", text)

    def test_summary_falls_back_to_goal(self):
        self.assertEqual(verdict.summary({"goal": "ship it"}), "ship it")
        self.assertEqual(verdict.summary(None), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
