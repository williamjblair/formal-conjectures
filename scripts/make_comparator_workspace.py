#!/usr/bin/env python3
"""Generate a comparator workspace for one problem statement.

`leanprover/lean-eval` verifies a submission by building it against a Challenge
module whose statement the maintainers trust, under a config that pins the
permitted axioms. The `.comparator/dean_conjecture` workspace in this repository
was written by hand to that shape; this script generates the same shape from any
problem file, so every trusted statement can have one.

Layout produced, matching the hand-made prototype:

  <out>/<id>/
    lakefile.toml       pins: this checkout's Mathlib rev and FC commit
    ChallengeDeps.lean  the problem file's docstring, imports and supporting
                        definitions, with research statements removed
    Challenge.lean      the target statement, attributes stripped, proof
                        replaced by `sorry`, and each `answer(sorry)` hoisted
                        into a definition hole the solver must fill
    Solution.lean       a stub the solver replaces
    config.json         theorem and definition names, permitted axioms
    holes.json          the extracted blocks, for tooling and for review

`answer(sorry)` handling follows the mechanism's own semantics: a slot flanking
an `↔` is a `Prop`; any other slot's type cannot be read off the surface syntax,
so it must be supplied with `--answer-type`, and the script refuses to guess.

Usage:
  python make_comparator_workspace.py DECLARATION [--out DIR] [--answer-type T]

The workspace's own build needs a network fetch of its pinned dependencies, so
this script does not attempt it; generation is offline and the build belongs to
the comparator run.
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_DIRS = [ROOT / "FormalConjectures"]

LICENSE_HEADER = """/-
Copyright 2026 The Formal Conjectures Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-/
"""

PERMITTED_AXIOMS = ["propext", "Quot.sound", "Classical.choice"]

DECL_START = re.compile(
    r"^(?:noncomputable\s+)?(?:private\s+)?"
    r"(theorem|lemma|def|abbrev|structure|inductive|instance|notation)\s",
)
KEEP_LOOSE = re.compile(r"^(open|variable|universe|section|namespace|end|attribute)\b")


class Block:
    """One top-level chunk: docstring + attributes + declaration, or a loose line."""

    def __init__(self, lines):
        self.lines = lines
        self.text = "\n".join(lines)
        self.kind = None
        self.name = None
        for line in lines:
            if KEEP_LOOSE.match(line):
                self.kind = line.split()[0]
                break
            m = DECL_START.match(line)
            if m:
                self.kind = m.group(1)
                after = line[m.end():].strip()
                nm = re.match(r"([\w.«»]+)", after)
                self.name = nm.group(1) if nm else None
                break

    @property
    def category(self):
        m = re.search(r"@\[category\s+([\w ]+?)[,\]]", self.text)
        return m.group(1).strip() if m else None


def split_blocks(body):
    """Group a file body into blocks separated by blank lines at top level.

    Docstrings and attribute lines have no blank line before their declaration
    in this repository's style, so they stay attached to it. A blank line
    *inside* a doc comment is part of the comment, not a separator, so comment
    depth is tracked across lines; Lean block comments nest.
    """
    blocks, current, depth = [], [], 0
    for line in body.split("\n"):
        if line.strip() == "" and current and depth == 0:
            blocks.append(Block(current))
            current = []
            continue
        if line.strip() != "" or current:
            current.append(line)
        depth += len(re.findall(r"/-", line)) - len(re.findall(r"-/", line))
        depth = max(depth, 0)
    if current:
        blocks.append(Block(current))
    return blocks


def find_declaration(basename):
    """Locate the file declaring `basename`. Returns (path, module_docstring, body)."""
    pattern = re.compile(rf"^(?:theorem|lemma|def)\s.*\b{re.escape(basename)}\b",
                         re.MULTILINE)
    hits = []
    for src in SOURCE_DIRS:
        for path in sorted(src.rglob("*.lean")):
            text = path.read_text(encoding="utf-8")
            if re.search(rf"(?:theorem|lemma)\s+(?:[\w.«»]*\.)?{re.escape(basename)}[\s:]",
                         text):
                hits.append(path)
    if not hits:
        raise SystemExit(f"no declaration named {basename!r} found under FormalConjectures/")
    if len(hits) > 1:
        raise SystemExit(f"{basename!r} is ambiguous: " + ", ".join(str(h) for h in hits))
    path = hits[0]
    text = path.read_text(encoding="utf-8")
    # Drop the license header; keep the module docstring; the rest is the body.
    text = re.sub(r"\A/-.*?-/\s*", "", text, flags=re.DOTALL)
    doc = ""
    m = re.match(r"\s*(/-!.*?-/)\s*", text, flags=re.DOTALL)
    if m:
        doc = m.group(1)
        text = text[m.end():]
    # Imports precede the docstring in source order; recover them from the original.
    imports = re.findall(r"^import\s+(\S+)", path.read_text(encoding="utf-8"),
                         re.MULTILINE)
    return path, imports, doc, text


def strip_decorations(block_text):
    """Remove the docstring and attribute list from a declaration block."""
    block_text = re.sub(r"\A\s*/--.*?-/\s*", "", block_text, flags=re.DOTALL)
    return re.sub(r"\A\s*@\[[^\]]*\]\s*", "", block_text, flags=re.DOTALL)


def replace_proof_with_sorry(text):
    """Cut the proof body after `:=`, keeping the statement."""
    m = re.search(r":=\s*by\b", text)
    if m:
        return text[: m.start()].rstrip() + " := by\n  sorry"
    m = re.search(r":=", text)
    if m:
        return text[: m.start()].rstrip() + " := by\n  sorry"
    return text.rstrip() + " := by\n  sorry"


def hoist_answers(statement, basename, answer_type):
    """Replace each `answer(sorry)` with a named definition hole.

    Returns (statement, [hole definition lines]). A slot flanking `↔` is a
    `Prop`; anything else needs `--answer-type`, because the surface syntax
    does not carry the type and guessing it would corrupt the challenge.
    """
    holes = []
    count = statement.count("answer(sorry)")
    if count == 0:
        return statement, holes
    for i in range(count):
        hole = f"{basename}_answer" if count == 1 else f"{basename}_answer_{i + 1}"
        idx = statement.index("answer(sorry)")
        window = statement[max(0, idx - 8): idx + 24]
        is_iff = "↔" in window
        if is_iff:
            hole_type = "Prop"
        elif answer_type:
            hole_type = answer_type
        else:
            raise SystemExit(
                "answer(sorry) is not flanking an ↔, so its type cannot be read "
                "from the statement; pass --answer-type")
        holes.append(f"noncomputable def {hole} : {hole_type} := sorry")
        statement = statement.replace("answer(sorry)", hole, 1)
    return statement, holes


def pins(source_path=None):
    """Revisions the workspace's own build can actually fetch.

    The FC pin must be reachable from the upstream repository the lakefile
    names, so it is the merge-base with `origin/main`, not HEAD: a local
    branch commit would generate a workspace whose build fails at fetch time.
    When the source file differs from that merge-base, the workspace would
    restate a statement upstream does not carry, and the generator warns.
    """
    manifest = json.loads((ROOT / "lake-manifest.json").read_text())
    mathlib_rev = next(p["rev"] for p in manifest["packages"] if p["name"] == "mathlib")
    fc_rev = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "HEAD", "origin/main"],
        capture_output=True, text=True).stdout.strip()
    if source_path is not None:
        differs = subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--quiet", fc_rev, "--",
             str(source_path)]).returncode != 0
        if differs:
            print(f"WARNING: {source_path} differs from the pinned FC revision "
                  f"{fc_rev[:12]}; the workspace restates a version upstream "
                  f"does not carry", file=sys.stderr)
    return mathlib_rev, fc_rev


def lakefile(workspace_id, mathlib_rev, fc_rev):
    return f"""name = "{workspace_id}"
testDriver = "workspace_test"
defaultTargets = ["Challenge", "Solution", "Submission"]

[leanOptions]
autoImplicit = false

[[require]]
name = "mathlib"
git = "https://github.com/leanprover-community/mathlib4.git"
rev = "{mathlib_rev}"

[[require]]
name = "formal_conjectures"
git = "https://github.com/google-deepmind/formal-conjectures.git"
rev = "{fc_rev}"

[[lean_lib]]
name = "ChallengeDeps"

[[lean_lib]]
name = "Challenge"

[[lean_lib]]
name = "Solution"

[[lean_lib]]
name = "Submission"
"""


def generate(basename, out_dir, answer_type):
    path, imports, module_doc, body = find_declaration(basename)
    blocks = split_blocks(body)

    target = None
    deps, namespaces, opens = [], [], []
    for b in blocks:
        if b.name and b.name.rsplit(".", 1)[-1] == basename:
            target = b
            continue
        if b.kind == "namespace":
            namespaces.append(b.lines[0].split(None, 1)[1])
            continue
        if b.kind == "end":
            continue
        if b.kind == "open":
            opens.append(b.text)
            continue
        if b.kind in ("theorem", "lemma"):
            # Another statement in the file. Research statements are separate
            # problems and their sorries must not enter the challenge; test and
            # API lemmas are usually sorried scaffolding here. Proved supporting
            # lemmas do get carried, since a statement may genuinely use them.
            if b.category in ("research open", "research solved") or "sorry" in b.text:
                continue
            deps.append(b.text)
            continue
        if b.kind in ("def", "abbrev", "structure", "inductive", "instance",
                      "notation", "variable", "universe", "attribute", "section"):
            deps.append(b.text)

    if target is None:
        raise SystemExit(f"{basename!r} not found as a block in {path}")

    statement = strip_decorations(target.text)
    statement = replace_proof_with_sorry(statement)
    statement, holes = hoist_answers(statement, basename, answer_type)

    ns_open = f"open {' '.join(dict.fromkeys(namespaces))}\n" if namespaces else ""
    ns_wrap_open = "".join(f"namespace {n}\n" for n in dict.fromkeys(namespaces))
    ns_wrap_close = "".join(f"end {n}\n" for n in reversed(list(dict.fromkeys(namespaces))))

    # ChallengeDeps: imports mapped off the problem-attribute machinery, which
    # the challenge must not depend on. FormalConjecturesForMathlib carries the
    # repository's supporting definitions without the attributes.
    dep_imports = sorted({
        "FormalConjecturesForMathlib" if imp.startswith(("FormalConjecturesUtil",
                                                         "FormalConjectures.Util"))
        else imp
        for imp in imports
    }) or ["FormalConjecturesForMathlib"]

    deps_body = "\n\n".join(deps)
    challenge_deps = (
        LICENSE_HEADER + "\n"
        + "\n".join(f"import {i}" for i in dep_imports) + "\n\n"
        + (module_doc + "\n\n" if module_doc else "")
        + "\n".join(opens) + ("\n\n" if opens else "")
        + ns_wrap_open
        + (deps_body + "\n" if deps_body else "")
        + ns_wrap_close
    )

    challenge = (
        "import ChallengeDeps\n\n"
        + (ns_open + "\n" if ns_open else "")
        + "\n\n".join(holes) + ("\n\n" if holes else "")
        + statement + "\n"
    )

    solution = (
        "import Challenge\n\n"
        "/- Replace this file with a proof of the Challenge statement. The\n"
        "comparator builds it under config.json's permitted axioms; `sorry`\n"
        "does not pass. -/\n"
    )

    mathlib_rev, fc_rev = pins(path.relative_to(ROOT))
    full_names = [f"{'.'.join(dict.fromkeys(namespaces))}.{basename}"
                  if namespaces else basename]
    hole_names = [h.split()[2] for h in holes]

    ws = pathlib.Path(out_dir) / basename
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "lakefile.toml").write_text(lakefile(basename, mathlib_rev, fc_rev))
    (ws / "ChallengeDeps.lean").write_text(challenge_deps)
    (ws / "Challenge.lean").write_text(challenge)
    (ws / "Solution.lean").write_text(solution)
    (ws / "config.json").write_text(json.dumps({
        "challenge_module": "Challenge",
        "solution_module": "Solution",
        "theorem_names": [basename],
        "permitted_axioms": PERMITTED_AXIOMS,
        "enable_nanoda": False,
        "definition_names": hole_names,
    }, indent=2) + "\n")
    (ws / "holes.json").write_text(json.dumps({
        "id": basename,
        "module": str(path.relative_to(ROOT)),
        "holes": [
            {"name": n, "basename": n.rsplit(".", 1)[-1], "kind": "def",
             "body": h}
            for n, h in zip(
                [f"{'.'.join(dict.fromkeys(namespaces))}.{hn}" if namespaces else hn
                 for hn in hole_names], holes)
        ] + [
            {"name": full_names[0], "basename": basename, "kind": "theorem",
             "body": target.text}
        ],
    }, indent=2, ensure_ascii=False) + "\n")
    return ws


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("declaration", help="basename, e.g. dean_conjecture or erdos_940")
    ap.add_argument("--out", default=str(ROOT / ".comparator"))
    ap.add_argument("--answer-type", default=None,
                    help="type of a non-Prop answer(sorry) slot")
    args = ap.parse_args(argv)
    ws = generate(args.declaration, args.out, args.answer_type)
    print(ws)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
