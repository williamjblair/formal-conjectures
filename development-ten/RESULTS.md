# Ten-review development results — 2026-09-08

Ten review attempts finished using GPT-5.6 Sol high: five cases, each with and without the skill. Eight reports assembled and received separate Sol grades. The baseline had one timeout and one invalid report. There were no retries or edited model outputs.

The skill produced more valid reports in this batch, but this is not an accuracy score. All reference labels and grades remain provisional. These five development cases represent three families, and some were examined in earlier pilots. See [the frozen plan](PLAN.md) and [raw summary and grades](summary.json).

| Case | With skill | Baseline |
| --- | --- | --- |
| R01: Known defect | [Domain defect found; repair checked](runs/5cb2a17660651978/report/summary.md) — 2.8 min | [Domain defect found; repair checked](runs/a9ce4f467471f788/report/summary.md) — 3.0 min |
| R02: Corrected counterpart | [No findings](runs/27025e6764082fea/report/summary.md) — 5.0 min | [No findings](runs/38b24fcec9b0f60a/report/summary.md) — 2.3 min |
| R17: Jacobson candidate clean | [Universe-scope finding; key disputed](runs/532254c9e414ce99/report/summary.md) — 5.6 min | [Timed out; no final report](runs/7c13300fa8cd29bf/result.json) — 7.0 min |
| R22: Source unavailable | [No findings; incomplete source coverage](runs/da5b89a9d8c4dfed/report/summary.md) — 3.8 min | [Unresolved semantic finding and documentation nit](runs/48e707e65cd518c9/report/summary.md) — 6.2 min |
| R23: Contested finding | [Prior claim withdrawn; valid report](runs/b72708e5d96aa6d4/report/summary.md) — 5.4 min | [Prior claim withdrawn; report rejected for evidence reference](runs/76b72f2b33d6072c/result.json) — 2.3 min |

## Runtime

Skill: 22.6 total run-minutes, averaging 4.5 minutes; baseline: 20.8 total run-minutes, averaging 4.2 minutes. This is about 9% more time with the skill. These totals include failed runs and the baseline timeout; they are not a controlled estimate of time per correct review. Two reviewer workers ran concurrently, with grading overlapping completed reviews.

The corrected clean case is the clear inefficiency: 301 seconds / 19 tool calls with the skill versus 137 seconds / 6 calls without it, with no findings from either. Focused Lean builds took approximately six seconds in each. Recorded tool execution totaled 17.9 versus 6.4 seconds, so most elapsed time was outside command execution. The remainder includes model reasoning, generation and round-trip overhead.

## Findings and limits

- Both conditions found the known domain defect and checked an appropriate replacement. Both returned no findings on its corrected counterpart.
- The skill handled missing-source uncertainty better in this pair. The baseline escalated an unresolved ambiguity into a semantic finding. The earlier cleanup smoke test showed the skill can make the same mistake; this single pair does not establish reliable prevention.
- The Jacobson skill finding concerns Lean universe scope. The model grader disputes the clean reference label and supports the finding, but human adjudication remains necessary. The baseline timed out, so this is not a paired mathematical-quality comparison.
- Both rereviews withdrew the obsolete domain claim. The baseline placed prose in `prior_evidence` instead of `evidence/prior.txt`; validation rejected its otherwise readable review. That invalid report was not graded.
- The grader called the missing-source semantic finding unresolved while marking uncertainty handling appropriate. That coarse assessment does not establish that escalating it to NEEDS REVISION was justified. Rereview correctness is described in grader comments rather than a dedicated score.

## Next changes suggested by this batch

1. Add a stopping rule for clean reviews and focused rereviews. Require further witnesses or reference searches only when they resolve a concrete uncertainty that affects the finding or verdict.
2. Constrain reconciliation evidence references in the native output schema, using the already-known retained context paths. Keep invalid attempts intact.
3. Assess whether the final severity/verdict is justified, rather than equating missing-source disclosure with appropriate uncertainty. Have a human resolve the disputed Jacobson reference before using it as a clean scoring case.

No skill, schema, reference key or tooling was changed during this batch. Improve these specific points before spending on a larger evaluation.

## Retained evidence

The [manifest](manifest.json) binds the exact procedure, tooling, cases, budgets and image. All frozen input hashes and the artifact hashes of all eight assembled reports were verified. Each run retains native events, commands, outputs, scratch files, raw answer and invocation status. The timeout has no final usage accounting; reported token totals therefore do not support a fair cost comparison. [Blind human review packets](../development-ten-human/feedback.json) are available for all eight assembled reports; human forms remain blank.
