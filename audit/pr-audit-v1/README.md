# Pull-request audit records, version 1

> **Prototype safety gate:** do not install this packet as automatic upstream PR execution yet. Read [THREAT_MODEL.md](THREAT_MODEL.md). Any future untrusted execution must use the unprivileged `pull_request` event, an explicit read-only token with no secrets, and an ephemeral GitHub-hosted runner; it must never execute contributor bytes from `pull_request_target`, `workflow_run`, or another privileged job. The retained historical build successes are evidence about those exact historical jobs, not evidence that a future acquisition/execution sandbox is safe.

This packet defines an offline evidence record for a Formal Conjectures pull request. It separates two things that age differently:

- `formal-conjectures.pr-audit.v1` is an immutable core over exact source/method identity and normalized deterministic results.
- `formal-conjectures.pr-audit-observation.v1` is a separately rooted envelope for mutable GitHub status, reviews, acquisition events, and presentation provenance. It points to the core root.

Neither record decides whether to merge a pull request. A `pass` means only that the named implementation evaluated the named property over the listed, rooted inputs. Every check records this boundary explicitly in `does_not_establish`; disposition-wide boundaries remain in `nonclaims`. `unavailable` is not `fail`, and a successful mechanical check does not establish source fidelity.

## Generate

From the repository root:

```sh
python3 scripts/generate_pr_audit.py core \
  --input audit/pr-audit-v1/fixtures/conditional-erdos-427-4884/core-input.json \
  --output /tmp/core.json --sha256-sidecar

python3 scripts/generate_pr_audit.py observation \
  --input audit/pr-audit-v1/fixtures/conditional-erdos-427-4884/observation-input.json \
  --core /tmp/core.json \
  --output /tmp/observation.json --sha256-sidecar

python3 scripts/project_pr_audit_summary.py \
  --core /tmp/core.json \
  --output /tmp/summary.md
```

The Markdown file is an escaped, deterministic projection of a validated,
canonically framed core. It is suitable for a GitHub summary dry run, but the
command performs no GitHub write and the JSON core remains authoritative. The
summary projection is intentionally outside the generator's attested overlay,
so adding or changing presentation code does not change existing core roots.

The full test command includes an offline Draft 2020-12 registry containing both local schemas and validates all ten frozen core/observation records without network resolution:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s scripts -p 'test_*.py'
```

The repo-local skill at
`.agents/skills/review-formal-conjectures-pr/SKILL.md` gives an agent the same
offline sequence: generate with the native CLI, optionally bind an observation,
then render this advisory summary. It forbids live acquisition, contributor-code
execution, GitHub posting, or authority claims. The skill is an operator guide;
it does not add another audit implementation or conclusion.

The library and CLI do not call Git, GitHub, Lean, a model, the network, or a subprocess. Producers run those systems separately. The core manifest retains only exact source/method/configuration identity, exact query and variables, time-free normalized results, typed per-check results, and their roots. Raw host responses, acquisition receipts, request IDs, HTTP metadata, cursors, runner details, timestamps, and preparation events live only in the observation/provenance manifest. Each check input names its core artifact ID; generation rejects both unreferenced evidence artifacts and references whose roots do not match the retained bytes. Generation also refuses absolute paths, traversal, symlinks, missing files, digest mismatches, duplicate identifiers, unknown versions, floats, out-of-range integers, lone surrogates, and duplicate JSON keys.

A missing required method/configuration file is a malformed input packet and generation refuses it; it is not silently converted to an `unavailable` check. A producer-level missing tool may be `unavailable` only when the packet retains the exact execution procedure and a real attempted invocation with the requested and resolved command, environment, process-start state, exit status, stdout, and stderr. The Rupert fixture carries both boundaries separately. Its packet-inspection check says the original proof packet lacks an exact Comparator execution identity. Its tool-availability check runs the inert command `comparator --help` under the declared closed `PATH=/usr/bin:/bin`, records that resolution and invocation were attempted, and records `process_started: false`, a null resolved path and exit status, and normalized `executable_not_found` evidence. That is an unavailable tool in that declared environment, not a proof failure or a claim that Comparator is generally unavailable.

Model checks are likewise deferred in v1. The generator rejects `model-*` properties until a profile roots the model/version, provider or local weights, prompt, rubric, exact inputs, request parameters, and raw output. This keeps a copied metadata check from masquerading as a model error or disagreement record.

The core examples retain exact source bytes, commit/tree/blob identities, commit-qualified workflow or review-guide bytes, the exact named snapshot query and variables, a time-free normalized repository result, and a time-free normalized job result where a build is claimed. The request identity binds the exact query and normalized-result digests without importing an acquisition clock. The generator recomputes Git blob OIDs, binds every implementation and evidence tuple to retained inputs, and verifies the exact job/workflow, job/run/head/success, and URL tuple. Immutable linked proof bytes remain core evidence; their HTTP acquisition event remains outside the core.

The observation manifests retain the raw public GitHub GraphQL and job responses, named observation query, acquisition receipts, HTTP/raw-URL provenance, and AI packet-preparation events. Changing any of those event or presentation fields changes the observation root but not the core root. The primary GraphQL receipt-derived fields are embedded in the published envelope so standalone validation can recompute that descriptor binding rather than trusting a detached summary. Auxiliary provenance artifacts are content-rooted as events; their presence is not an authenticated-host claim. No receipt is a cryptographic GitHub signature.

## Typed result waist

Every supported check binds exactly one `formal-conjectures.pr-audit-typed-result.v1` artifact. That artifact repeats the complete normalized check projection and its exact input relations, then records a typed producer. Its relation locator carries the producer kind and identity, so standalone core validation can reconstruct the canonical result bytes and verify the retained descriptor digest. Generation refuses an unknown property, a check-only rewrite, a result-only rewrite, or a missing/extra typed result. Property-specific validation additionally binds the repository snapshot, exact-head job success, conditional proof/condition/assumption tuple, proof-target classification, Comparator packet identity, retained missing-tool invocation, or semantic review as applicable.

A semantic result carries the exact outcome, severity, finding, witness, head commit/blob/source root, scope, declarations, method, preparer, reviewer, authority, independence, and head-source relation. Current semantic fixtures are explicitly AI-prepared advisory records. They may expose a finding, but they cannot claim independent-human authority or produce `clean`. Version 1 has no fabricated independent clean result.

## Canonical byte profile

Roots use the exact bytes of an integer-only I-JSON subset of RFC 8785 JSON Canonicalization Scheme:

- strings and object keys are preserved exactly; Unicode is not normalized;
- lone surrogates are rejected;
- floats and integers outside `[-(2^53-1), 2^53-1]` are rejected;
- object keys are ordered by UTF-16 code units;
- JSON is compact and has no terminal newline.

Files add one LF as transport framing. A record's internal `root` hashes the unframed JCS bytes with its `root` member omitted. A `.sha256` sidecar hashes the stored file bytes, including the framing LF. Set-like arrays are ordered explicitly by the generator; proof records use the full declaration, kind, locator, and condition tuple.

## Generator identity

Every record carries the exact upstream baseline commit and tree plus a content-addressed overlay of the executable Python and both schemas. This is truthful before the overlay is committed: it does not invent a future source commit. Rebuilding fixtures updates the overlay file digests and root.

## Frozen examples

| Fixture | Distinction represented | Advisory result |
| --- | --- | --- |
| `clean-candidate-dean-4878` | mechanically well-identified candidate, without retained independent semantic ground truth | `inconclusive` |
| `conditional-erdos-427-4884` | full formal-proof tuple with an explicit Shiu assumption | `inconclusive` |
| `fidelity-erdos-887-1237` | `answer(sorry)` under `C`/`n` binders despite the exact-head docstring asking for one absolute `K` | `needs_revision` |
| `vacuity-erdos-80-4830` | impossible density witness at `c = 2`, `n = 100` | `needs_revision` |
| `unavailable-rupert-3959` | exact-head build passes; proof metadata names only a mutable repository root, and a separate retained Comparator availability preflight records a missing executable in its declared environment | `unavailable` |

The first fixture is intentionally named `clean-candidate` and is not marked `clean` in its record. The generator permits `clean` only when a retained passing semantic check is in `human_review` mode and has the `independent` role. GitHub approval in an observation does not silently become that semantic ground truth.

The FC-03 five-case ground-truth exit remains unmet. An exact-head independent human fidelity review is still required for the clean candidate; the fixtures must not be described as a completed clean/source-faithful ground-truth set until that record exists. The Erdős 887 and 80 witnesses are rooted to their exact PR-head blobs and are retained replays, not substitutes for that clean-case review.

See [example-pr-4878.md](example-pr-4878.md) for the escaped human-readable projection. The JSON record is authoritative.
