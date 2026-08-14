# Comparator

[leanprover/comparator](https://github.com/leanprover/comparator) is a
trustworthy judge for Lean proofs: given a Challenge module stating a theorem
over `sorry` and a Solution module proving it, it certifies that the solution
proves the same statement using only the permitted axioms. This directory
holds what this repository needs to generate such a challenge from any of its
problem statements.

## Where each piece lives

| piece | place | why there |
|---|---|---|
| the generator | [`scripts/make_comparator_workspace.py`](../scripts/make_comparator_workspace.py) | repository automation lives in `scripts/`, where CI runs its tests |
| per-problem manifests | [`problems/`](problems/) | one TOML per problem, described below |
| workspace test | [`templates/WorkspaceTest.lean`](templates/WorkspaceTest.lean) | copied into each workspace so `lake test` runs comparator; a Lean file, so it can be edited as one |
| generated workspaces | `.comparator/`, gitignored | whether generated output is committed is an open question, [#4930](https://github.com/google-deepmind/formal-conjectures/issues/4930) |

The layout of a generated workspace follows
[`leanprover/lean-eval`](https://github.com/leanprover/lean-eval): the solver
works in `Submission.lean`, and a fixed `Solution.lean` closes the trusted
statement with the Submission theorem, so the statement cannot drift.

## Generating a workspace

```bash
python3 scripts/make_comparator_workspace.py erdos_940.variants.large_integers
```

The script's docstring covers the layout it produces and the cases where it
refuses rather than guesses. `--all` generates every reachable workspace and
an `index.json` cataloguing them.

An open problem accepts a proof or a disproof. A statement whose
`answer(sorry)` flanks an `↔` carries that choice in its hole. For a plain
statement, `--disprove` poses the negation instead, as its own workspace:
`(∀ <binders>, <statement>) → False`. Passing `--disprove` on a holed
statement is refused, since the hole already asks the question.

## Manifests

A manifest supplies what the Lean source cannot. Most statements need none.

| field | |
|---|---|
| `id` | required; must equal the filename stem, and names the workspace directory |
| `declaration` | required; the Lean name, which need not be unique in the repository |
| `module` | the file declaring it, when more than one does |
| `answer_type` | the type of an `answer(sorry)` slot that does not flank an `↔` |
| `notes`, `source` | surfaced in the workspace README |

Two situations need one. A name two files share: `conjecture_1_1` is declared
by both `Arxiv/2501.03234` and `Arxiv/2504.17644`, so each gets a manifest
naming its file, and `--module` does the same for a single run. And a non-Prop
answer slot, whose type is not in the syntax, so `answer_type` has to say; 134
statements are in this position, and they are the only ones the generator
cannot reach on its own.

```bash
python3 scripts/make_comparator_workspace.py --validate
```

checks every manifest still resolves to exactly one declaration. Run it after
moving or renaming a statement.

## Pins

The external tools carry pins of their own, taken from lean-eval's tested set:
comparator at or after `71b52ec2`, which added definition-hole support that
our `answer(sorry)` workspaces rely on; landrun at `5ed4a3db`, since tagged
releases lack fixes comparator needs; and `lean4export` built with the
workspace's own `lean-toolchain`, never its default, because olean headers
differ between Lean releases.

A workspace pins Mathlib to the revision in this checkout's
`lake-manifest.json`, and `formal_conjectures` to the merge-base of `HEAD`
with `origin/main`, so the workspace's own build can fetch both. The pins
move by regenerating; there is no separate bump step. If the source file
changed since the merge-base, the generator warns that the statement and its
imported context may disagree, and the fix is to push first.

## The intended end state

Extraction currently reads Lean by regex, in Python. The honest long-term
home is a `lake exe`, the way `scripts/extract_names.lean` already elaborates
these files and the way lean-eval's own generator works. When that lands, the
Python goes away and this directory holds the whole subsystem.
