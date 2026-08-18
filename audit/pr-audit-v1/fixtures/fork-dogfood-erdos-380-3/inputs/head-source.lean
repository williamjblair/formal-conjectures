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
# Erdős Problem 380

*References:*
- [erdosproblems.com/380](https://www.erdosproblems.com/380)
- [ErGr80] Erdős, P. and Graham, R., *Old and new problems and results in combinatorial number
  theory*, Monographies de l'Enseignement Mathématique (1980), p. 73.
- [Ta26c] Tao, T., *Products of consecutive integers with unusual anatomy*,
  [arXiv:2603.27990](https://arxiv.org/abs/2603.27990) (2026).

OEIS sequences: [A070003](https://oeis.org/A070003), [A388654](https://oeis.org/A388654),
[A387054](https://oeis.org/A387054), [A389100](https://oeis.org/A389100).
-/

open Filter Asymptotics BigOperators

namespace Erdos380

/-- The product of the integers in the interval $[u,v]$. -/
def intervalProduct (u v : ℕ) : ℕ :=
  ∏ m ∈ Finset.Icc u v, m

/-- An interval is bad when the square of the greatest prime factor of its product divides it. -/
def IsBadInterval (u v : ℕ) : Prop :=
  1 ≤ u ∧ u ≤ v ∧ (Nat.maxPrimeFac (intervalProduct u v)) ^ 2 ∣ intervalProduct u v

/-- A positive integer is contained in a bad interval. -/
def InBadInterval (n : ℕ) : Prop :=
  ∃ u v, u ≤ n ∧ n ≤ v ∧ IsBadInterval u v

/-- The number of positive integers at most $x$ contained in a bad interval. -/
noncomputable def B (x : ℕ) : ℕ :=
  Set.ncard {n : ℕ | 1 ≤ n ∧ n ≤ x ∧ InBadInterval n}

/-- The number of positive integers at most $x$ divisible by the square of their greatest prime factor. -/
noncomputable def squareDivCount (x : ℕ) : ℕ :=
  Set.ncard {n : ℕ | 1 ≤ n ∧ n ≤ x ∧ (Nat.maxPrimeFac n) ^ 2 ∣ n}

/--
We call an interval $[u,v]$ 'bad' if the greatest prime factor of
$\prod_{u\leq m\leq v}m$ occurs with an exponent greater than $1$. Let $B(x)$ count the number of
$n\leq x$ which are contained in at least one bad interval. Is it true that
$$B(x)\sim \#\{ n\leq x: P(n)^2\mid n\},$$
where $P(n)$ is the largest prime factor of $n$?

This has been solved in the affirmative; see [Ta26c].
-/
@[category research solved, AMS 11]
theorem erdos_380 : answer(True) ↔
    (fun x : ℕ ↦ (B x : ℝ)) ~[atTop] (fun x : ℕ ↦ (squareDivCount x : ℝ)) := by
  sorry

/-- An interval is very bad when its product is powerful. -/
def IsVeryBadInterval (u v : ℕ) : Prop :=
  1 ≤ u ∧ u ≤ v ∧ Nat.Powerful (intervalProduct u v)

/-- A positive integer is contained in a very bad interval. -/
def InVeryBadInterval (n : ℕ) : Prop :=
  ∃ u v, u ≤ n ∧ n ≤ v ∧ IsVeryBadInterval u v

/-- The number of positive integers at most $x$ contained in a very bad interval. -/
noncomputable def veryBadCount (x : ℕ) : ℕ :=
  Set.ncard {n : ℕ | 1 ≤ n ∧ n ≤ x ∧ InVeryBadInterval n}

/-- The number of positive powerful integers at most $x$. -/
noncomputable def powerfulCount (x : ℕ) : ℕ :=
  Set.ncard {n : ℕ | 1 ≤ n ∧ n ≤ x ∧ Nat.Powerful n}

/--
Similarly, we call an interval $[u,v]$ 'very bad' if
$\prod_{u\leq m\leq v}m$ is powerful. The number of integers $n\leq x$ contained in at least one
very bad interval should be asymptotic to the number of powerful numbers $\leq x$.

This has been solved in the affirmative; see [Ta26c].
-/
@[category research solved, AMS 11]
theorem erdos_380.variants.very_bad : answer(True) ↔
    (fun x : ℕ ↦ (veryBadCount x : ℝ)) ~[atTop] (fun x : ℕ ↦ (powerfulCount x : ℝ)) := by
  sorry

@[category test, AMS 11]
theorem erdos_380.test.bad_interval_zero : ¬ IsBadInterval 0 0 := by
  simp [IsBadInterval]

@[category test, AMS 11]
theorem erdos_380.test.bad_interval_one : ¬ IsBadInterval 1 1 := by
  simp [IsBadInterval, intervalProduct]

@[category test, AMS 11]
theorem erdos_380.test.empty_interval : ¬ IsBadInterval 2 1 := by
  simp [IsBadInterval]

@[category test, AMS 11]
theorem erdos_380.test.source_positive_bad_24_25 : IsBadInterval 24 25 := by
  classical
  have hmax : Nat.maxPrimeFac 600 = 5 := by
    have hbdd : BddAbove {p : ℕ | p.Prime ∧ p ∣ 600} := by
      refine ⟨600, ?_⟩
      intro p hp
      exact Nat.le_of_dvd (by norm_num) hp.2
    have hne : {p : ℕ | p.Prime ∧ p ∣ 600}.Nonempty := by
      exact ⟨5, by norm_num⟩
    have hdiv : Nat.maxPrimeFac 600 ∣ 600 := (Nat.sSup_mem hne hbdd).2
    have hp : Nat.Prime (Nat.maxPrimeFac 600) :=
      Nat.prime_maxPrimeFac_of_one_lt 600 (by norm_num)
    have hle5 : Nat.maxPrimeFac 600 ≤ 5 := by
      have hfactor : 600 = 2 ^ 3 * 3 * 5 ^ 2 := by norm_num
      have hdiv' : Nat.maxPrimeFac 600 ∣ 2 ^ 3 * 3 * 5 ^ 2 := by
        rwa [← hfactor]
      rcases (hp.dvd_mul.mp hdiv') with h23 | h5
      · rcases (hp.dvd_mul.mp h23) with h2pow | h3
        · have h2 : Nat.maxPrimeFac 600 ∣ 2 := hp.dvd_of_dvd_pow h2pow
          exact le_trans (Nat.le_of_dvd (by norm_num) h2) (by norm_num)
        · exact le_trans (Nat.le_of_dvd (by norm_num) h3) (by norm_num)
      · have h5' : Nat.maxPrimeFac 600 ∣ 5 := hp.dvd_of_dvd_pow h5
        exact Nat.le_of_dvd (by norm_num) h5'
    exact le_antisymm hle5 (by
      have h5 : 5 ≤ Nat.maxPrimeFac 600 := by
        exact le_csSup hbdd ⟨by norm_num, by norm_num⟩
      exact h5)
  have hprod : intervalProduct 24 25 = 600 := by decide
  rw [show IsBadInterval 24 25 =
      (1 ≤ 24 ∧ 24 ≤ 25 ∧
        (Nat.maxPrimeFac (intervalProduct 24 25)) ^ 2 ∣ intervalProduct 24 25) by rfl]
  rw [hprod, hmax]
  norm_num

@[category test, AMS 11]
theorem erdos_380.test.source_positive_very_bad_8_9 : IsVeryBadInterval 8 9 := by
  have hprod : intervalProduct 8 9 = 72 := by decide
  rw [show IsVeryBadInterval 8 9 =
      (1 ≤ 8 ∧ 8 ≤ 9 ∧ Nat.Powerful (intervalProduct 8 9)) by rfl]
  rw [hprod]
  decide +native

@[category test, AMS 11]
theorem erdos_380.test.very_bad_interval_zero : ¬ IsVeryBadInterval 0 0 := by
  simp [IsVeryBadInterval]

end Erdos380
