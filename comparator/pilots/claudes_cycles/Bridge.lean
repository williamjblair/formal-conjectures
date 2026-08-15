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

/- Draft bridge. This file is not imported by Formal Conjectures. -/
import FormalConjectures.Paper.ClaudesCycles
import KnuthClaudeLean

namespace ClaudesCyclesPilot

/-- The external proof theorem uses the same function representation as FC,
but packages adjacency as a `Digraph`. All conversions are exposed here. -/
theorem external_proof_implies_fc
    {m : ℕ} [NeZero m] (hm : Odd m) (hm' : 1 < m) :
    ClaudesCycles.HasHamiltonianArcDecomposition m := by
  simpa [ClaudesCycles.HasHamiltonianArcDecomposition,
    ClaudesCycles.IsDirectedHamiltonianCycle, ClaudesCycles.cubeAdj,
    ClaudesCycles.bumpAt, cubeDigraph, bumpAt] using
      (_root_.cube_hamiltonian_arc_decomposition hm hm')

end ClaudesCyclesPilot
