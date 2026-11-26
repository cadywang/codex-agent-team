"""One folder per run, plus the manifest that indexes it.

`runs/` is git-ignored: evidence belongs to one concrete execution, not to the
repository. Keeping the layout boring and predictable is what makes a failure
reviewable after the fact ("who said what, in which round, on which command").
"""

from __future__ import annotations

import io
import json
import pathlib
import re
from datetime import datetime, timezone
from typing import List, Optional

_SLUG = re.compile(r"[^a-z0-9]+")


class RunDirectory:
    """The directory tree for one pipeline run."""

    def __init__(self, out_root, task_text: str, now: Optional[datetime] = None):
        stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        # Absolute: the stage argv is handed to a subprocess that runs with a
        # different cwd, and `codex exec -o <relative>` would then land
        # somewhere else than where this harness reads it back.
        root = pathlib.Path(out_root).resolve()
        self.path = root / ("%s-%s" % (stamp, slug(task_text)))
        self.path.mkdir(parents=True, exist_ok=False)
        self.stage_ids: List[str] = []
        self.records: List[dict] = []

    def write(self, relative: str, text: str) -> pathlib.Path:
        """Write ``text`` as UTF-8 with LF endings, creating parents."""
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with io.open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return target

    def stage_dir(self, index: int, role_id: str) -> pathlib.Path:
        """Create (and remember) the directory for stage ``index``."""
        directory = self.path / ("%02d-%s" % (index, role_id))
        directory.mkdir(parents=True, exist_ok=False)
        self.stage_ids.append(role_id)
        return directory

    def record(self, entry: dict) -> None:
        self.records.append(entry)
        self._dump("running", 0, "")

    def finish(self, status: str, exit_code: int, error: str = "") -> None:
        self._dump(status, exit_code, error)

    @property
    def manifest_path(self) -> pathlib.Path:
        return self.path / "manifest.json"

    def _dump(self, status: str, exit_code: int, error: str) -> None:
        manifest = {
            "run": self.path.name,
            "status": status,
            "exit_code": exit_code,
            "error": error,
            "stages": self.records,
        }
        self.write("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def slug(text: str, limit: int = 40) -> str:
    """A filesystem-safe slug from the first meaningful line of the task."""
    for line in (text or "").splitlines():
        candidate = line.strip().lstrip("#").strip()
        if not candidate:
            continue
        value = _SLUG.sub("-", candidate.lower()).strip("-")
        if value:
            return value[:limit].strip("-")
    return "task"
