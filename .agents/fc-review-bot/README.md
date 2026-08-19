# FC Review Bot

FC Review Bot is an exact-head, fail-closed evidence engine for advisory pull-request review. It prepares a sanitized,
content-addressed review packet; validates fresh structured model receipts; records typed mechanical checks and provider
cost metadata; validates localized suggestions; and renders one stable summary plus independently addressable inline
requests.

The engine does not approve, merge, label, accept, or establish mathematical truth. It never needs a GitHub App private
key or model credential. A trusted GitHub Actions job supplies model output to the validator, and a separate App-authenticated
publisher applies the engine's already-rendered payloads only after rechecking the PR head.

## Extracted contract

- `src/fc_review_bot/runner.py`: offline orchestration, exact-head preparation, receipt/schema validation, suggestion
  validation, deterministic result capture, cost ledger, renderers, and publication selection.
- `src/fc_review_bot/canonical.py`: strict canonical JSON and content roots.
- `schemas/review-role-output.schema.json`: the proven structured reviewer output contract. Its existing
  `formal-conjectures.*` wire identifier is retained for first-extraction compatibility; it is not maintainer policy.
- Consumer `SKILL.md` and `AGENTS.md`: the review method and tool policy. The engine binds both into the
  evidence packet and invokes them; it does not carry a competing domain-review prompt.
- `tests/`: synthetic, credential-free contract tests.
- `examples/formal-conjectures/`: a thin ownership map and configuration shape for the first consumer.

## Local verification

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m unittest discover -s tests -v
```

The CLI is then available as `fc-review-bot`. All commands operate on local files and environment-provided structured
receipts. None performs network or GitHub writes. A consumer must provide its pinned `SKILL.md` and `AGENTS.md` to
`prepare`; the agent's tools and review method are owned by that skill, not this engine.

## Security and authority

See [Architecture](docs/architecture.md), [Security boundaries](docs/security.md), and the
[Formal Conjectures consumer boundary](docs/formal-conjectures.md). The first extraction is additive: Formal Conjectures
keeps its working implementation until a separately reviewed thin integration pins a released engine commit.
