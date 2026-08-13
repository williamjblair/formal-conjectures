---
name: review-statement
description: Review a Formal Conjectures statement against the source it cites. Use when reviewing a pull request that adds or changes a statement, or before submitting one. Answers whether the Lean says what the source says, which no check in the repository decides. Covers misformalisation, vacuous hypotheses, boundary cases, answer() semantics, and formal_proof claims.
license: Apache-2.0
compatibility: Needs a checkout of google-deepmind/formal-conjectures and a Lean toolchain, so that the automatic checks in step 1 can run.
---

# Review a statement

This skill runs the second pass over a formalisation. The first pass is mechanical, and
`AGENTS.md` covers it. This one needs judgement.

You produce **recommendations**. You do not decide whether to merge. The contributor can
disagree with a finding and ask a maintainer to decide.

## Step 1: read the automatic checks

Do not examine what a script decides already. Take these results as given.

```bash
lake --wfail build <the modules that changed>
python3 scripts/check_proof_links.py            # does each formal_proof link resolve?
python3 scripts/check_erdos_status.py           # does the repo agree with erdosproblems.com?
```

`extract_names` gives the category, the subjects and the formal-proof data for each
declaration. The category linter warns when a `research open` statement has a sorry-free proof.

If a check fails, report it and stop. Do not review the mathematics of a file that does not
build.

## Step 2: read the source

Open the source that the module docstring cites. Do not review the Lean against the docstring
alone, because the docstring is also under review.

## Step 3: work through the defect classes

[`references/defect-classes.md`](references/defect-classes.md) lists six classes, each with an
example from this repository:

1. the statement does not match the source
2. the hypotheses cannot hold
3. boundary cases
4. `answer()` semantics
5. what a `formal_proof` link shows
6. variants

Read that file before you start. The examples are marked **confirmed** or **lead**. A lead is a
place to look, and not a finding.

## Step 4: report

Each finding **must** carry a witness. A witness is a concrete case where the Lean and the
source disagree. A reader can then check the finding without doing the review again.

- "This looks too strong" is not a finding.
- "At `c = 2` and `n = 100` the hypothesis needs 20000 edges, and a simple graph has at most
  4950" is a finding.

Give the declaration, the line, what the source says with a locator, what the Lean says, the
witness, and a suggested change.

Report what the witness shows, and also what it does not show. A finding that claims too much
costs the reviewer more time than no finding.

Then give one verdict:

- **CLEAN**: no findings.
- **ACCEPT WITH NITS**: the findings do not change the meaning of the statement.
- **NEEDS REVISION**: at least one finding changes the meaning, or makes the statement vacuous,
  or shows that a `formal_proof` claims more than the linked proof gives.

## Out of scope

Do not report style, naming or format, which `AGENTS.md` and the linters cover. Do not report a
shorter proof for a statement that builds. Do not report a different but equivalent
formalisation, unless the difference is observable. Do not say whether the conjecture is true.
Do not say whether to merge.

## Uncertainty

Report your confidence. If you cannot give a witness, write the item as a question.
