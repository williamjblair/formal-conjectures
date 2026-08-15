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

An open problem accepts a proof or a disproof. A holed statement carries that
choice in its `answer(sorry)` slot. For plain statements, disproof submission
is comparator's `allow_disproofs` (its PR #48), not a protocol of ours; this
generator stays prove-only until that lands.

## Manifests

A manifest supplies what the Lean source cannot. Most statements need none.

| field | |
|---|---|
| `id` | required; must equal the filename stem, and names the workspace directory |
| `declaration` | required; the Lean name, which need not be unique in the repository |
| `module` | the file declaring it, when more than one does |
| `answer_type` | override only; slot types are inferred from the elaborated statement |
| `notes`, `source` | surfaced in the workspace README |

One situation needs one: a name two files share. `conjecture_1_1` is declared
by both `Arxiv/2501.03234` and `Arxiv/2504.17644`, so each gets a manifest
naming its file, and `--module` does the same for a single run. Answer slot
types are read from the elaborated statement, so no statement needs type
metadata; `answer_type` survives only as an explicit override.

```bash
python3 scripts/make_comparator_workspace.py --validate
```

checks every manifest still resolves to exactly one declaration. Run it after
moving or renaming a statement.

## Pins

The external tools are locked in [`tools.toml`](tools.toml), one
machine-readable source of truth: comparator at the commit that added the
definition-hole support our `answer(sorry)` workspaces rely on, landrun at
the commit lean-eval tests (tagged releases lack fixes comparator needs),
and `lean4export` at the tag matching the workspace's `lean-toolchain`,
because olean headers differ between Lean releases.

A workspace pins Mathlib to the revision in this checkout's
`lake-manifest.json`, and `formal_conjectures` to the merge-base of `HEAD`
with `origin/main`, so the workspace's own build can fetch both. The pins
move by regenerating; there is no separate bump step. If the source file
changed since the merge-base, the generator warns that the statement and its
imported context may disagree, and the fix is to push first.

## The intended end state

Semantic extraction lives in `scripts/comparator_facts.lean`, on the
elaborator; the Python that remains is workspace assembly and source-text
surgery. The end state worth pursuing upstream is lean-eval's tooling
factored into a reusable library that this repository consumes through a
small adapter, so nobody maintains a second evaluation stack; #4930 is where
that conversation lives.
