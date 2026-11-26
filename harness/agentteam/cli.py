"""Command line entry point: ``python -m agentteam <command>``."""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import List, Optional

from .pipeline import (EXIT_USAGE, Pipeline, RunConfig)
from .roles import DEFAULT_CATALOGUE, RoleError, load_catalogue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentteam",
        description="Run the Codex agent team over a target repository.",
    )
    commands = parser.add_subparsers(dest="command")

    roles = commands.add_parser("roles", help="print the role catalogue")
    roles.add_argument("--catalogue", default="",
                       help="path to roles.json (default: agents/roles.json)")
    roles.add_argument("--json", action="store_true", help="machine-readable output")

    run = commands.add_parser("run", help="run the pipeline")
    run.add_argument("--task", default="", help="file holding the task description")
    run.add_argument("--task-text", default="", help="task description as a string")
    run.add_argument("--repo", required=True, help="target repository to work in")
    run.add_argument("--out", default="runs", help="where run evidence is written")
    run.add_argument("--codex", default="codex",
                     help="codex binary, or a .py entrypoint (used by the self-tests)")
    run.add_argument("--catalogue", default="", help="path to roles.json")
    run.add_argument("--model", default="", help="model passed to codex exec")
    run.add_argument("--max-debug-rounds", type=int, default=2,
                     help="debug attempts per gate (default: 2)")
    run.add_argument("--allow-flash", action="store_true",
                     help="enable the flash stage; it still only produces a plan")
    run.add_argument("--dry-run", action="store_true",
                     help="print the orchestration without calling codex")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return EXIT_USAGE

    catalogue = pathlib.Path(args.catalogue) if args.catalogue else DEFAULT_CATALOGUE

    if args.command == "roles":
        return _list_roles(catalogue, args.json)

    task_text = _task_text(args)
    if task_text is None:
        print("agentteam: pass exactly one of --task or --task-text", file=sys.stderr)
        return EXIT_USAGE

    if args.max_debug_rounds < 0:
        print("agentteam: --max-debug-rounds must be >= 0", file=sys.stderr)
        return EXIT_USAGE

    config = RunConfig(
        task_text=task_text,
        workdir=pathlib.Path(args.repo),
        out_root=pathlib.Path(args.out),
        codex_bin=_codex_argv(args.codex),
        catalogue_path=catalogue,
        model=args.model,
        max_debug_rounds=args.max_debug_rounds,
        allow_flash=bool(args.allow_flash),
        dry_run=bool(args.dry_run),
    )
    try:
        pipeline = Pipeline(config)
    except (RoleError, ValueError) as exc:
        print("agentteam: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    return pipeline.run()


def _task_text(args) -> Optional[str]:
    if bool(args.task) == bool(args.task_text.strip()):
        return None
    if args.task:
        path = pathlib.Path(args.task)
        if not path.is_file():
            print("agentteam: task file not found: %s" % path, file=sys.stderr)
            return None
        return path.read_text(encoding="utf-8")
    return args.task_text.strip()


def _codex_argv(codex: str) -> List[str]:
    if codex.lower().endswith(".py"):
        # The self-tests inject a Python stand-in; run it with this interpreter
        # so it works on Windows, where a .py file is not executable by itself.
        return [sys.executable, codex]
    return [codex]


def _list_roles(catalogue, as_json: bool) -> int:
    try:
        roles = load_catalogue(catalogue)
    except RoleError as exc:
        print("agentteam: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    if as_json:
        import json
        payload = [
            {
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "sandbox": role.sandbox,
                "writes": role.writes,
                "gate": role.gate,
                "timeout_seconds": role.timeout_seconds,
                "requires_flag": role.requires_flag,
            }
            for role in roles.values()
        ]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("%-9s %-5s %-6s %-16s %s"
          % ("id", "gate", "writes", "sandbox", "description"))
    for role in roles.values():
        print("%-9s %-5s %-6s %-16s %s"
              % (role.id, "yes" if role.gate else "-", "yes" if role.writes else "no",
                 role.sandbox, role.description))
    return 0
