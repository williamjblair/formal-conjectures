# Agent workflow implementation and qualification

Recorded 10 September 2026. This is development work, not a new published release
or upstream acceptance. No model was launched and no paid API call was made.

| Scope | Delivery |
| --- | --- |
| Skill discovery and explicit installation | `codex/fc-toolkit-cli`, existing deferred #5386 |
| Standalone workspaces and local Linux controller | `codex/fc-toolkit-proof-cli`, existing deferred #5387 |
| Frozen suites and Harbor export/grading | `codex/fc-toolkit-evals`, follow-up to the proof branch |
| Combined testing | `codex/fc-toolkit-integration` |

## Recorded checks

- Integration: 98 deterministic toolkit tests passed, including atomic evaluation
  export, external target binding, symlink rejection, configuration preservation,
  missing verifier results and non-scored infrastructure failures.
- Focused branches: 50 core tests, 73 proof tests, and 77 evaluation-branch tests passed.
- Clean wheel/source-distribution packaging passed on macOS and Linux at
  `74299491840e73ba9f070a11384cefeb9425ec08`:
  [package qualification](https://github.com/williamjblair/formal-conjectures/actions/runs/34487976713).
  The installed wheel exposed skill discovery/installation outside a checkout,
  without AI credentials or an installed model adapter.
- Harbor's actual `TaskConfig` accepted the generated task at upstream revision
  `191d1b989bbba1d77c2db23e17aec308d7c08046` (version 0.22.0). This validates the task
  contract, not an end-to-end agent trial or a verifier image.
- The added AF_UNIX filter denied Unix sockets and socket pairs in a native ARM
  Linux container, also denying a child's socket creation while retaining AF_INET.
  This was a functional probe with an installed distribution libseccomp, not a
  pinned production-image qualification. An x86-emulated container could not load
  the filter and correctly returned an execution error.

- A real Harbor no-op trial transferred the submission and retained an infrastructure
  error with no reward when trusted toolkit/tools were deliberately absent. See
  [the receipt](harbor-missing-tools.json). This checks actual artifact/error handling
  through the harness without invoking a model; it is not successful proof grading.

## Linux proof qualification

[34488055221](https://github.com/williamjblair/formal-conjectures/actions/runs/34488055221)
at `0881caf46` exposed a missing source-cache acquisition step: fresh export timed out
before Comparator. The result correctly remained an infrastructure error with policy
unevaluated. The original failed result is preserved.

The controller now populates the exact source's pinned dependencies before export and
retains acquisition logs. A regression checks that acquisition failure cannot reach
export or import submitted code. The corrected matrix is running at
[`74628f9febe204e87f5387338b240124e8b7fd4e`](https://github.com/williamjblair/formal-conjectures/actions/runs/34490305986).
It covers standalone initialization, unfinished proofs, imported assumptions, a valid
proof and a changed executor. Record its final outcome before claiming qualification.

## Remaining acceptance

A complete Harbor trial using qualified, digest-pinned solver and verifier images
remains required. The exporter does not provision or publish arbitrary images.
Until then the adapter remains experimental. Retain failures and missing rewards;
do not interpret a parser check or a Linux socket probe as proof-verifier qualification.

Reopen #5386 only after #4899/#5375 land. Reopen #5387 after #5386/#5337 and
Comparator #87 land. Replay each child's own changes onto current upstream main.
The evaluation follow-up does not block the core CLI. Keep #4394 as the roadmap.
