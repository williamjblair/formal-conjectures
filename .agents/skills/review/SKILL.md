---
name: review
description: Use when reviewing a Formal Conjectures pull request, when checking whether a Lean statement says what its cited source says, or before submitting a formalisation. Use it also when asked whether a statement is correct, vacuous, too strong, or degenerate at small inputs, even when the request does not mention review. Finds misformalisation, unsatisfiable hypotheses, boundary cases, answer() polarity, and formal_proof claims that exceed the linked proof.
license: Apache-2.0
compatibility: Needs a checkout of google-deepmind/formal-conjectures and a Lean toolchain, so that the commands in step 1 can run.
---

# Review a statement

This is the second pass over a formalisation. `AGENTS.md` covers the first pass, which is
mechanical. This one needs judgement, and it answers one question: does the Lean statement say
what the source says?

You produce **recommendations**. You do not decide whether to merge. The contributor can
disagree with a finding and ask a maintainer to decide.

First fix the scope. If a pull request is named, review its diff. If a file is named, review
the whole file, and read `git status` and `git log -1` so you know whether the work is even in
the tree yet.

## Step 1: take the automatic checks as given

```bash
lake --wfail build 'FormalConjectures.ErdosProblems.«361»'   # each module in scope
python3 scripts/check_erdos_status.py                         # only for ErdosProblems/
```

If a module does not build, report that and stop.

`--wfail` runs the repository's own linters, including the category and `answer` ones, because
they are `leanOptions` in `lakefile.toml`. A clean module build therefore covers them, and you
do not need `check_category_warnings.py`, which takes an `extract_names` dump and needs the
whole repository built.

`check_erdos_status.py` prints every mismatch in the repository. Find your problem number in
that list. Absence is the pass.

## Step 2: read every definition the statement uses

Do this before you read the Lean statement closely. Most findings turn on a definition, and
most false findings come from assuming one.

Look up each name the statement mentions in `FormalConjecturesForMathlib/` or Mathlib, and ask
what it does at its degenerate values. The *Check the degenerate cases* table in `AGENTS.md`
lists the ones that recur. Two more from this repository:

- `Nat.Full k n` is `∀ p ∈ n.primeFactors, p ^ k ∣ n`, and `primeFactors 0 = ∅`, so `0` and `1`
  are vacuously Full.
- `Finset.Coprime S` is `S.gcd id = 1`, the gcd of the whole set. It is not pairwise, so a set
  containing `1` is coprime whatever else it holds.

## Step 3: read the cited source

Open the source the module docstring cites. Do not review the Lean against the docstring alone.
The docstring is also under review, and a docstring that disagrees with its own Lean is itself
a finding.

For an Erdős problem, `https://www.erdosproblems.com/<n>` returns 403 to a plain fetch. Use
`curl` with a browser user agent. The `teorth/erdosproblems` YAML that `check_erdos_status.py`
reads carries status only, and no statement text, so it is not the source.

For a paper, a fetch returns raw PDF bytes. Save the file and run `pdftotext -layout` on it.

**Read the whole document, and check its date.** A source revises. Knuth's *Claude's Cycles* is
"28 February 2026; revised 14 April 2026". Page 5 says the even case is open, and page 6 opens
"Breaking news: The problem for even values of m is no longer in doubt!". A reviewer who reads
the problem statement and stops will pass a file that records a question its own source has
closed. Read the remarks, the postscripts and any addendum, and compare the source's early
status claims against its later sections.

Quote formulas from the LaTeX source rather than the rendered page. Rendering runs terms
together: `3^7\cdot 61^5` reads as `3761^5`, and that misreading is already in this repository.

## Step 4: review, then check yourself

Work through the statement yourself first. Two checks pay for themselves almost every time.
Substitute the smallest value of each bound. Then ask, for each hypothesis, what must exist for
it to hold, and whether anything does.

Only then read [`references/defect-classes.md`](references/defect-classes.md), and use it to
find what you missed. It lists six classes with a worked example each. Reading it first anchors
you to its examples, and it contains the answer to some reviews outright.

1. the statement does not match the source
2. the hypotheses cannot hold
3. boundary cases
4. `answer()` semantics
5. what a `formal_proof` link shows
6. variants

Skip class 5 unless the scope adds or changes a `formal_proof` attribute.

## Step 5: report

Each finding **must** carry a witness: a concrete case where the Lean and the source disagree.
Check the witness in Lean where you can, with `lake env lean` on a scratch file outside the
tree that imports the module.

You may also write a program. Two things repay the effort. Encode the source's own construction
and run it against the Lean predicate, as a positive control that the definition is faithful and
not vacuous. And enumerate the smallest case exhaustively. A positive control convinces a
reviewer more than a second reading of the definition does.

Say what the witness shows, and also what it does not show. A finding that claims too much
costs a reviewer more time than no finding.

A finding looks like this:

> **`erdos_940.variants.large_integers`, 940.lean:62** — quantifies over `r ≥ 2`.
> The source opens "Let $r \geq 3$". At `r = 2` the statement asserts that almost every integer
> is a sum of at most two `2`-powerful numbers, so that set is cofinite.
> `erdos_940.variants.two`, in the same file and `research solved`, states that the same set
> has density `0`. Both cannot hold.
> *Shows*: the `r = 2` conjunct is false, so the answer is forced for a reason the source
> excludes. *Does not show*: anything about `r ≥ 3`, which is the real question.
> *Suggested change*: `∀ r ≥ 3`, and say so in the docstring.

Say what you verified, and not only what you found. When the answer to the contributor's
question is yes, a bare verdict tells them nothing about what was checked, and reads as though
you did not look.

Then give one verdict:

- **CLEAN**: no findings.
- **ACCEPT WITH NITS**: the findings do not change the meaning of the statement.
- **NEEDS REVISION**: at least one finding changes the meaning, or makes the statement vacuous,
  or shows that a `formal_proof` claims more than the linked proof gives, or records a status or
  category that the cited source contradicts.

If you cannot give a witness for an item, write it as a question instead of a finding.

## Out of scope

- style, naming and format, which `AGENTS.md` and the linters cover
- a shorter proof for a statement that already builds
- a different but equivalent formalisation, unless the difference is observable
- a `sorry` under `research solved`. That category means the result is known in the literature,
  and almost every statement in this repository is `sorry`
- whether the conjecture is true
- whether to merge
