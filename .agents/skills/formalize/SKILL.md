---
name: formalize
description: Turn a source problem statement into a faithful Lean statement for this repository. Use when adding a problem file, adding a variant to an existing file, or translating a statement from erdosproblems.com, a paper, or a book.
license: Apache-2.0
---

# Formalise a statement

A formalisation here is a claim about what a source says, made in a language
that cannot hedge. Every failure mode this skill guards against was found in a
merged or reviewed file of this repository: a bound copied from the neighbouring
problem instead of the source, a binder that swallowed the answer slot, an
existential where the source says pairwise, a `∀ n` where the source's big-O
means eventually, a junk value that decided an open problem. The conventions
live in `AGENTS.md` and the directory READMEs; this is the working order and
the traps.

## Step 1: read the source, not a rendering and not a neighbour

Fetch the source as close to its own markup as it exists. For erdosproblems.com
that is `https://www.erdosproblems.com/latex/<n>`, which serves the LaTeX; it
answers 200 to a named user agent where the bare fetch may 403. Read the whole
page: the remarks below the problem box carry the hypotheses, the known partial
results, and sometimes a status the box does not show.

Quote, in your working notes, the exact sentence that carries each restriction.
"Let $r \ge 3$" at the top of a page scopes everything under it. Do not
reconstruct a hypothesis from a sibling file in this repository: the sibling may
formalise a different problem that differs by exactly the hypothesis you need,
and the two will read almost identically.

## Step 2: choose the statement shape before writing any Lean

- An open yes/no question is `answer(sorry) ↔ <the question>`, with the slot
  **first** and every binder after the `↔`. A slot to the right of an
  existential gets swallowed into the binder, and the resulting statement is
  provable without answering anything. Putting the slot first makes that
  impossible by construction.
- An open "determine the value" question puts `answer(sorry)` on one side of an
  equality. Ask whether the other side can be fed back into the slot: if
  `answer(X) = X` would close it by `rfl`, the statement determines nothing,
  and the question needs restating (for instance as bounds) or a maintainer's
  view.
- A known result is a plain theorem under `research solved`, with the citation
  in the docstring; `sorry` is the sanctioned proof for a literature result.
- Multi-part problems are `erdos_N.parts.i`, `.parts.ii`; readings the source
  does not ask are `.variants.<name>`. If the file will have no bare main
  statement, know that some tooling reads only main statements, and say in the
  module docstring which declaration carries the problem.

## Step 3: transcribe against the junk-value table

The table in `AGENTS.md` is the reference. The instances that have actually
decided statements in this repository:

- `∑' n, f n = 0` when `f` is not `Summable`, and `0` is rational. Writing
  "converges to a rational" as a bare `tsum` equality admits every divergent
  series. Use `HasSum`, which carries convergence in the statement.
- `Filter.limsup` over `ℝ` is `sInf ∅ = 0` on an unbounded sequence. Encode
  `limsup > 1` as `∃ c > 1, ∃ᶠ n in atTop, ...`; `∀ᶠ` would encode liminf.
- A source's big-O or o(1) is a statement about large `n`. `∀ n` asserts it at
  `n = 2`, where `log log n < 0` and similar accidents make statements false
  for reasons the source never raises. Use `∀ᶠ n in atTop`.
- `sInf ∅ = 0` in `ℕ` sits on the easy side of an upper bound and the fatal
  side of a lower bound or an equality. Know which side your statement is on.
- Where a junk value sits inside the *admissibility predicate* of an
  `∃ a, Admissible a ∧ P a`, it makes the existential easier to witness and
  can make an open statement provable. This is the one direction the "junk
  only weakens" intuition gets wrong.
- A type ascription on an application, `(s.lcm f : ℝ)`, elaborates the
  operation in `ℝ`, where every nonzero element is a unit and `lcm` collapses
  to `1`. Force the operation in `ℕ` and coerce the result:
  `((s.lcm f : ℕ) : ℝ)`.
- "Different sizes" over a family means pairwise distinct, `∀ i j, i ≠ j → ...`
  or `Function.Injective`. The existential `∃ i j, i ≠ j ∧ ...` says almost
  nothing and is usually satisfiable outright.

## Step 4: check the draft the way a sceptic would

Elaborate and read back. `lake build` the module, then `#check` the statement
with `pp.parens` or print it, and read what Lean parsed rather than what you
wrote. This is one command and it catches the binder and ascription traps
outright.

Controls, where the source provides them cheaply. If the source names a
witness, a small case, or its own construction, run it against your predicate:
a positive control that the intended objects satisfy it, a negative control
that a near-miss fails it. A definition that accepts everything or nothing
elaborates fine and formalises nothing. Machine-check what you can and say
what you did not.

Degenerate inputs. Evaluate the statement at 0, 1, the empty set, the empty
`Finset`, and whatever sits at the bottom of each type you quantify over.
Every hypothesis that exists to exclude a degenerate case gets one docstring
sentence saying so.

Status. The source's status today, not the status the problem had when you
started. A revised paper or an updated page can settle a question between your
first read and your commit; cite the revision date when the source carries one.

## Step 5: the file around the statement

`AGENTS.md` and the directory README own the conventions; the ones that decide
review outcomes: the verbatim problem text in the theorem docstring, the module
header carrying title and references only, references in the header block
rather than inline, one docstring sentence per load-bearing hypothesis,
formalisation caveats in the pull request description and not in the file, and
the current year in the copyright header, which the linter does not check.

## Step 6: review your own draft before anyone else does

Read the finished file as if it were someone else's submission, against the
same table in step 3, and fix what you find before opening the pull request.
That pass is cheap next to a review round-trip with a maintainer.

If a `review` skill is available alongside this one, run it here: checking a
statement and writing one are complements, and the reviewer's questions are
sharper than an author's second reading of their own work.
