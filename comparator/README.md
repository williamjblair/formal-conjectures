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
| per-problem manifests | [`problems/`](problems/) | one TOML per problem; see its README |
| workspace test | [`templates/WorkspaceTest.lean`](templates/WorkspaceTest.lean) | copied into each workspace so `lake test` runs comparator; a Lean file, so it can be edited as one |
| generated workspaces | `.comparator/`, gitignored | whether generated output is committed is an open question, [#4930](https://github.com/google-deepmind/formal-conjectures/issues/4930) |

## Generating a workspace

```bash
python3 scripts/make_comparator_workspace.py erdos_940.variants.large_integers
```

The script's docstring covers the layout it produces and the cases where it
refuses. `--validate` checks every manifest still resolves to exactly one
declaration.

The layout follows [`leanprover/lean-eval`](https://github.com/leanprover/lean-eval):
the solver works in `Submission.lean`, and a fixed `Solution.lean` closes the
trusted statement with the Submission theorem, so the statement cannot drift.

## The intended end state

Extraction currently reads Lean by regex, in Python. The honest long-term
home is a `lake exe`, the way `scripts/extract_names.lean` already elaborates
these files and the way lean-eval's own generator works. When that lands, the
Python goes away and this directory holds the whole subsystem.
