# Ten-review development batch

Frozen FC tooling and skill: 0e5d023001ba962e729c96055b0b83a5385fbded.
Five cases from three families; one run per skill/baseline condition (ten reviews).
Selection was fixed before seeing these results:

- R01: known integer-domain defect (479).
- R02: corrected counterpart (479).
- R17: candidate clean control (Jacobson); key remains disputed/provisional.
- R22: source-unavailable workflow (354).
- R23: authored contested prior finding on the corrected statement (479).

All are development cases; none is held-out qualification. Some were examined in
previous pilots. Use GPT-5.6 Sol high with 420 seconds and 30 tool calls per review,
two review workers, and equal tool/source access except for the skill procedure.
A separate Sol call grades each successfully assembled report. These grades are
provisional model judgements, not human scores. No review or grade is silently
retried. Failures stay in the denominator for run completion.

This batch diagnoses behavior; it cannot establish a reliable general accuracy
or improvement rate. No skill, labels or tooling changes are made during it.
