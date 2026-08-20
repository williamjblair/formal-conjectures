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

import FormalConjectures.ErdosProblems.«479»

/-!
# Tests for Erdős Problem 479

This proves the natural-number case added when the guard is corrected from `k > 1` to `k ≠ 1`.
-/

namespace Erdos479Test

theorem zero_case : {n : ℕ | 2 ^ n ≡ 0 [MOD n]}.Infinite := by
  apply Set.infinite_of_injective_forall_mem (f := fun m : ℕ ↦ 2 ^ m)
    (Nat.pow_right_injective (by norm_num))
  intro m
  apply Nat.modEq_zero_iff_dvd.mpr
  apply pow_dvd_pow
  induction m with
  | zero => simp
  | succ m ih =>
      rw [pow_succ]
      have := Nat.one_le_two_pow (n := m)
      omega

end Erdos479Test
