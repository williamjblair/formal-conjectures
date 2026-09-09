import «FormalConjecturesTest».«PackageExport»

import Submission

theorem fc_problem : @Eq.{1} Nat
  (@HAdd.hAdd.{0, 0, 0} Nat Nat Nat (@instHAdd.{0} Nat instAddNat)
    (@OfNat.ofNat.{0} Nat (nat_lit 2) (instOfNatNat (nat_lit 2)))
    (@OfNat.ofNat.{0} Nat (nat_lit 2) (instOfNatNat (nat_lit 2))))
  (@OfNat.ofNat.{0} Nat (nat_lit 4) (instOfNatNat (nat_lit 4))) := @Submission.fc_problem

