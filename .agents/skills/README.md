# Agent skills

Three skills covering the loop a contributor walks: choose work, write a statement, check one.
Each is a directory whose name matches its `name:` field, holding `SKILL.md`, optional
`references/` read on demand, and optional `scripts/` that travel with the skill.

| skill | for |
|---|---|
| `pick-issue` | choosing an issue that is genuinely unclaimed and within reach |
| `formalize` | turning a source statement into a faithful Lean statement |
| `review` | checking a statement against its source, with two bundled tools |

They compose: `formalize`'s last step runs `review` against your own draft, and `pick-issue`
runs before either.

## Skill tools and repository scripts are different things

A tool under a skill's `scripts/` is invoked by whoever is following that skill, and must run
without a checkout of this repository. A script under the repository's top-level `scripts/` is
CI automation, invoked by a workflow, and may assume the repository around it.

`review/scripts/verify_formal_proof.py` deliberately restates the `formal_proof` link regex
that `scripts/check_proof_links.py` owns, for that reason. If the two disagree, the repository
script is the definition.

## Validating

```bash
uvx --from git+https://github.com/agentskills/agentskills#subdirectory=skills-ref \
  skills-ref validate .agents/skills/<name>
```

The directory name must equal the skill's `name:`. Tests for the bundled tools live beside
them and run with `pytest`.
