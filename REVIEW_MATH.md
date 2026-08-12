# Mathematical Review Guide

This is a guide for the second pass over a formalisation: does the Lean statement say what the
source says? It is written for a human reviewer or an agent doing an initial pass.

`AGENTS.md` covers the first pass, which is mechanical: attributes, naming, imports, build. This
file covers what is left, which is the part that needs judgement.

## What this pass is

A review under this guide produces **recommendations**. It does not decide whether a pull request
is merged. A contributor is free to disagree with a finding and ask a maintainer to make the call.

A finding is only useful if a reader can check it without redoing the review. So every finding
carries a **witness**: a concrete instantiation under which the Lean statement and the source
disagree. "This looks too strong" is not a finding. "At `c = 2` and `n = 100` the hypothesis needs
20000 edges and a simple graph has at most 4950, so the set is empty and `sInf ∅ = 0`" is a
finding.

## Run the deterministic checks first

Do not spend attention on anything a script already decides. Read the output of the build and the
existing checks before reading the statement, and take those results as given:

| Question | Where the answer already is |
| --- | --- |
| Does it build, and is it `sorry`-free? | `lake build`, and `hasSorryFreeProof` in the extract |
| Does every statement have `category` and `AMS`? | `extract_names`, and the category linter |
| Is a `research open` statement secretly proved? | the category linter warns on this |
| Does a `formal_proof` link resolve? | `scripts/check_proof_links.py` |
| Does the repo agree with erdosproblems.com? | `scripts/check_erdos_status.py` |
| Is a hypothesis binder unused? | the `unusedArguments` linter from Batteries |

If one of these is red, say so and stop. There is no point reviewing the mathematics of a file
that does not compile.

## The semantic pass

Work through these in order. Each is a class of defect that has actually occurred in this
repository, with a real instance named so you can see the shape.

### 1. The statement does not match the source

Read the cited source, not the docstring. The docstring is part of what you are reviewing.

Check that the quantifiers, the direction of the inequality, the constants and the ranges all
match. Reversals are common and easy to miss, because the Lean statement reads fluently either
way.

- *Green 72*: the statement appears to assert that the extremal value is `2N`, where the source
  asks whether `2N` is eventually impossible. The conclusion is reversed. (#4896)
- *Erdős 757*: `IsAdmissible` uses `(B - B).ncard = 11` where the source has `11 ≤ (B - B).ncard`.
  Equality rather than a bound changes the optimum. (#4896)
- *Erdős 1167*: the module docstring records the source condition `κ α > r`, and the theorem omits
  it. (#4896)

### 2. The hypotheses cannot be satisfied

A statement whose hypotheses are unsatisfiable is true and says nothing. This is the defect that
survives every mechanical check, because such a file builds and its statement is well typed.

For each hypothesis, ask what has to exist for it to hold, and whether anything does.

- *Erdős 80*: `Admissible c G` required `c * n ^ 2 ≤ #G.edgeFinset`, but a simple graph on `n`
  vertices has at most `n * (n - 1) / 2` edges. For `c ≥ 1/2` nothing qualifies, so the set is
  empty, `sInf ∅ = 0`, and both `research open` statements were false. Found by a contributor,
  fixed in #4877.
- *Erdős 694*: the hypotheses assume a greatest and a least element of every totient fibre. The
  fibre over `3` is empty, so the hypotheses are inconsistent and the wrapper is vacuous. (#4896)

### 3. Degenerate boundary cases

Check the smallest value of every bound. Off-by-one in the base case is the most common finding in
this repository.

- *Erdős 940*: `large_integers` quantifies over `r ≥ 2` where the intended range is `r ≥ 3`. At
  `r = 2` the conclusion contradicts a solved theorem in the same file. (#4896)
- *Green 21*: `fox_kleitman_modular` admits `k = 0`, where the hypotheses are vacuous but the
  conclusion asks `0 ≠ 0`. (#4896)
- *Erdős 939*: no positivity condition on the summands, so `{0, 1}` satisfies a statement the
  source intends for positive integers. (#4896)

### 4. Lean total functions returning junk

Lean functions are total, so a definition that looks partial silently returns a default outside its
intended domain. A statement can then be about the default rather than about the mathematics.

The ones that come up here:

| Expression | Value outside the intended domain |
| --- | --- |
| `sInf ∅`, `sSup ∅` on `ℕ` | `0` |
| `a - b` on `ℕ` when `b > a` | `0` |
| `x / 0` | `0` |
| `Matrix.inv` on a singular matrix | `0` |
| `SimpleGraph.minDegree` on an empty graph | `0` |
| `Nat.log`, `Nat.sqrt` at `0` | `0` |

Ask whether the statement can be satisfied by reaching one of these values rather than by the
mathematics. Erdős 80 above is the worked example: `sInf ∅ = 0` made the whole statement collapse.

### 5. `answer()` semantics

`answer(sorry)` marks the part of the problem that is unknown. Two failures recur.

**Polarity.** `answer(True) ↔ P` and `answer(False) ↔ P` say opposite things. Check the answer
against the source before checking anything else about the statement.

**Self-answer.** An `answer` term that can be instantiated with the thing it is supposed to
determine makes the statement provable by `rfl` and settles nothing. *Erdős 195* admits
`answer (sSup S) = sSup S`. *Erdős 887* `parts.i` places the answer term inside the binders, so it
can be instantiated pointwise and closed by reflexivity. (#4896)

Also check scope: an `answer` inside a binder is a different claim from one outside it.

### 6. What a `formal_proof` link actually establishes

A link is a claim that a proof of *this statement* exists somewhere. Three things go wrong.

**The proof assumes something unproved.** A file can be `sorry`-free and still establish the
statement only under an axiom the author declared. `#print axioms` on a proof that takes its
assumption as a hypothesis comes back clean, so this is not visible from the proof term. Erdős 427,
750 and 1141 each link a `sorry`-free proof that declares a published theorem as an `axiom`. These
now carry `conditional formal_proof ... assuming <decl>`, which names the assumption as a
declaration in the same file. See #4881.

**The link does not name a file.** A repository root, a commit page or a discussion thread does not
tell a reader which file to open, and no check can read it. See #4895.

**The kind is wrong.** A proof that lives in this repository takes
`formal_proof using formal_conjectures at ""`, not a `lean4` link pointing at the file itself. See
#4883.

When reviewing a linked proof, check the *declaration* rather than the file. A file that contains a
`sorry` on some other statement is normal; what matters is the declaration the link points at.

### 7. Variants

A variant is a claim about the same problem, so it inherits the same checks. Two extra questions:
does the variant's category match its actual status, and does a shared definition make a variant
weaker or stronger than its docstring says? A defect in a shared definition affects every statement
in the file at once.

## Reporting

Return concrete findings, not a score. For each finding give:

- the declaration name and the line
- what the source says, with a locator (theorem number, page, or a URL with an anchor)
- what the Lean says
- the witness: the instantiation under which they disagree
- a suggested fix, if you have one

Then one overall verdict:

- **CLEAN** — no findings.
- **ACCEPT WITH NITS** — findings that do not change what the statement means. Wording, a missing
  reference, a docstring that does not match the theorem.
- **NEEDS REVISION** — at least one finding that changes what the statement means, or that makes it
  vacuous, or that makes a `formal_proof` claim more than the linked proof establishes.

The verdict is advice about the statement. It is not a merge decision, and it is not a judgement
about the contributor.

## Out of scope

Do not report these under this guide:

- style, naming and formatting, which `AGENTS.md` and the linters cover
- proof golf on a `test` or `API` statement that already compiles
- a preference for a different but equivalent formalisation, unless the difference is observable
- whether the conjecture is true
- whether the pull request should be merged

## Uncertainty

Say when you are unsure. A finding you cannot produce a witness for is a question, not a finding,
and should be written as one. An audit that reports its own confidence honestly is worth more to a
reviewer than one that does not: see #4896, which labels its contents as triage leads rather than
confirmed bugs.

## Prior art

This guide draws on work by others in and around this repository. It cites that work rather than
copying from it, because [ryantuck/erdos-ai](https://github.com/ryantuck/erdos-ai) carries no
licence and this repository requires the CLA. If @ryantuck would like any of it brought over
directly, that is his to contribute.

- [`FABLE_REVIEW.md`](https://github.com/ryantuck/erdos-ai/blob/master/FABLE_REVIEW.md) in
  `ryantuck/erdos-ai`, which names the recurring Lean failure modes and has the reviewer audit the
  previous review rather than the statement alone
- [`ryantuck/formal-conjectures#1`](https://github.com/ryantuck/formal-conjectures/pull/1), a worked
  example of this kind of pass on Erdős 7, raised here by @franzhusch
- the verdict vocabulary suggested by @bocowgill in #4876
- the statement audit by @KitaKen1 in #4896, which is the source of most of the examples above
