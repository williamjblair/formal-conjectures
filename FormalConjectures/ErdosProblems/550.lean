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
# Erdős Problem 550

*References:*
- [erdosproblems.com/550](https://www.erdosproblems.com/550)
- [EFRS85] P. Erdős, R. J. Faudree, C. C. Rousseau, and R. H. Schelp, *Multipartite graph-sparse
  graph Ramsey numbers*. Combinatorica **5** (1985), no. 4, 311–318.
- [Ch77] V. Chvátal, *Tree-complete graph Ramsey numbers*. Journal of Graph Theory **1** (1977), 93.
-/

open SimpleGraph

namespace Erdos550

/-- The off-diagonal Ramsey number $R(G_1,G_2)$, defined as the least $N$ such that every
graph on $N$ vertices contains a copy of $G_1$ or its complement contains a copy of $G_2$.
This definition is total for arbitrary graph types: if no natural number qualifies, it returns
`0` by the convention `Nat.sInf ∅ = 0`. -/
noncomputable def offDiagRamseyNumber {V₁ V₂ : Type*}
    (G₁ : SimpleGraph V₁) (G₂ : SimpleGraph V₂) : ℕ :=
  sInf {N : ℕ | ∀ H : SimpleGraph (Fin N), G₁.IsContained H ∨ G₂.IsContained Hᶜ}

/-- The complete multipartite graph whose part sizes are given by `sizes`. -/
abbrev multipartiteGraph {k : ℕ} (sizes : Fin k → ℕ) :
    SimpleGraph (Σ i : Fin k, Fin (sizes i)) :=
  SimpleGraph.completeMultipartiteGraph (fun i => Fin (sizes i))

/-- In `multipartiteGraph`, two vertices are adjacent exactly when they are in different parts. -/
@[category test, AMS 5]
theorem multipartiteGraph_adj {k : ℕ} (sizes : Fin k → ℕ) {i j : Fin k}
    {x : Fin (sizes i)} {y : Fin (sizes j)} :
    (multipartiteGraph sizes).Adj ⟨i, x⟩ ⟨j, y⟩ ↔ i ≠ j := by
  rfl

/-- If all parts are nonempty, the chromatic number of `multipartiteGraph sizes` is the number of
parts. The positivity hypothesis is needed because a zero-sized part contributes no vertices. -/
@[category API, AMS 5]
theorem multipartiteGraph_chromaticNumber {k : ℕ} (sizes : Fin k → ℕ)
    (hpos : ∀ i, 0 < sizes i) :
    (multipartiteGraph sizes).chromaticNumber.toNat = k := by
  rw [multipartiteGraph]
  have hχ := SimpleGraph.completeMultipartiteGraph.chromaticNumber
    (fun i : Fin k => Fin (sizes i)) (fun i => ⟨0, hpos i⟩)
  rw [hχ]
  simp

/-- With its sole part zero-sized, the one-part complete multipartite graph has no vertices and
chromatic number zero. -/
@[category test, AMS 5]
theorem multipartiteGraph_empty_parts :
    (multipartiteGraph (fun _ : Fin 1 => 0)).chromaticNumber = 0 := by
  letI : IsEmpty (Σ i : Fin 1, Fin 0) := ⟨fun x => Fin.elim0 x.2⟩
  exact SimpleGraph.chromaticNumber_eq_zero_of_isEmpty

/-- The definition of `offDiagRamseyNumber` gives zero for a pair with an empty target graph on no
vertices; this is a boundary case excluded by the positive part-size hypotheses in the problem. -/
@[category test, AMS 5]
theorem offDiagRamseyNumber_empty_target :
    offDiagRamseyNumber (⊥ : SimpleGraph (Fin 0)) (⊥ : SimpleGraph (Fin 0)) = 0 := by
  apply Nat.sInf_eq_zero.mpr
  left
  intro H
  exact Or.inr SimpleGraph.IsContained.of_isEmpty

/--
Let $m_1\leq\cdots\leq m_k$ and $n$ be sufficiently large. If $T$ is a tree on $n$ vertices and
$G$ is the complete multipartite graph with vertex class sizes $m_1,\ldots,m_k$ then prove that
$$R(T,G)\leq (\chi(G)-1)(R(T,K_{m_1,m_2})-1)+m_1.$$

The formal statement represents the ordered positive part sizes by a monotone function on `Fin k`,
and represents “$n$ sufficiently large” by one threshold that works for every `n`-vertex tree.
For a complete multipartite graph with positive parts, `χ(G) = k`; the displayed natural-number
form uses the `toNat` of Mathlib's extended-natural chromatic number.
-/
@[category research open, AMS 5]
theorem erdos_550 (k : ℕ) (hk : 2 ≤ k) (sizes : Fin k → ℕ)
    (hsizes_pos : ∀ i, 0 < sizes i) (hsizes_mono : Monotone sizes) :
    let m₁ := sizes ⟨0, by omega⟩
    let m₂ := sizes ⟨1, by omega⟩
    ∃ N₀ : ℕ, ∀ n ≥ N₀, ∀ T : SimpleGraph (Fin n), T.IsTree →
      offDiagRamseyNumber T (multipartiteGraph sizes) ≤
        ((multipartiteGraph sizes).chromaticNumber.toNat - 1) *
            (offDiagRamseyNumber T (completeBipartiteGraph (Fin m₁) (Fin m₂)) - 1) + m₁ := by
  sorry

/-- Chvátal [Ch77] proved that $R(T,K_m)=(m-1)(n-1)+1$. -/
@[category research solved, AMS 5]
theorem erdos_550.variants.chvatal (m n : ℕ) (hm : 0 < m) (hn : 0 < n) :
    ∀ T : SimpleGraph (Fin n), T.IsTree →
      offDiagRamseyNumber T (completeGraph (Fin m)) = (m - 1) * (n - 1) + 1 := by
  sorry

end Erdos550
