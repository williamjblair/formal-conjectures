/-
Copyright 2026 The Formal Conjectures Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-/

import FormalConjecturesUtil

/-!
# Minimum modulus for the unique multiset-sum problem

*References:*
- [arxiv/2607.08366](https://arxiv.org/abs/2607.08366)
  **Minimum modulus for the unique multiset-sum problem**
  by *José A. R. Fonollosa*
- [jarfo/min-modulus](https://github.com/jarfo/min-modulus), the author's Lean development of
  the paper's Main Theorem. Section 7 of the paper describes it.

The paper's Main Theorem and its Conjecture 1 differ in what they quantify over. Theorems A
and B fix the super-increasing set $\{2^k - 1\}$ and prove that the least modulus at which
*that set* is valid is $2^n - 2^{\lfloor\log_2 n\rfloor}$ for every $n \geq 2$; Conjecture 1
says that no other set of $n$ residues is valid below that modulus, and is open.
-/

open Finset

namespace Arxiv.«2607.08366»

variable {N : ℕ}

/-- `A` is *valid mod* `N` when the all-ones multiset is the only multiset of size `#A` drawn
from `A` whose sum matches `∑ a ∈ A, a`.

`m a` is how many copies of `a` the multiset uses, so the all-ones multiset is `m = 1`. -/
def IsValidMod (A : Finset (ZMod N)) : Prop :=
  ∀ m : ZMod N → ℕ, ∑ a ∈ A, m a = #A → ∑ a ∈ A, (m a : ZMod N) * a = ∑ a ∈ A, a →
    ∀ a ∈ A, m a = 1

/-- The least modulus admitting a valid set of `n` residues, conjecturally
$2^n - 2^{\lfloor\log_2 n\rfloor}$. -/
def minModulus (n : ℕ) : ℕ := 2 ^ n - 2 ^ (Nat.log 2 n)

/--
**Conjecture 1 (Fonollosa, 2026).** For every $n \geq 2$ and every
$N < 2^n - 2^{\lfloor \log_2 n\rfloor}$, no set of $n$ residues mod $N$ is valid.

Equivalently the super-increasing set $\{2^k - 1 : 0 \leq k \leq n-1\}$ attains the least
valid modulus, which is `minModulus n`.

The hypothesis $0 < N$ is needed: `minModulus 2 = 2`, so the range includes $N = 0$, where
`ZMod 0` is $\mathbb{Z}$ rather than a finite modulus and $\{1, 2\} \subseteq \mathbb{Z}$ is
valid. No guard is needed at $N = 1$, since `ZMod 1` is trivial and so has no subset of size
$n \geq 2$.
-/
@[category research open, AMS 5 11]
theorem min_modulus :
    answer(sorry) ↔ ∀ n N : ℕ, 2 ≤ n → 0 < N → N < minModulus n →
      ∀ A : Finset (ZMod N), #A = n → ¬ IsValidMod A := by
  sorry

/--
**Theorem A (Fonollosa, 2026).** The bound `minModulus n` is attained: the super-increasing
set $\{2^k - 1 : 0 \leq k \leq n - 1\}$ is valid mod $2^n - 2^{\lfloor\log_2 n\rfloor}$.

This bounds the least modulus admitting a valid set of $n$ residues from above only; that no
smaller modulus admits one is the open half, stated in `min_modulus`. The linked development
proves this as `theoremA` in `MinModulus/UniqueSums.lean`.
-/
@[category research solved, AMS 5 11,
  formal_proof using lean4 at "https://github.com/jarfo/min-modulus"]
theorem exists_isValidMod_minModulus (n : ℕ) (hn : 2 ≤ n) :
    ∃ A : Finset (ZMod (minModulus n)), #A = n ∧ IsValidMod A := by
  sorry

/-- The all-ones multiset always has the right size and the right sum, so `IsValidMod` is a
uniqueness statement rather than an existence one. -/
@[category API, AMS 5 11]
theorem one_sum_eq (A : Finset (ZMod N)) :
    ∑ _a ∈ A, (1 : ℕ) = #A ∧ ∑ a ∈ A, ((1 : ℕ) : ZMod N) * a = ∑ a ∈ A, a :=
  ⟨by simp, by simp⟩

/-- A set with fewer than two elements is valid for a silly reason, so the conjecture asks
about `2 ≤ n`: with `#A ≤ 1` the only multiset of size `#A` drawn from `A` is the all-ones one. -/
@[category API, AMS 5 11]
theorem isValidMod_of_subsingleton {A : Finset (ZMod N)} (hA : #A ≤ 1) : IsValidMod A := by
  intro m hsize _ a ha
  rcases Finset.card_le_one.mp hA with h
  have : A = {a} := Finset.eq_singleton_iff_unique_mem.mpr ⟨ha, fun b hb => h b hb a ha⟩
  subst this
  simpa using hsize

end Arxiv.«2607.08366»
