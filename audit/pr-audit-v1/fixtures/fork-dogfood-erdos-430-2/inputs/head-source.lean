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
# Erdős Problem 430

*References:*
- [erdosproblems.com/430](https://www.erdosproblems.com/430)
- [erdosproblems.com/385](https://www.erdosproblems.com/385)
- [ErGr80] Erdős, P. and Graham, R., *Old and new problems and results in combinatorial number
  theory*. Monographies de L'Enseignement Mathématique (1980).
-/

namespace Erdos430

open Filter

/--
The next term in the greedy sequence for Erdős Problem 430.  The value `0` records that the
sequence has terminated.  The source's example for `n = 8` stops after `7, 5`; accordingly,
continuing terms are required to be at least `2`, rather than treating `1` as an admissible
vacuous prime-factor condition.  For reachable terms `m < n`, the condition
`n < m + m.minFac` says that the least prime factor of `m` is greater than `n - m`, and hence
that all prime factors of `m` are greater than `n - m`.
-/
def nextTerm (n prev : ℕ) : ℕ :=
  let S := (Finset.Ico 2 prev).filter (fun m => n < m + m.minFac)
  if h : S.Nonempty then S.max' h else 0

/-- The sequence starts at `n - 1` and repeatedly takes `nextTerm`. -/
def seq (n : ℕ) : ℕ → ℕ
  | 0 => n - 1
  | k + 1 => nextTerm n (seq n k)

@[category test, AMS 11]
theorem nextTerm_eight : nextTerm 8 7 = 5 := by
  decide +kernel

@[category test, AMS 11]
theorem nextTerm_eight_stop : nextTerm 8 5 = 0 := by
  decide +kernel

@[category test, AMS 11]
theorem nextTerm_zero_prev (n : ℕ) : nextTerm n 0 = 0 := by
  simp [nextTerm]

@[category test, AMS 11]
theorem seq_eight : seq 8 0 = 7 ∧ seq 8 1 = 5 ∧ seq 8 2 = 0 := by
  decide +kernel

@[category test, AMS 11]
theorem seq_small : seq 0 0 = 0 ∧ seq 1 0 = 0 := by
  decide +kernel

/--
Fix some integer $n$ and define a decreasing sequence in $[1,n)$ by $a_1=n-1$ and, for
$k\geq 2$, letting $a_k$ be the greatest integer in $[1,a_{k-1})$ such that all of the prime
factors of $a_k$ are $>n-a_k$.
Is it true that, for sufficiently large $n$, not all of this sequence can be prime?

Erdős and Graham write 'preliminary calculations made by Selfridge indicate that this is the
case but no proof is in sight'. For example if $n=8$ we have $a_1=7$ and $a_2=5$ and then must
stop.
Sarosh Adenwalla has observed that this problem is equivalent to (the first part of) [385].
Indeed, assuming a positive answer to that, for all large $n$, there exists a composite $m<n$
such that all primes dividing $m$ are $>n-m$. It follows that such an $m$ is equal to some
$a_i$ in the sequence defined for $[1,n)$, and $m$ is composite by assumption.
-/
@[category research open, AMS 11]
theorem erdos_430 :
    answer(sorry) ↔ ∀ᶠ n : ℕ in atTop, ∃ k : ℕ, (seq n k).Composite := by
  sorry

end Erdos430
