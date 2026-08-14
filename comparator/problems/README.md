# Comparator problem manifests

One TOML file per problem, named for its `id`. `scripts/make_comparator_workspace.py`
reads them.

A manifest exists to supply what the Lean source cannot. Most statements need
none, and the generator works without one.

| field | |
|---|---|
| `id` | required. Must equal the filename stem. Names the workspace directory |
| `declaration` | required. The Lean name, which need not be unique in the repository |
| `module` | the file declaring it, relative to the repository root |
| `answer_type` | the type of an `answer(sorry)` slot that does not flank an `↔` |
| `notes` | free text for a reviewer |
| `source` | a citation or URL |

## When you need one

**The name is not unique.** `conjecture_1_1` is declared by both
`Arxiv/2501.03234/ArithmeticSumS.lean` and `Arxiv/2504.17644/Margulis.lean`.
The generator refuses rather than choosing, so each gets a manifest with its
own `id` and a `module` naming its file. 92 statements are in this position,
over ten shared names: `conjecture`, `conjecture1` and `upper_bound` among
them, mostly across OEIS files.

`--module` does the same thing for one run, and is the quicker way to try a
problem. Write the manifest when you want the choice to persist, since it also
fixes the workspace directory name.

**The answer slot's type is not in the syntax.** A slot flanking an `↔` is a
`Prop` and needs nothing. Any other slot's type cannot be read off the surface
syntax, and guessing it would pose a different problem from the one the file
states, so `answer_type` has to say. 134 statements are in this position, and
they are the only ones the generator cannot reach on its own.

One file per problem means two pull requests adding different problems never
touch the same file. This follows
[`leanprover/lean-eval`](https://github.com/leanprover/lean-eval), whose
`manifests/problems/` works the same way.

## Checking them

```bash
python3 scripts/make_comparator_workspace.py --validate
```

Each manifest must resolve to exactly one declaration. Run it after moving or
renaming a statement, rather than finding a stale `module` months later when
someone generates the workspace.
