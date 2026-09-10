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

import FormalConjectures.Util.ProblemImports

namespace Erdos686FourThree

private abbrev Vec3 := Fin 3 → ℤ

private def vec (a b c : ℤ) : Vec3 := ![a, b, c]

private def stepN (x : Vec3) : Vec3 :=
  vec (-x 0 + 2 * x 2) (x 0 - x 1) (x 1 - x 2)

private def stepM (x : Vec3) : Vec3 :=
  vec (x 0 + 2 * x 1 + 2 * x 2) (x 0 + x 1 + 2 * x 2) (x 0 + x 1 + x 2)

private def iterN (k : ℕ) (x : Vec3) : Vec3 := (stepN^[k]) x

private def iterM (k : ℕ) (x : Vec3) : Vec3 := (stepM^[k]) x

private def norm (x : Vec3) : ℤ :=
  x 0 ^ 3 + 2 * x 1 ^ 3 + 4 * x 2 ^ 3 - 6 * x 0 * x 1 * x 2

private noncomputable def rho : ℝ := (2 : ℝ) ^ ((3 : ℝ)⁻¹)

private noncomputable def eval (x : Vec3) : ℝ :=
  x 0 + x 1 * rho + x 2 * rho ^ 2

private noncomputable def eta : ℝ := 1 + rho + rho ^ 2

private lemma rho_cube : rho ^ 3 = 2 := by
  rw [rho]
  simpa using Real.rpow_inv_natCast_pow (x := (2 : ℝ)) (n := 3) (by positivity) (by norm_num)

private lemma rho_pos : 0 < rho := by
  exact Real.rpow_pos_of_pos (by norm_num) _

private lemma rho_gt_one : 1 < rho := by
  rw [rho]
  have h : (0 : ℝ) < (3 : ℝ)⁻¹ := by positivity
  simpa using Real.rpow_lt_rpow (by norm_num : (0 : ℝ) ≤ 1) (by norm_num : (1 : ℝ) < 2) h

private lemma rho_lt_thirteen_tenths : rho < (13 : ℝ) / 10 := by
  by_contra h
  have hle : (13 : ℝ) / 10 ≤ rho := le_of_not_gt h
  have hmul : ((13 : ℝ) / 10) ^ 3 ≤ rho ^ 3 := by
    exact pow_le_pow_left₀ (by norm_num) hle 3
  rw [rho_cube] at hmul
  norm_num at hmul

private lemma eta_gt_one : 1 < eta := by
  rw [eta]
  nlinarith [rho_pos, sq_nonneg rho]

private lemma eta_pos : 0 < eta := lt_trans zero_lt_one eta_gt_one

private lemma eta_lt_four : eta < 4 := by
  rw [eta]
  have hs : rho ^ 2 < ((13 : ℝ) / 10) ^ 2 := by
    nlinarith [rho_pos, rho_lt_thirteen_tenths]
  nlinarith [rho_lt_thirteen_tenths]

private lemma delta_mul_eta : (rho - 1) * eta = 1 := by
  rw [eta]
  nlinarith [rho_cube]

private lemma stepM_stepN (x : Vec3) : stepM (stepN x) = x := by
  funext i
  fin_cases i <;> simp [stepM, stepN, vec] <;> ring

private lemma stepN_stepM (x : Vec3) : stepN (stepM x) = x := by
  funext i
  fin_cases i <;> simp [stepM, stepN, vec] <;> ring

private lemma norm_stepN (x : Vec3) : norm (stepN x) = norm x := by
  simp [norm, stepN, vec]
  ring

private lemma norm_stepM (x : Vec3) : norm (stepM x) = norm x := by
  simp [norm, stepM, vec]
  ring

private lemma eval_stepN (x : Vec3) : eval (stepN x) = (rho - 1) * eval x := by
  simp [eval, stepN, vec]
  ring_nf
  nlinarith [rho_cube]

private lemma eval_stepM (x : Vec3) : eval (stepM x) = eta * eval x := by
  simp [eval, stepM, vec, eta]
  ring_nf
  nlinarith [rho_cube]

private lemma norm_iterN (k : ℕ) (x : Vec3) : norm (iterN k x) = norm x := by
  induction k generalizing x with
  | zero => simp [iterN]
  | succ k ih =>
      rw [iterN, Function.iterate_succ_apply]
      calc
        norm (stepN^[k] (stepN x)) = norm (stepN x) := ih (stepN x)
        _ = norm x := norm_stepN x

private lemma norm_iterM (k : ℕ) (x : Vec3) : norm (iterM k x) = norm x := by
  induction k generalizing x with
  | zero => simp [iterM]
  | succ k ih =>
      rw [iterM, Function.iterate_succ_apply]
      calc
        norm (stepM^[k] (stepM x)) = norm (stepM x) := ih (stepM x)
        _ = norm x := norm_stepM x

private lemma eval_iterM (k : ℕ) (x : Vec3) : eval (iterM k x) = eta ^ k * eval x := by
  induction k generalizing x with
  | zero => simp [iterM]
  | succ k ih =>
      rw [iterM, Function.iterate_succ_apply]
      calc
        eval (stepM^[k] (stepM x)) = eta ^ k * eval (stepM x) := ih (stepM x)
        _ = eta ^ k * (eta * eval x) := by rw [eval_stepM]
        _ = eta ^ (k + 1) * eval x := by rw [pow_succ]; ring

private lemma iterN_iterM (k : ℕ) (x : Vec3) : iterN k (iterM k x) = x := by
  exact (Function.LeftInverse.iterate stepN_stepM k) x

private lemma exists_scale (R : ℝ) (hRpos : 0 < R) (hRone : R < 1) :
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
  have hkdecomp : k - 1 + 1 = k := Nat.sub_add_cancel (Nat.one_le_iff_ne_zero.mpr (Nat.ne_of_gt hkpos))
  rw [← hkdecomp, pow_succ]
  nlinarith [eta_pos]

private noncomputable def pcoord (x : Vec3) : ℝ :=
  x 0 - x 1 * rho / 2 - x 2 * rho ^ 2 / 2

private noncomputable def scoord (x : Vec3) : ℝ :=
  x 1 * rho - x 2 * rho ^ 2

private noncomputable def qcoord (x : Vec3) : ℝ :=
  pcoord x ^ 2 + (3 / 4 : ℝ) * scoord x ^ 2

private lemma eval_mul_qcoord (x : Vec3) : eval x * qcoord x = (norm x : ℝ) := by
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

private lemma reduced_coeff_bounds (x : Vec3) (t : ℕ) (ht : t ≤ 60)
    (hnorm : norm x = -(t : ℤ)) (hlo : -eta < eval x) (hhi : eval x ≤ -1) :
    -6 ≤ x 0 ∧ x 0 ≤ 4 ∧ -8 ≤ x 1 ∧ x 1 ≤ 6 ∧ -8 ≤ x 2 ∧ x 2 ≤ 6 := by
  have hnormR : (norm x : ℝ) = -(t : ℝ) := by exact_mod_cast hnorm
  have hid := eval_mul_qcoord x
  rw [hnormR] at hid
  have hqnonneg : 0 ≤ qcoord x := by
    simp [qcoord]
    positivity
  have htR : (t : ℝ) ≤ 60 := by exact_mod_cast ht
  have hqle : qcoord x ≤ 60 := by
    nlinarith
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
      mul_le_mul_of_nonpos_left rho_gt_one.le hbnonpos
    nlinarith
  have hbU : x 1 ≤ 6 := by
    by_contra h
    have hb : 7 ≤ x 1 := by omega
    have hbR : (7 : ℝ) ≤ (x 1 : ℝ) := by exact_mod_cast hb
    have hbpos : 0 < (x 1 : ℝ) := by linarith
    have hmul : (x 1 : ℝ) * 1 < (x 1 : ℝ) * rho :=
      mul_lt_mul_of_pos_left rho_gt_one hbpos
    nlinarith
  have hrho2 : 1 < rho ^ 2 := by
    nlinarith [sq_nonneg (rho - 1)]
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

end Erdos686FourThree
