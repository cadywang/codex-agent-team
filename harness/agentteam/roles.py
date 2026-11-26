"""Role catalogue: ``agents/roles.json`` plus one prompt file per role.

Loading is strict and happens before a run starts. A missing prompt, a
duplicate id, an unknown sandbox or an unreachable schema would otherwise only
surface halfway through a pipeline, after the expensive stages have run.
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")
READ_ONLY = "read-only"

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CATALOGUE = REPO_ROOT / "agents" / "roles.json"

ROLE_ID = re.compile(r"^[a-z][a-z0-9-]*$")


class RoleError(ValueError):
    """The role catalogue is inconsistent, so a run must not start."""


@dataclass(frozen=True)
class Role:
    """One agent role, as declared in ``agents/roles.json``."""

    id: str
    name: str
    description: str
    sandbox: str
    writes: bool
    gate: bool
    timeout_seconds: int
    prompt_path: pathlib.Path
    output_schema: Optional[pathlib.Path] = None
    requires_flag: str = ""
    extra_args: Tuple[str, ...] = ()

    @property
    def read_only(self) -> bool:
        return self.sandbox == READ_ONLY

    def prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8")


def load_catalogue(path=None) -> Dict[str, Role]:
    """Load and validate the catalogue, keyed by role id."""
    catalogue = pathlib.Path(path) if path else DEFAULT_CATALOGUE
    if not catalogue.is_file():
        raise RoleError("role catalogue not found: %s" % catalogue)
    try:
        data = json.loads(catalogue.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise RoleError("role catalogue is not valid JSON: %s" % exc)
    if not isinstance(data, dict):
        raise RoleError("role catalogue must be a JSON object: %s" % catalogue)

    entries = data.get("roles")
    if not isinstance(entries, list) or not entries:
        raise RoleError("role catalogue has no roles: %s" % catalogue)

    root = catalogue.resolve().parent
    roles: Dict[str, Role] = {}
    for entry in entries:
        role = _build_role(entry, root)
        if role.id in roles:
            raise RoleError("duplicate role id: %s" % role.id)
        roles[role.id] = role
    return roles


def _build_role(entry, catalogue_dir: pathlib.Path) -> Role:
    if not isinstance(entry, dict):
        raise RoleError("every entry in roles[] must be an object")

    role_id = str(entry.get("id", "")).strip()
    if not ROLE_ID.match(role_id):
        raise RoleError("invalid role id %r (want [a-z][a-z0-9-]*)" % role_id)

    sandbox = str(entry.get("sandbox", ""))
    if sandbox not in SANDBOX_MODES:
        raise RoleError("%s: unknown sandbox %r (want one of %s)"
                        % (role_id, sandbox, ", ".join(SANDBOX_MODES)))

    writes = entry.get("writes")
    if not isinstance(writes, bool):
        raise RoleError("%s: 'writes' must be true or false" % role_id)
    if writes and sandbox == READ_ONLY:
        raise RoleError("%s: writes=true needs a writable sandbox, not read-only" % role_id)

    gate = entry.get("gate", False)
    if not isinstance(gate, bool):
        raise RoleError("%s: 'gate' must be true or false" % role_id)

    timeout = entry.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        raise RoleError("%s: 'timeout_seconds' must be a positive integer" % role_id)

    prompt_name = entry.get("prompt") or ("%s.md" % role_id)
    prompt_path = _resolve(catalogue_dir, str(prompt_name),
                           (catalogue_dir,))
    if prompt_path is None:
        raise RoleError("%s: prompt file not found: %s" % (role_id, prompt_name))

    schema_path = None
    schema_name = entry.get("output_schema")
    if schema_name:
        schema_path = _resolve(catalogue_dir, str(schema_name),
                               (catalogue_dir,
                                catalogue_dir.parent,
                                catalogue_dir.parent / "harness" / "schemas"))
        if schema_path is None:
            raise RoleError("%s: output schema not found: %s" % (role_id, schema_name))

    requires_flag = entry.get("requires_flag", "")
    if requires_flag is not None and not isinstance(requires_flag, str):
        raise RoleError("%s: 'requires_flag' must be a string" % role_id)

    extra = entry.get("extra_args", [])
    if not isinstance(extra, list) or any(not isinstance(a, str) for a in extra):
        raise RoleError("%s: 'extra_args' must be an array of strings" % role_id)

    return Role(
        id=role_id,
        name=str(entry.get("name") or role_id),
        description=str(entry.get("description") or ""),
        sandbox=sandbox,
        writes=writes,
        gate=gate,
        timeout_seconds=timeout,
        prompt_path=prompt_path,
        output_schema=schema_path,
        requires_flag=requires_flag or "",
        extra_args=tuple(extra),
    )


def _resolve(base: pathlib.Path, name: str, search) -> Optional[pathlib.Path]:
    """Resolve ``name`` against the given roots, or return None."""
    candidate = pathlib.Path(name)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    for root in search:
        path = (root / candidate)
        if path.is_file():
            return path.resolve()
    return (base / candidate).resolve() if (base / candidate).is_file() else None
