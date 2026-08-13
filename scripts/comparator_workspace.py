#!/usr/bin/env python3
"""Generate a comparator workspace from a Formal Conjectures statement.

This is a prototype. It follows the layout that `leanprover/lean-eval` generates, so that a
statement in this repository can be handed to `leanprover/comparator` as a trusted challenge.

    python scripts/comparator_workspace.py FormalConjectures/Paper/ClaudesCycles.lean \
        cube_hamiltonian_arc_decomposition

The workspace it writes:

    <out>/ChallengeDeps.lean   the definitions the statement needs, over Mathlib
    <out>/Challenge.lean       the trusted statement, with a `sorry`
    <out>/Submission.lean      what a solver fills in
    <out>/Solution.lean        discharges the challenge from the submission
    <out>/config.json          comparator's configuration
    <out>/holes.json           the lean-eval manifest for the generated hole
    <out>/lakefile.toml        pinned to this repository's Mathlib
    <out>/lean-toolchain       pinned to this repository's toolchain

Known limits, which are the point of the prototype:

  * The split into definitions and statement is textual. It takes the file up to the target
    declaration as the dependencies. A file whose later declarations the statement needs will
    not work.
  * It handles a problem file that imports only `FormalConjecturesUtil`. A file that imports
    `FormalConjecturesForMathlib` needs those modules vendored into `ChallengeDeps`.
  * It rejects a statement containing `answer(`. That elaborator is defined in this repository,
    so a Mathlib-only workspace cannot elaborate it. lean-eval models an unknown value as a
    `def` hole, which is the shape that would fit.
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Attributes that mean something only in this repository.
FC_ATTR = re.compile(
    r"@\[[^\]]*(?:category|AMS|formal_proof)[^\]]*\]\s*\n", re.MULTILINE | re.DOTALL
)

STANDARD_AXIOMS = ["propext", "Quot.sound", "Classical.choice"]


def pins():
    """This repository's toolchain and Mathlib revision, so the workspace matches our build."""
    toolchain = (ROOT / "lean-toolchain").read_text().strip()
    manifest = json.loads((ROOT / "lake-manifest.json").read_text())
    rev = next(p["rev"] for p in manifest["packages"] if p.get("name") == "mathlib")
    return toolchain, rev


def split_at_declaration(source, name):
    """Return the text before the declaration, and the declaration itself.

    Works on lines rather than on one regex. A regex with `DOTALL` will happily match a
    docstring that opened much earlier in the file, which puts the split in the wrong place.
    """
    lines = source.splitlines(keepends=True)
    head = re.compile(rf"^(theorem|lemma)\s+{re.escape(name)}\b")
    index = next((i for i, line in enumerate(lines) if head.match(line)), None)
    if index is None:
        sys.exit(f"no declaration named {name}")

    # Walk back over the attributes and the docstring that belong to this declaration. Both can
    # span several lines, so match on the closing token and then find the opening one.
    start = index
    while start > 0:
        previous = lines[start - 1].rstrip()
        if not previous:
            break
        if previous.endswith("]"):
            opening = start - 1
            while opening > 0 and not lines[opening].lstrip().startswith("@["):
                opening -= 1
            if not lines[opening].lstrip().startswith("@["):
                break
            start = opening
        elif previous.endswith("-/"):
            opening = start - 1
            while opening > 0 and not lines[opening].lstrip().startswith("/--"):
                opening -= 1
            start = opening
        else:
            break

    # The declaration ends at the next thing that starts at column zero.
    end = index + 1
    boundary = re.compile(r"^(/--|@\[|theorem |lemma |def |abbrev |noncomputable |end |namespace )")
    while end < len(lines) and not boundary.match(lines[end]):
        end += 1
    return "".join(lines[:start]), "".join(lines[start:end])


def namespace_of(source):
    match = re.search(r"^namespace\s+(\S+)", source, re.MULTILINE)
    return match.group(1) if match else None


def statement_of(declaration):
    """Drop the docstring, the attributes and the proof, leaving `theorem foo ... : T`."""
    body = FC_ATTR.sub("", declaration)
    body = re.sub(r"^/--.*?-/\n", "", body, flags=re.DOTALL | re.MULTILINE)
    body = re.sub(r":=\s*by\b.*\Z", "", body, flags=re.DOTALL)
    return body.rstrip().rstrip(":=").rstrip()


def generate(problem_file, name, out_dir):
    source = (ROOT / problem_file).read_text()

    if "FormalConjecturesForMathlib" in source:
        sys.exit("this file imports FormalConjecturesForMathlib; vendor those modules first")

    before, declaration = split_at_declaration(source, name)
    if "answer(" in declaration:
        sys.exit(f"{name} uses `answer(`, which needs a def hole; see the module docstring")

    namespace = namespace_of(source)
    if namespace is None:
        sys.exit("no namespace found in the problem file")

    # Dependencies: everything before the statement, over Mathlib rather than our own prelude.
    deps = FC_ATTR.sub("", before)
    deps = deps.replace("import FormalConjecturesUtil", "import Mathlib")
    deps = deps.rstrip() + f"\n\nend {namespace}\n"

    statement = statement_of(declaration)
    signature = re.sub(r"^(theorem|lemma)\s+\S+", r"\1 " + name.split(".")[-1], statement)

    out = ROOT / out_dir
    out.mkdir(parents=True, exist_ok=True)
    toolchain, rev = pins()

    (out / "ChallengeDeps.lean").write_text(deps)
    (out / "Challenge.lean").write_text(
        f"import ChallengeDeps\n\nopen {namespace}\n\n{signature} := by\n  sorry\n"
    )
    (out / "Submission.lean").write_text(
        f"import ChallengeDeps\n\nopen {namespace}\n\nnamespace Submission\n\n"
        f"{signature} := by\n  sorry\n\nend Submission\n"
    )
    (out / "Solution.lean").write_text(
        f"import ChallengeDeps\nimport Submission\n\nopen {namespace}\n\n"
        f"{signature} := by\n  exact Submission.{name.split('.')[-1]} ..\n"
    )
    (out / "config.json").write_text(json.dumps({
        "challenge_module": "Challenge",
        "solution_module": "Solution",
        "theorem_names": [name.split(".")[-1]],
        "permitted_axioms": STANDARD_AXIOMS,
        "enable_nanoda": False,
    }, indent=2) + "\n")
    (out / "holes.json").write_text(json.dumps({
        "id": name.split(".")[-1],
        "module": str(problem_file),
        "holes": [{
            "name": f"{namespace}.{name}",
            "basename": name.split(".")[-1],
            "kind": "theorem",
            "body": declaration.strip(),
        }],
    }, indent=2) + "\n")
    (out / "lakefile.toml").write_text(
        f'name = "{name.split(".")[-1]}"\n'
        'testDriver = "workspace_test"\n'
        'defaultTargets = ["Challenge", "Solution", "Submission"]\n\n'
        "[leanOptions]\nautoImplicit = false\n\n"
        "[[require]]\nname = \"mathlib\"\n"
        'git = "https://github.com/leanprover-community/mathlib4.git"\n'
        f'rev = "{rev}"\n\n'
        + "".join(f'[[lean_lib]]\nname = "{lib}"\n\n'
                 for lib in ("ChallengeDeps", "Challenge", "Solution", "Submission"))
    )
    (out / "lean-toolchain").write_text(toolchain + "\n")
    print(f"wrote {out.relative_to(ROOT)} for {namespace}.{name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("problem_file")
    parser.add_argument("declaration")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    out = args.out or f".comparator/{args.declaration.split('.')[-1]}"
    generate(args.problem_file, args.declaration, out)


if __name__ == "__main__":
    main()
