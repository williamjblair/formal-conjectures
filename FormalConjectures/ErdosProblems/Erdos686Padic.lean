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

import Mathlib

/-! Auxiliary p-adic lifting lemmas for Erdős Problem 686. -/

namespace Erdos686Padic

abbrev Vec3 := Fin 3 → ℤ
abbrev End3 := Module.End ℤ Vec3

def affineEnd (c : ℤ) (B : End3) : End3 :=
  LinearMap.id + c • B

def affineStep (c : ℤ) (B : End3) : Vec3 → Vec3 :=
  fun x => affineEnd c B x

def remainder (c : ℤ) (B : End3) : ℕ → End3
  | 0 => 0
  | n + 1 =>
      remainder c B n + n • (B.comp B) + c • (B.comp (remainder c B n))

lemma iterate_affineStep_apply (c : ℤ) (B : End3) (n : ℕ) (x : Vec3) :
    (affineStep c B)^[n] x =
      x + ((n : ℤ) * c) • B x + c ^ 2 • (remainder c B n) x := by
  induction n generalizing x with
  | zero =>
      simp [remainder]
  | succ n ih =>
      rw [Function.iterate_succ_apply', ih]
      change
        (x + ((n : ℤ) * c) • B x + c ^ 2 • (remainder c B n) x) +
            c • B (x + ((n : ℤ) * c) • B x + c ^ 2 • (remainder c B n) x) = _
      rw [B.map_add, B.map_add, B.map_smul, B.map_smul]
      ext i
      simp [remainder]
      ring

def liftB (p : ℕ) (B : End3) : End3 :=
  B + remainder (p : ℤ) B p

lemma first_prime_block (p : ℕ) (B : End3) :
    (affineStep (p : ℤ) B)^[p] =
      affineStep ((p : ℤ) ^ 2) (liftB p B) := by
  funext x
  rw [iterate_affineStep_apply]
  ext i
  simp only [affineStep, affineEnd, liftB, LinearMap.add_apply, LinearMap.id_apply,
    LinearMap.smul_apply, Pi.add_apply, Pi.smul_apply, smul_eq_mul]
  ring

def nextB (p : ℕ) (s : ℤ) (B : End3) : End3 :=
  B + ((p : ℤ) * s) • remainder ((p : ℤ) ^ 2 * s) B p

lemma prime_block (p : ℕ) (s : ℤ) (B : End3) :
    (affineStep ((p : ℤ) ^ 2 * s) B)^[p] =
      affineStep ((p : ℤ) ^ 2 * ((p : ℤ) * s)) (nextB p s B) := by
  funext x
  rw [iterate_affineStep_apply]
  ext i
  simp only [affineStep, affineEnd, nextB, LinearMap.add_apply, LinearMap.id_apply,
    LinearMap.smul_apply, Pi.add_apply, Pi.smul_apply, smul_eq_mul]
  ring

lemma nextB_mod_prime (p : ℕ) (s : ℤ) (B : End3) (x : Vec3) (i : Fin 3) :
    (p : ℤ) ∣ nextB p s B x i - B x i := by
  refine ⟨s * (remainder ((p : ℤ) ^ 2 * s) B p x i), ?_⟩
  simp [nextB]

theorem zero_of_affine_iterate_zero
    (p : ℕ) (hp : p.Prime) (x : Vec3) (i : Fin 3) (hx : x i = 0)
    (q : ℕ) (s : ℤ) (hs : s ≠ 0) (B : End3)
    (hB : ¬ (p : ℤ) ∣ B x i)
    (hz : ((affineStep ((p : ℤ) ^ 2 * s) B)^[q] x) i = 0) :
    q = 0 := by
  induction q using Nat.strong_induction_on generalizing s B with
  | h q ih =>
      by_cases hq : q = 0
      · exact hq
      have hpZ : Prime (p : ℤ) := Nat.prime_iff_prime_int.mp hp
      have hpne : (p : ℤ) ≠ 0 := by exact_mod_cast hp.ne_zero
      have hcne : (p : ℤ) ^ 2 * s ≠ 0 := mul_ne_zero (pow_ne_zero _ hpne) hs
      have hexp := congrArg (fun y : Vec3 => y i)
        (iterate_affineStep_apply ((p : ℤ) ^ 2 * s) B q x)
      have hexp' :
          ((q : ℤ) * ((p : ℤ) ^ 2 * s)) * B x i +
              (((p : ℤ) ^ 2 * s) ^ 2) *
                (remainder ((p : ℤ) ^ 2 * s) B q x i) = 0 := by
        simpa only [Pi.add_apply, Pi.smul_apply, smul_eq_mul, hz, hx, zero_add] using hexp.symm
      have hinner :
          (q : ℤ) * B x i + ((p : ℤ) ^ 2 * s) *
            (remainder ((p : ℤ) ^ 2 * s) B q x i) = 0 := by
        have hfac :
            ((p : ℤ) ^ 2 * s) *
                ((q : ℤ) * B x i + ((p : ℤ) ^ 2 * s) *
                  (remainder ((p : ℤ) ^ 2 * s) B q x i)) = 0 := by
          calc
            _ = ((q : ℤ) * ((p : ℤ) ^ 2 * s)) * B x i +
                  (((p : ℤ) ^ 2 * s) ^ 2) *
                    (remainder ((p : ℤ) ^ 2 * s) B q x i) := by ring
            _ = 0 := hexp'
        exact (mul_eq_zero.mp hfac).resolve_left hcne
      have hpTerm : (p : ℤ) ∣
          ((p : ℤ) ^ 2 * s) * (remainder ((p : ℤ) ^ 2 * s) B q x i) := by
        exact dvd_mul_of_dvd_left (dvd_mul_of_dvd_left (dvd_pow_self (p : ℤ) (by norm_num)) s) _
      have hpMul : (p : ℤ) ∣ (q : ℤ) * B x i := by
        rw [show (q : ℤ) * B x i =
          -(((p : ℤ) ^ 2 * s) * (remainder ((p : ℤ) ^ 2 * s) B q x i)) by
            linarith [hinner]]
        exact dvd_neg.mpr hpTerm
      have hpqZ : (p : ℤ) ∣ (q : ℤ) :=
        (hpZ.dvd_mul.mp hpMul).resolve_right hB
      have hpq : p ∣ q := by
        exact_mod_cast hpqZ
      obtain ⟨r, hqr⟩ := hpq
      have hrlt : r < q := by
        have hp2 : 2 ≤ p := hp.two_le
        have hrpos : 0 < r := by
          by_contra hr
          have : r = 0 := Nat.eq_zero_of_not_pos hr
          subst r
          simp at hqr
          exact hq hqr
        rw [hqr]
        exact (show r < 2 * r by omega).trans_le (Nat.mul_le_mul_right r hp2)
      let B' := nextB p s B
      have hB' : ¬ (p : ℤ) ∣ B' x i := by
        intro hd
        have hdiff : (p : ℤ) ∣ B' x i - B x i := by
          exact nextB_mod_prime p s B x i
        have : (p : ℤ) ∣ B x i := by
          have := dvd_sub hd hdiff
          simpa using this
        exact hB this
      have hs' : (p : ℤ) * s ≠ 0 := mul_ne_zero hpne hs
      have hz' :
          ((affineStep ((p : ℤ) ^ 2 * ((p : ℤ) * s)) B')^[r] x) i = 0 := by
        rw [hqr, Function.iterate_mul, prime_block] at hz
        exact hz
      have hr0 := ih r hrlt ((p : ℤ) * s) hs' B' hB' hz'
      rw [hqr, hr0, mul_zero]

end Erdos686Padic
