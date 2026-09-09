import FormalConjectures.Wikipedia.Jacobson
/-! Scoped satisfiability controls. -/
example : IsNoetherianRing (ZMod 2) := inferInstance
example : IsRightNoetherianRing (ZMod 2) := inferInstance
example : (Ring.jacobson (ZMod 2)).IsTwoSided := inferInstance
example : Jacobson.JacobsonConjectureFor (ZMod 2) ↔ (⨅ n : ℕ, Ring.jacobson (ZMod 2) ^ n) = (0 : Ideal (ZMod 2)) := Iff.rfl
