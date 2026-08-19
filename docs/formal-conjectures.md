# Formal Conjectures consumer boundary

Formal Conjectures remains the canonical contribution and maintainer-decision surface. It owns:

- exact source retention and provenance;
- `.agents/skills/formal-conjectures-review/SKILL.md`, its references, and `AGENTS.md` as the source-fidelity and
  Lean-semantics review method and tool policy;
- Lean module target, style, import, and diff commands;
- maintainer policy, acceptance, approval, and merge decisions;
- GitHub Actions secrets, variables, and the installed App scope.

FC Review Bot owns only reusable evidence mechanics: sanitized binding, structured receipt validation, typed outcomes,
suggestion safety checks, cost observability, artifact rendering, and marker-bound publication planning.

The existing Formal Conjectures implementation is intentionally retained during this first extraction. The remaining
thin-integration change is to package/install a pinned `fc-review-bot` version, replace local engine invocations with that
pin, pass FC's existing skill/AGENTS/config/mechanical adapters explicitly, migrate or retire legacy comment markers, and rerun a
nonpublishing fixture before enabling App publication. No source packet or maintainer policy should move here.
