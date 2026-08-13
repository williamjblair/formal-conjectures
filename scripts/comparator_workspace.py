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
  * The statement may use definitions from `FormalConjecturesForMathlib`. Every problem file has
    those in scope, because `FormalConjecturesUtil` re-exports the whole library, so the source
    text does not say whether a statement needs them. Pass `--check` to compile the generated
    workspace against Mathlib alone and find out.
  * An `answer(...)` becomes a `def` hole, which is how comparator models an unknown value. The
    type comes from the source: `answer(sorry : T)` states it, and `answer(...) ↔ P` makes it
    `Prop`. Any other shape needs the elaborator, and the script says so rather than guess.
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile

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


def head_revision():
    """The commit of this repository, so a workspace that needs our library can pin it.

    The commit must be reachable from the remote, or the workspace builds only on this machine.
    """
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    pushed = subprocess.run(["git", "branch", "-r", "--contains", revision],
                            cwd=ROOT, capture_output=True, text=True)
    if not pushed.stdout.strip():
        print(f"WARNING: {revision[:12]} is not on any remote branch. The generated workspace "
              f"pins it, so it will not build elsewhere until you push.", file=sys.stderr)
    return revision


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


def find_answer(statement):
    """Locate `answer(...)` and return its span and its contents, matching parentheses.

    A regex cannot do this, because the contents frequently contain parentheses.
    """
    start = statement.find("answer(")
    if start < 0:
        return None
    i = start + len("answer(")
    depth = 1
    while i < len(statement) and depth:
        if statement[i] == "(":
            depth += 1
        elif statement[i] == ")":
            depth -= 1
        i += 1
    if depth:
        sys.exit("unbalanced parentheses in `answer(`")
    return start, i, statement[start + len("answer("):i - 1]


def answer_type(statement, span):
    """The type of the answer, inferred from the source.

    Two shapes cover almost all of the repository:

      * `answer(sorry : T)` states the type outright
      * `answer(...) ↔ P` makes the answer a `Prop`

    Anything else needs the elaborator, so report it rather than guess.
    """
    start, end, contents = span
    depth = 0
    for index, char in enumerate(contents):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == ":" and depth == 0 and contents[index:index + 2] != ":=":
            return contents[index + 1:].strip()
    if statement[end:].lstrip().startswith("↔"):
        return "Prop"
    sys.exit(
        "cannot infer the type of the answer. Write it as `answer(sorry : T)`, or extend this "
        "script to elaborate the statement."
    )


def generate(problem_file, name, out_dir, with_library=False):
    source = (ROOT / problem_file).read_text()

    before, declaration = split_at_declaration(source, name)
    namespace = namespace_of(source)
    if namespace is None:
        sys.exit("no namespace found in the problem file")

    # Dependencies: everything before the statement, over Mathlib rather than our own prelude.
    deps = FC_ATTR.sub("", before)
    # `FormalConjecturesForMathlib` re-exports Mathlib, so it is the wider of the two imports.
    prelude = "import FormalConjecturesForMathlib" if with_library else "import Mathlib"
    deps = deps.replace("import FormalConjecturesUtil", prelude)
    deps = deps.rstrip() + f"\n\nend {namespace}\n"

    statement = statement_of(declaration)
    basename = name.split(".")[-1]
    signature = re.sub(r"^(theorem|lemma)\s+\S+", r"\1 " + basename, statement)

    # An `answer(...)` marks the unknown part of the problem. comparator models an unknown value
    # as a `def` hole listed in `definition_names`, so split the statement into the two holes.
    span = find_answer(signature)
    if span is None:
        answer_def = None
    else:
        start, end, _ = span
        answer_name = f"{basename}_answer"
        answer_def = (answer_name, answer_type(signature, span))
        signature = signature[:start] + answer_name + signature[end:]

    out = ROOT / out_dir
    out.mkdir(parents=True, exist_ok=True)
    toolchain, rev = pins()

    challenge_def = solution_def = submission_def = ""
    if answer_def:
        answer_name, answer_ty = answer_def
        challenge_def = f"noncomputable def {answer_name} : {answer_ty} := sorry\n\n"
        submission_def = f"noncomputable def {answer_name} : {answer_ty} := sorry\n\n"
        solution_def = (f"@[reducible] noncomputable def {answer_name} : {answer_ty} := "
                        f"Submission.{answer_name}\n\n")

    (out / "ChallengeDeps.lean").write_text(deps)
    (out / "Challenge.lean").write_text(
        f"import ChallengeDeps\n\nopen {namespace}\n\n{challenge_def}{signature} := by\n  sorry\n"
    )
    (out / "Submission.lean").write_text(
        f"import ChallengeDeps\n\nopen {namespace}\n\nnamespace Submission\n\n"
        f"{submission_def}{signature} := by\n  sorry\n\nend Submission\n"
    )
    (out / "Solution.lean").write_text(
        f"import ChallengeDeps\nimport Submission\n\nopen {namespace}\n\n"
        f"{solution_def}{signature} :=\n  Submission.{basename}\n"
    )
    config = {
        "challenge_module": "Challenge",
        "solution_module": "Solution",
        "theorem_names": [basename],
        "permitted_axioms": STANDARD_AXIOMS,
        "enable_nanoda": False,
    }
    if answer_def:
        config["definition_names"] = [answer_def[0]]
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n")

    holes = []
    if answer_def:
        holes.append({
            "name": f"{namespace}.{answer_def[0]}",
            "basename": answer_def[0],
            "kind": "def",
            "body": f"noncomputable def {answer_def[0]} : {answer_def[1]} := sorry",
        })
    holes.append({
        "name": f"{namespace}.{name}",
        "basename": basename,
        "kind": "theorem",
        "body": declaration.strip(),
    })
    (out / "holes.json").write_text(json.dumps({
        "id": basename,
        "module": str(problem_file),
        "holes": holes,
    }, indent=2) + "\n")
    requires = ("[[require]]\nname = \"mathlib\"\n"
                'git = "https://github.com/leanprover-community/mathlib4.git"\n'
                f'rev = "{rev}"\n\n')
    if with_library:
        # The statement uses definitions from `FormalConjecturesForMathlib`, which this
        # repository exposes as a `lean_lib`. Requiring it beats copying those definitions in.
        requires += ("[[require]]\nname = \"formal_conjectures\"\n"
                     'git = "https://github.com/google-deepmind/formal-conjectures.git"\n'
                     f'rev = "{head_revision()}"\n\n')
    (out / "lakefile.toml").write_text(
        f'name = "{basename}"\n'
        'testDriver = "workspace_test"\n'
        'defaultTargets = ["Challenge", "Solution", "Submission"]\n\n'
        "[leanOptions]\nautoImplicit = false\n\n"
        + requires
        + "".join(f'[[lean_lib]]\nname = "{lib}"\n\n'
                 for lib in ("ChallengeDeps", "Challenge", "Solution", "Submission"))
    )
    (out / "lean-toolchain").write_text(toolchain + "\n")
    print(f"wrote {out.relative_to(ROOT)} for {namespace}.{name}")


def check(out_dir, quiet=False):
    """Compile the generated challenge.

    A statement that needs `FormalConjecturesForMathlib` fails when the workspace has only
    Mathlib. The source text cannot tell you which it is, because every problem file imports
    the whole library through `FormalConjecturesUtil`.
    """
    out = ROOT / out_dir
    body = (out / "ChallengeDeps.lean").read_text()
    body += "\n" + re.sub(r"^import .*\n", "", (out / "Challenge.lean").read_text(), flags=re.M)
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False) as handle:
        handle.write(body)
        path = handle.name
    result = subprocess.run(["lake", "env", "lean", path], cwd=ROOT,
                            capture_output=True, text=True)
    errors = [line for line in (result.stdout + result.stderr).splitlines()
              if "error" in line.lower()]
    if errors:
        if not quiet:
            print(f"FAIL {out_dir}")
            for line in errors[:6]:
                print("  " + line.split(":", 3)[-1].strip()[:110])
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("problem_file")
    parser.add_argument("declaration")
    parser.add_argument("--out", default=None)
    parser.add_argument("--check", action="store_true",
                        help="compile the generated challenge against Mathlib alone")
    args = parser.parse_args()
    out = args.out or f".comparator/{args.declaration.split('.')[-1]}"
    generate(args.problem_file, args.declaration, out)
    if not args.check:
        return

    # Prefer a workspace that needs only Mathlib. Fall back to requiring this repository's
    # library, which is what a statement using `FormalConjecturesForMathlib` needs.
    if check(out, quiet=True):
        print(f"OK   {out}: the challenge builds over Mathlib alone")
        return
    generate(args.problem_file, args.declaration, out, with_library=True)
    if check(out):
        print(f"OK   {out}: the challenge needs FormalConjecturesForMathlib, which it requires")
        return
    sys.exit(1)


if __name__ == "__main__":
    main()
