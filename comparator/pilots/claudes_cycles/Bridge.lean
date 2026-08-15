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
