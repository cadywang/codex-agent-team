#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  dev-setup.sh -- configure a clone for contributing.
#
#  Turns on the conventions this repository is maintained with:
#    * core.hooksPath     -> tools/git-hooks validates every commit message
#    * prepare-commit-msg -> appends Signed-off-by: (DCO) when it is missing
#  then runs the checker over the current history as a smoke test.
#
#  Usage:  bash tools/dev-setup.sh
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "dev-setup: not inside a git work tree" >&2
    exit 1
fi

git config format.signOff true
git config core.hooksPath tools/git-hooks
chmod +x tools/git-hooks/commit-msg tools/git-hooks/prepare-commit-msg 2>/dev/null || true

echo "core.hooksPath  = $(git config --get core.hooksPath)"
echo "hooks           = commit-msg, prepare-commit-msg"

PY="$(command -v python3 || command -v python || true)"
if [ -n "$PY" ]; then
    "$PY" tools/check-commits.py --all | tail -n 3
else
    echo "dev-setup: python not found, skipping the history smoke test"
fi
echo "dev-setup: done"
