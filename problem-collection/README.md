# Formal Conjectures Problem collection profile

This directory is a small source-owned candidate registry for durable Problem identities. It is
deliberately narrower than the declaration inventory produced by `extract_names`: only explicitly
reviewed `research open` declarations may be grouped into a Problem. Open status is an attributed
source assertion with declaration evidence and a last-checked revision, not an inference from
missing proof data.

The pilot makes no decision for Formal Conjectures maintainers. In particular,
`authority_effect` is `none`; the output cannot create a Vela Claim or Standing, prove that a
conjecture is open, or imply maintainer acceptance.

## Files

- `profile-v1.json` defines the inclusion, identity, history, rights, and authority boundaries.
- `pilot/registry.json` assigns candidate Problem IDs, groups declarations, and records exclusions.
- `pilot/candidate-metadata-v2.json` is a rooted, reviewed projection of the metadata-v2 extractor's
  actual `theorem`, `module`, and `category` fields; the builder deterministically maps each Lean
  module to its tracked source path, and every entry must have exactly one durable included/excluded
  route.
- `schema/problem-collection-snapshot-v1.schema.json` describes canonical generated output.
- `pilot/snapshot.json` is generated from one exact Git commit and committed separately.
- `../scripts/build_problem_collection.py` validates and deterministically builds the snapshot.
- `../scripts/test_build_problem_collection.py` includes hostile-mutation tests.

The registry JSON and generated snapshot are non-software materials covered by the repository's
CC-BY-4.0 grant. The validator and schema are software covered by Apache-2.0. Each retained
question has its own attribution, license, derivation, and retention permission. This pilot keeps
only questions from source classes the repository identifies as CC-BY-SA-4.0 (Wikipedia, OEIS,
and MathOverflow); rights-unknown questions are explicit exclusions. Source-page and paper bytes
are not copied into the registry.

## Exact reproduction

From a clone containing the bound commit printed in `pilot/snapshot.json`:

```bash
python3 scripts/build_problem_collection.py \
  --source-commit <40-character-commit> \
  --check problem-collection/pilot/snapshot.json
```

The builder reads every input with `git show <commit>:<path>`. Pages output, a network service,
and the working tree are therefore not inputs. The command fails if the tracked snapshot differs
byte-for-byte, if a listed declaration is absent or not `research open`, or if any identity,
history, question, rights, status, title, or source field violates the profile. A machine-only
declaration without one unique included/excluded registry route fails closed; it cannot become a
ghost Problem. Parameterized families retain their own IDs and use explicit Problem relations.
FC module-derived source keys are kept distinct from upstream identities: an upstream identity is
recorded only where the tracked locator exposes an exact provider ID.

## Candidate decisions still owned upstream

Before this can be canonical, Formal Conjectures maintainers must decide whether to own this ID
namespace, where the registry lives, who reviews additions and history events, whether verbatim
FC docstrings are the preferred question text, and which third-party rights states are admissible.
Until then this branch is a falsifiable contributor-fork candidate only.
