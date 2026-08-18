# Live AI advisory review

This is the local, unshipped contract for a repeatable Formal Conjectures review bot. It uses
Claude as an isolated reasoning backend and a GitHub App as the only review identity. It does not
approve, merge, label, accept, or determine mathematical truth.

## One review loop

The manual workflow `.github/workflows/live-ai-advisory-pr-review.yml` accepts a base repository,
pull request number, exact 40-character head, conclusion-free retained input configuration, and
bounded Lean build target. `run_ai_review` and `publish_comment` both default to `false`.
The local adapter pins `anthropics/claude-code-action` to commit
`d40ddef4c030e508327d6e35a9c45f3368482c50`, defaults to the fixed model ID
`claude-sonnet-5`, and caps each role at USD 5 by default.

When `run_ai_review` is true, the workflow:

1. reads the live PR and refuses a base, PR, or head mismatch;
2. copies only the exact Lean statement, retained source text, role prompt, schema, and
   content-addressed manifest into a sanitized artifact;
3. runs source-fidelity, Lean-semantics, and adversarial-edge-case Claude jobs independently;
4. runs the exact module build and diff check in parallel;
5. validates the three actual model outputs against the schema, with no stored-role fallback;
6. validates every high-confidence localized patch independently and suppresses any patch that
   does not match the pinned line or pass its bounded Lean build and diff check; and
7. emits the complete structured artifact, one stable summary, and zero or more independently
   addressable inline payloads.

The summary marker is stable across the in-progress and final phases. Each inline payload has a
stable role-scoped finding marker and is bound to the exact commit, path, line, and side. Only the
GitHub App publication jobs receive the App key. Model jobs receive only the Anthropic key, a
read-only GitHub token, and sanitized input. Claude is restricted to read-only file tools, MCP is
disabled, full output and progress reporting are disabled, and the model jobs cannot publish.

The PR #2 configuration under `fixtures/fork-dogfood-erdos-430-2/` is an acceptance fixture. It
does not contain a verdict or semantic result. Other reviews use the same engine and contract with
their own exact, source-retaining input identity; they do not require a custom prompt, renderer, or
publication path.

## Outputs

- `input-manifest.json`: exact repository, base, head, declaration, Lean source, retained sources,
  rubric identity, schema identity, and nonclaims.
- `ai-review-panel.json`: all three Claude session receipts, validated structured role outputs,
  every finding, limitations, disposition basis, model/action pins, and content root.
- `runtime-deterministic.json`: typed `pass`, `fail`, or `error` Lean/diff evidence.
- `suggestion-validation.json`: every proposed patch and its independent validation or suppression
  reason.
- `summary.md` and `summary.json`: the single concise marker-bound review state.
- `inline/*.json`: zero or more apply-ready GitHub suggestions. These exist only after exact-line,
  diff, and Lean validation.

Artifacts are retained for 14 days by the sample workflow. A neutral check links to the workflow
run. Neutral is deliberate: model review and deterministic checks are evidence, not acceptance.

## Credentials and first run

The one new credential is an Anthropic API key stored as the protected repository or environment
secret `FC_REVIEW_ANTHROPIC_API_KEY`. Store it outside source control, bound each role with the
workflow's `max_budget_usd_per_role` input, and never paste it into a workflow, issue, PR, artifact,
or chat. The existing
App variables remain `FC_REVIEW_APP_ID` and `FC_REVIEW_APP_PRIVATE_KEY` and are used only by
publication jobs.

The first credentialed run should set `run_ai_review=true` and `publish_comment=false`. It should
demonstrate three fresh structured model receipts, a parallel typed Lean result, patch suppression
or validation, and the final artifact without changing the PR. Publication needs a separate run
with `publish_comment=true` after a human inspects that artifact.

## Design rationale

- The official [Claude Code Action structured-output contract](https://github.com/anthropics/claude-code-action/blob/main/docs/usage.md#structured-outputs)
  exposes one JSON `structured_output` when `--json-schema` is supplied. The workflow pins the
  action commit, preserves the action session ID, and validates the JSON again in the FC runner
  before any downstream behavior.
- [Claude Code structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs)
  define schema-constrained agent results. The FC validator additionally binds each result to the
  exact input root, role, authority, and nonclaims, and refuses a missing receipt.
- [GitHub App best practices](https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/best-practices-for-creating-a-github-app)
  call for minimum permissions, secure credentials, appropriate token types, and minimal event
  subscriptions. The publisher uses a short-lived installation token; the model never receives it.
- [Claude Code Review](https://code.claude.com/docs/en/code-review) documents parallel specialist
  analysis followed by candidate verification and neutral, non-blocking review output. The FC roles
  are independent and their patch proposals face a separate Lean validator.
- [CodeRabbit walkthroughs](https://docs.coderabbit.ai/pr-reviews/walkthroughs) separate a stable
  overview from inline findings. The FC renderer adopts only that information architecture.
- The [mathlib contribution lifecycle](https://leanprover-community.github.io/contribute/how-to-contribute.html)
  makes CI, review state, queue state, and maintainer approval distinct. FC Review Bot borrows that
  explicit-state discipline but has no queue, merge, approval, or maintainer authority.

These are design references, not affiliations or claims of feature equivalence.

## Extraction boundary

The reusable engine is the prompt/schema contract, sanitized input builder, receipt validator,
finding renderer, suggestion validator, and App-scoped upsert selector. Formal Conjectures owns:

- discovery and retention of the original mathematical source;
- declaration and bounded Lean build-target selection;
- repository-specific source-fidelity rubric text;
- execution of `lake --wfail build`; and
- maintainer policy and disposition.

The extraction manifest is `audit/pr-audit-v1/fc-review-bot-extraction.json`. A standalone engine
must receive those FC-owned values through a thin consumer adapter; it must not infer or redefine
them.
