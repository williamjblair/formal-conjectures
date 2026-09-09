# Review evaluation overhaul — 2026-09-08

These are development observations, not human-validated mathematical accuracy scores.
The implementation is in FC PR #4899. Generated runs are excluded from the source tree.

## Review pilot

Three cases from three families, each run once with and without the skill using GPT-5.6 Sol.
Each run had 420 seconds and 30 workspace-tool calls. Both conditions received the same
candidate and available source documents. Reference keys and fix provenance were hidden.

| Case | Skill | Baseline |
| --- | --- | --- |
| R01: historical integer-domain mismatch | Report assembled; reference defect detected | Report assembled; reference defect detected |
| R17: candidate clean Jacobson statement | Report assembled; reference key disputed by model assessor | Report assembled; reference key disputed by model assessor |
| R22: source unavailable | Timed out | Rejected: claimed complete source review without retained sources |

Four of six reports assembled. Both arms detected the one confirmed reference defect.
The candidate clean key remains disputed, so no clean-case false-alarm rate can be estimated.
Neither condition passed the source-unavailable case. The pilot establishes no skill advantage.

The separate model assessments are provisional. In particular, claims about universe scope
and the answer wrapper need human adjudication. Typechecking a proposed replacement does
not establish that the original was a semantic defect. See [raw counts and assessments](pilot/assessments-v2/summary.json).

An initial assessor response used one-based finding indices and failed validation. The revised
assessor uses a bounded zero-based schema and a separate output set. Both sets are retained.
No raw output was repaired or overwritten.

## Routing

The same description was tested on 12 development and 8 validation queries, three runs each.
Development: 31/36 expected loading decisions; validation: 18/24. All negative queries skipped
the skill. Some positive runs stated intent to use it but never called the loading tool.
These are controlled MCP routing observations, not native-client auto-discovery measurements.
See [development records](routing/development/results.json) and [validation records](routing/validation/results.json).
Earlier protocol attempts remain under `routing-before-isolation/` and are not pooled.

## Validation and next step

- 64 offline script tests pass; all 20 distinct fixture files build with Lean 4.33.1 and --wfail.
- Every candidate matches its recorded Git commit byte-for-byte.
- Container checks confirm non-root execution, a read-only candidate, writable scratch space,
  no networking, no FC history and no unrelated problem sources.
- All 24 mathematical reference keys remain provisional. Qualification runs are blocked until
  a named human reviewer supplies adjudication and evidence.
- [Reference-key packets](key-adjudication/adjudication.json) omit provisional answers.
- [Review feedback forms](human-review/feedback.json) omit model grades and arm labels.
- Native-client discovery/activation and live-web source acquisition remain unmeasured.

## Complete example

[Skill-assisted R01 report](pilot/runs/2bdabb7671f5014c/report/summary.md) ·
[canonical JSON](pilot/runs/2bdabb7671f5014c/report/report.json) ·
[raw model JSON](pilot/runs/2bdabb7671f5014c/model/answer.json)

Keep the entire archive to retain evidence links, exact tooling, provenance, failed attempts,
model events, usage and scratch outputs. Credentials were not copied into this archive.

## Procedure cleanup smoke test

See [cleanup-smoke/RESULTS.md](cleanup-smoke/RESULTS.md). Both new reports assembled; the skill still escalated an unresolved docstring ambiguity. These observations are separate from the earlier pilot and do not establish an accuracy improvement.

## Ten-review development batch

See [development-ten/RESULTS.md](development-ten/RESULTS.md): ten reviews, eight assembled and graded reports; skill 5/5 versus baseline 3/5. Both found the known defect and cleared the corrected counterpart. Skill runs took about 9% more total time; the clean case took over twice as long. Reference/grade disputes and earlier failures remain explicit.
