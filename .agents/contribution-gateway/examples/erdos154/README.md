# Historical Erdős 154 reconstruction

This example runs the Contribution v0 contract against a real contribution that
already entered the Formal Conjectures ecosystem.

It is a **reconstruction**, not a claim that the gateway participated in the
original 2026 review.

## Historical contribution

- Authority: `google-deepmind/formal-conjectures`.
- Upstream PR: #4340, merged 2026-06-29 at
  `fbe4917de96511a6553e58144d59814110c47b2e`.
- Target: `FormalConjectures/ErdosProblems/154.lean:Erdos154.erdos_154`.
- External proof: `Erdos154.erdos_154_sumset` in `williamjblair/lean-proofs`.
- The current proof index contains a Lean-kernel attestation with the axiom
  footprint `[propext, Classical.choice, Quot.sound]` and `axioms_clean: true`.

## Why the packet does not say ready

The historical exact-reference object records the producer/authority relation as
`close` with a `normalized` translation and explicitly says that this does **not**
claim byte identity or automatic semantic equivalence with Formal Conjectures.

Therefore the reconstructed manifest records:

- mechanical validity: `pass`;
- provenance: `pass`;
- priority: `not_applicable` for this historical formal-proof-link contribution;
- semantic fidelity: `unresolved`;
- resolution validity: `unresolved`;
- dependency impact: `unresolved`.

Running the gateway should therefore yield:

```text
NEEDS_FIDELITY_REVIEW
```

That is the intended behavior. A kernel-clean external proof and a merged link
are evidence, but they do not cause the gateway to manufacture a missing
semantic-equivalence review after the fact.

## Replay

From `.agents/contribution-gateway/`:

```bash
PYTHONPATH=src python -m fc_contribution.cli check \
  examples/erdos154/contribution.json --root .

PYTHONPATH=src python -m fc_contribution.cli packet \
  examples/erdos154/contribution.json --root . \
  --out /tmp/erdos154-packet.json
```

This example is deliberately useful as a gap detector. A future independent
fidelity review can be bound to the manifest with `bind-review`, at which point
resolution review can proceed without rewriting or discarding the mechanical
and provenance evidence already bound here.
