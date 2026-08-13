# FC-07 Comparator pilot

This packet exercises one exact stable Comparator revision over four retained
execution cases and composes the already-rooted missing/ambiguous target case
from the PR-audit fixture suite.

The execution cases distinguish:

1. an unconditional theorem that Comparator accepts;
2. the same theorem proved through one explicitly permitted named axiom;
3. a solution declaration whose target/kind differs from the challenge;
4. a definition-hole solution that Comparator accepts but that still requires
   an additional semantic verifier; and
5. a proof packet whose exact external artifact and Comparator execution
   identity are unavailable.

The first, third, and fourth inputs are exact copies of Comparator `v4.33.0`
test projects. The conditional case is a bounded derivative of the upstream
disallowed-axiom test: it makes `helper` explicit in `permitted_axioms` so the
conditional pass is visible rather than being collapsed into a clean pass.

The macOS capture uses Comparator's development `fake-landrun.sh`; it is not a
sandbox-isolation test. Nanoda is disabled. Every observation says so. A pass
establishes only the exact configured Comparator property. It does not establish
source fidelity, mathematical novelty, FC acceptance, merge status, Vela
Verification, a human Decision, or Standing.

Reproduce from an exact public Comparator checkout:

```sh
python3 scripts/capture_comparator_pilot.py \
  --comparator-checkout /path/to/comparator-at-3927ad383f208ae977c340a91c48ac9b497d2097
python3 scripts/build_comparator_pilot.py
python3 -B scripts/test_comparator_pilot.py
```

The capture command rebuilds Comparator and lean4export under the pinned Lean
toolchain before executing the cases. `pilot.json` is a canonical, rooted index
over the retained observation records and the existing unavailable fixture.
