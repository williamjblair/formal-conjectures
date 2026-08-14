#!/usr/bin/env python3
"""Generate a comparator workspace for one problem statement.

`leanprover/lean-eval` verifies a submission by building it against a Challenge
module whose statement the maintainers trust, under a config that pins the
permitted axioms. This script generates that shape from any problem file in
this repository.

Challenge.lean imports the problem's own module. lean-eval's generated
Challenge is one `import Mathlib` and one statement, because its problems are
authored self-contained; this repository's are not, so the import here is the
problem's module and the statement's context comes with it. Only what Lean
scopes to a file has to be copied: `open`, `variable`, `universe`,
`set_option` and `local notation`.

Layout produced:

  <out>/<id>/
    lakefile.toml       pins: this checkout's Mathlib rev and FC commit
    Challenge.lean      the import, the file-scoped preamble, the target
                        statement with attributes stripped and its proof
                        replaced by `sorry`, and each `answer(sorry)` hoisted
                        into a definition hole the solver must fill
    Solution.lean       a stub the solver replaces
    config.json         theorem and definition names, permitted axioms
    holes.json          the extracted blocks, for tooling and for review

`answer(sorry)` handling follows the mechanism's own semantics: a slot flanking
an `↔` is a `Prop`; any other slot's type cannot be read off the surface syntax,
so it must be supplied, and the script refuses to guess.

Two things the source cannot settle live in `comparator/problems/<id>.toml`,
one file per problem: that answer type, and which file is meant when two
declare the same name. See that directory's README.

Usage:
  python make_comparator_workspace.py (ID | DECLARATION) [--out DIR]
      [--answer-type T] [--module FILE]
  python make_comparator_workspace.py --validate

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
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_DIRS = [ROOT / "FormalConjectures"]
MANIFEST_DIR = ROOT / "comparator" / "problems"

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
    # `local notation` and `scoped notation` carry the modifier before the
    # keyword. Without them here, Erdos 125's `local notation "A" => ...` typed
    # as nothing and was dropped, and its statements lost the sets they name.
    r"^(?:noncomputable\s+|private\s+|protected\s+|local\s+|scoped\s+)*"
    r"(theorem|lemma|def|abbrev|structure|inductive|instance|notation)\s",
)
KEEP_LOOSE = re.compile(
    r"^(open|variable|universe|section|namespace|end|attribute|set_option)\b")
# A doc comment at column zero documents whatever follows it, so it always
# starts a declaration. A declaration body is indented and cannot begin one.
DOC_START = re.compile(r"^/-[-!]")

# Lean scopes these to the file that writes them, so importing the problem's
# module does not bring them along and Challenge.lean has to restate them.
# Erdos 940's statement needs `atTop`, and Erdos 125's needs the `A` and `B`
# its two `local notation` lines define.
FILE_SCOPED = ("open", "variable", "universe", "set_option", "notation")


class Block:
    """One top-level chunk: docstring + attributes + declaration, or a loose line."""

    def __init__(self, lines):
        self.lines = lines
        self.text = "\n".join(lines)
        self.kind = None
        self.name = None
        # The line the kind came from, which is not always `lines[0]`: a `/-!`
        # section docstring can sit above a `namespace` inside one block, and
        # reading the name off `lines[0]` then crashes.
        self.kind_line = None
        # Prose inside a doc comment is not Lean. A docstring whose line begins
        # `end ...` or `open ...` at column zero would otherwise type the whole
        # block as that directive, and a block typed `end` used to be dropped
        # with the declaration it documented.
        depth = 0
        for line in lines:
            if depth == 0:
                # `open X in` modifies the declaration below it and is not a
                # directive in its own right. Typing the block `open` swept
                # Koethe's whole research statement, `@[category]` and all,
                # into Challenge.lean as if it were preamble.
                if KEEP_LOOSE.match(line) and not line.rstrip().endswith(" in"):
                    self.kind = line.split()[0]
                    self.kind_line = line
                    break
                m = DECL_START.match(line)
                if m:
                    self.kind = m.group(1)
                    after = line[m.end():].strip()
                    nm = re.match(r"([\w.«»]+)", after)
                    self.name = nm.group(1) if nm else None
                    break
            depth += len(re.findall(r"/-", line)) - len(re.findall(r"-/", line))
            depth = max(depth, 0)

    @property
    def category(self):
        m = re.search(r"@\[category\s+([\w ]+?)[,\]]", self.text)
        return m.group(1).strip() if m else None


def peel_loose(lines):
    """Split leading single-line directives off a block.

    This repository writes `namespace Erdos269` directly above the first
    declaration, with no blank line between them, so grouping on blank lines
    puts both into one block. Reading one kind per block then kept the
    namespace and dropped the declaration, and dropped it silently: Erdos 41
    lost `variable {α : Type}` and Erdos 269 lost `HasPrimeFactorsIn`. Both
    workspaces generated, and both failed only when Lean elaborated them.

    A trailing `end X` is peeled for the same reason: the namespace stack is
    read off these lines, and an `end` hidden inside a declaration's block
    would leave the stack too deep. `KEEP_LOOSE` anchors at column zero, so an
    indented line inside a proof body cannot be peeled by mistake.

    A doc comment at column zero also starts a block. Several files write one
    declaration directly below another with no blank line between them, and
    blank lines are all `split_blocks` has to go on: Erdos 1108's `parts.i`
    was swallowed by the `def IsPowerful` above it and lost its name, as were
    Erdos 1072's `variants.littleo` and Artin's `parts.i`.

    `open X in` is a modifier on the declaration below it, so it is not peeled.
    """
    out, current, depth = [], [], 0
    for line in lines:
        loose = (depth == 0 and KEEP_LOOSE.match(line)
                 and not line.rstrip().endswith(" in"))
        doc = depth == 0 and DOC_START.match(line)
        # `open X in` is written *above* the docstring it precedes, so a block
        # holding only modifiers must not be split off from the declaration
        # they modify. Erdos 184 lost its `open scoped Classical in` this way,
        # and the statement then could not synthesize a `Decidable` instance.
        modifier_only = bool(current) and all(
            line_.rstrip().endswith(" in") for line_ in current if line_.strip())
        if (loose or (doc and not modifier_only)) and current:
            out.append(current)
            current = []
        if loose:
            out.append([line])
        else:
            current.append(line)
        # Depth is counted after the decision, so a line *inside* a doc comment
        # is never taken for a directive. `end of the story` on its own line in
        # a docstring would otherwise split the declaration away from its
        # documentation.
        depth += len(re.findall(r"/-", line)) - len(re.findall(r"-/", line))
        depth = max(depth, 0)
    if current:
        out.append(current)
    return out


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
            blocks.extend(Block(g) for g in peel_loose(current))
            current = []
            continue
        if line.strip() != "" or current:
            current.append(line)
        depth += len(re.findall(r"/-", line)) - len(re.findall(r"-/", line))
        depth = max(depth, 0)
    if current:
        blocks.extend(Block(g) for g in peel_loose(current))
    return blocks


def declares(declared, requested):
    """Whether a block declaring `declared` answers a request for `requested`.

    Most research statements in this repository carry a qualified name:
    `erdos_940.variants.large_integers`, `erdos_1038.parts.i`. A request may
    give that name in full, or drop any whole prefix of it, so the variant
    above is reachable as itself, as `variants.large_integers`, or as
    `large_integers`. Matching on the last component alone, which is what this
    did first, made every qualified name unreachable: all 413 of them.
    """
    return declared == requested or declared.endswith("." + requested)


def resolve(matches, declaration):
    """Narrow to the block named exactly, when there is one.

    Paper/WeaklyFirstCountable declares both
    `existsWeaklyFirstCountableCompactNotFirstCountable` and
    `CH.existsWeaklyFirstCountableCompactNotFirstCountable` in one file, so
    the first name is a suffix of the second and asking for it matched both.
    Naming a declaration in full is unambiguous, so an exact match wins.
    """
    exact = [b for b in matches if b.name == declaration]
    return exact if len(exact) == 1 else matches


def slug(name):
    """A Lake package name and directory name for a declaration.

    A Lake package name is an identifier, so the dots in a qualified
    declaration cannot go into one verbatim.
    """
    return re.sub(r"[^0-9A-Za-z_]", "_", name)


def load_manifest(problem_id):
    """Per-problem facts the source cannot supply, or supplies ambiguously.

    Two things cannot be read off a statement. The type of an `answer(sorry)`
    slot that does not flank an `↔`, which the surface syntax does not carry;
    and which file is meant when two declare the same name, as
    `conjecture_1_1` is declared by both Arxiv/2501.03234 and Arxiv/2504.17644.
    Guessing either would pose a problem nobody asked for.

    `leanprover/lean-eval` keeps one TOML per problem, and the reason is worth
    copying: two pull requests adding different problems never touch the same
    file.

      id           the filename stem, and the workspace directory name
      declaration  the Lean name, which need not be unique across the repository
      module       the file declaring it, relative to the repository root
      answer_type  the type of a non-`Prop` answer slot
      notes        free text for a reviewer
      source       a citation or URL
    """
    path = MANIFEST_DIR / f"{problem_id}.toml"
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if data.get("id") != problem_id:
        raise SystemExit(
            f"{path} declares id {data.get('id')!r}, but its filename says "
            f"{problem_id!r}; the two must agree")
    if "declaration" not in data:
        raise SystemExit(f"{path} has no `declaration` field")
    return data


def manifest_ids():
    return sorted(p.stem for p in MANIFEST_DIR.glob("*.toml"))


def module_name(rel_path):
    """The Lean module name for a path under `FormalConjectures/`.

    Most problem files are named for a number, which is not an identifier, so
    the component is written in guillemets:
    `FormalConjectures.ErdosProblems.«940»`.
    """
    parts = [c if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", c) else f"«{c}»"
             for c in str(rel_path)[:-len(".lean")].split("/")]
    return ".".join(parts)


def find_declaration(basename, module=None):
    """Locate the file declaring `basename`. Returns (path, module_docstring, body).

    `module` names the file when more than one declares the name, and comes
    from the problem's manifest.
    """
    pattern = re.compile(rf"^(?:theorem|lemma|def)\s.*\b{re.escape(basename)}\b",
                         re.MULTILINE)
    if module is not None:
        named = ROOT / module
        if not named.exists():
            raise SystemExit(f"manifest names {module}, which does not exist")
        return _read_source(named)
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
        raise SystemExit(
            f"{basename!r} is ambiguous: "
            + ", ".join(str(h.relative_to(ROOT)) for h in hits)
            + "; pass --module to choose one, or record the choice in "
              "comparator/problems/<id>.toml")
    return _read_source(hits[0])


def _read_source(path):
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
    """Remove the docstring, line comments and attributes from a declaration.

    These interleave. Erdos 918 puts a `--` formalisation note between its
    docstring and its `@[category ...]` line, and one anchored pass each left
    the attribute in place. `@[category research open, AMS 5]` then reached
    Challenge.lean, where the workspace has no such attribute, and Lean parsed
    as far as the `open` inside it before giving up.
    """
    # `open X in` binds to the declaration and has to survive, but it sits
    # above the docstring, so stripping anchored at the start would stop dead
    # on it.
    prefix = ""
    m = re.match(r"\A\s*(open\b[^\n]*\bin)\n", block_text)
    if m:
        prefix = m.group(1) + "\n"
        block_text = block_text[m.end():]
    while True:
        stripped = re.sub(r"\A\s*/--.*?-/\s*", "", block_text, flags=re.DOTALL)
        stripped = re.sub(r"\A\s*--[^\n]*\n", "", stripped)
        stripped = re.sub(r"\A\s*@\[[^\]]*\]\s*", "", stripped, flags=re.DOTALL)
        if stripped == block_text:
            return prefix + stripped
        block_text = stripped


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
            # Challenge.lean now restates the statement read from the working
            # tree while importing its context from `fc_rev`. If the two
            # disagree the workspace can fail to build, or worse, build the
            # statement against definitions it was not written for.
            print(f"WARNING: {source_path} differs from the pinned FC revision "
                  f"{fc_rev[:12]}. The statement is read from the working tree "
                  f"and its context is imported from that revision, so the two "
                  f"may disagree. Push the change first.", file=sys.stderr)
    return mathlib_rev, fc_rev


def lakefile(workspace_id, mathlib_rev, fc_rev):
    # Only the two libraries that are written. The hand-made prototype copied
    # lean-eval's `Submission` library and `workspace_test` driver, which this
    # generator does not produce, so a plain `lake build` or `lake test` in the
    # workspace failed on a missing target. Naming `Challenge` explicitly, as
    # the validation harness did, hid that for the whole of its development.
    return f"""name = "{workspace_id}"
defaultTargets = ["Challenge", "Solution"]

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
name = "Challenge"

[[lean_lib]]
name = "Solution"
"""


def generate(basename, out_dir, answer_type=None, module=None):
    """Write a comparator workspace for one declaration.

    Challenge.lean imports the problem's own module rather than restating its
    dependencies. `leanprover/lean-eval` generates a Challenge that is one
    `import` and one statement, and reconstructing the surrounding definitions
    by hand instead cost six defects that only Lean could find: file-scoped
    `open` and `variable` lost, `local notation` unrecognised, a `namespace`
    swallowing the declaration below it, `section` lines left unclosed. An
    import has none of those failure modes.

    Importing a repository full of `sorry` is safe here because comparator
    checks axioms. A solution closing the goal with the imported statement
    reports `sorryAx`, which `permitted_axioms` does not allow.
    """
    manifest = load_manifest(basename)
    declaration = manifest.get("declaration", basename)
    # An argument given on the command line is explicit, so it wins over the
    # manifest; the manifest is the durable record of the same choice.
    answer_type = answer_type or manifest.get("answer_type")
    module = module or manifest.get("module")
    path, _imports, _module_doc, body = find_declaration(declaration, module)
    blocks = split_blocks(body)

    target, matches, preamble = None, [], []
    stack, namespaces_at_target = [], []
    for b in blocks:
        if b.kind == "namespace":
            name = (b.kind_line or "").split(None, 1)
            if len(name) > 1:
                stack.append(name[1].strip())
            continue
        if b.kind == "end":
            name = (b.kind_line or "").split(None, 1)
            if len(name) > 1 and stack and stack[-1] == name[1].strip():
                stack.pop()
            continue
        if b.name and declares(b.name, declaration):
            matches.append(b)
            target = b
            # The namespaces open *here*, which is what the statement's short
            # names resolve against. Tracking the stack rather than collecting
            # every `namespace` line handles both nesting and siblings.
            namespaces_at_target = list(stack)
            continue
        if b.kind in FILE_SCOPED:
            # Lean scopes these to their file, so an import does not carry
            # them and they have to be copied. Everything else the statement
            # needs is a real declaration, and the import supplies it.
            preamble.append(b.text)

    if target is None:
        raise SystemExit(f"{declaration!r} not found as a block in {path}")
    matches = resolve(matches, declaration)
    target = matches[0] if len(matches) == 1 else target
    if len(matches) > 1:
        # Taking the last silently would pose a problem the caller did not ask
        # for, and nothing downstream would notice.
        raise SystemExit(
            f"{declaration!r} matches more than one declaration in {path}: "
            + ", ".join(b.name for b in matches)
            + "; name one of them in full")

    declared = target.name
    statement = strip_decorations(target.text)
    statement = replace_proof_with_sorry(statement)
    statement, holes = hoist_answers(statement, declared, answer_type)

    # `open A`, then `open A.B`: opening the inner namespace does not open the
    # outer one, and a statement may name siblings from either.
    opens = [f"open {'.'.join(namespaces_at_target[:i + 1])}"
             for i in range(len(namespaces_at_target))]

    challenge = (
        f"import {module_name(path.relative_to(ROOT))}\n\n"
        + ("\n".join(opens) + "\n" if opens else "")
        + ("\n".join(preamble) + "\n" if preamble else "")
        + ("\n" if opens or preamble else "")
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
    full_name = ".".join(namespaces_at_target + [declared])
    hole_names = [h.split()[2] for h in holes]

    workspace_id = slug(manifest.get("id", declared))
    ws = pathlib.Path(out_dir) / workspace_id
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "lakefile.toml").write_text(lakefile(workspace_id, mathlib_rev, fc_rev))
    # Without a toolchain file, lake in the workspace falls back to elan's
    # default, which need not exist and need not match the pinned Mathlib.
    (ws / "lean-toolchain").write_text((ROOT / "lean-toolchain").read_text())
    (ws / "Challenge.lean").write_text(challenge)
    (ws / "Solution.lean").write_text(solution)
    (ws / "config.json").write_text(json.dumps({
        "challenge_module": "Challenge",
        "solution_module": "Solution",
        "theorem_names": [declared],
        "permitted_axioms": PERMITTED_AXIOMS,
        "enable_nanoda": False,
        "definition_names": hole_names,
    }, indent=2) + "\n")
    (ws / "holes.json").write_text(json.dumps({
        "id": manifest.get("id", declared),
        "module": str(path.relative_to(ROOT)),
        "holes": [
            {"name": ".".join(namespaces_at_target + [hn]), "basename": hn,
             "kind": "def", "body": body_}
            for hn, body_ in zip(hole_names, holes)
        ] + [
            {"name": full_name, "basename": declared, "kind": "theorem",
             "body": target.text}
        ],
    }, indent=2, ensure_ascii=False) + "\n")
    return ws


def validate():
    """Check every manifest resolves to exactly one declaration.

    Run this rather than discovering a stale `module` field when someone
    generates the workspace months later.
    """
    bad = 0
    for problem_id in manifest_ids():
        try:
            manifest = load_manifest(problem_id)
            declaration = manifest["declaration"]
            path, _i, _d, body = find_declaration(declaration, manifest.get("module"))
            matches = resolve([b for b in split_blocks(body)
                               if b.name and declares(b.name, declaration)],
                              declaration)
            if len(matches) != 1:
                raise SystemExit(
                    f"{declaration!r} matches {len(matches)} declarations in "
                    f"{path.relative_to(ROOT)}")
        except SystemExit as exc:
            print(f"{problem_id}: {exc}", file=sys.stderr)
            bad += 1
            continue
        print(f"{problem_id}: {declaration} in {path.relative_to(ROOT)}")
    if bad:
        print(f"{bad} manifest(s) do not resolve", file=sys.stderr)
    return 1 if bad else 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("declaration", nargs="?",
                    help="a manifest id, or a declaration name such as erdos_940")
    ap.add_argument("--out", default=str(ROOT / ".comparator"))
    ap.add_argument("--answer-type", default=None,
                    help="type of a non-Prop answer(sorry) slot; "
                         "the manifest's `answer_type` is used when absent")
    ap.add_argument("--module", default=None,
                    help="the file declaring it, when more than one does; "
                         "overrides the manifest's `module`")
    ap.add_argument("--validate", action="store_true",
                    help="check every manifest resolves, and generate nothing")
    args = ap.parse_args(argv)
    if args.validate:
        return validate()
    if not args.declaration:
        ap.error("give a declaration, or --validate")
    ws = generate(args.declaration, args.out, args.answer_type, args.module)
    print(ws)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
