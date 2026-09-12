# Formal Conjectures contribution gateway v0

This package turns an **untrusted external mathematical contribution** into a
content-addressed review packet for an authoritative Formal Conjectures target.

It is deliberately not a prover, not a Lean verifier service, and not an approval
bot. Existing tools should produce the evidence. The gateway binds that evidence
to one exact authority revision and exposes the unresolved acceptance questions.

The design principle is:

> federated production, native authority, portable verification.

Formal Conjectures remains authoritative for its statements and merge decisions.
External agents and repositories remain free to produce candidate work. This
package records the relationship between them.

## Contribution v0

Every contribution identifies:

- an authoritative repository, revision, and target;
- the producer and proposed artifact;
- the claimed relationship to the target;
- evidence for six review dimensions.

The five mandatory gates are:

1. `mechanical_validity`: does the artifact pass the relevant executable checker?
2. `semantic_fidelity`: does it formalize/prove the intended source statement, without hidden strengthening or drift?
3. `resolution_validity`: does it actually settle the named target at the claimed scope?
4. `priority`: is the novelty/priority claim resolved enough for the requested contribution?
5. `provenance`: are producer identity, source artifacts, revisions, and evidence bindings explicit?

`dependency_impact` is informative in v0 and can record what the contribution
uses, supersedes, or changes downstream.

A packet may end in `READY_FOR_MAINTAINER_REVIEW`, but never `APPROVED`. Human or
upstream authority remains final.

## CLI

```bash
cd .agents/contribution-gateway
python -m venv .venv
. .venv/bin/activate
pip install -e .

fc-contribution init \
  --repository google-deepmind/formal-conjectures \
  --revision <exact-commit> \
  --target FormalConjectures/.../Target.lean:TheoremName \
  --artifact ../producer/Proof.lean \
  --producer external-agent \
  --out contribution.json

# Edit the gate statuses and bind evidence receipts.
fc-contribution check contribution.json --root /path/to/evidence-root

# Bind an independent fc-review-bot result to the gate it was commissioned to assess.
fc-contribution bind-review contribution.json \
  --gate semantic_fidelity \
  --review reviews/fidelity.json \
  --root /path/to/evidence-root

fc-contribution packet contribution.json --root /path/to/evidence-root --out packet.json
```

The packet contains canonical hashes of the manifest and every bound local
evidence file. Re-running the command on the same bytes yields the same packet
root.

## Existing evidence producers

v0 is intended to consume, not replace, artifacts from existing repository
machinery, including:

- `lake env lean` / `#print axioms` receipts;
- the embedded `fc-review-bot` advisory review JSON;
- source/fidelity audits;
- `formal_proof` link checks;
- literature/priority review artifacts;
- Git commit and environment identifiers.

The `bind-review` adapter accepts only independent `fc-review-bot` v1 receipts,
preserves their exact input root and nonclaims boundary, and cannot be used for
`mechanical_validity`.

An evidence reference can be a local file, a URL, or both. A local evidence file
may carry a required SHA-256 digest, in which case `check` fails closed on a
mismatch.

## Recommendation states

The deterministic v0 classifier can emit:

- `INVALID`
- `FIDELITY_FAILED`
- `DOES_NOT_RESOLVE_TARGET`
- `PROVENANCE_FAILED`
- `PRIORITY_CONFLICT`
- `NEEDS_MECHANICAL_VERIFICATION`
- `NEEDS_FIDELITY_REVIEW`
- `NEEDS_RESOLUTION_REVIEW`
- `NEEDS_PROVENANCE_REVIEW`
- `PRIORITY_UNRESOLVED`
- `READY_FOR_MAINTAINER_REVIEW`

The classifier is intentionally boring. It does not infer scientific truth from
prose. It makes missing review dimensions impossible to hide behind a green Lean
build.

## Tests

The tests use only the Python standard library:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Why this lives under `.agents/`

This is experimental agent-facing tooling, like `fc-review-bot`. It is not part
of the Formal Conjectures mathematical authority and should not be imported by
formal statements.
