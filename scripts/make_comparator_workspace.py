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
    Submission.lean     where the solver works; helper modules go under
                        Submission/
    Solution.lean       fixed: restates the statement and closes it with the
                        Submission theorem, so the statement cannot drift
    WorkspaceTest.lean  `lake test` runs comparator on config.json
    README.md           what the solver needs to know, cache fetch included
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
    """Cut the proof body after `:=`, keeping the statement.

    A tactic proof is found by `:= by`, which a statement cannot contain,
    `by` being a keyword. A term proof leaves only a bare `:=` to cut at, and
    a statement can contain one of those: a structure literal `{ a := b }`
    inside the statement would be cut in half. With more than one candidate
    the script refuses, as everywhere else it cannot decide.
    """
    m = re.search(r":=\s*by\b", text)
    if m:
        return text[: m.start()].rstrip() + " := by\n  sorry"
    if text.count(":=") > 1:
        raise SystemExit(
            "the declaration has a term-mode proof and more than one `:=`, so "
            "the start of the proof cannot be read off the text")
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


def hole_names_of(holes):
    return [h.split()[2] for h in holes]


def explicit_binder_names(signature):
    """Names of the explicit binders in a theorem signature.

    Solution.lean proves the statement by applying the participant's
    `Submission` theorem to exactly these, the way lean-eval's generated
    adapter writes `exact Submission.abel_ruffini n _hn`. Implicit and
    instance binders are left to elaboration. A group this cannot read is
    refused, as everywhere else the script cannot decide.
    """
    lines = signature.split("\n")
    for i, line in enumerate(lines):
        m = DECL_START.match(line)
        if m:
            rest = "\n".join(lines[i:])[m.end():]
            break
    else:
        raise SystemExit("no declaration line in the signature")
    nm = re.match(r"\s*([\w.«»]+)", rest)
    rest = rest[nm.end():]
    um = re.match(r"\.\{[^}]*\}", rest)
    if um:
        rest = rest[um.end():]

    names, depth, i = [], 0, 0
    openers, closers = "({[⦃⟨", ")}]⦄⟩"
    while i < len(rest):
        c = rest[i]
        if depth == 0 and c == ":":
            return names
        if c in openers:
            if depth == 0 and c == "(":
                j, d = i, 0
                while j < len(rest):
                    if rest[j] in openers:
                        d += 1
                    elif rest[j] in closers:
                        d -= 1
                    if d == 0:
                        break
                    j += 1
                group = rest[i + 1:j]
                # `(r)` is a binder too: no ascription, type left to Lean.
                # Erdos 1055 writes one. The names are the whole group then.
                head, _, _ = group.partition(":")
                got = head.split()
                if not got or not all(
                        re.fullmatch(r"[^\s(){}\[\]:]+", n) for n in got):
                    raise SystemExit(
                        f"cannot read the explicit binder group ({group.strip()}); "
                        "the Solution adapter needs its names")
                names.extend(got)
                i = j + 1
                continue
            depth += 1
        elif c in closers:
            depth -= 1
        i += 1
    raise SystemExit("no top-level `:` in the signature")


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
name = "Challenge"

[[lean_lib]]
name = "Solution"

[[lean_lib]]
name = "Submission"

[[lean_exe]]
name = "workspace_test"
root = "WorkspaceTest"
"""


WORKSPACE_TEST = """import Lean

open Lean

/-- Run comparator on this workspace's `config.json`, so that `lake test`
is the check. Adapted from `leanprover/lean-eval`'s workspace test template.
The binary comes from `PATH`, or from `COMPARATOR_BIN`. -/
def main : IO UInt32 := do
  let comparatorBin := (← IO.getEnv "COMPARATOR_BIN").getD "comparator"
  try
    let child ← IO.Process.spawn {
      cmd := "lake"
      args := #["env", comparatorBin, "config.json"]
    }
    child.wait
  catch err =>
    IO.eprintln s!"Failed to run comparator via `{comparatorBin}`."
    IO.eprintln "Install comparator, with landrun and lean4export, and put it \
on PATH, or set COMPARATOR_BIN. See leanprover/comparator's README."
    IO.eprintln s!"Original error: {err}"
    pure 1
"""


def locate(blocks, declaration, path=""):
    """Find the target declaration, and what is in force at its position.

    Returns (target block, namespaces open at it, file-scoped preamble).

    The preamble keeps only directives that precede the target and whose
    scope still encloses it. A `variable` inside a `section` that closed
    before the statement is out of force there, and an `open` written after
    the statement played no part in how its names resolved. Carrying either
    would change the statement, silently in the `open` case: an extra open
    namespace can make a name ambiguous, which is how a stray research
    statement broke the Koethe workspace.
    """
    matches, preamble, stack = [], [], []
    for index, b in enumerate(blocks):
        if b.kind in ("namespace", "section"):
            parts = (b.kind_line or "").split(None, 1)
            stack.append((b.kind, parts[1].strip() if len(parts) > 1 else None))
            continue
        if b.kind == "end":
            parts = (b.kind_line or "").split(None, 1)
            name = parts[1].strip() if len(parts) > 1 else None
            if stack and (stack[-1][1] == name
                          or (name is None and stack[-1][0] == "section")):
                stack.pop()
            continue
        if b.name and declares(b.name, declaration):
            matches.append((index, b, list(stack)))
            continue
        if b.kind in FILE_SCOPED:
            preamble.append((index, b.text, list(stack)))

    if not matches:
        raise SystemExit(f"{declaration!r} not found as a block in {path}")
    chosen = resolve([b for _, b, _ in matches], declaration)
    if len(chosen) > 1:
        # Taking the last silently would pose a problem the caller did not ask
        # for, and nothing downstream would notice.
        raise SystemExit(
            f"{declaration!r} matches more than one declaration in {path}: "
            + ", ".join(b.name for b in chosen)
            + "; name one of them in full")
    index, target, scope = next(
        (i, b, s) for i, b, s in matches if b is chosen[0])
    namespaces = [n for kind, n in scope if kind == "namespace" and n]
    in_force = [text for i, text, s in preamble
                if i < index and s == scope[:len(s)]]
    return target, namespaces, in_force


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
    target, namespaces_at_target, preamble = locate(
        split_blocks(body), declaration, path)

    declared = target.name
    statement = strip_decorations(target.text)
    statement = replace_proof_with_sorry(statement)
    statement, holes = hoist_answers(statement, declared, answer_type)

    # `open A`, then `open A.B`: opening the inner namespace does not open the
    # outer one, and a statement may name siblings from either.
    opens = [f"open {'.'.join(namespaces_at_target[:i + 1])}"
             for i in range(len(namespaces_at_target))]

    # One header shared by all three Lean files: the statement's text is
    # identical in each, so what it needs to elaborate must be too.
    header = (
        ("\n".join(opens) + "\n" if opens else "")
        + ("\n".join(preamble) + "\n" if preamble else "")
        + ("\n" if opens or preamble else "")
    )
    fc_module = module_name(path.relative_to(ROOT))
    suffix = ":= by\n  sorry"
    signature = statement.rstrip()
    if signature.endswith(suffix):
        signature = signature[: -len(suffix)].rstrip()
    args = explicit_binder_names(statement)

    challenge = (
        f"import {fc_module}\n\n" + header
        + "\n\n".join(holes) + ("\n\n" if holes else "")
        + statement + "\n"
    )

    # The participant's file. The statement sits inside `namespace Submission`
    # so nothing here can collide with, or stand in for, the trusted names.
    submission = (
        f"import {fc_module}\n\n" + header
        + "namespace Submission\n\n"
        + "\n\n".join(holes) + ("\n\n" if holes else "")
        + statement + "\n\n"
        + "end Submission\n"
    )

    # The fixed adapter, lean-eval's shape: it restates the trusted statement
    # and closes it with the Submission theorem, so it fails to compile the
    # moment the submission proves anything else. The participant never edits
    # it, which is what keeps the statement pinned.
    delegated = [h.rsplit(":= sorry", 1)[0] + ":= Submission." + hn
                 for h, hn in zip(holes, hole_names_of(holes))]
    solution = (
        f"import {fc_module}\nimport Submission\n\n" + header
        + "\n\n".join(delegated) + ("\n\n" if delegated else "")
        + signature + " :=\n  Submission." + declared
        + ("".join(" " + a for a in args)) + "\n"
    )

    mathlib_rev, fc_rev = pins(path.relative_to(ROOT))
    full_name = ".".join(namespaces_at_target + [declared])
    hole_names = hole_names_of(holes)

    workspace_id = slug(manifest.get("id", declared))
    ws = pathlib.Path(out_dir) / workspace_id
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "lakefile.toml").write_text(lakefile(workspace_id, mathlib_rev, fc_rev))
    # Without a toolchain file, lake in the workspace falls back to elan's
    # default, which need not exist and need not match the pinned Mathlib.
    (ws / "lean-toolchain").write_text((ROOT / "lean-toolchain").read_text())
    holes_line = (
        "\nFill each definition hole in `Submission.lean` too. Hole answers "
        "also get a\nhuman check, because a hole can be gamed in ways the "
        "comparator cannot see.\n" if holes else "")
    manifest_lines = "".join(
        f"- {field.capitalize()}: {' '.join(str(manifest[field]).split())}\n"
        for field in ("source", "notes") if manifest.get(field))
    (ws / "README.md").write_text(
        f"# {workspace_id}\n\n"
        f"A comparator challenge for `{declared}`, generated from\n"
        f"`{path.relative_to(ROOT)}` in google-deepmind/formal-conjectures.\n\n"
        + manifest_lines +
        "\nProve the statement in `Submission.lean`, keeping it as it stands; "
        "put helper\nmodules under `Submission/` if you need them. Do not "
        "modify `Challenge.lean` or\n`Solution.lean`: the trusted statement "
        "lives there, and `Solution.lean` closes it\nwith your `Submission` "
        "theorem, so it fails to compile if the submission proves\nanything "
        "else.\n"
        "\nComparator accepts the workspace only if the statement is proved "
        "under the\naxioms in `config.json`. `sorry` adds `sorryAx`, which is "
        "not permitted, and\nclosing the goal with the imported original "
        "fails the same way, since that is\n`sorry` too. `lake test` runs "
        "comparator, from `PATH` or `COMPARATOR_BIN`.\n"
        + holes_line +
        "\nFetch the Mathlib cache before the first build; a cold build takes "
        "the best\npart of an hour without it:\n\n"
        "    lake exe cache get\n"
        "    lake build\n")
    (ws / "Challenge.lean").write_text(challenge)
    (ws / "Solution.lean").write_text(solution)
    (ws / "Submission.lean").write_text(submission)
    (ws / "WorkspaceTest.lean").write_text(WORKSPACE_TEST)
    config = {
        "challenge_module": "Challenge",
        "solution_module": "Solution",
        "theorem_names": [declared],
        "permitted_axioms": PERMITTED_AXIOMS,
        "enable_nanoda": False,
    }
    if hole_names:
        # Comparator's documented no-hole config carries no such field.
        config["definition_names"] = hole_names
    (ws / "config.json").write_text(json.dumps(config, indent=2) + "\n")
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
            locate(split_blocks(body), declaration, path.relative_to(ROOT))
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
