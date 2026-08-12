# Mathematical Review Guide

This is a guide for the second pass over a formalisation: does the Lean statement say what the
source says? It is written for a human reviewer or an agent doing an initial pass.

`AGENTS.md` covers the first pass, which is mechanical: attributes, naming, imports, build. This
file covers what is left, which is the part that needs judgement.

It is worth being clear about what this pass is not. A tool such as `leanprover/comparator` decides
whether a submitted proof establishes a given statement under a permitted set of axioms. That
question is mechanical and it is being automated. This guide is about the other question, whether
the statement is the right one, which no checker settles because the statement is the thing every
checker takes as given. The better the automated side becomes, the more this side carries.

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
repository.

Examples below are marked **confirmed** where the witness has been checked against the repository,
and **lead** where it has not. A lead is a place to look, not a finding. Treating one as settled is
the mistake this guide is trying to prevent, so it would be poor form for the guide to make it.

### 1. The statement does not match the source

Read the cited source, not the docstring. The docstring is part of what you are reviewing.

Check that the quantifiers, the direction of the inequality, the constants and the ranges all
match. Reversals are easy to miss, because the Lean statement reads fluently either way.

No confirmed instance is recorded yet. Open leads, all from #4896:

- *Green 72* (lead): the statement may assert that the extremal value is `2N`, where the source
  asks whether `2N` is eventually impossible.
- *Erdős 757* (lead): `IsAdmissible` may use `(B - B).ncard = 11` where the source has
  `11 ≤ (B - B).ncard`.
- *Erdős 1167* (lead): the module docstring records the source condition `κ α > r`, which the
  theorem may omit.

Confirming one of these means reading the cited paper. That is the work, and it is why this class
is the expensive one.

### 2. The hypotheses cannot be satisfied

A statement whose hypotheses are unsatisfiable is true and says nothing. This defect survives every
mechanical check, because such a file builds and its statement is well typed.

For each hypothesis, ask what must exist for it to hold, and whether anything does.

- *Erdős 80* (confirmed): `Admissible c G` required `c * n ^ 2 ≤ #G.edgeFinset`, but a simple graph
  on `n` vertices has at most `n * (n - 1) / 2` edges. At `c = 2` and `n = 100` that is 20000
  required against 4950 available. For `c ≥ 1/2` nothing qualifies, so the set is empty,
  `sInf ∅ = 0`, and both `research open` statements were false. Reported in #4867, fixed in #4877.
- *Erdős 694* (lead): the hypotheses assume a greatest and a least element of every totient fibre,
  and the fibre over `3` is empty. (#4896)

### 3. Degenerate boundary cases

Check the smallest value of every bound.

- *Erdős 940* (confirmed): `large_integers` quantifies over `r ≥ 2`. At `r = 2` it asserts that
  eventually every integer is a sum of at most two `2`-powerful numbers, so that set is cofinite.
  `erdos_940.variants.two`, in the same file and categorised `research solved`, states that the
  same set has density `0`. The two cannot both hold.
- *Green 21* (confirmed): `fox_kleitman_modular` admits `k = 0`. There the hypothesis holds
  vacuously, the only `x : Fin 0 → (ZMod p)ˣ` makes the antecedent vacuous, and the conclusion
  reduces to `(0 : ZMod p) ≠ 0`. So no `f` works and the answer is forced to `False`, for a reason
  unrelated to the question.
- *Erdős 939* (confirmed, and weaker than it looks): `Nat.Full k n` is
  `∀ p ∈ n.primeFactors, p ^ k ∣ n`, and `primeFactors 0 = ∅`, so `0` and `1` are vacuously Full.
  Hence `{0, 1} ∈ Erdos939Sums 4`. But the theorem quantifies over all `r ≥ 4`, and at `r = 5` a
  set of three pairwise-coprime Full numbers cannot contain `0`, since `gcd 0 x = x`. The witness
  settles one case and does not collapse the statement.

That last one is the shape to imitate. Report what the witness establishes and what it does not.
A finding that overstates its own reach costs a reviewer more time than no finding at all.

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
determine makes the statement provable by `rfl` and settles nothing. Two leads in #4896:
*Erdős 195* may admit `answer (sSup S) = sSup S`, and *Erdős 887* `parts.i` may place the answer
term inside the binders, where it can be instantiated pointwise.

Also check scope: an `answer` inside a binder is a different claim from one outside it.

### 6. What a `formal_proof` link establishes, until comparator does it

This section describes the interim state. `leanprover/comparator` answers this question
mechanically: it builds a submitted proof in a sandbox, checks that it proves the trusted statement
and no other, and enforces a `permitted_axioms` list. Where a proof has been through comparator,
read its verdict and skip this section.

Comparator does not settle the classes above. It takes the statement as given, so a machine-checked
proof of a statement that misformalises its source is a machine-checked proof of the wrong thing.
Sections 1 to 5 are what protect its trusted side.

Meanwhile the repository holds around 330 links that predate any of this, and each is a claim that
a proof of *this statement* exists somewhere. Three things go wrong.

**The proof assumes something unproved** (confirmed). A file can be `sorry`-free and still
establish the statement only under an axiom the author declared. `#print axioms` on a proof that
takes its assumption as a hypothesis comes back clean, so this is not visible from the proof term.
Erdős 427, 750 and 1141 each link a `sorry`-free proof that declares a published theorem as an
`axiom`: Shiu's theorem, Stiebitz's theorem, and Pollack's Theorem 1.3 with Mertens' third. These
now carry `conditional formal_proof ... assuming <decl>`, which names the assumption as a Lean
declaration rather than as a bare axiom name. That is the one thing this records which comparator's
`permitted_axioms` does not. See #4881.

**The link does not name a file** (confirmed). A repository root, a commit page or a discussion
thread does not tell a reader which file to open, and no check can read it. 18 links were in this
state. One pointed at `FormalizedFormalLogic/Foundation`, which no longer contains any modal logic,
so a link checker would have called it healthy while a reader found nothing. See #4895.

**The kind is wrong** (confirmed). A proof that lives in this repository takes
`formal_proof using formal_conjectures at ""`, not a `lean4` link pointing at the file itself.
Erdős 316 and 399 each linked their own file. See #4883.

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
