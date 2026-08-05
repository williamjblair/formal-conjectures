#!/usr/bin/env python3
"""Report the category diagnostics that `extract_names` metadata implies.

`scripts/extract_names.lean` notices three things: a `research open` problem
with a sorry-free proof, and `test` or `API` statements without one. It writes
them to stderr as prose, but every field it decides them from is already in
`site/data/conjectures.json`, so this script classifies the JSON directly
rather than parsing warning text.

The three are not equally serious:

* A `research open` problem with a sorry-free proof is a contradiction in the
  repository and fails the build, whether or not it is new.
* A `test` or `API` statement without a proof is worth seeing but not worth
  blocking on. Adding the statement is better than not adding it, and someone
  else often supplies the proof shortly after.

To tell which advisory diagnostics a pull request introduces, each successful
push to `main` uploads the normalised snapshot written by `--snapshot`, and a
pull request compares against the snapshot for its base commit. When that
snapshot is missing (the base predates this, its run failed, the artifact
expired, or the runs raced) the comparison is skipped and totals are reported
instead. A missing baseline never fails the build; a `research open` problem
with a proof always does, since that is decided from this commit alone.

Usage:
  lake exe extract_names ... > site/data/conjectures.json
  python3 check_category_warnings.py site/data/conjectures.json \
      --snapshot category-diagnostics.json \
      --base-snapshot base/category-diagnostics.json \
      --base-sha "$BASE_SHA" --source-sha "$GITHUB_SHA"
"""

import argparse
import json
import os
import pathlib
import sys

SCHEMA_VERSION = 1

BLOCKING = "research_open_with_proof"

# In report order, with the sentence `extract_names` uses for each.
CODES = {
    "research_open_with_proof":
        "is categorised as `research open` but has a sorry-free proof",
    "test_without_proof":
        "is categorised as `test` but has no sorry-free proof",
    "api_without_proof":
        "is categorised as `API` but has no sorry-free proof",
}

REQUIRED_FIELDS = (
    ("theorem", str),
    ("module", str),
    ("category", str),
    ("hasSorryFreeProof", bool),
)


class DataError(Exception):
    """Input that cannot be classified, as opposed to a diagnostic finding."""


def diagnostic_for(problem):
    """The diagnostic code a problem earns, or `None`."""
    category = problem["category"]
    has_proof = problem["hasSorryFreeProof"]
    if category == "research open" and has_proof:
        return "research_open_with_proof"
    if category == "test" and not has_proof:
        return "test_without_proof"
    if category == "API" and not has_proof:
        return "api_without_proof"
    return None


def split_module(module):
    """The components of a Lean module name, with any `«...»` quoting removed.

    Splitting on `.` alone is wrong: `FormalConjectures.Arxiv.«1609.08688»`
    has three components, not four.
    """
    parts = []
    current = []
    depth = 0
    for ch in module:
        if ch == "«":
            depth += 1
        elif ch == "»":
            depth -= 1
        elif ch == "." and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def module_to_path(module):
    """The source file a module name came from, for workflow annotations."""
    return "/".join(split_module(module)) + ".lean"


def classify(problems, source):
    """The set of `(code, theorem, module)` triples the problems imply."""
    found = set()
    for index, problem in enumerate(problems):
        if not isinstance(problem, dict):
            raise DataError(f"{source}: entry {index} is not an object")
        for field, kind in REQUIRED_FIELDS:
            if field not in problem:
                raise DataError(f"{source}: entry {index} has no `{field}`")
            if not isinstance(problem[field], kind):
                raise DataError(
                    f"{source}: entry {index} has a `{field}` that is not "
                    f"{kind.__name__}")
        code = diagnostic_for(problem)
        if code:
            found.add((code, problem["theorem"], problem["module"]))
    return found


def read_json(path, source):
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise DataError(f"cannot read {source}: {error}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise DataError(f"{source} is not valid JSON: {error}")


def load_extraction(path):
    """Classify the `extract_names` output at `path`."""
    raw = read_json(path, path)
    if not isinstance(raw, dict):
        raise DataError(f"{path} is not a JSON object")
    problems = raw.get("problems")
    if not isinstance(problems, list):
        raise DataError(f"{path} has no `problems` list")
    return classify(problems, path)


def load_snapshot(path, expected_sha):
    """Read a snapshot written by `write_snapshot`.

    Returns the set of diagnostics. Raises `DataError` if the file is
    unreadable, malformed, or describes a commit other than `expected_sha`.
    """
    raw = read_json(path, path)
    if not isinstance(raw, dict):
        raise DataError(f"{path} is not a JSON object")
    version = raw.get("schemaVersion")
    if version != SCHEMA_VERSION:
        raise DataError(
            f"{path} has schemaVersion {version!r}, expected {SCHEMA_VERSION}")
    if expected_sha and raw.get("sourceSha") != expected_sha:
        raise DataError(
            f"{path} describes {raw.get('sourceSha')!r}, not {expected_sha!r}")
    entries = raw.get("diagnostics")
    if not isinstance(entries, list):
        raise DataError(f"{path} has no `diagnostics` list")
    found = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise DataError(f"{path}: diagnostic {index} is not an object")
        for field in ("code", "theorem", "module"):
            if not isinstance(entry.get(field), str):
                raise DataError(
                    f"{path}: diagnostic {index} has no string `{field}`")
        if entry["code"] not in CODES:
            raise DataError(
                f"{path}: diagnostic {index} has unknown code "
                f"{entry['code']!r}")
        found.add((entry["code"], entry["theorem"], entry["module"]))
    return found


def write_snapshot(path, source_sha, found):
    """Write `found` in a form `load_snapshot` can read, in a fixed order."""
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "sourceSha": source_sha,
        "diagnostics": [
            {"code": code, "theorem": theorem, "module": module}
            for code, theorem, module in sorted(found)
        ],
    }
    pathlib.Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def annotate(level, code, theorem, module):
    """A workflow annotation, which GitHub attaches to the file it names."""
    print(f"::{level} file={module_to_path(module)},title={code}::"
          f"{theorem} {CODES[code]}")


def summarise(lines):
    """Append to the workflow run summary, or to stdout when run by hand."""
    text = "\n".join(lines) + "\n"
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        print(text, end="")
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)


def report(head, base, unavailable):
    """The run summary.

    Totals always, the delta when `base` is a snapshot to compare with, and a
    note when one was wanted but could not be had.
    """
    lines = ["### Category diagnostics", ""]
    if base is None:
        if unavailable:
            lines += [f"Comparison against the base commit is unavailable: "
                      f"{unavailable}. Totals for this commit only.", ""]
        lines.append("| Diagnostic | Total |")
        lines.append("| --- | ---: |")
        for code in CODES:
            total = sum(1 for d in head if d[0] == code)
            lines.append(f"| `{code}` | {total} |")
        lines.append("")
        return lines

    new = head - base
    resolved = base - head
    lines.append("| Diagnostic | New | Resolved | Total |")
    lines.append("| --- | ---: | ---: | ---: |")
    for code in CODES:
        lines.append(
            f"| `{code}` | {sum(1 for d in new if d[0] == code)} "
            f"| {sum(1 for d in resolved if d[0] == code)} "
            f"| {sum(1 for d in head if d[0] == code)} |")
    lines.append("")
    for title, group in (("New in this change", new),
                         ("Resolved in this change", resolved)):
        if group:
            lines.append(f"#### {title}")
            lines.append("")
            for code, theorem, module in sorted(group):
                lines.append(f"- `{code}`: `{theorem}` in "
                             f"`{module_to_path(module)}`")
            lines.append("")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("extraction",
                        help="the JSON written by `lake exe extract_names`")
    parser.add_argument("--snapshot",
                        help="where to write this commit's snapshot")
    parser.add_argument("--base-snapshot",
                        help="a snapshot of the base commit to compare with")
    parser.add_argument("--base-sha", default="",
                        help="the commit `--base-snapshot` must describe")
    parser.add_argument("--source-sha", default="",
                        help="the commit `--snapshot` describes")
    args = parser.parse_args(argv)

    try:
        head = load_extraction(args.extraction)
    except DataError as error:
        print(f"::error::{error}")
        return 2

    if args.snapshot:
        write_snapshot(args.snapshot, args.source_sha, head)

    # `base` stays `None` unless there is a snapshot to compare against, so
    # that a missing one is never mistaken for an empty one.
    base = None
    unavailable = None
    if args.base_snapshot:
        if not pathlib.Path(args.base_snapshot).exists():
            unavailable = (f"no snapshot was found for base commit "
                           f"{args.base_sha[:7] or '(unknown)'}")
        else:
            try:
                base = load_snapshot(args.base_snapshot, args.base_sha)
            except DataError as error:
                # The comparison is a convenience. Say loudly that it did not
                # happen, but do not fail a change over it.
                print(f"::warning::unusable base snapshot: {error}")
                unavailable = "the base snapshot could not be read"

    summarise(report(head, base, unavailable))

    blocking = sorted(d for d in head if d[0] == BLOCKING)
    for code, theorem, module in blocking:
        annotate("error", code, theorem, module)
    if base is not None:
        for code, theorem, module in sorted(head - base):
            if code != BLOCKING:
                annotate("warning", code, theorem, module)

    for code in CODES:
        print(f"{code}: {sum(1 for d in head if d[0] == code)}")

    if blocking:
        print("\nA problem categorised as `research open` should not have a "
              "sorry-free proof. Either the proof settles it, in which case "
              "the category should be `research solved`, or the proof is of "
              "something weaker than the statement.")
        for _, theorem, _ in blocking:
            print(f"  {theorem}")
        summarise(["", f"**Failing**: {len(blocking)} `research open` "
                       "problem(s) with a sorry-free proof."])
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
