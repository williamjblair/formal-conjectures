# Agents and proof evaluations

Use the existing agent for reasoning. The toolkit prepares exact inputs and verifies
submissions. Evaluation adapters are experimental until their recorded acceptance
checks pass. No model is launched by these commands.

## Install guidance

The normal uv installation includes both portable skills. No global agent settings
are changed during installation.

```sh
conjectures skill path
conjectures skill install --dir .agents/skills
conjectures skill install --name formal-conjectures-review --dir .agents/skills
```

`--dir` is the parent discovery directory. For a Claude project use `.claude/skills`;
other hosts can read the path directly or use their usual skill import mechanism.
Reload the agent after installation. Repeating an identical installation succeeds;
different existing guidance is preserved and reported as a conflict.

## Work on one problem

Run `find` and `show`, select an exact declaration, then use `init TARGET --out DIR`.
Initialization now also works outside an FC checkout. It obtains the exact public
source commit and writes `AGENTS.md` into the generated workspace. Public catalog
availability still depends on #5375; `--catalog FILE` explicitly selects a native
extract for qualification.

The agent edits `Submission.lean` and `.lean` files under `Submission/`. `lake build`
provides development feedback. `conjectures verify DIR` reconstructs trusted files
in a fresh workspace and checks only the submitted Lean files. Configuration,
dependency files, compiled artifacts and candidate workflow files are never imported.

Target bindings are retained outside the submission in the operator's user cache.
The generated provenance is descriptive, not permission to change the trusted target.
A copied or moved workspace requires a new `init` at its destination. Local run
inspection works from a generated workspace, without an FC checkout. Use global
executor configuration when operating across multiple workspaces.

## Linux execution without publishing a candidate

The existing GitHub executor remains available. For local files, use a dedicated,
unprivileged Linux worker with systemd, elan, Go, Rust, and no private credentials.
Do not use a general personal workstation as a verifier for adversarial submissions:
Comparator's Landrun policy can read files outside the candidate directory.

```sh
conjectures setup verify --local --global \
  --toolkit /opt/fc --tools /opt/fc-tools --build-tools
conjectures verify ./proof --json
```

`/opt/fc` must be a clean, operator-owned checkout of the trusted toolkit revision.
`--build-tools` explicitly acquires and builds the pinned generator, Comparator,
Landrun, nanoda and toolchain-compatible exporter. Omit it for already-built tools.
Setup records the toolkit revision and binary digests. Each verification rechecks
them and probes systemd's AF_UNIX restriction. No candidate Git commit or push is
required. Results are attributed to the local operator, not GitHub or an independent
hosted authority. Changed binaries require explicit setup again.

## Freeze a suite

A suite references the existing catalog. It does not contain a duplicate catalog,
reference answers, or agent credentials. Its source must match the selected catalog.

```json
{
  "schema_version": "fc.proof-suite.v1",
  "source": {"repository": "OWNER/REPO", "commit": "EXACT_SOURCE_COMMIT"},
  "execution": {
    "solver_image": "registry/solver@sha256:DIGEST",
    "verifier_image": "registry/verifier@sha256:DIGEST",
    "toolkit_commit": "EXACT_VERIFIER_COMMIT",
    "agent_seconds": 600
  },
  "cases": [{"id": "example", "declaration": "Exact.declaration", "exposure": "Describe prior development exposure"}]
}
```

This is a schema example, not an executable release command. Supply full 40-character
commits and 64-character image digests. The exporter rejects floating tags, duplicate
cases, missing exposure descriptions, and mismatching catalog revisions before export.

```sh
conjectures eval export suite.json --format harbor --out tasks
harbor run -p ./tasks -a YOUR_AGENT -m YOUR_MODEL
conjectures eval summarize ./jobs --json
```

Export records a file-digest manifest and creates one Harbor task per declaration.
The solver gets a workspace and instructions. Only `/app/Submission.lean` and
`/app/Submission/` transfer to a fresh verifier environment. No solution keys are
exported. Harbor owns model access, attempt counts, budgets and trial logs.

## Verifier image contract

Use Harbor task schema 1.4 with **separate verifier environments**. Both base images
must be available by registry digest and support UID/GID 1000. The solver image needs
the source's Lean toolchain and dependencies. The verifier image needs Python 3.11+,
Git, elan, libseccomp2, the clean pinned toolkit at `/opt/fc`, and already-built tools
at `/opt/fc-tools/{generator,comparator,landrun,nanoda}`. Build the compatible exporter
in `/opt/fc/comparator/verifier`. The shared tool acquisition implementation can build
these resources during image construction. Keep credentials and agent logs out of it.

The grader adds an inherited AF_UNIX seccomp restriction before running the same
trusted FC controller and Comparator. Existing container restrictions remain in
force; Landrun and both kernels remain required. Missing tools, unsupported emulation,
failed restrictions and mismatched revisions produce infrastructure errors. This is
not a claim that an arbitrary supplied image has passed release qualification.

| Retained status | Harbor reward | Meaning |
| --- | --- | --- |
| `verified` | 1 | Exact proof passed the configured formal checks |
| `rejected` | 0 | Submission rejected |
| `assessment_required` | None | Formal checks passed; definition-hole semantics need assessment |
| `error` | None | Execution did not establish an outcome |

An absent reward deliberately prevents infrastructure/manual-assessment cases from
becoming ordinary zero scores. Harbor may display these as verifier errors; use
`fc-result.json` to distinguish them. The summary counts retained verifier attempts,
not missing, timed-out or cancelled trials that never reached grading. Use the harness
trial manifest and frozen suite for the complete denominator. Never silently retry
until a proof passes or drop failed attempts from a reported success rate.

The public corpus and any prior solution exposure must remain visible in evaluation
reports. Successful export is not successful proof, and formal verification is not
source-fidelity review, catalog admission, or maintainer acceptance.
