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
the whole file, and run `git status` and `git log -1 -- <path>` so you know whether the work is
even in the tree yet. Use the `-- <path>`: a bare `git log -1` reports the branch tip, which is
usually about something else. If the named pull request does not exist, say so and review the
file instead. The repository squash-merges, so a local date can belong to a repository-wide
refactor rather than to the work; confirm with `gh pr list --state all --search` when the commit
title does not mention the file.

Then check whether an open pull request already touches the file. Match on the full path, not on
a bare number, which also matches line counts and unrelated files. Get every path in one request
rather than one request for each of the several hundred open pull requests:

```bash
gh pr list --limit 400 --json number,title,files \
  --jq '.[] | select(.files[].path == "FormalConjectures/ErdosProblems/939.lean")
        | "\(.number) \(.title)"'
```

Read the diff of anything that comes back with `gh api repos/OWNER/REPO/pulls/N/files
--paginate`. `gh pr diff` returns nothing for a large pull request.

Reporting a defect that someone is already fixing wastes a maintainer's time. If a pull request
already makes the change, still report the findings in full, then say which one covers them and
what it misses. "See #4934" alone gives the contributor nothing to check. Read its diff rather
than its title: a title that names the problem is luck, not evidence. Two open pull requests
that touch the same lines will conflict, and saying so is worth a finding.

## Step 1: take the automatic checks as given

```bash
lake --wfail build 'FormalConjectures.ErdosProblems.«N»'   # each module in scope
python3 scripts/check_erdos_status.py                       # only for ErdosProblems/
```

Run every `lake` command from the repository root. From anywhere else it reports a missing
default toolchain, which reads as a broken install rather than a wrong directory.

Outside `ErdosProblems/`, build the module in scope and skip the status script. It only knows
about Erdős problems, and skipping it is not a skipped check.

If a module does not build, report that and stop.

`--wfail` runs the repository's own linters, including the category and `answer` ones, because
they are `leanOptions` in `lakefile.toml`. A clean module build therefore covers them, and you
do not need `check_category_warnings.py`, which takes an `extract_names` dump and needs the
whole repository built.

`check_erdos_status.py` prints a JSON array of every mismatch in the repository. Match your
problem against the `number` field, not with a bare grep, which also hits line numbers and
other fields. Absence is the pass. The `WARNING: unrecognized YAML status state` lines are
expected noise and are not a check failure.

The script compares a file against the site's single status for the whole problem. A file with
several variants can carry one whose status the source contradicts while the script stays
silent, so passing it is not evidence about any individual variant.

## Step 2: read every definition the statement uses

Do this before you read the Lean statement closely. Most findings turn on a definition, and
most false findings come from assuming one.

Look up each name the statement mentions in `FormalConjecturesForMathlib/` or Mathlib, and ask
what it does at its degenerate values. The *Check the degenerate cases* table in `AGENTS.md`
lists the ones that recur. Two more from this repository:

- `Nat.Full k n` is `∀ p ∈ n.primeFactors, p ^ k ∣ n`, and `primeFactors 0 = ∅`, so `0` and `1`
  are vacuously Full. `decide` cannot settle it: the `Decidable` instance exists but does not
  reduce, and gets stuck on `List.decidableBAll` over `primeFactorsList`. Use the lemmas in
  `FormalConjecturesForMathlib/Data/Nat/Full.lean`, which ships `Full.zero_right`,
  `Full.one_right` and a `primeFactorsEq` dsimproc, or `norm_num [Nat.Full, Nat.primeFactors,
  Nat.primeFactorsList]`, which needs a raised `maxRecDepth`.
- `Finset.Coprime S` is `S.gcd id = 1`, the gcd of the whole set. It is not pairwise, so a set
  containing `1` is coprime whatever else it holds. Before you propose making it pairwise, check
  the source's own example: for Erdős 939 that example is not pairwise coprime, so the change
  would break it.

## Step 3: read the cited source

Open the source the module docstring cites. Do not review the Lean against the docstring alone.
The docstring is also under review, and a docstring that disagrees with its own Lean is itself
a finding.

For an Erdős problem, read `https://www.erdosproblems.com/latex/<n>`. That is still a full HTML
page, but the LaTeX is unrendered inside it: the statement sits in the `#content` div and the
remarks in `problem-additional-text`. The site refuses a request that does not identify itself, so a
web fetch tool and the default `Python-urllib` user agent both get a 403 while `curl`
succeeds. Send a user agent that names you. Do not imitate a browser, and do not conclude from
the 403 that the source is unreadable: a reviewer who gives up there reconstructs the statement
from a neighbouring problem file, which is how a wrong bound gets copied instead of caught.

The `teorth/erdosproblems` YAML that `check_erdos_status.py` reads carries status and tags
only, and no statement text, so it is not the source.

For a paper, a fetch returns raw PDF bytes. Save the file and run `pdftotext -layout` on it.

**Read the whole document, and check its date.** A source revises, and a later section can
close a question its own earlier section calls open. Read the remarks, the postscripts and any
addendum, and compare the source's early status claims against its later ones. A reviewer who
reads the problem statement and stops will pass a file that records a settled question as open.

Then compare the source's revision date against the date the file landed, with
`git log -1 --format=%as -- <path>`. A file older than the revision is where this defect lives.

Follow the source's own cross-references. When a page says "see also [1107]", open that
problem and the file that formalises it. A wrong bound is often a correct bound copied from a
neighbour whose statement differs by one.

Distinguish a result in the literature from a claim in the site's comments. Both can be true,
and only the first supports `research solved`. Report a comment-level claim as a question.

Quote formulas from the LaTeX source rather than the rendered page. Rendering runs terms
together: `3^7\cdot 61^5` reads as `3761^5`, and that misreading is already in this repository.
When there is no LaTeX, as for a PDF-only paper, do not trust the extracted formula at all.
`pdftotext` drops overlines and splits sentences across them. Compute the identity instead.

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

Two things are sanctioned and are not defects. Do not report either. `answer(sorry) ↔ ∀ᵉ ...`,
with the answer slot outside the binders, is the shape the `AnswerLinter` recommends. And a
`sorry` under `research solved` records a result known in the literature.

## Step 5: report

Each finding **must** carry a witness: checkable evidence, which is usually a concrete case
where the Lean and the source disagree. Not every class produces a disagreement of that shape.
A `formal_proof` link that names no file, or points at a `sorry`, is a defect whose witness is
what the linked repository contains.

Check the witness in Lean where you can, with `lake env lean` on a scratch file outside the
tree that imports the module. Run it from the repository root, or `lake` reports a missing
default toolchain, which looks like a broken install rather than a wrong directory. The scratch
file will trip `linter.style.moduleDocstring`. That warning is expected.

**A contradiction derived from a `sorry` proves nothing.** Almost every statement here is
`sorry`, so a witness that uses one inherits it. Run `#print axioms` on your witness and say
where each `sorryAx` comes from. "The only `sorryAx` is the cited declaration's, not my proof's"
is the claim that makes the witness mean something.

**Write the positive control.** This is the instruction that repays the most effort. Encode the
source's own construction, run it against the Lean predicate, and check that it satisfies it.
That is what lets you write "the definition is faithful" instead of "the definition reads
correctly", and it is the difference between reporting what a source claims and reporting what
you checked. Run a negative control too, on a case the source excludes.

If the paper ships code, fetch and run the paper's own program rather than reimplementing the
construction. A search you write yourself may not terminate on the smallest interesting case.
Then enumerate that smallest case exhaustively.

The control is not always reachable in Lean. `Equiv.Perm.IsCycle` has no `Decidable` instance,
for one. Running the control outside Lean, against your own transcription of the definitions,
is a fair fallback, but it tests your reading of the Lean rather than the Lean. Say which one
you did.

Say what the witness shows, and also what it does not show. A finding that claims too much
costs a reviewer more time than no finding.

A finding looks like this. The declaration below is invented, so that the shape is the only
thing you take from it:

> **`erdos_N.variants.small_cases`, N.lean:62** — quantifies over `k ≥ 1`.
> The source opens "Let $k \geq 2$". At `k = 1` the hypothesis holds for every input, so the
> statement asserts something about all of `ℕ` that `erdos_N.variants.base`, in the same file
> and `research solved`, contradicts. Both cannot hold.
> *Shows*: the `k = 1` conjunct is false, so the answer is forced for a reason the source
> excludes. *Does not show*: anything about `k ≥ 2`, which is the real question.
> *Suggested change*: `∀ k ≥ 2`, and say so in the docstring.

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
- whether the conjecture is true
- whether to merge
