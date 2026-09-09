# FC review

**Freshness:** current
**Semantic review:** NEEDS REVISION
**Review completeness:** complete

Reviewed commit: `2b3c097656ebdece14355e8038f68716c831f60c`
Request: `0e0e251e98b8beb34b13231c6ee97f80f57919969b632936d2ca3b67be841122`
Reviewer: gpt\-5\.6\-sol

Supplied evidence; producer claims are not independently authenticated by this tool.
This report does not decide acceptance or establish source fidelity or proof correctness.

| Check | Reported result | Policy |
| --- | --- | --- |
| build | pass | lake \-\-wfail build FormalConjectures\.Wikipedia\.Jacobson |

- **semantic / source-fidelity** — FormalConjectures/Wikipedia/Jacobson\.lean:49: The source asserts the conjecture rather than asking a yes\-or\-no question\. Wrapping it as \`answer\(sorry\) ↔ \.\.\.\` therefore misclassifies what the source asks to determine and conflicts with the contribution guidance for non\-question statements\.
  Suggestion: State the universal proposition directly, without \`answer\(sorry\) ↔\`\.

- **semantic / statement-soundness** — FormalConjectures/Wikipedia/Jacobson\.lean:49: \`R : Type\` fixes the quantified rings to universe level 0, even though \`JacobsonConjectureFor\` is universe\-polymorphic and the source states the conjecture for rings without this size restriction\. The declared universe \`u\` is consequently unused by this theorem\.
  Suggestion: Quantify \`R : Type u\`, for example \`theorem jacobson\_conjecture : ∀ \(R : Type u\) \[Ring R\] \[IsNoetherianRing R\] \[IsRightNoetherianRing R\], JacobsonConjectureFor R := by \.\.\.\`\.

- **nit / metadata-hygiene** — FormalConjectures/Wikipedia/Jacobson\.lean:46: The theorem docstring calls \`J\` the “Jacobson ideal,” whereas the source and the local definition identify it as the Jacobson radical\. The current term is nonstandard and potentially confusing\.
  Suggestion: Replace “Jacobson ideal” with “Jacobson radical” and terminate the sentence with a period\.

Evidence:

- [evidence/tool\-001\.json](evidence/tool-001.json) (`03e6a6f55d09cfb8a67573a1aeb893505fe395b04cce5ea4731f7d064f165411`)
- [evidence/tool\-002\.json](evidence/tool-002.json) (`dbe37d8561c1e4dd2dce35ac9424904d746bfa3dcd1b1819581e54d94379eda1`)
- [evidence/tool\-003\.json](evidence/tool-003.json) (`d709b796b7ac1bfc0b588d898dd61cd5ed56caa83f11921585952f1abe51c2bc`)
- [evidence/tool\-004\.json](evidence/tool-004.json) (`3ec899c1e0c9a75f8c08670fc66eb5f2d5209998594b7b887ef774e87f5ebea6`)
- [evidence/tool\-005\.json](evidence/tool-005.json) (`462393ba47753d575f03624f2178c9e6cf0bca93133ab04a58f640d47a62354e`)
- [evidence/tool\-006\.json](evidence/tool-006.json) (`13db1985400816e163736f4e03509c48f6c8669e9645e17dc0cb833bcbebc114`)
- [evidence/tool\-007\.json](evidence/tool-007.json) (`50a7313ee54dcca0cb22e0ac318ed21c6b73fa4211ce53ae03ea4ddbe08e7755`)
- [evidence/tool\-008\.json](evidence/tool-008.json) (`f82985a5637bf9339032f1dcfffdf5e4072eefa5f123caea5072f0a470387041`)
- [evidence/tool\-009\.json](evidence/tool-009.json) (`094ff0493dfd9d1de478412b216c3be87889be38ba4d209b4ba0d951cf92eef7`)
- [evidence/tool\-010\.json](evidence/tool-010.json) (`c7c6b48ffae5c53068955bdd11cb8f3fd3f22c20bd461ebf11a304b116588f9b`)
- [evidence/tool\-011\.json](evidence/tool-011.json) (`73daa9a0ea39a829999f0956c8795a4f4d2e7b667dd03134062e5068d70382f1`)
- [evidence/tool\-012\.json](evidence/tool-012.json) (`f4780242ce0dcb5d1b0bdea6e14fa5ba524b517581f86cd5837c042384d2e56a`)
- [evidence/tool\-013\.json](evidence/tool-013.json) (`1b0e752fabd3fe5b06d3a053643254aa36b01075926badd6a1dce3281e2edd6d`)
- [evidence/tool\-014\.json](evidence/tool-014.json) (`fb1cdbc484093715fc40befc32b4542a59459949f43f4046f570559970762004`)
- [procedure/SKILL\.md](procedure/SKILL.md) (`cc379df226f604c67f3d296bf251a8a223ce8e62042b82d3717898aa19080d3f`)
- [sources/document\-1\.txt](sources/document-1.txt) (`0ad18dc15c9bad2baebfcb7c4c2f70c24832f5df1ab50510bf0c8ec8c342a6ef`)
