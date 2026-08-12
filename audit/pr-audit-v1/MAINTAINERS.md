# Maintainer note

This packet is an additive prototype. It does not replace `AGENTS.md`, the Lean build, repository linters, `REVIEW_MATH.md`, Comparator, or maintainer judgement.

Before changing version 1:

1. Keep all acquisition and presentation state out of the core. Timestamps, request IDs, HTTP fields, raw host responses, cursors, runner/step details, and preparation events belong in the separately rooted observation/provenance manifest. Changing them must not change the core.
2. Do not let the generator fetch or execute evidence. Add an upstream producer that retains bytes, then list those bytes and roots in the manifest.
3. Keep both manifests complete without crossing their boundary. The core retains exact source, method/configuration, query/variables, normalized time-free results, and typed check results. The observation retains raw authoritative/tool responses and acquisition/preparation events. Every core evidence artifact must be referenced by a check input with the same digest; every provenance event must appear in `provenance_artifact_ids`. Do not imply that a rooted receipt is a cryptographic host signature.
4. Treat check identifiers as stable within a core. A changed evaluated property, scope, implementation, mode, input, or assumption is a changed check record.
5. Preserve all formal-proof tuples. Never collapse several locators or conditional assumptions to a declaration-level Boolean.
6. Keep per-check boundaries in `does_not_establish` and disposition-wide boundaries in `nonclaims`. Do not map `unavailable` or `error` to `fail`, or a mechanical pass to source fidelity.
7. Require an independently produced, retained human semantic review before an advisory `clean` result.
8. Require one typed result per check. It must derive the complete check projection and artifact relations; semantic results must bind the exact finding, witness, source, method, scope, preparer/reviewer, authority, and independence.
9. Escape every string in HTML or Markdown projections. `scripts/pr_audit.py` provides a small escaped Markdown example; downstream renderers remain responsible for their own context.
10. Rebuild the five fixtures with `python3 scripts/build_pr_audit_fixtures.py`, then review the byte changes and run the full script-test suite.
11. Keep summary and skill projections thin. They must validate and render the
    native core rather than carrying a second verdict table, and they must not
    write to GitHub without a separately authorized integration.

Breaking changes require a new schema version and parallel fixtures. Do not reinterpret existing version-1 roots.
