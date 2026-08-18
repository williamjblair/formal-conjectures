# PR 7 audit example

Advisory disposition: **needs\_revision**

| Check | Property | Outcome |
| --- | --- | --- |
| snapshot\-identity | immutable\-input\-identity | pass |
| source\-statement\-fidelity | source\-statement\-fidelity | fail |

## Evidence

- **snapshot\-identity:** The retained PR snapshot binds Paul\-Lez/formal\-conjectures PR 7 to its exact base, head, tree, path, declaration source, and Git blob identity\.
- **source\-statement\-fidelity:** The advisory aggregation fails at meaning severity\. Although the source\_fidelity role reports pass, the lean\_semantics and adversarial\_edge\_cases roles both report that the absorbing terminal value 0 satisfies Nat\.Composite and can witness the unguarded existential after the retained source sequence has stopped\. The deterministic\_verification role remains a typed error because its bounded Lean build did not complete; it is not reclassified as a review failure\. Witness: For n = 8, the structured role evidence gives seq 8 0 = 7, seq 8 1 = 5, and seq 8 2 = 0, while the retained\-source behavior stops after 7, 5; the Lean existential accepts k = 2 through the terminal 0\. This meaning\-level witness resolves the role conflict in favor of fail without relying on the separate verification error\.

Core root: `sha256:cf43baded2bf92aee2ab6f671a0a5fb92940a9d780da452437e85a238a2c12f9`

This is advisory evidence, not a merge decision or a claim of mathematical truth.
