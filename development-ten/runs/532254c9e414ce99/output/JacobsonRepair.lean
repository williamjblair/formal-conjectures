import FormalConjectures.Wikipedia.Jacobson
/-! Typecheck the scoped universe-polymorphic repair. -/
open Ring
universe u
namespace Jacobson
@[category research open, AMS 16]
theorem jacobson_conjecture_universe_repair :
    answer(sorry) ↔ ∀ (R : Type u) [Ring R] [IsNoetherianRing R] [IsRightNoetherianRing R],
      JacobsonConjectureFor R := by
  sorry
end Jacobson
