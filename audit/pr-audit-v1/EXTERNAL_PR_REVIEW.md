# Pinned external pull-request review

This is the manual, GitHub-first contract for reviewing a contributor-fork pull request with the existing Formal Conjectures advisory audit. The repository supplies a dry-run workflow. It reads a pull request, checks out its exact pinned head, runs deterministic checks, validates retained isolated-role evidence, and uploads advisory artifacts. It does not post a comment, approve, merge, or make a maintainer decision.

## Trigger and retained inputs

A human or a `workflow_dispatch` acquisition job supplies:

- GitHub owner, repository, and pull-request number;
- expected base and head commit OIDs;
- the freshly observed head commit OID;
- changed path, declaration, head blob OID, and head source SHA-256;
- retained source references and exact roots;
- one content-addressed v1 core manifest;
- four isolated role results: `source_fidelity`, `lean_semantics`, `adversarial_edge_cases`, and `deterministic_verification`.

Each role receives the same pinned input packet and the repository skill at `.agents/skills/review-formal-conjectures-pr/SKILL.md`. A role must not read another role's result before it returns. Role results are advisory evidence and must record typed `pass`, `fail`, `inconclusive`, `error`, or `unavailable` outcomes. Errors and unavailable tools are not failures.

The request file uses `formal-conjectures.external-pr-review-request.v1`. Repository and revision values remain inputs; they are not new authority or acceptance fields.

The source-fidelity, Lean-semantics, and adversarial results must already have been produced in isolated sessions from the same retained packet. This first MVP does not pretend that GitHub Actions can perform semantic review without a configured reviewer runtime. The dry run replays their exact content-addressed results, freshly reruns the deterministic role, and refuses any digest or head mismatch. A later GitHub App may supply the reviewer identity without changing these review semantics.

## Local finalization

After the role outputs have been aggregated into the retained core manifest, run:

```sh
python3 -B scripts/run_external_pr_review.py \
  --request PATH/review-request.json \
  --observed-head HEAD_COMMIT_OID \
  --output-dir PATH/output
```

The entrypoint validates that:

- the observed head equals the pinned head;
- all four role results bind the same exact head source root and claim no independence;
- the generated core binds the requested owner, repository, PR, base, head, path, declaration, and role-result roots;
- the disposition retains the no-acceptance boundary;
- publication mode is `local_draft_only` and `github_write` is false.

It then calls the existing v1 generator and projection code. It emits:

- `audit-core.json` and its SHA-256 sidecar;
- `ReviewReport.md`, the established human projection;
- `pr-comment-draft.md`, a concise local draft suitable for later human editing or publication.

The entrypoint has no GitHub client, token, network call, subprocess adapter, or comment-posting operation.

## Manual GitHub Actions dry run

Run **Advisory external PR review (dry run)** from the Actions tab on the trusted default branch. Supply:

- `owner`: base-repository owner;
- `repository`: base-repository name;
- `pull_request`: positive PR number;
- `expected_head`: exact lowercase 40-character head OID;
- `request_path`: a retained request bundle on the trusted branch;
- `build_target`: the exact Lean module passed to `lake --wfail build`.

The workflow at `.github/workflows/advisory-external-pr-review.yml` has `contents: read`, `pull-requests: read`, and `checks: write`. The sole write creates a neutral `FC advisory review` Check Run on the exact PR head, linked to the workflow run. It cannot approve, merge, or post a comment. The workflow checks out trusted review code and the untrusted PR into separate directories with persisted credentials disabled. Before running contributor code it compares the dispatch values, retained request, live PR base/head, and checked-out commit. A changed head exits as stale and requires a new packet and all roles to rerun.

The deterministic job records the targeted Lean build and `git diff --check` as typed `pass`, `fail`, or `error`. Exit `126` or `127` is an invocation error, not a formalization failure. Logs and the workflow binding are retained separately from the advisory core.

The uploaded artifact is named `advisory-external-pr-<number>-<head>` and contains:

- `action-evidence/live-pr.json` and `workflow-binding.json`;
- deterministic command logs;
- `action-output/audit-core.json` and its SHA-256 sidecar;
- `action-output/ReviewReport.md`;
- `action-output/pr-comment-draft.md`.

There is deliberately no comment-publication job. The Markdown file is ready for human inspection, not automatically posted. The neutral Check Run makes the evidence discoverable from the PR without changing advisory or merge authority.

## New heads and reruns

An observed head mismatch exits with status `3`, emits no output directory, and instructs the operator to prepare a new packet and rerun all four roles. Results from the old head must not be rebound to the new head. `error` and malformed-input exits use status `2`; they must not be reported as review failures.

Comment publication must be a separate later manual action with explicit authorization. It is a public write and is not part of this contract.

## Product and workflow evidence

The MVP uses manual dispatch because GitHub documents typed `workflow_dispatch` inputs and job-level permission reduction, while its security guidance warns against combining privileged triggers with untrusted pull-request checkout. Third-party actions are pinned to full commit OIDs. See [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) and [secure use of GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use).

The artifact-first UX follows GitHub's durable workflow-artifact model. It keeps the machine core, logs, human report, and comment draft inspectable before any public write. See [workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts).

The reviewer products studied support both manual and automatic triggers, but keep useful separations that apply here:

- OpenAI's Codex Action supports structured output files and shows read-only review separated from a write-enabled comment job. Codex's PR-review guidance also says mechanical checks belong in CI rather than being replaced by model review. See [Codex GitHub Action](https://learn.chatgpt.com/docs/github-action) and [Codex GitHub PR review](https://learn.chatgpt.com/docs/third-party/github).
- Claude Code documents interactive and automated review modes, narrow read-only review permissions, actor checks, and optional comment publication. See [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions).
- CodeRabbit distinguishes incremental review from a full rerun after new commits. This contract chooses the simpler, safer rule: every new head invalidates the full panel. See [CodeRabbit commands](https://docs.coderabbit.ai/guides/commands).

The Lean community also separates CI machinery from library code and leaves merge authority with maintainers. The local design follows that boundary: deterministic Lean evidence is producer evidence; semantic roles are advisory; only a human maintainer can act. See [mathlib-ci](https://github.com/leanprover-community/mathlib-ci), [mathlib's PR review guide](https://github.com/leanprover-community/leanprover-community.github.io/blob/lean4/templates/contribute/pr-review.md), and [mathlib4 build guidance](https://github.com/leanprover-community/mathlib4).

These sources support six concrete choices: manual-first triggering; least-privilege identity; artifacts before comments; complete rerun on a new head; explicit human escalation; and deterministic checks kept separate from semantic review. They do not imply an integration with any reviewed product.

## Private GitHub App setup checklist

No App registration, installation, key, webhook, or secret is needed for the current dry-run workflow. When the user is ready to give the bot a dedicated identity, perform this one-time account-side setup. GitHub documents the registration fields and recommends minimum permissions in [Registering a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app), [Choosing permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app), and [Installing your own App](https://docs.github.com/en/apps/using-github-apps/installing-your-own-github-app).

1. Under the user's personal account, open **Settings → Developer settings → GitHub Apps → New GitHub App**.
2. Use a unique, clearly test-labeled name, a short advisory-review description, and the user's fork or account URL as the homepage.
3. Leave callback URL, OAuth authorization during installation, device flow, and setup URL disabled. The bot acts as an installation, not on behalf of a user.
4. For the manual-only MVP, disable webhooks. There is no webhook URL or webhook secret. A later automatic mode would separately enable the `pull_request` event with a webhook secret and SSL verification.
5. Set repository permissions to **Contents: Read-only** and **Pull requests: Read-only**. Leave Actions, Checks, Issues, Workflows, Administration, and every other permission at **No access**. Metadata read access is implicit.
6. Select **Only on this account**. Install it with **Only select repositories**, choosing only the user's Formal Conjectures fork.
7. Do not generate or store a private key for the dry run. If a later explicitly authorized publication job is added, generate one key, store the App ID and private key as protected repository or environment secrets, use a short-lived installation token, and never put the key in the repository or artifacts.
8. Only for that later publication job, raise **Pull requests** to **Read and write**. Do not add Issues write unless publication is implemented through the issue-comment endpoint. Add Actions write only if the App itself must dispatch workflows; manual dispatch does not need it. Add Checks write only if a future design chooses GitHub Check Runs instead of artifacts.

GitHub distinguishes App, installation, and user authentication. This design uses installation identity for future automation and does not need user OAuth. See [GitHub App authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/about-authentication-with-a-github-app).

Nothing here is a Vela Verification, maintainer disposition, acceptance, a merge decision, or a claim of mathematical truth.
