# FC review

**Freshness:** current
**Semantic review:** NEEDS REVISION
**Review completeness:** complete

Reviewed commit: `812349d4fbc1d69b403b12b65ba7770592736a5c`
Request: `015af8cdde2380ccc404fcb4173a958f2f8db0863d35053e6728994527a90f3b`
Reviewer: gpt\-5\.6\-sol

Supplied evidence; producer claims are not independently authenticated by this tool.
This report does not decide acceptance or establish source fidelity or proof correctness.

| Check | Reported result | Policy |
| --- | --- | --- |
| build | pass | lake \-\-wfail build FormalConjectures\.Wikipedia\.Jacobson |

- **semantic / source-fidelity** — FormalConjectures/Wikipedia/Jacobson\.lean:49: The source quantifies over every left\-and\-right Noetherian ring, but \`\(R : Type\)\` restricts the formal statement to universe\-zero carriers\. This is narrower than both the source and the universe\-polymorphic \`JacobsonConjectureFor\`\.
  Suggestion: Change \`\(R : Type\)\` to \`\(R : Type u\)\`\. The resulting universe\-polymorphic declaration typechecks\.

Evidence:

- [evidence/tool\-001\.json](evidence/tool-001.json) (`feed208f8955b1fd6cdba7acddd4833d7a74183acd33efd135c0234023c591de`)
- [evidence/tool\-002\.json](evidence/tool-002.json) (`baef0ca42bc826ba52a6d3845d6c2fa3787564e2bd789b81b7b59ba8919732db`)
- [evidence/tool\-003\.json](evidence/tool-003.json) (`ba1ca77e8d0fb8aca750ef4790a4207880f3213d93581bbb763eaa4715065622`)
- [evidence/tool\-004\.json](evidence/tool-004.json) (`3f7dd4ebb8c09a7236fccf8d5ba71c9626e04009fe0c62195449811669a2af14`)
- [evidence/tool\-005\.json](evidence/tool-005.json) (`f45b7cf0e3e05acaf62be785cc585844884e4f2fb7295a67fad30b665a636982`)
- [evidence/tool\-006\.json](evidence/tool-006.json) (`15a2487c2827d5e051d20eb24bfcc2c06a3891de1fc87ec7070bd217a90777df`)
- [evidence/tool\-007\.json](evidence/tool-007.json) (`82b2fc8fa3cd7f3591b5324a3489de545e2b9b0b1d02eff9df53fe7d340aaa15`)
- [evidence/tool\-008\.json](evidence/tool-008.json) (`90203608bb9a5eb57570176493885fbc22765a685bd778d5c789d6eba85d9726`)
- [evidence/tool\-009\.json](evidence/tool-009.json) (`ef9a3c94b127976bb9c721f9f3f2be51dbfe90e869dad1ef0a9d77c8c91b30fd`)
- [evidence/tool\-010\.json](evidence/tool-010.json) (`7d651cd0fd2d26df5ec31920fa61e711b4b3a387a6951552a921467c3b8dba28`)
- [evidence/tool\-011\.json](evidence/tool-011.json) (`fa4dd41c7dd320f540812ed28ac6bb58c5677b515c266ed3dbd05f8eba826144`)
- [evidence/tool\-012\.json](evidence/tool-012.json) (`675e0fe6f80b676d69de0e9de6e22f7ac12fe290c2db08c3963a93031ac71135`)
- [evidence/tool\-013\.json](evidence/tool-013.json) (`4a59e373d74e6b89f3a9bf0f6ad1f27a96acc90bb76c954cc476d0e602dd7248`)
- [evidence/tool\-014\.json](evidence/tool-014.json) (`f09e519e2053f351a70f1c9174c7ab1abeac77e21267920527192f81bdbf4447`)
- [evidence/tool\-015\.json](evidence/tool-015.json) (`1ed8f75c39277032874afe6332efaafc240a1193b176d17591182b0f60d7fc32`)
- [evidence/tool\-016\.json](evidence/tool-016.json) (`bc0d03274c6bcb53b533571d03b234affd6b03c14a07ec4a242bb7109c8ea512`)
- [evidence/tool\-017\.json](evidence/tool-017.json) (`c879ee5f5afa2b9681765448145b64a17f948363a400c2c33327c0ccca70b762`)
- [evidence/tool\-018\.json](evidence/tool-018.json) (`e77de1688ed1fa805ec1339a1f6def946046a303552ce932370d8713530998d3`)
- [evidence/tool\-019\.json](evidence/tool-019.json) (`5ce082bcb340bf5c099bfa7c6644bf9bce6d2a82125dfe324bbb75ca095acc66`)
- [procedure/SKILL\.md](procedure/SKILL.md) (`c9180bc59c72cf49717fc44d7b28328362f86d8e96b240c57f033402f010f9d9`)
- [procedure/references/checking\-in\-lean\.md](procedure/references/checking-in-lean.md) (`2b313bbf1cf6c7c6dc640dc97915abfa5ec30b9c4eb045b86cd957aa340ded42`)
- [procedure/references/verifying\-proofs\.md](procedure/references/verifying-proofs.md) (`42074928475cbdd005b854b5948117339597d7fcb8349496a011675c34f9c1b1`)
- [procedure/rubrics/metadata\-hygiene\.md](procedure/rubrics/metadata-hygiene.md) (`6e9eeaf0b84688d05869221e7a6b0109aa86b426b744a752dc2a24e851a41a23`)
- [procedure/rubrics/source\-fidelity\.md](procedure/rubrics/source-fidelity.md) (`3d7f30b41c805d59eb38f17d19d87f7823d50f284f45c9d7f0bc23dbcf44c6af`)
- [procedure/rubrics/statement\-soundness\.md](procedure/rubrics/statement-soundness.md) (`a5349ffc3a8339a644fa810ef16b9bbf7fb87f23ccc325fc2d7a13aabca994e0`)
- [sources/document\-1\.txt](sources/document-1.txt) (`0ad18dc15c9bad2baebfcb7c4c2f70c24832f5df1ab50510bf0c8ec8c342a6ef`)
