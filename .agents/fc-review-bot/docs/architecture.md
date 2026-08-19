# Architecture

The reusable engine is a deterministic state machine around one primary clean-room review and an optional escalation.

1. `prepare` binds repository, PR, base, exact head, declaration/file, retained sources, the consumer's `SKILL.md`,
   `AGENTS.md`, and output schema.
2. A trusted CI job invokes the consumer's existing review skill with the bound inputs. The model cannot publish and
   receives no App key.
3. `inspect-primary` and `validate-panel` reject missing, stale, malformed, over-authoritative, or fallback evidence.
4. Consumer-owned mechanical lanes run separately and return typed pass/fail/error exit evidence.
5. Suggested patches are accepted only at the pinned path/line/original text and only after consumer-owned validation.
6. `aggregate-cost-ledger` retains reported cost, caps, turns, durations, cache, retry state, and typed unknowns.
7. `render` emits a concise summary payload, zero or more inline payloads, and complete structured artifacts.
8. An App-authenticated publisher rechecks the head, uses `select-summary`/`select-inline`, and performs the minimal API writes.

Model evidence and mechanical checks are producer evidence. The rendered disposition is advisory. Only humans and the
consumer repository's maintainers decide acceptance.

The CLI is the extracted orchestrator. GitHub Actions remains a consumer adapter because build commands, retained source
assembly, model/provider credentials, and repository policy differ by consumer.
