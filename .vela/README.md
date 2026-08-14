# Formal Conjectures native integration

This source-owned Phase 1 packet exposes exact retained Formal Conjectures
declarations and PR-audit evidence through the draft, non-authoritative Vela
integration chain:

```text
Manifest -> Profile -> Binding -> Method
```

It does not initialize Vela authority and cannot create a Decision, Event, or
Standing. Formal Conjectures keeps ownership of its statements, build,
reviews, proof links, conditions, and governance. The contributor fork proves
the interface without claiming adoption by `google-deepmind/formal-conjectures`.

Validate and reproduce the committed portable example offline:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/validate_formal_conjectures_integration.py
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/build_formal_conjectures_integration_example.py --check
```

The selected cold-consumer example is `Erdos887.erdos_887`. Its retained
mechanical build passed while the separately attributed semantic review found
a binder-scope defect. The mutable observation says the PR later merged and
was approved; none of those facts is acceptance or Vela Standing.

The packet also binds the exact conditional proof metadata for Erdős 427 and
the retained source-fidelity chain for MinModulus. All referenced source and
review bytes are retained in this Git tree. No Math checkout, authority key,
private credential, hosted Vela service, or mutable latest reference is needed.

Contract roots use the Phase 0 framing: parse TOML, normalize it to canonical
JSON, replace the document root field with the empty string, prefix the UTF-8
schema tag and NUL byte, then hash with SHA-256. Generated JSON adds one LF for
file framing; its sidecar hashes those stored bytes.

Architecture custody for this packet:

- canonical memo SHA-256: `3ac5740763db46c2c64a0d2154c6ab464def2cd8371e265d16a9be083f374ead`;
- execution plan SHA-256: `4e499ed9703560bf8f859a709d4e8f9265980e1a089a4e3fe1427583c6a0836f`;
- frozen source packet commit: `96eeecf40bc06ddc8bae6d106f461d4fd774858a`.

Rights are mixed. Repository software is Apache-2.0, repository-authored
non-software material is generally CC-BY-4.0, and conjecture sources may have
source-specific rights. `NOASSERTION` is retained where one license cannot
truthfully cover the combined export. Public availability was observed on
2026-08-13 and is not a promise of perpetual hosting.
