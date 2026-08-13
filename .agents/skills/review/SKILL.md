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

## Step 1: take the automatic checks as given

Run these, and do not re-derive what they decide.

```bash
lake --wfail build 'FormalConjectures.ErdosProblems.«361»'   # each module that changed
python3 scripts/check_proof_links.py                          # does each formal_proof link resolve?
python3 scripts/check_erdos_status.py                         # does the repo agree with erdosproblems.com?
```

If a module does not build, report that and stop.

## Step 2: read the cited source

Open the source that the module docstring cites. Do not review the Lean against the docstring
alone. The docstring is also under review, and a docstring that disagrees with its own Lean is
itself a finding.

## Step 3: work through the defect classes

Read [`references/defect-classes.md`](references/defect-classes.md) now. It gives a worked
example from this repository for each class below, and each example is marked **confirmed** or
**lead**. A lead is a place to look, and not a finding.

1. the statement does not match the source
2. the hypotheses cannot hold
3. boundary cases
4. `answer()` semantics
5. what a `formal_proof` link shows
6. variants

Skip class 5 unless the pull request adds or changes a `formal_proof` attribute.

Two checks pay for themselves on almost every statement, so do them even when time is short.
Substitute the smallest value of each bound. Then ask, for each hypothesis, what must exist for
it to hold, and whether anything does.

## Step 4: report

Each finding **must** carry a witness. A witness is a concrete case where the Lean and the
source disagree. A reader can then check the finding without doing the review again.

- "This looks too strong" is not a finding.
- "At `c = 2` and `n = 100` the hypothesis needs 20000 edges, and a simple graph has at most
  4950" is a finding.

For each finding give the declaration, the line, what the source says with a locator, what the
Lean says, the witness, and a suggested change.

Say what the witness shows, and also what it does not show. A finding that claims too much
costs a reviewer more time than no finding.

Then give one verdict:

- **CLEAN**: no findings.
- **ACCEPT WITH NITS**: the findings do not change the meaning of the statement.
- **NEEDS REVISION**: at least one finding changes the meaning, or makes the statement vacuous,
  or shows that a `formal_proof` claims more than the linked proof gives.

If you cannot give a witness for an item, write it as a question instead of a finding.

## Out of scope

- style, naming and format, which `AGENTS.md` and the linters cover
- a shorter proof for a statement that already builds
- a different but equivalent formalisation, unless the difference is observable
- whether the conjecture is true
- whether to merge the pull request
