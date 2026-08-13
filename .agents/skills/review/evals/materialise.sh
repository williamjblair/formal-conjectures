#!/usr/bin/env bash
# Materialise an eval case at its pinned commit.
#
# Each case reviews a file in this repository. The defect is only present at the
# commit the case pins. A run that reviews the working tree stops testing anything
# as soon as the fix merges, which is what killed the 940 case. Give every run a
# worktree from this script instead.
#
#   ./materialise.sh <case-id> <destination>
#
# Prints the destination on success. Remove the worktree with
#   git worktree remove <destination>

set -euo pipefail

case_id="${1:?usage: materialise.sh <case-id> <destination>}"
dest="${2:?usage: materialise.sh <case-id> <destination>}"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"
evals="$here/evals.json"

read -r pin pr < <(
  python3 - "$evals" "$case_id" <<'PY'
import json, sys
cases = json.load(open(sys.argv[1]))["evals"]
want = int(sys.argv[2])
for c in cases:
    if c["id"] == want:
        print(c["pinned_commit"], c.get("reviews_pull_request", ""))
        break
else:
    sys.exit(f"no case with id {want}")
PY
)

# A pull request head is not on any branch, so fetch it before the worktree add.
if [[ -n "$pr" ]]; then
  git -C "$repo" fetch -q origin "refs/pull/$pr/head"
fi

if ! git -C "$repo" cat-file -e "${pin}^{commit}" 2>/dev/null; then
  git -C "$repo" fetch -q origin
fi

git -C "$repo" worktree add --detach "$dest" "$pin" >/dev/null
echo "$dest"
