/-
Copyright 2025 The Formal Conjectures Authors.

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

import FormalConjectures.ErdosProblems.Erdos686OrbitCases

/-! Unit reduction in `ℤ[∛2]` for Erdős Problem 686. -/

namespace Erdos686Reduction

open Erdos686Orbit

abbrev Vec3 := Vec ℤ

def stepN (x : Vec3) : Vec3 :=
  vec (-x 0 + 2 * x 2) (x 0 - x 1) (x 1 - x 2)

def stepM (x : Vec3) : Vec3 :=
  vec (x 0 + 2 * x 1 + 2 * x 2) (x 0 + x 1 + 2 * x 2) (x 0 + x 1 + x 2)

def iterN (k : ℕ) (x : Vec3) : Vec3 := (stepN^[k]) x

def iterM (k : ℕ) (x : Vec3) : Vec3 := (stepM^[k]) x

def norm (x : Vec3) : ℤ :=
  x 0 ^ 3 + 2 * x 1 ^ 3 + 4 * x 2 ^ 3 - 6 * x 0 * x 1 * x 2

noncomputable def rho : ℝ := (2 : ℝ) ^ ((3 : ℝ)⁻¹)

noncomputable def eval (x : Vec3) : ℝ :=
  x 0 + x 1 * rho + x 2 * rho ^ 2

noncomputable def eta : ℝ := 1 + rho + rho ^ 2

lemma stepN_eq_step : stepN = step ℤ := by
  funext x
  ext i
  fin_cases i <;>
    simp [stepN, step, nMat, vec, Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

lemma rho_cube : rho ^ 3 = 2 := by
  rw [rho]
  simpa using Real.rpow_inv_natCast_pow (x := (2 : ℝ)) (n := 3) (by positivity) (by norm_num)

lemma rho_pos : 0 < rho := by
  exact Real.rpow_pos_of_pos (by norm_num) _

lemma one_lt_rho : 1 < rho := by
  rw [rho]
  have h : (0 : ℝ) < (3 : ℝ)⁻¹ := by positivity
  simpa using Real.rpow_lt_rpow (by norm_num : (0 : ℝ) ≤ 1) (by norm_num : (1 : ℝ) < 2) h

lemma five_four_lt_rho : (5 : ℝ) / 4 < rho := by
  by_contra h
  have hle : rho ≤ (5 : ℝ) / 4 := le_of_not_gt h
  have hpow : rho ^ 3 ≤ ((5 : ℝ) / 4) ^ 3 := by
    exact pow_le_pow_left₀ rho_pos.le hle 3
  rw [rho_cube] at hpow
  norm_num at hpow

lemma rho_lt_thirteen_tenths : rho < (13 : ℝ) / 10 := by
  by_contra h
  have hle : (13 : ℝ) / 10 ≤ rho := le_of_not_gt h
  have hpow : ((13 : ℝ) / 10) ^ 3 ≤ rho ^ 3 := by
    exact pow_le_pow_left₀ (by norm_num) hle 3
  rw [rho_cube] at hpow
  norm_num at hpow

lemma rho_sq_lower : (25 : ℝ) / 16 < rho ^ 2 := by
  nlinarith [sq_nonneg (rho - 5 / 4)]

lemma rho_sq_upper : rho ^ 2 < (169 : ℝ) / 100 := by
  nlinarith [sq_nonneg (rho - 13 / 10)]

lemma eta_gt_one : 1 < eta := by
  rw [eta]
  nlinarith [rho_pos, sq_nonneg rho]

lemma eta_pos : 0 < eta := zero_lt_one.trans eta_gt_one

lemma eta_lt_four : eta < 4 := by
  rw [eta]
  nlinarith [rho_lt_thirteen_tenths, rho_sq_upper]

lemma stepM_stepN (x : Vec3) : stepM (stepN x) = x := by
  funext i
  fin_cases i <;> simp [stepM, stepN, vec] <;> ring

lemma stepN_stepM (x : Vec3) : stepN (stepM x) = x := by
  funext i
  fin_cases i <;> simp [stepM, stepN, vec] <;> ring

lemma norm_stepN (x : Vec3) : norm (stepN x) = norm x := by
  simp [norm, stepN, vec]
  ring

lemma norm_stepM (x : Vec3) : norm (stepM x) = norm x := by
  simp [norm, stepM, vec]
  ring

lemma eval_stepN (x : Vec3) : eval (stepN x) = (rho - 1) * eval x := by
  simp [eval, stepN, vec]
  ring_nf
  nlinarith [rho_cube]

lemma eval_stepM (x : Vec3) : eval (stepM x) = eta * eval x := by
  simp [eval, stepM, vec, eta]
  ring_nf
  nlinarith [rho_cube]

lemma norm_iterM (k : ℕ) (x : Vec3) : norm (iterM k x) = norm x := by
  induction k generalizing x with
  | zero => simp [iterM]
  | succ k ih =>
      rw [iterM, Function.iterate_succ_apply]
      calc
        norm (stepM^[k] (stepM x)) = norm (stepM x) := ih (stepM x)
        _ = norm x := norm_stepM x

lemma eval_iterM (k : ℕ) (x : Vec3) : eval (iterM k x) = eta ^ k * eval x := by
  induction k generalizing x with
  | zero => simp [iterM]
  | succ k ih =>
      rw [iterM, Function.iterate_succ_apply]
      calc
        eval (stepM^[k] (stepM x)) = eta ^ k * eval (stepM x) := ih (stepM x)
        _ = eta ^ k * (eta * eval x) := by rw [eval_stepM]
        _ = eta ^ (k + 1) * eval x := by rw [pow_succ]; ring

lemma iterN_iterM (k : ℕ) (x : Vec3) : iterN k (iterM k x) = x := by
  exact (Function.LeftInverse.iterate stepN_stepM k) x

lemma exists_scale (R : ℝ) (hRpos : 0 < R) (hRone : R < 1) :
    ∃ k : ℕ, 0 < k ∧ 1 ≤ R * eta ^ k ∧ R * eta ^ k < eta := by
  have hex : ∃ k : ℕ, 1 ≤ R * eta ^ k := by
    obtain ⟨k, hk⟩ := pow_unbounded_of_one_lt R⁻¹ eta_gt_one
    refine ⟨k, ?_⟩
    have hRne : R ≠ 0 := ne_of_gt hRpos
    have hmul := mul_lt_mul_of_pos_right hk hRpos
    rw [inv_mul_cancel₀ hRne] at hmul
    exact hmul.le
  let k := Nat.find hex
  have hk : 1 ≤ R * eta ^ k := Nat.find_spec hex
  have hkpos : 0 < k := by
    by_contra h
    have hkzero : k = 0 := Nat.eq_zero_of_not_pos h
    rw [hkzero, pow_zero, mul_one] at hk
    exact (not_le_of_gt hRone) hk
  have hprev : R * eta ^ (k - 1) < 1 := by
    apply lt_of_not_ge
    exact Nat.find_min hex (Nat.sub_one_lt (Nat.ne_of_gt hkpos))
  refine ⟨k, hkpos, hk, ?_⟩
  have hkdecomp : k - 1 + 1 = k :=
    Nat.sub_add_cancel (Nat.one_le_iff_ne_zero.mpr (Nat.ne_of_gt hkpos))
  rw [← hkdecomp, pow_succ]
  nlinarith [eta_pos]

noncomputable def pcoord (x : Vec3) : ℝ :=
  x 0 - x 1 * rho / 2 - x 2 * rho ^ 2 / 2

noncomputable def scoord (x : Vec3) : ℝ :=
  x 1 * rho - x 2 * rho ^ 2

noncomputable def qcoord (x : Vec3) : ℝ :=
  pcoord x ^ 2 + (3 / 4 : ℝ) * scoord x ^ 2

lemma eval_mul_qcoord (x : Vec3) : eval x * qcoord x = (norm x : ℝ) := by
  have h :
      eval x * qcoord x - (norm x : ℝ) =
        (rho ^ 3 - 2) *
          (-3 * (x 0 : ℝ) * (x 1 : ℝ) * (x 2 : ℝ) + (x 1 : ℝ) ^ 3 +
            (x 2 : ℝ) ^ 3 * rho ^ 3 + 2 * (x 2 : ℝ) ^ 3) := by
    simp [eval, qcoord, pcoord, scoord, norm]
    ring
  have hz : eval x * qcoord x - (norm x : ℝ) = 0 := by
    rw [h, rho_cube]
    ring
  linarith

lemma reduced_coeff_bounds (x : Vec3) (t : ℕ) (ht : t ≤ 60)
    (hnorm : norm x = -(t : ℤ)) (hlo : -eta < eval x) (hhi : eval x ≤ -1) :
    -6 ≤ x 0 ∧ x 0 ≤ 4 ∧ -8 ≤ x 1 ∧ x 1 ≤ 6 ∧ -8 ≤ x 2 ∧ x 2 ≤ 6 := by
  have hnormR : (norm x : ℝ) = -(t : ℝ) := by exact_mod_cast hnorm
  have hid := eval_mul_qcoord x
  rw [hnormR] at hid
  have hqnonneg : 0 ≤ qcoord x := by
    simp [qcoord]
    positivity
  have htR : (t : ℝ) ≤ 60 := by exact_mod_cast ht
  have hqle : qcoord x ≤ 60 := by nlinarith
  have hp2 : pcoord x ^ 2 ≤ 60 := by
    rw [qcoord] at hqle
    nlinarith [sq_nonneg (scoord x)]
  have hs2 : scoord x ^ 2 ≤ 80 := by
    rw [qcoord] at hqle
    nlinarith [sq_nonneg (pcoord x)]
  have hpL : -8 < pcoord x := by nlinarith
  have hpU : pcoord x < 8 := by nlinarith
  have hsL : -9 < scoord x := by nlinarith
  have hsU : scoord x < 9 := by nlinarith
  have heL : -4 < eval x := by linarith [eta_lt_four]
  have haid : 3 * (x 0 : ℝ) = eval x + 2 * pcoord x := by
    simp [eval, pcoord]
    ring
  have hbid : 6 * (x 1 : ℝ) * rho = 2 * (eval x - pcoord x) + 3 * scoord x := by
    simp [eval, pcoord, scoord]
    ring
  have hcid : 6 * (x 2 : ℝ) * rho ^ 2 = 2 * (eval x - pcoord x) - 3 * scoord x := by
    simp [eval, pcoord, scoord]
    ring
  have haLr : (-7 : ℝ) < (x 0 : ℝ) := by nlinarith
  have haUr : (x 0 : ℝ) < 5 := by nlinarith
  have haLz : (-7 : ℤ) < x 0 := by exact_mod_cast haLr
  have haUz : x 0 < (5 : ℤ) := by exact_mod_cast haUr
  have hbProdL : (-17 : ℝ) / 2 < (x 1 : ℝ) * rho := by nlinarith
  have hbProdU : (x 1 : ℝ) * rho < (41 : ℝ) / 6 := by nlinarith
  have hcProdL : (-17 : ℝ) / 2 < (x 2 : ℝ) * rho ^ 2 := by nlinarith
  have hcProdU : (x 2 : ℝ) * rho ^ 2 < (41 : ℝ) / 6 := by nlinarith
  have hbL : -8 ≤ x 1 := by
    by_contra h
    have hb : x 1 ≤ -9 := by omega
    have hbR : (x 1 : ℝ) ≤ -9 := by exact_mod_cast hb
    have hbnonpos : (x 1 : ℝ) ≤ 0 := by linarith
    have hmul : (x 1 : ℝ) * rho ≤ (x 1 : ℝ) * 1 :=
      mul_le_mul_of_nonpos_left one_lt_rho.le hbnonpos
    nlinarith
  have hbU : x 1 ≤ 6 := by
    by_contra h
    have hb : 7 ≤ x 1 := by omega
    have hbR : (7 : ℝ) ≤ (x 1 : ℝ) := by exact_mod_cast hb
    have hbpos : 0 < (x 1 : ℝ) := by linarith
    have hmul : (x 1 : ℝ) * 1 < (x 1 : ℝ) * rho :=
      mul_lt_mul_of_pos_left one_lt_rho hbpos
    nlinarith
  have hrho2 : 1 < rho ^ 2 := by nlinarith [sq_nonneg (rho - 1)]
  have hcL : -8 ≤ x 2 := by
    by_contra h
    have hc : x 2 ≤ -9 := by omega
    have hcR : (x 2 : ℝ) ≤ -9 := by exact_mod_cast hc
    have hcnonpos : (x 2 : ℝ) ≤ 0 := by linarith
    have hmul : (x 2 : ℝ) * rho ^ 2 ≤ (x 2 : ℝ) * 1 :=
      mul_le_mul_of_nonpos_left hrho2.le hcnonpos
    nlinarith
  have hcU : x 2 ≤ 6 := by
    by_contra h
    have hc : 7 ≤ x 2 := by omega
    have hcR : (7 : ℝ) ≤ (x 2 : ℝ) := by exact_mod_cast hc
    have hcpos : 0 < (x 2 : ℝ) := by linarith
    have hmul : (x 2 : ℝ) * 1 < (x 2 : ℝ) * rho ^ 2 :=
      mul_lt_mul_of_pos_left hrho2 hcpos
    nlinarith
  omega

def lowerBound (a b c : ℤ) : ℤ :=
  10000 * a + (if 0 ≤ b then 12500 * b else 13000 * b) +
    (if 0 ≤ c then 15625 * c else 16900 * c)

def upperBound (a b c : ℤ) : ℤ :=
  10000 * a + (if 0 ≤ b then 13000 * b else 12500 * b) +
    (if 0 ≤ c then 16900 * c else 15625 * c)

lemma lowerBound_le (a b c : ℤ) :
    (lowerBound a b c : ℝ) ≤
      10000 * ((a : ℝ) + (b : ℝ) * rho + (c : ℝ) * rho ^ 2) := by
  by_cases hb : 0 ≤ b <;> by_cases hc : 0 ≤ c
  all_goals
    have hbR : if 0 ≤ b then 0 ≤ (b : ℝ) else (b : ℝ) ≤ 0 := by
      split <;> rename_i h <;> exact_mod_cast h
    have hcR : if 0 ≤ c then 0 ≤ (c : ℝ) else (c : ℝ) ≤ 0 := by
      split <;> rename_i h <;> exact_mod_cast h
    simp [lowerBound, hb, hc] at *
    push_cast
    nlinarith [five_four_lt_rho, rho_lt_thirteen_tenths, rho_sq_lower, rho_sq_upper]

lemma le_upperBound (a b c : ℤ) :
    10000 * ((a : ℝ) + (b : ℝ) * rho + (c : ℝ) * rho ^ 2) ≤
      (upperBound a b c : ℝ) := by
  by_cases hb : 0 ≤ b <;> by_cases hc : 0 ≤ c
  all_goals
    have hbR : if 0 ≤ b then 0 ≤ (b : ℝ) else (b : ℝ) ≤ 0 := by
      split <;> rename_i h <;> exact_mod_cast h
    have hcR : if 0 ≤ c then 0 ≤ (c : ℝ) else (c : ℝ) ≤ 0 := by
      split <;> rename_i h <;> exact_mod_cast h
    simp [upperBound, hb, hc] at *
    push_cast
    nlinarith [five_four_lt_rho, rho_lt_thirteen_tenths, rho_sq_lower, rho_sq_upper]

def tValue : Fin 12 → ℕ := ![1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60]

def representative : Fin 12 → Vec3 :=
  ![z1, z2, z3, z4, z5, z6, z10, z12, z15, z20, z30, z60]

def coordA (a : Fin 11) : ℤ := (a : ℕ) - 6

def coordB (b : Fin 15) : ℤ := (b : ℕ) - 8

set_option maxRecDepth 1000000 in
set_option maxHeartbeats 10000000 in
lemma finite_reduced_classification :
    ∀ (a : Fin 11) (b c : Fin 15) (j : Fin 12),
      norm (vec (coordA a) (coordB b) (coordB c)) = -(tValue j : ℤ) →
      0 < upperBound (coordA a + 1) (coordB b + 1) (coordB c + 1) →
      lowerBound (coordA a + 1) (coordB b) (coordB c) ≤ 0 →
      vec (coordA a) (coordB b) (coordB c) = representative j := by
  decide

lemma divisor_60_index (t : ℕ) (htpos : 0 < t) (htdiv : t ∣ 60) :
    ∃ j : Fin 12, t = tValue j := by
  have ht : t ≤ 60 := Nat.le_of_dvd (by norm_num) htdiv
  interval_cases t <;> norm_num at htdiv ⊢ <;> decide

lemma classify_reduced (x : Vec3) (t : ℕ) (htpos : 0 < t) (htdiv : t ∣ 60)
    (hnorm : norm x = -(t : ℤ)) (hlo : -eta < eval x) (hhi : eval x ≤ -1) :
    ∃ j : Fin 12, t = tValue j ∧ x = representative j := by
  obtain ⟨j, rfl⟩ := divisor_60_index t htpos htdiv
  have htLe : tValue j ≤ 60 := Nat.le_of_dvd (by norm_num) (by
    fin_cases j <;> norm_num [tValue])
  obtain ⟨haL, haU, hbL, hbU, hcL, hcU⟩ :=
    reduced_coeff_bounds x (tValue j) htLe hnorm hlo hhi
  let a : Fin 11 := ⟨Int.toNat (x 0 + 6), by omega⟩
  let b : Fin 15 := ⟨Int.toNat (x 1 + 8), by omega⟩
  let c : Fin 15 := ⟨Int.toNat (x 2 + 8), by omega⟩
  have ha : coordA a = x 0 := by
    dsimp [coordA, a]
    rw [Int.toNat_of_nonneg (by omega)]
    omega
  have hb : coordB b = x 1 := by
    dsimp [coordB, b]
    rw [Int.toNat_of_nonneg (by omega)]
    omega
  have hc : coordB c = x 2 := by
    dsimp [coordB, c]
    rw [Int.toNat_of_nonneg (by omega)]
    omega
  have hupper : 0 < upperBound (x 0 + 1) (x 1 + 1) (x 2 + 1) := by
    have hpoly : 0 <
        (x 0 + 1 : ℝ) + (x 1 + 1 : ℝ) * rho + (x 2 + 1 : ℝ) * rho ^ 2 := by
      have heq :
          (x 0 + 1 : ℝ) + (x 1 + 1 : ℝ) * rho + (x 2 + 1 : ℝ) * rho ^ 2 =
            eval x + eta := by
        simp [eval, eta]
        ring
      rw [heq]
      linarith
    have hs : 0 < 10000 *
        ((x 0 + 1 : ℝ) + (x 1 + 1 : ℝ) * rho + (x 2 + 1 : ℝ) * rho ^ 2) :=
      mul_pos (by norm_num) hpoly
    have hu := le_upperBound (x 0 + 1) (x 1 + 1) (x 2 + 1)
    have : (0 : ℝ) < upperBound (x 0 + 1) (x 1 + 1) (x 2 + 1) := hs.trans_le hu
    exact_mod_cast this
  have hlower : lowerBound (x 0 + 1) (x 1) (x 2) ≤ 0 := by
    have hpoly :
        (x 0 + 1 : ℝ) + (x 1 : ℝ) * rho + (x 2 : ℝ) * rho ^ 2 ≤ 0 := by
      have heq :
          (x 0 + 1 : ℝ) + (x 1 : ℝ) * rho + (x 2 : ℝ) * rho ^ 2 = eval x + 1 := by
        simp [eval]
        ring
      rw [heq]
      linarith
    have hl := lowerBound_le (x 0 + 1) (x 1) (x 2)
    have : (lowerBound (x 0 + 1) (x 1) (x 2) : ℝ) ≤ 0 :=
      hl.trans (mul_nonpos_of_nonneg_of_nonpos (by norm_num) hpoly)
    exact_mod_cast this
  have hclass := finite_reduced_classification a b c j
  rw [ha, hb, hc] at hclass
  exact ⟨j, rfl, hclass hnorm hupper hlower⟩

theorem reduce_primitive (z : Vec3) (t : ℕ) (htpos : 0 < t) (htdiv : t ∣ 60)
    (hnorm : norm z = -(t : ℤ)) (hRpos : 0 < -eval z) (hRone : -eval z < 1) :
    ∃ (k : ℕ) (j : Fin 12),
      0 < k ∧ t = tValue j ∧ iterM k z = representative j ∧
        z = iterN k (representative j) := by
  obtain ⟨k, hkpos, hklo, hkhi⟩ := exists_scale (-eval z) hRpos hRone
  let w := iterM k z
  have hwnorm : norm w = -(t : ℤ) := by
    rw [norm_iterM]
    exact hnorm
  have hweval : eval w = -((-eval z) * eta ^ k) := by
    rw [eval_iterM]
    ring
  have hwlo : -eta < eval w := by rw [hweval]; linarith
  have hwhi : eval w ≤ -1 := by rw [hweval]; linarith
  obtain ⟨j, htj, hwj⟩ := classify_reduced w t htpos htdiv hwnorm hwlo hwhi
  refine ⟨k, j, hkpos, htj, hwj, ?_⟩
  rw [← hwj]
  exact (iterN_iterM k z).symm

end Erdos686Reduction
