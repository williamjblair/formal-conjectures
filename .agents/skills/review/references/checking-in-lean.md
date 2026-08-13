# Checking a witness in Lean

Read this when you are about to build a witness or a control. `defect-classes.md` says what to
look for. This says how to check it, and it is mostly a list of traps that have cost real time.

## The scratch file

Write it outside the tree and import the module under review.

```bash
cd <repository root>
lake env lean /path/to/scratch/Witness.lean
```

Run `lake` from the repository root and pass an absolute path. Never `cd` elsewhere, including
inside a compound command: the working directory persists into the next call, and `lake` then
reports `no default toolchain configured`, which reads as a broken install rather than a wrong
directory. This has caught three separate reviews, each after reading the warning.

Two warnings are expected and are not failures. `linter.style.moduleDocstring` fires once for the
file. A file with more than one `/-! ... -/` section trips a second, differently worded variant
once per extra section.

## Axioms, and where a `sorry` came from

Almost every statement in this repository is `sorry`. A witness that uses one inherits it, so a
contradiction derived from two `sorry`s says nothing at all.

Run `#print axioms` on every witness and report what it returns. The useful shape is to split the
proof so the general part is clean:

```lean
theorem helper : ... := by ...          -- [propext, Classical.choice, Quot.sound]
theorem application : False := helper (TheSorriedDeclaration ...)
                                        -- [propext, sorryAx, Classical.choice, Quot.sound]
```

Then you can say: the only `sorryAx` is the cited declaration's, not mine. That is the claim that
makes the witness mean something, and it is worth restructuring a proof to be able to make it.

## Refute by proving the negation

Better than deriving a contradiction from a `sorry`ed declaration: prove its negation outright,
so nothing in your chain touches the file's `sorry`.

That leaves one gap. A reader has to trust that the statement you negated is the one in the tree.
Close it by elaborating the declaration against your transcription:

```lean
example : <the statement you wrote out> := fun x => TheDeclaration x
```

If that type-checks, your transcription is the real thing. Without it, a `sorry`-free refutation
is still only a transcription you might have got wrong.

## What actually reduces

`decide` fails more often than you expect, and the failure is usually a stuck instance rather
than a real obstruction.

| | |
|---|---|
| `Nat.Full` | has a `Decidable` instance that does not reduce; it gets stuck on `List.decidableBAll` over `primeFactorsList`. Use `Full.zero_right`, `Full.one_right` and the `primeFactorsEq` dsimproc in `FormalConjecturesForMathlib/Data/Nat/Full.lean`, or `norm_num [Nat.Full, Nat.primeFactors, Nat.primeFactorsList]` with `set_option maxRecDepth 4000`; the default 512 fails |
| `Equiv.Perm.IsCycle` | no instance, but a Hamiltonian cycle encodes as a nodup `List`, and `List.formPerm`, `List.isCycle_formPerm` and `List.support_formPerm_of_nodup` give a kernel-checked witness |
| `Collinear ℝ` | no instance. Three integer points are collinear exactly when the integer cross product vanishes, so a control runs outside Lean and you say so |
| `sInf ∅` emptiness | show the set is `∅` with `ext m; simp`, then `simpa [f] using congrArg sInf h`. Watch for `simp` closing the goal without using your hypothesis; the `unusedSimpArgs` linter is what catches that, and without it you ship a witness that proves nothing about the case you meant |

Before you give up on Lean, look for the constructive encoding. A missing instance is not the end
of the road.

## Finding the lemma

Names in `FormalConjecturesForMathlib` are hard to guess, and the namespace structure is not what
it looks like. `Nat.hasDensity_zero_of_finite` sits inside `namespace Set`, but `end Set.HasDensity`
closes `Set` first, so it is not `Set.Nat.*`. Grep the `namespace` and `end` lines of the file
before guessing a full name.

Two gaps that have each cost a review most of its time:

- **`Set.HasDensity` has no complement and no cofinite lemma.** The natural witness, that a
  cofinite set cannot have density `0`, needs `partialDensity S b + partialDensity Sᶜ b = 1`
  proved from the definition. Budget for it, and consider upstreaming the result.
- **An `sSup` bound does not instantiate for free.** A lemma bounding `sSup S` gives you nothing
  about a particular member until you have `BddAbove S`, because an unbounded `sSup` over `ℕ` is
  `0`. A statement about a degenerate definition can be weaker than it reads.

## Controls that finish

A control that does not terminate is not evidence.

If the paper ships code, fetch and run the paper's own program rather than reimplementing the
construction. A search you write yourself may not terminate on the smallest interesting case,
and this is not hypothetical: an annealing search for one even case ran hundreds of thousands of
iterations and found nothing, while the paper's own program produced it immediately.

For a density or coverage sieve, hold the sieve as one big integer and use shifts with
`.bit_count()`. Indexing it bit by bit is quadratic and will time out around `10^7`.
