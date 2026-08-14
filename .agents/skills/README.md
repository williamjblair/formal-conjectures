# Agent skills

Each skill is a directory whose name matches its `name:` field, holding `SKILL.md` and,
where useful, `references/` read on demand and `scripts/` that travel with the skill.

| skill | for |
|---|---|
| `pick-issue` | choosing an issue that is genuinely unclaimed and within reach |
| `formalize` | turning a source statement into a faithful Lean statement |

They compose in that order, and both stop short of review: a `review` skill covering the
third step is proposed separately.

## Skill tools and repository scripts are different things

A tool under a skill's `scripts/` is invoked by whoever follows that skill, and must run
without a checkout of this repository. A script under the top-level `scripts/` is CI
automation, invoked by a workflow, and may assume the repository around it. When a skill
tool needs something a repository script also defines, it restates it rather than importing
it, and says so in a comment naming the repository script as the definition.

## Validating

```bash
uvx --from git+https://github.com/agentskills/agentskills#subdirectory=skills-ref \
  skills-ref validate .agents/skills/<name>
```

The directory name must equal the skill's `name:`. Tests for any bundled tool live beside it
and run with `pytest`.
