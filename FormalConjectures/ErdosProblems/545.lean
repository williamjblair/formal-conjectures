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
# Erdős Problem 545

*References:*
- [erdosproblems.com/545](https://www.erdosproblems.com/545)
- [ErGr75] Erdős, P. and Graham, R., *On partition theorems for finite graphs*.
  In *Infinite and finite sets* (Colloq., Keszthely, 1973; dedicated to P. Erdős on his 60th
  birthday), Vol. I, Colloq. Math. Soc. János Bolyai 10, North-Holland (1975), 515--527.
- [Er84b] Erdős, P., *On some problems in graph theory, combinatorial analysis and combinatorial
  number theory*. In *Graph theory and combinatorics* (Cambridge, 1983), Academic Press (1984),
  1--17.
- [CoLo75] Cockayne, E. J. and Lorimer, P. J., *The Ramsey number for stripes*. J. Austral. Math.
  Soc. Ser. A 19 (1975), 252--256.
-/

open SimpleGraph

namespace Erdos545

/- The diagonal Ramsey number of a finite simple graph. -/
noncomputable def ramseyNumber {k : ℕ} (G : SimpleGraph (Fin k)) : ℕ :=
  sInf {N : ℕ | ∀ H : SimpleGraph (Fin N), G.IsContained H ∨ G.IsContained Hᶜ}

/-- The graph formed from `K_n` by adding one vertex adjacent to the first `t` vertices. -/
def asCompleteAsPossible (n t : ℕ) : SimpleGraph (Fin (n + 1)) where
  Adj u v :=
    u ≠ v ∧ ((u.val < n ∧ v.val < n) ∨
      (u.val = n ∧ v.val < t) ∨ (v.val = n ∧ u.val < t))
  symm u v := by
    rintro ⟨hne, h | h | h⟩
    · exact ⟨hne.symm, Or.inl ⟨h.2, h.1⟩⟩
    · exact ⟨hne.symm, Or.inr (Or.inr h)⟩
    · exact ⟨hne.symm, Or.inr (Or.inl h)⟩
  loopless u h := h.1 rfl

/- The construction has the advertised adjacency pattern in a small nontrivial case. -/
@[category test, AMS 5]
theorem asCompleteAsPossible_adjacency :
    (asCompleteAsPossible 3 2).Adj 0 1 ∧
      (asCompleteAsPossible 3 2).Adj 3 1 ∧
      ¬ (asCompleteAsPossible 3 2).Adj 2 3 := by
  simp [asCompleteAsPossible]

/--
Let $G$ be a graph with $m$ edges and no isolated vertices. Is the Ramsey number $R(G)$ maximised
when $G$ is 'as complete as possible'? That is, if $m=\binom{n}{2}+t$ edges with $0\leq t<n$ then
is $$R(G)\leq R(H),$$ where $H$ is the graph formed by connecting a new vertex to $t$ of the vertices
of $K_n$?
-/
@[category research solved, AMS 5]
theorem erdos_545 : answer(False) ↔
    ∀ (n t k : ℕ), 0 ≤ t → t < n →
      ∀ (G : SimpleGraph (Fin k)),
        G.edgeSet.ncard = n.choose 2 + t →
        (∀ v : Fin k, ∃ w : Fin k, G.Adj v w) →
        ramseyNumber G ≤ ramseyNumber (asCompleteAsPossible n t) := by
  sorry

end Erdos545
