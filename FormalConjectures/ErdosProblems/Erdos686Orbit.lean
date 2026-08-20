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

import FormalConjectures.ErdosProblems.Erdos686Padic

/-! Finite modular orbit infrastructure for Erdős Problem 686. -/

namespace Erdos686Orbit

open Matrix
open Erdos686Padic

abbrev Idx := Fin 3
abbrev Vec (R : Type*) := Idx → R
abbrev Mat (R : Type*) := Matrix Idx Idx R

def vec {R : Type*} [Zero R] (a b c : R) : Vec R := ![a, b, c]

def nMat (R : Type*) [Ring R] : Mat R :=
  !![-1, 0, 2;
      1, -1, 0;
      0, 1, -1]

def step (R : Type*) [CommRing R] (x : Vec R) : Vec R :=
  nMat R *ᵥ x

lemma iterate_step (R : Type*) [CommRing R] (k : ℕ) (x : Vec R) :
    (step R)^[k] x = (nMat R) ^ k *ᵥ x := by
  induction k generalizing x with
  | zero => simp
  | succ k ih =>
      rw [Function.iterate_succ_apply, ih, step]
      rw [← Matrix.mulVec_mulVec, ← pow_succ]

def castVec (m : ℕ) (x : Vec ℤ) : Vec (ZMod m) :=
  fun i => x i

lemma cast_step (m : ℕ) (x : Vec ℤ) :
    castVec m (step ℤ x) = step (ZMod m) (castVec m x) := by
  ext i
  fin_cases i <;>
    simp [castVec, step, nMat, Matrix.mulVec, dotProduct, Fin.sum_univ_succ]

lemma cast_iterate_step (m k : ℕ) (x : Vec ℤ) :
    castVec m ((step ℤ)^[k] x) = (step (ZMod m))^[k] (castVec m x) := by
  induction k generalizing x with
  | zero => simp
  | succ k ih =>
      rw [Function.iterate_succ_apply, Function.iterate_succ_apply, ih, cast_step]

lemma pow_eq_pow_mod {R : Type*} [Monoid R] (A : R) (L k : ℕ)
    (_hL : 0 < L) (hperiod : A ^ L = 1) :
    A ^ k = A ^ (k % L) := by
  calc
    A ^ k = A ^ (k % L + L * (k / L)) := by rw [Nat.mod_add_div]
    _ = A ^ (k % L) * A ^ (L * (k / L)) := by rw [pow_add]
    _ = A ^ (k % L) * (A ^ L) ^ (k / L) := by rw [pow_mul]
    _ = A ^ (k % L) := by rw [hperiod, one_pow, mul_one]

end Erdos686Orbit
