# Architecture

The reusable engine is a deterministic state machine around one primary clean-room review and an optional escalation.

1. `prepare` binds repository, PR, base, exact head, declaration/file, retained sources, the consumer's `SKILL.md`,
   `AGENTS.md`, and output schema.
2. A trusted CI job invokes the consumer's existing review skill with the bound inputs. The model cannot publish and
   receives no App key.
3. `inspect-primary` and `validate-panel` reject missing, stale, malformed, over-authoritative, or fallback evidence.
4. Consumer-owned mechanical lanes run separately and return typed pass/fail/error exit evidence.
5. Suggested patches are accepted only at the pinned path/line/original text and only after consumer-owned validation.
6. `evaluate-provider-controls` independently compares reported cost, turns, action outcome, structured-output presence,
   and elapsed time with the pinned numeric limits. Any exceeded or unavailable control fails closed; the consumer retains
   this receipt even when the provider action fails. The GitHub job also has a separate hard wall-clock timeout. Because a
   hard cancellation can prevent in-job cleanup, a dependent observer job retains a canonical typed-error receipt with
   unknown usage instead of inferring a candidate result.
7. `aggregate-cost-ledger` retains reported cost, caps, turns, durations, cache, retry state, and typed unknowns.
8. `render` emits a concise summary payload, zero or more inline payloads, and complete structured artifacts.
9. An App-authenticated publisher rechecks the head, uses `select-summary`/`select-inline`, and performs the minimal API writes.

Artifact-only runs gate both the App publisher and the neutral GitHub check; they create no PR-visible review surface.

Model evidence and mechanical checks are producer evidence. The rendered disposition is advisory. Only humans and the
consumer repository's maintainers decide acceptance.

The CLI is the extracted orchestrator. GitHub Actions remains a consumer adapter because build commands, retained source
assembly, model/provider credentials, and repository policy differ by consumer.
