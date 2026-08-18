# Live AI advisory review

This is the reusable contract for the user-fork Formal Conjectures review pilot. It uses
Claude as an isolated reasoning backend and a GitHub App as the only review identity. It does not
approve, merge, label, accept, or determine mathematical truth.

The architecture is deliberately small: Paul’s upstream autoformalization pipeline may run its
own writer–reviewer loop, while FC Review Bot applies one independent final-QC review skill to the
pinned contribution and joins it with mechanical CI. Source fidelity is the core semantic metric.
Detecting an upstream typo may be useful secondary evidence, but does not replace checking that the
Lean declaration matches the retained source. Batch dispatch may reduce repetitive prompting; it
does not introduce a standing service or a mandatory review panel.

## One review loop

The manual workflow `.github/workflows/live-ai-advisory-pr-review.yml` accepts a base repository,
pull request number, exact 40-character head, conclusion-free retained input configuration, and
bounded Lean build target. In the user-fork dogfood workflow, `run_ai_review` and `publish_comment`
default to `true`; a credential-free or nonpublishing run must opt out explicitly. The App token is
still requested only for the named repository, so a Paul/upstream installation remains a separate
account-side authorization and is not implied by this default.
The local adapter pins `anthropics/claude-code-action` to commit
`d40ddef4c030e508327d6e35a9c45f3368482c50`, defaults to the fixed model ID
`claude-sonnet-5`, and caps the primary or optional escalation review at USD 5 each by default.

When `run_ai_review` is true, the workflow:

1. reads the live PR and refuses a base, PR, or head mismatch;
2. copies only the exact Lean statement, retained source text, fixed review prompt, schema, and
   content-addressed manifest into a sanitized artifact;
3. runs one clean-room primary Claude review over the fixed source-fidelity, Lean-semantic, and
   boundary-case checklist;
4. runs typed Lean, diff, style-lint, and import-policy gates independently of model reasoning;
5. validates the actual primary receipt against the schema, with no stored-result fallback;
6. optionally runs one independent escalation review only when the primary is inconclusive, its
   output fails validation, or `escalation_mode=force` records a manual trigger;
7. validates every high-confidence localized patch independently and suppresses any patch that
   does not match the pinned line or pass its bounded Lean build and diff check; and
8. emits the complete structured artifact, one stable summary, and zero or more independently
   addressable inline payloads.

The summary marker is stable across the in-progress and final phases. Each inline payload has a
stable role-scoped finding marker and is bound to the exact commit, path, line, and side. Only the
GitHub App publication jobs receive the App key. Model jobs receive only the Anthropic key, a
read-only GitHub token, and sanitized input. The escalation reviewer does not receive the primary
conclusion. Claude is restricted to read-only file tools, MCP is
disabled, full output and progress reporting are disabled, and the model jobs cannot publish.

The PR #2 configuration under `fixtures/fork-dogfood-erdos-430-2/` is an acceptance fixture. It
does not contain a verdict or semantic result. Other reviews use the same engine and contract with
their own exact, source-retaining input identity; they do not require a custom prompt, renderer, or
publication path.

## Outputs

- `input-manifest.json`: exact repository, base, head, declaration, Lean source, retained sources,
  rubric identity, schema identity, and nonclaims.
- `ai-review-panel.json`: the primary receipt, optional escalation receipt or typed primary error,
  every validated finding, limitations, disposition basis, model/action pins, and content root.
- `runtime-deterministic.json`: typed `pass`, `fail`, or `error` Lean, diff, style, and import
  evidence.
- `suggestion-validation.json`: every proposed patch and its independent validation or suppression
  reason.
- `summary.md` and `summary.json`: the single concise marker-bound review state.
- `inline/*.json`: zero or more apply-ready GitHub suggestions. These exist only after exact-line,
  diff, and Lean validation.
- `cost-ledger.json`: provider-reported cost and usage when available, configured per-pass and total
  caps, model and turn count, phase wall-clock durations, and typed cache/retry availability. Missing
  provider fields remain `unknown/not reported by provider`; raw prompts, model messages, and secrets
  are excluded.

Artifacts are retained for 14 days by the sample workflow. A neutral check links to the workflow
run. Neutral is deliberate: model review and deterministic checks are evidence, not acceptance.

## Credentials and first run

The one new credential is an Anthropic API key stored as the protected repository or environment
secret `FC_REVIEW_ANTHROPIC_API_KEY`. Store it outside source control, bound each model pass with the
workflow's `max_budget_usd_per_role` input, and never paste it into a workflow, issue, PR, artifact,
or chat. The existing
App variables remain `FC_REVIEW_APP_ID` and `FC_REVIEW_APP_PRIVATE_KEY` and are used only by
publication jobs.

For the installed user-fork pilot, the normal manual dispatch sets `run_ai_review=true`,
`escalation_mode=auto`, and `publish_comment=true`. It produces one fresh primary receipt, typed
mechanical gates, patch suppression or validation, the cost ledger, and the stable App summary.
Set `publish_comment=false` explicitly when a later target needs a nonpublishing inspection gate.

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
- [Claude Code Review](https://code.claude.com/docs/en/code-review) separates model analysis from
  candidate verification and neutral, non-blocking output. FC uses one primary review and reserves
  a second clean-room reviewer for uncertainty or validation recovery.
- [CodeRabbit walkthroughs](https://docs.coderabbit.ai/pr-reviews/walkthroughs) separate a stable
  overview from inline findings. The FC renderer adopts only that information architecture.
- The [mathlib contribution lifecycle](https://leanprover-community.github.io/contribute/how-to-contribute.html)
  makes CI, review state, queue state, and maintainer approval distinct. FC Review Bot borrows that
  explicit-state discipline but has no queue, merge, approval, or maintainer authority.

These are design references, not affiliations or claims of feature equivalence.

## Extraction boundary

The reusable engine is the primary-review prompt/schema contract, sanitized input builder, receipt validator,
finding renderer, suggestion validator, and App-scoped upsert selector. Formal Conjectures owns:

- discovery and retention of the original mathematical source;
- declaration and bounded Lean build-target selection;
- repository-specific source-fidelity rubric text;
- execution of `lake --wfail build`; and
- maintainer policy and disposition.

The extraction manifest is `audit/pr-audit-v1/fc-review-bot-extraction.json`. A standalone engine
must receive those FC-owned values through a thin consumer adapter; it must not infer or redefine
them. The manifest remains a preparation record. Do not create the standalone remote repository
until this simplified contract completes one successful nonpublishing live run.
