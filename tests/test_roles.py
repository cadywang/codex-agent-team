#!/usr/bin/env python3
"""The role catalogue is the contract between prompts and the orchestrator."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from agentteam.roles import RoleError, load_catalogue  # noqa: E402


class CatalogueTests(unittest.TestCase):
    def test_repository_catalogue_is_valid(self):
        roles = load_catalogue()
        self.assertEqual(
            sorted(roles),
            ["coding", "debug", "flash", "research", "review", "test"])
        self.assertTrue(roles["review"].gate)
        self.assertTrue(roles["test"].gate)
        self.assertFalse(roles["coding"].gate)
        self.assertEqual(roles["flash"].requires_flag, "allow-flash")
        self.assertTrue(roles["review"].read_only)
        self.assertTrue(roles["coding"].writes)

    def test_every_prompt_and_schema_exists(self):
        for role in load_catalogue().values():
            self.assertTrue(role.prompt_path.is_file(), role.id)
            self.assertTrue(role.prompt().strip(), role.id)
            if role.gate:
                self.assertIsNotNone(role.output_schema, role.id)
                self.assertTrue(role.output_schema.is_file(), role.id)

    def test_gate_roles_use_the_verdict_schema(self):
        roles = load_catalogue()
        for role_id in ("review", "test"):
            self.assertEqual(roles[role_id].output_schema.name, "verdict.schema.json")

    def test_duplicate_id_is_rejected(self):
        with self.assertRaises(RoleError):
            self._load([{"id": "review", "sandbox": "read-only", "writes": False,
                         "timeout_seconds": 5},
                        {"id": "review", "sandbox": "read-only", "writes": False,
                         "timeout_seconds": 5}])

    def test_unknown_sandbox_is_rejected(self):
        with self.assertRaises(RoleError):
            self._load([{"id": "review", "sandbox": "yolo", "writes": False,
                         "timeout_seconds": 5}])

    def test_writable_sandbox_contradiction_is_rejected(self):
        with self.assertRaises(RoleError):
            self._load([{"id": "review", "sandbox": "read-only", "writes": True,
                         "timeout_seconds": 5}])

    def test_missing_prompt_is_rejected(self):
        with self.assertRaises(RoleError):
            self._load([{"id": "review", "prompt": "nope.md", "sandbox": "read-only",
                         "writes": False, "timeout_seconds": 5}])

    def test_missing_schema_is_rejected(self):
        with self.assertRaises(RoleError):
            self._load([{"id": "review", "prompt": "review.md", "sandbox": "read-only",
                         "writes": False, "timeout_seconds": 5,
                         "output_schema": "nope.schema.json"}])

    def test_empty_catalogue_is_rejected(self):
        with self.assertRaises(RoleError):
            self._load([])

    def _load(self, roles):
        """Write a throwaway catalogue next to the real prompts."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp) / "agents"
            directory.mkdir()
            for name in ("review.md", "coding.md"):
                (directory / name).write_text("# Role\n", encoding="utf-8")
            catalogue = directory / "roles.json"
            catalogue.write_text(json.dumps({"version": 1, "roles": roles}),
                                 encoding="utf-8")
            return load_catalogue(catalogue)


if __name__ == "__main__":
    unittest.main(verbosity=2)
