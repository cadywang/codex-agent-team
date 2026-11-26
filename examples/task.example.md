# Add a `--dry-run` flag to the sample CLI

Sample task for `python -m agentteam run --task examples/task.example.md --repo <target>`.
It is written against the toy project the harness is usually demonstrated on; point
`--repo` at any checkout that has a small CLI with tests.

## Context

`tools/samplecli.py` writes output files directly. Running it by accident
overwrites fixtures, which has bitten us twice during review.

## What to do

1. Add `--dry-run` to the CLI: parse arguments, resolve every path, and print
   what would be written instead of writing it.
2. Keep the default behaviour unchanged.
3. Add a test that proves the dry run touches no files.

## Acceptance

- `python -m pytest tests/` passes.
- `python tools/samplecli.py --dry-run` prints a plan and creates no files.
- No new third-party dependency.
