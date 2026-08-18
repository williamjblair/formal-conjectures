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
import Mathlib.Analysis.SpecialFunctions.Log.Basic

/-!
# Erdős Problem 461

*References:*
- [erdosproblems.com/461](https://www.erdosproblems.com/461)
- [ErGr80, p.92] Erdős, P. and Graham, R., *Old and new problems and results in combinatorial
  number theory*. Monographies de L'Enseignement Mathématique 28 (1980).
-/

open Finset BigOperators

namespace Erdos461

/-- The $t$-smooth component of $n$. -/
noncomputable def smoothComponent (t n : ℕ) : ℕ :=
  (n.factorization.support.filter (· < t)).prod
    (fun p => p ^ n.factorization p)

/-- The number of distinct $t$-smooth components among the integers from $n+1$ through $n+t$. -/
noncomputable def f (n t : ℕ) : ℕ :=
  ((Finset.Icc (n + 1) (n + t)).image (smoothComponent t)).card

/-- The empty interval contributes no smooth components. -/
@[category test, AMS 11]
theorem f_empty_interval (n : ℕ) : f n 0 = 0 := by
  simp [f]

/-- A one-element interval contributes one distinct smooth component. -/
@[category test, AMS 11]
theorem f_singleton_interval (n : ℕ) : f n 1 = 1 := by
  simp [f]

/--
Let $s_t(n)$ be the $t$-smooth component of $n$ - that is, the product of all primes $p$ (with
multiplicity) dividing $n$ such that $p<t$. Let $f(n,t)$ count the number of distinct possible
values for $s_t(m)$ for $m\in [n+1,n+t]$. Is it true that
$$f(n,t)\gg t$$
(uniformly, for all $t$ and $n$)?
-/
@[category research open, AMS 11]
theorem erdos_461 :
    answer(sorry) ↔
      ∃ c : ℝ, 0 < c ∧ ∀ n t : ℕ, (f n t : ℝ) ≥ c * (t : ℝ) := by
  sorry

/--
Erd\H{o}s and Graham report they can show
$$f(n,t) \gg \frac{t}{\log t}.$$
-/
@[category research solved, AMS 11]
theorem erdos_461.variants.erdos_graham :
    ∃ c : ℝ, 0 < c ∧ ∀ n t : ℕ, 2 ≤ t →
      (f n t : ℝ) ≥ c * ((t : ℝ) / Real.log (t : ℝ)) := by
  sorry

end Erdos461
