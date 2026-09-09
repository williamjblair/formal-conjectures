# FC #4899 review evidence

This is a data-only review packet for [FC #4899](https://github.com/google-deepmind/formal-conjectures/pull/4899), published on 9 September 2026. It is separate from the FC source branch. The original local records are preserved.

## Start here

| Evidence | Contents |
| --- | --- |
| [Ten-review development batch](development-ten/RESULTS.md) | Five cases, both arms; eight assembled reports and two failures; raw runs and grades |
| [Six targeted follow-ups](targeted-followup/RESULTS.md) | Clean, unavailable-source and rereview cases; all six reports and grades |
| [Earlier pilot](RESULTS.md) | Six initial reviews, including the timeout and invalid report; separate provisional assessments |
| [Human review forms](development-ten-human/feedback.json) | Blank forms and anonymous packets; no human approval is inferred |
| [Reference-key adjudication](key-adjudication/adjudication.json) | All 24 candidate/source packets with blank adjudication forms |
| [Fixture builds](fixture-builds/) | Historical exact-source build logs |
| [Description routing](routing/) | Controlled loading trials; separate from review accuracy |
| [Build-isolation regression](validation/build-isolation/result.json) | Real Docker/Lean checks for the 9 September fix |
| [Publication manifest](publication-manifest.json) | Original and published digests, redaction status and original-archive verification counts |

## What the new check establishes

The reviewer can edit its scratch Lake configuration. In the regression, an invalid candidate fails normally, then the modified scratch configuration reports a successful build. The new recorded build still rejects that candidate because it uses a fresh container from the pinned image. A separately pinned valid candidate builds twice. No scratch files, shared caches or build outputs enter the recorded build. The test uses no model calls or credentials.

73 offline tests pass, and the seven #5356 integration tests pass against the updated prerequisite. The maintained regression command is `python3 scripts/review-eval/check_build_isolation.py --image fc-review-eval:lean4.33.1 --out <new-directory>`.

## Historical limits

The September 8 build receipts used the same container as reviewer scratch commands. They do not establish the stronger fresh-container check. Their model answers, grades, failures and timing remain historical observations; they have not been silently upgraded or replaced. The 5/5 versus 3/5 result measures report completion, not mathematical accuracy. The six follow-up grades are single model observations. Reference keys remain provisional, including the disputed Jacobson case. Human adjudication is required before qualification.

The named batches include every scheduled run, including empty or invalid JSON answers and timeouts. Earlier setup attempts, the pre-isolation routing experiment and cleanup-smoke raw directories remain local and are described in [ATTEMPTS.md](ATTEMPTS.md); they are not pooled into the reported batches. Links in the original historical notes to those omitted directories will not resolve in this packet.

## Preservation and redaction

Before export, all 140 frozen-file entries and all 329 report-artifact references across 18 assembled reports matched their recorded SHA-256 digests. Operator home paths are replaced with `/home/operator`, and `/private/tmp/` is normalized to `/tmp/`. This changes 125 published files. The publication manifest records each original and published digest. Original embedded hashes remain unchanged, so use the publication manifest for redacted files. Bytecode caches are omitted. Mathematical content, model findings and grades are not edited.

The export was checked for credential-like tokens, and the recorded resource-discovery results in these review batches were empty. Source excerpts and candidate files retain their original provenance and notices. This packet is an inspectable snapshot; it is not a production evidence-retention service or a self-contained Docker image archive. The image ID and exact tooling are recorded for replay where that image remains available.

## Maintainer decision

Review the code and the isolation regression for merging the advisory tool. Review the blank mathematical packets separately before promoting the benchmark to qualification. No maintainer approval, mathematical accuracy estimate, automated acceptance or deployment is claimed here.
