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

import FormalConjectures.ErdosProblems.Erdos686Orbit

/-! The modular orbit certificates used in the proof of Erdős Problem 686. -/

namespace Erdos686Orbit

open Matrix
open Erdos686Padic

def c2 : Mat ℤ :=
  !![-4, 6, -2;
      -1, -4, 6;
      3, -1, -4]

def c3 : Mat ℤ :=
  !![0, -2, 2;
      1, 0, -2;
      -1, 1, 0]

def c5 : Mat ℤ :=
  !![0, -32, 40;
      20, 0, -32;
      -16, 20, 0]

def c7 : Mat ℤ :=
  !![-7280, 41382, -40582;
      -20291, -7280, 41382;
      20691, -20291, -7280]

lemma nMat_pow_3 : (nMat ℤ) ^ 3 = 1 + (3 : ℤ) • c3 := by decide
lemma nMat_pow_4 : (nMat ℤ) ^ 4 = 1 + (2 : ℤ) • c2 := by decide
lemma nMat_pow_8 : (nMat ℤ) ^ 8 = 1 + (5 : ℤ) • c5 := by decide
lemma nMat_pow_19 : (nMat ℤ) ^ 19 = 1 + (7 : ℤ) • c7 := by decide

lemma base_block (p L : ℕ) (C : Mat ℤ)
    (hpow : (nMat ℤ) ^ L = 1 + (p : ℤ) • C) :
    (step ℤ)^[L] = affineStep p C.mulVecLin := by
  funext x
  rw [iterate_step, hpow]
  ext i
  simp [step, affineStep, affineEnd]

lemma full_block (p L : ℕ) (C : Mat ℤ)
    (hpow : (nMat ℤ) ^ L = 1 + (p : ℤ) • C) :
    (step ℤ)^[L * p] = affineStep ((p : ℤ) ^ 2) (liftB p C.mulVecLin) := by
  rw [Function.iterate_mul, base_block p L C hpow, first_prime_block]

lemma modular_middle_zero (m k : ℕ) (z : Vec ℤ)
    (hz : ((step ℤ)^[k] z) 1 = 0) :
    ((((nMat (ZMod m)) ^ k) *ᵥ castVec m z) 1 = 0) := by
  have h := congrArg (fun x => x 1) (cast_iterate_step m k z)
  rw [hz, iterate_step] at h
  simpa [castVec] using h.symm

lemma exact_root_of_mod
    (p L r k : ℕ) (hp : p.Prime) (C : Mat ℤ)
    (hpow : (nMat ℤ) ^ L = 1 + (p : ℤ) • C)
    (z : Vec ℤ) (hrlt : r < L * p) (hmod : k % (L * p) = r)
    (hrzero : ((step ℤ)^[r] z) 1 = 0)
    (hderiv : ¬ (p : ℤ) ∣ (liftB p C.mulVecLin ((step ℤ)^[r] z)) 1)
    (hz : ((step ℤ)^[k] z) 1 = 0) :
    k = r := by
  let q := k / (L * p)
  have hk : k = (L * p) * q + r := by
    have h := Nat.mod_add_div k (L * p)
    dsimp [q]
    omega
  have hzblock :
      ((affineStep ((p : ℤ) ^ 2) (liftB p C.mulVecLin))^[q]
        ((step ℤ)^[r] z)) 1 = 0 := by
    rw [hk, Function.iterate_add_apply, Function.iterate_mul,
      full_block p L C hpow] at hz
    exact hz
  have hq := zero_of_affine_iterate_zero p hp ((step ℤ)^[r] z) 1 hrzero
    q 1 (by norm_num) (liftB p C.mulVecLin) hderiv hzblock
  rw [hk, hq]
  simp

def z1 : Vec ℤ := vec (-1) 0 0
def z2 : Vec ℤ := vec 0 (-1) 0
def z3 : Vec ℤ := vec (-1) (-1) 0
def z4 : Vec ℤ := vec 0 0 (-1)
def z5 : Vec ℤ := vec (-1) 0 (-1)
def z6 : Vec ℤ := vec 0 (-1) (-1)
def z10 : Vec ℤ := vec (-2) (-1) 0
def z12 : Vec ℤ := vec (-2) 0 (-1)
def z15 : Vec ℤ := vec 1 (-2) 0
def z20 : Vec ℤ := vec (-2) 2 (-1)
def z30 : Vec ℤ := vec 0 1 (-2)
def z60 : Vec ℤ := vec (-4) 0 1

lemma period_mod2 : (nMat (ZMod 4)) ^ 8 = 1 := by decide
lemma period_mod3 : (nMat (ZMod 9)) ^ 9 = 1 := by decide
lemma period_mod5 : (nMat (ZMod 25)) ^ 40 = 1 := by decide
lemma period_mod7 : (nMat (ZMod 49)) ^ 133 = 1 := by decide
lemma period_mod11 : (nMat (ZMod 121)) ^ 440 = 1 := by decide

set_option maxRecDepth 100000 in
lemma roots_1 : ∀ r : Fin 9,
    (((((nMat (ZMod 9)) ^ (r : ℕ)) *ᵥ castVec 9 z1) 1 = 0) ↔ r = 0) := by
  decide

set_option maxRecDepth 100000 in
lemma roots_2 : ∀ r : Fin 8,
    ((((nMat (ZMod 4)) ^ (r : ℕ)) *ᵥ castVec 4 z2) 1 ≠ 0) := by
  decide

set_option maxRecDepth 100000 in
lemma roots_3 : ∀ r : Fin 40,
    (((((nMat (ZMod 25)) ^ (r : ℕ)) *ᵥ castVec 25 z3) 1 = 0) ↔ r = 1) := by
  decide

set_option maxRecDepth 100000 in
lemma roots_4 : ∀ r : Fin 9,
    (((((nMat (ZMod 9)) ^ (r : ℕ)) *ᵥ castVec 9 z4) 1 = 0) ↔
      r = 0 ∨ r = 1) := by
  decide

set_option maxRecDepth 100000 in
lemma roots_5 : ∀ r : Fin 9,
    (((((nMat (ZMod 9)) ^ (r : ℕ)) *ᵥ castVec 9 z5) 1 = 0) ↔
      r = 0 ∨ r = 2) := by
  decide

set_option maxRecDepth 100000 in
lemma roots_6 : ∀ r : Fin 9,
    ((((nMat (ZMod 9)) ^ (r : ℕ)) *ᵥ castVec 9 z6) 1 ≠ 0) := by
  decide

set_option maxRecDepth 100000 in
lemma roots_10 : ∀ r : Fin 8,
    ((((nMat (ZMod 4)) ^ (r : ℕ)) *ᵥ castVec 4 z10) 1 ≠ 0) := by
  decide

set_option maxRecDepth 100000 in
lemma roots_12 : ∀ r : Fin 133,
    (((((nMat (ZMod 49)) ^ (r : ℕ)) *ᵥ castVec 49 z12) 1 = 0) ↔
      r = 0 ∨ r = 3) := by
  decide

set_option maxRecDepth 100000 in
lemma roots_15 : ∀ r : Fin 9,
    ((((nMat (ZMod 9)) ^ (r : ℕ)) *ᵥ castVec 9 z15) 1 ≠ 0) := by
  decide

set_option maxRecDepth 100000 in
lemma roots_20 : ∀ r : Fin 9,
    ((((nMat (ZMod 9)) ^ (r : ℕ)) *ᵥ castVec 9 z20) 1 ≠ 0) := by
  decide

set_option maxRecDepth 100000 in
lemma roots_30 : ∀ r : Fin 9,
    ((((nMat (ZMod 9)) ^ (r : ℕ)) *ᵥ castVec 9 z30) 1 ≠ 0) := by
  decide

set_option maxRecDepth 200000 in
set_option maxHeartbeats 2000000 in
lemma roots_60_mod5 : ∀ r : Fin 40,
    (((((nMat (ZMod 25)) ^ (r : ℕ)) *ᵥ castVec 25 z60) 1 = 0) ↔
      r = 0 ∨ r = 22 ∨ r = 26 ∨ r = 28) := by
  decide

set_option maxRecDepth 500000 in
set_option maxHeartbeats 5000000 in
lemma roots_60_mod11 : ∀ r : Fin 440,
    (((((nMat (ZMod 121)) ^ (r : ℕ)) *ᵥ castVec 121 z60) 1 = 0) ↔
      r = 0 ∨ r = 110 ∨ r = 313) := by
  decide

lemma root_3 : ((step ℤ)^[1] z3) 1 = 0 := by decide
lemma root_4_0 : ((step ℤ)^[0] z4) 1 = 0 := by decide
lemma root_4_1 : ((step ℤ)^[1] z4) 1 = 0 := by decide
lemma root_5_0 : ((step ℤ)^[0] z5) 1 = 0 := by decide
lemma root_5_2 : ((step ℤ)^[2] z5) 1 = 0 := by decide
lemma root_12_0 : ((step ℤ)^[0] z12) 1 = 0 := by decide
lemma root_12_3 : ((step ℤ)^[3] z12) 1 = 0 := by decide
lemma root_60_0 : ((step ℤ)^[0] z60) 1 = 0 := by decide

lemma deriv_1 : ¬ (3 : ℤ) ∣ (liftB 3 c3.mulVecLin z1) 1 := by
  norm_num [liftB, remainder, c3, z1, vec, Matrix.mulVecLin_apply,
    Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

lemma deriv_3 : ¬ (5 : ℤ) ∣ (liftB 5 c5.mulVecLin ((step ℤ)^[1] z3)) 1 := by
  norm_num [liftB, remainder, c5, z3, vec, step, nMat, Function.iterate_succ_apply,
    Matrix.mulVecLin_apply, Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

lemma deriv_4_0 : ¬ (3 : ℤ) ∣ (liftB 3 c3.mulVecLin ((step ℤ)^[0] z4)) 1 := by
  norm_num [liftB, remainder, c3, z4, vec, Matrix.mulVecLin_apply,
    Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

lemma deriv_4_1 : ¬ (3 : ℤ) ∣ (liftB 3 c3.mulVecLin ((step ℤ)^[1] z4)) 1 := by
  norm_num [liftB, remainder, c3, z4, vec, step, nMat, Function.iterate_succ_apply,
    Matrix.mulVecLin_apply, Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

lemma deriv_5_0 : ¬ (3 : ℤ) ∣ (liftB 3 c3.mulVecLin ((step ℤ)^[0] z5)) 1 := by
  norm_num [liftB, remainder, c3, z5, vec, Matrix.mulVecLin_apply,
    Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

lemma deriv_5_2 : ¬ (3 : ℤ) ∣ (liftB 3 c3.mulVecLin ((step ℤ)^[2] z5)) 1 := by
  norm_num [liftB, remainder, c3, z5, vec, step, nMat, Function.iterate_succ_apply,
    Matrix.mulVecLin_apply, Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

set_option maxRecDepth 200000 in
set_option maxHeartbeats 2000000 in
lemma deriv_12_0 : ¬ (7 : ℤ) ∣ (liftB 7 c7.mulVecLin ((step ℤ)^[0] z12)) 1 := by
  norm_num [liftB, remainder, c7, z12, vec, Matrix.mulVecLin_apply,
    Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

set_option maxRecDepth 200000 in
set_option maxHeartbeats 2000000 in
lemma deriv_12_3 : ¬ (7 : ℤ) ∣ (liftB 7 c7.mulVecLin ((step ℤ)^[3] z12)) 1 := by
  norm_num [liftB, remainder, c7, z12, vec, step, nMat, Function.iterate_succ_apply,
    Matrix.mulVecLin_apply, Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

lemma deriv_60_0 : ¬ (5 : ℤ) ∣ (liftB 5 c5.mulVecLin ((step ℤ)^[0] z60)) 1 := by
  norm_num [liftB, remainder, c5, z60, vec, Matrix.mulVecLin_apply,
    Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

theorem orbit_1 (k : ℕ) (hz : ((step ℤ)^[k] z1) 1 = 0) : k = 0 := by
  have hzmod := modular_middle_zero 9 k z1 hz
  rw [pow_eq_pow_mod (nMat (ZMod 9)) 9 k (by norm_num) period_mod3] at hzmod
  let r : Fin 9 := ⟨k % 9, Nat.mod_lt _ (by norm_num)⟩
  have hr : r = 0 := (roots_1 r).mp hzmod
  have hmod : k % 9 = 0 := by simpa [r] using congrArg Fin.val hr
  exact exact_root_of_mod 3 3 0 k (by norm_num) c3 nMat_pow_3 z1
    (by norm_num) hmod (by decide) deriv_1 hz

theorem orbit_2_absurd (k : ℕ) (hz : ((step ℤ)^[k] z2) 1 = 0) : False := by
  have hzmod := modular_middle_zero 4 k z2 hz
  rw [pow_eq_pow_mod (nMat (ZMod 4)) 8 k (by norm_num) period_mod2] at hzmod
  let r : Fin 8 := ⟨k % 8, Nat.mod_lt _ (by norm_num)⟩
  exact (roots_2 r) hzmod

theorem orbit_3 (k : ℕ) (hz : ((step ℤ)^[k] z3) 1 = 0) : k = 1 := by
  have hzmod := modular_middle_zero 25 k z3 hz
  rw [pow_eq_pow_mod (nMat (ZMod 25)) 40 k (by norm_num) period_mod5] at hzmod
  let r : Fin 40 := ⟨k % 40, Nat.mod_lt _ (by norm_num)⟩
  have hr : r = 1 := (roots_3 r).mp hzmod
  have hmod : k % 40 = 1 := by simpa [r] using congrArg Fin.val hr
  exact exact_root_of_mod 5 8 1 k (by norm_num) c5 nMat_pow_8 z3
    (by norm_num) hmod root_3 deriv_3 hz

theorem orbit_4 (k : ℕ) (hz : ((step ℤ)^[k] z4) 1 = 0) : k = 0 ∨ k = 1 := by
  have hzmod := modular_middle_zero 9 k z4 hz
  rw [pow_eq_pow_mod (nMat (ZMod 9)) 9 k (by norm_num) period_mod3] at hzmod
  let r : Fin 9 := ⟨k % 9, Nat.mod_lt _ (by norm_num)⟩
  rcases (roots_4 r).mp hzmod with hr | hr
  · left
    have hmod : k % 9 = 0 := by simpa [r] using congrArg Fin.val hr
    exact exact_root_of_mod 3 3 0 k (by norm_num) c3 nMat_pow_3 z4
      (by norm_num) hmod root_4_0 deriv_4_0 hz
  · right
    have hmod : k % 9 = 1 := by simpa [r] using congrArg Fin.val hr
    exact exact_root_of_mod 3 3 1 k (by norm_num) c3 nMat_pow_3 z4
      (by norm_num) hmod root_4_1 deriv_4_1 hz

theorem orbit_5 (k : ℕ) (hz : ((step ℤ)^[k] z5) 1 = 0) : k = 0 ∨ k = 2 := by
  have hzmod := modular_middle_zero 9 k z5 hz
  rw [pow_eq_pow_mod (nMat (ZMod 9)) 9 k (by norm_num) period_mod3] at hzmod
  let r : Fin 9 := ⟨k % 9, Nat.mod_lt _ (by norm_num)⟩
  rcases (roots_5 r).mp hzmod with hr | hr
  · left
    have hmod : k % 9 = 0 := by simpa [r] using congrArg Fin.val hr
    exact exact_root_of_mod 3 3 0 k (by norm_num) c3 nMat_pow_3 z5
      (by norm_num) hmod root_5_0 deriv_5_0 hz
  · right
    have hmod : k % 9 = 2 := by simpa [r] using congrArg Fin.val hr
    exact exact_root_of_mod 3 3 2 k (by norm_num) c3 nMat_pow_3 z5
      (by norm_num) hmod root_5_2 deriv_5_2 hz

theorem orbit_6_absurd (k : ℕ) (hz : ((step ℤ)^[k] z6) 1 = 0) : False := by
  have hzmod := modular_middle_zero 9 k z6 hz
  rw [pow_eq_pow_mod (nMat (ZMod 9)) 9 k (by norm_num) period_mod3] at hzmod
  let r : Fin 9 := ⟨k % 9, Nat.mod_lt _ (by norm_num)⟩
  exact (roots_6 r) hzmod

theorem orbit_10_absurd (k : ℕ) (hz : ((step ℤ)^[k] z10) 1 = 0) : False := by
  have hzmod := modular_middle_zero 4 k z10 hz
  rw [pow_eq_pow_mod (nMat (ZMod 4)) 8 k (by norm_num) period_mod2] at hzmod
  let r : Fin 8 := ⟨k % 8, Nat.mod_lt _ (by norm_num)⟩
  exact (roots_10 r) hzmod

theorem orbit_12 (k : ℕ) (hz : ((step ℤ)^[k] z12) 1 = 0) : k = 0 ∨ k = 3 := by
  have hzmod := modular_middle_zero 49 k z12 hz
  rw [pow_eq_pow_mod (nMat (ZMod 49)) 133 k (by norm_num) period_mod7] at hzmod
  let r : Fin 133 := ⟨k % 133, Nat.mod_lt _ (by norm_num)⟩
  rcases (roots_12 r).mp hzmod with hr | hr
  · left
    have hmod : k % 133 = 0 := by simpa [r] using congrArg Fin.val hr
    exact exact_root_of_mod 7 19 0 k (by norm_num) c7 nMat_pow_19 z12
      (by norm_num) hmod root_12_0 deriv_12_0 hz
  · right
    have hmod : k % 133 = 3 := by simpa [r] using congrArg Fin.val hr
    exact exact_root_of_mod 7 19 3 k (by norm_num) c7 nMat_pow_19 z12
      (by norm_num) hmod root_12_3 deriv_12_3 hz

theorem orbit_15_absurd (k : ℕ) (hz : ((step ℤ)^[k] z15) 1 = 0) : False := by
  have hzmod := modular_middle_zero 9 k z15 hz
  rw [pow_eq_pow_mod (nMat (ZMod 9)) 9 k (by norm_num) period_mod3] at hzmod
  let r : Fin 9 := ⟨k % 9, Nat.mod_lt _ (by norm_num)⟩
  exact (roots_15 r) hzmod

theorem orbit_20_absurd (k : ℕ) (hz : ((step ℤ)^[k] z20) 1 = 0) : False := by
  have hzmod := modular_middle_zero 9 k z20 hz
  rw [pow_eq_pow_mod (nMat (ZMod 9)) 9 k (by norm_num) period_mod3] at hzmod
  let r : Fin 9 := ⟨k % 9, Nat.mod_lt _ (by norm_num)⟩
  exact (roots_20 r) hzmod

theorem orbit_30_absurd (k : ℕ) (hz : ((step ℤ)^[k] z30) 1 = 0) : False := by
  have hzmod := modular_middle_zero 9 k z30 hz
  rw [pow_eq_pow_mod (nMat (ZMod 9)) 9 k (by norm_num) period_mod3] at hzmod
  let r : Fin 9 := ⟨k % 9, Nat.mod_lt _ (by norm_num)⟩
  exact (roots_30 r) hzmod

theorem orbit_60 (k : ℕ) (hz : ((step ℤ)^[k] z60) 1 = 0) : k = 0 := by
  have h5mod := modular_middle_zero 25 k z60 hz
  rw [pow_eq_pow_mod (nMat (ZMod 25)) 40 k (by norm_num) period_mod5] at h5mod
  let r5 : Fin 40 := ⟨k % 40, Nat.mod_lt _ (by norm_num)⟩
  have h5 := (roots_60_mod5 r5).mp h5mod
  have h11mod := modular_middle_zero 121 k z60 hz
  rw [pow_eq_pow_mod (nMat (ZMod 121)) 440 k (by norm_num) period_mod11] at h11mod
  let r11 : Fin 440 := ⟨k % 440, Nat.mod_lt _ (by norm_num)⟩
  have h11 := (roots_60_mod11 r11).mp h11mod
  have hmod : k % 40 = 0 := by
    rcases h5 with h5 | h5 | h5 | h5 <;>
      rcases h11 with h11 | h11 | h11 <;>
      simp [r5, r11] at h5 h11 <;> omega
  exact exact_root_of_mod 5 8 0 k (by norm_num) c5 nMat_pow_8 z60
    (by norm_num) hmod root_60_0 deriv_60_0 hz

end Erdos686Orbit
